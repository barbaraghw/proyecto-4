# processor.py

import pytesseract
from PIL import Image
import re
from datetime import datetime
import os
import tempfile
from pdf2image import convert_from_path

# Importar constantes de estado del módulo de la base de datos
POPPLER_PATH = r"C:\Users\barba\Downloads\Release-25.11.0-0\poppler-25.11.0\Library\bin"

try:
    from database import STATUS_EN_PROCESO, STATUS_RECHAZADO
except ImportError:
    # Definiciones de respaldo si database.py no está en el mismo nivel
    STATUS_EN_PROCESO = "En Proceso"
    STATUS_RECHAZADO = "Rechazado"

# -------------------------------------------------------------------------
# CONFIGURACIÓN CRÍTICA DE TESSERACT (AJUSTAR PARA TU RUTA EN WINDOWS)
# -------------------------------------------------------------------------
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# -------------------------------------------------------------------------
# EXPRESIONES REGULARES MEJORADAS
# -------------------------------------------------------------------------
REGEX_PATTERNS = {
    # 1. NÚMERO DE FACTURA - MEJORADO para más patrones
    "invoice_number": r"(?:Nro\.\s*de\s*Factura|FACTURA|N[°O\.]|N[UÚ]MERO|Documento\s*Fiscal|C[OÓ]DIGO|Número\s*de\s*Documento\s*Fiscal)\s*[:\s]*([^\s\n]+)",
    
    # 2. MONTO TOTAL - MEJORADO para capturar entre paréntesis
    "total_amount": r"(?<!Sub)(?:Importe\s*Total|TOTAL\s*A\s*PAGAR|TOTAL\s*[\(\)\sA-Z]*PAGAR)(?!\s*Neto)[\s\S]*?[:\s]*([\$€]?\s*[\d\.\,]+)",

    # 3. IMPUESTOS (IVA) - MEJORADO para capturar montos específicos
    "taxes": r"(?:Impuesto|IVA|TAX|Monto\s*de\s*Impuestos)[^\n]*?(?:\)|\s|:)*([\$€]?\s*[\d\.\,]+(?:\s*%)?)", 
    
    # 4. FECHA DE EMISIÓN - MEJORADO para más formatos
    "issue_date": r"(?:FECHA\s*DE\s*EMISI[OÓ]N|Fecha\s*de\s*Emisi[oó]n\s*del\s*Documento|Fecha\s*del\s*Documento)[^\n\d]*(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})",
    
    # 5. NOMBRE DEL PROVEEDOR - MEJORADO
    "provider_name": r"^([A-Z][A-ZÑÁÉÍÓÚ\s\.\,]*[A-Z])(?:\s*\n|\s*RIF|\s*NIT|\s*Dirección|$)",
    
    # 6. FECHA DE VENCIMIENTO - MEJORADO para más patrones
    "due_date": r"(?:VENCIMIENTO|Vence|Fecha\s*L[ií]mite\s*de\s*Pago|DUE\s*DATE)[^\n\d]*(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})", 
}

# -------------------------------------------------------------------------
# FUNCIONES DE CONVERSIÓN Y LIMPIEZA MEJORADAS
# -------------------------------------------------------------------------

def clean_and_convert(text):
    """Limpia el texto extraído (elimina comas, monedas) y lo convierte a float."""
    if text:
        # 1. Quita símbolos de moneda, porcentajes y espacio en blanco
        text = text.replace('€', '').replace('$', '').replace('%', '').replace('USD', '').strip()
        
        # 2. Manejo de separador de miles/decimales
        if ',' in text and text.rfind(',') > text.rfind('.'):
            # Formato Latino (coma como decimal): 1.999,99 -> 1999.99
            text = text.replace('.', '')
            text = text.replace(',', '.')
        elif ',' in text and '.' in text and text.rfind('.') > text.rfind(','):
            # Formato Anglosajón (punto como decimal): 1,999.99 -> 1999.99
            text = text.replace(',', '')
        elif ',' not in text and '.' in text:
            # Formato simple con punto decimal
            pass

        try:
            return float(text)
        except ValueError:
            return None
    return None

def extract_date(text):
    """Intenta convertir el texto extraído a un objeto datetime, manejando separadores flexibles."""
    if text:
        # Limpia el texto para estandarizar el separador
        text_clean = text.replace('.', '-').replace('/', '-')
        
        # Formatos comunes con guiones como separador estandarizado
        for fmt in ('%d-%m-%Y', '%Y-%m-%d', '%d-%m-%y', '%m-%d-%Y', '%y-%m-%d'):
            try:
                # Intenta el parseo
                dt_obj = datetime.strptime(text_clean, fmt)
                
                # Manejo simple de año corto (ej: 25 -> 2025)
                if dt_obj.year < 100:
                    if dt_obj.year < 50:  # Si el año es menor a 50, asumimos siglo 21
                        return dt_obj.replace(year=dt_obj.year + 2000)
                    else:  # Si es mayor a 50, asumimos siglo 20
                        return dt_obj.replace(year=dt_obj.year + 1900)
                return dt_obj
            except ValueError:
                continue
    return None

# -------------------------------------------------------------------------
# FUNCIÓN MEJORADA PARA EXTRACCIÓN DEL NOMBRE DEL PROVEEDOR
# -------------------------------------------------------------------------

def extract_provider_name_enhanced(text):
    """Estrategia múltiple para extraer el nombre del proveedor"""
    
    # Estrategia 1: Buscar al inicio del documento con patrón mejorado
    patterns = [
        r"^([A-Z][A-ZÑÁÉÍÓÚ\s\.\,]*[A-Z])(?:\s*\n|\s*RIF|\s*NIT|\s*Dirección|$)",
        r"^([^\n\r\d\$€@]{5,50})[\r\n]",
        r"^(.+?)[\r\n](?=.*RIF|.*NIT|.*Fecha|.*FACTURA|.*Dirección)",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            provider_name = match.group(1).strip()
            # Validar que sea un nombre razonable (no números solos, no muy corto)
            if len(provider_name) >= 3 and not re.match(r'^[\d\s\.\-]+$', provider_name):
                return provider_name
    
    # Estrategia 2: Buscar después de "RIF" o identificadores similares
    rif_patterns = [
        r"RIF[^\n]*[\r\n]\s*([^\n\r]+)",
        r"NIT[^\n]*[\r\n]\s*([^\n\r]+)",
        r"IDENTIFICACIÓN[^\n]*[\r\n]\s*([^\n\r]+)",
        r"RUC[^\n]*[\r\n]\s*([^\n\r]+)",
        r"Dirección[^\n]*[\r\n]\s*([^\n\r]+)"
    ]
    
    for pattern in rif_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if len(candidate) >= 3 and not re.match(r'^[\d\s\.\-]+$', candidate):
                return candidate
    
    return None

# -------------------------------------------------------------------------
# FUNCIÓN MEJORADA PARA EXTRACCIÓN DE FECHAS CON MÚLTIPLES ESTRATEGIAS
# -------------------------------------------------------------------------

def extract_issue_date_enhanced(text):
    """Estrategia múltiple para extraer la fecha de emisión"""
    
    # ESTRATEGIA 1: Búsqueda directa con múltiples patrones
    patterns = [
        # Patrón específico para "Fecha de Emisión del Documento: 15.06.2025"
        r"Fecha\s*de\s*Emisi[oó]n\s*del\s*Documento\s*[:\-]*\s*(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})",
        # Patrón para "Fecha de Emisión:"
        r"Fecha\s*de\s*Emisi[oó]n\s*[:\-]*\s*(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})",
        # Patrón más flexible
        r"(?:Fecha\s*de\s*Emisi[oó]n|FECHA\s*DE\s*EMISI[OÓ]N)[^\d]*(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})",
        # Patrón general para fecha después de "Fecha"
        r"Fecha[^\d\n]{0,30}(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})",
        # Buscar cualquier fecha cerca de "Emisión"
        r"Emisi[oó]n[^\d\n]{0,30}(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})",
        # Buscar "Documento" cerca de fecha
        r"Documento[^\d\n]{0,30}(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})",
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
        for date_str in matches:
            date_obj = extract_date(date_str)
            if date_obj:
                return date_obj
    
    # ESTRATEGIA 2: Búsqueda por contexto - línea después de patrones clave
    context_patterns = [
        r"(?:Número\s*de\s*Documento|Documento\s*Fiscal)[^\n]*\n([^\n]*)",
        r"¡Documento\s*Oficial\![^\n]*\n([^\n]*)"
    ]
    
    for pattern in context_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            context_line = match.group(1)
            # Buscar fecha en esta línea de contexto
            date_match = re.search(r'(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})', context_line)
            if date_match:
                date_obj = extract_date(date_match.group(1))
                if date_obj:
                    return date_obj
    
    # ESTRATEGIA 3: Buscar cualquier fecha que no sea la de vencimiento
    all_dates = re.findall(r'(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})', text)
    due_date_match = re.search(r'(?:Vencimiento|Fecha\s*L[ií]mite)[^\d]*(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})', text, re.IGNORECASE)
    due_date_str = due_date_match.group(1) if due_date_match else None
    
    for date_str in all_dates:
        if date_str != due_date_str:  # Excluir la fecha de vencimiento
            date_obj = extract_date(date_str)
            if date_obj:
                # Verificar que sea una fecha razonable (no en el futuro lejano)
                if date_obj.year <= datetime.now().year + 1:
                    return date_obj
    
    return None

# -------------------------------------------------------------------------
# FUNCIÓN PARA EXTRACCIÓN MEJORADA DE TOTAL
# -------------------------------------------------------------------------

def extract_total_amount_enhanced(text):
    """Extracción mejorada del monto total"""
    
    patterns = [
        r"TOTAL\s*A\s*PAGAR[^\(\)]*\([^\)]*\)[^\d]*([\d\.,]+)",
        r"TOTAL\s*A\s*PAGAR[^\d]*([\d\.,]+)",
        r"Importe\s*Total[^\d]*([\d\.,]+)",
        r"TOTAL[^\d]*([\d\.,]+)",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            return clean_and_convert(value)
    
    return None

# -------------------------------------------------------------------------
# FUNCIÓN DE DEBUG PARA ANALIZAR EL TEXTO OCR
# -------------------------------------------------------------------------

def debug_ocr_text(text, extraction_log):
    """Función para debug del texto OCR"""
    extraction_log += "\n=== DEBUG OCR TEXT ===\n"
    lines = text.split('\n')
    
    # Encontrar líneas con palabras clave
    keywords = ['fecha', 'emisión', 'emision', 'factura', 'vencimiento', 'documento', 'total', 'pagar']
    relevant_lines = []
    
    for i, line in enumerate(lines):
        line_lower = line.lower()
        if any(keyword in line_lower for keyword in keywords):
            relevant_lines.append(f"Línea {i}: '{line}'")
    
    if relevant_lines:
        extraction_log += "Líneas relevantes encontradas:\n" + "\n".join(relevant_lines) + "\n"
    else:
        extraction_log += "No se encontraron líneas con palabras clave relevantes.\n"
    
    # Mostrar todas las fechas encontradas
    all_dates = re.findall(r'\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}', text)
    if all_dates:
        extraction_log += f"Todas las fechas encontradas: {all_dates}\n"
    
    # Mostrar todos los montos encontrados
    all_amounts = re.findall(r'[\$€]?\s*[\d\.,]+\s*[\$€]?', text)
    if all_amounts:
        extraction_log += f"Todos los montos encontrados: {all_amounts}\n"
    
    extraction_log += "=== FIN DEBUG ===\n"
    return extraction_log

# -------------------------------------------------------------------------
# FUNCIÓN PRINCIPAL DE PROCESAMIENTO MEJORADA
# -------------------------------------------------------------------------

def process_invoice_file(file_path):
    """
    Implementa el Módulo 1: OCR, Extracción de PNL (simplificada) y Validación.
    Maneja archivos PDF convirtiéndolos primero a imágenes.
    """
    
    extraction_log = f"Iniciando OCR en: {file_path}\n"
    text = ""
    
    try:
        if file_path.lower().endswith('.pdf'):
            extraction_log += "Detectado archivo PDF. Convirtiendo a imagen...\n"
            # Usa pdf2image para convertir el PDF. Se requiere la ruta de Poppler.
            images = convert_from_path(file_path, poppler_path=POPPLER_PATH)
            
            if images:
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_img:
                    images[0].save(tmp_img.name, 'PNG')
                    temp_image_path = tmp_img.name
                
                text = pytesseract.image_to_string(Image.open(temp_image_path), lang='spa+eng')
                os.remove(temp_image_path)
            else:
                raise Exception("El PDF está vacío o no se pudo convertir.")
                
        else:
            text = pytesseract.image_to_string(Image.open(file_path), lang='spa+eng')
            
        extraction_log += "OCR completado con éxito.\n"
        
        # Añadir debug del texto OCR
        extraction_log = debug_ocr_text(text, extraction_log)
        
        extraction_log += "--- Texto Extraído (primeros 500 caracteres) ---\n" + text[:500] + "...\n----------------------\n"
    
    except Exception as e:
        extraction_log += f"🚨 Fallo crítico de OCR: {e}\n"
        return {"data": {}, "log": extraction_log, "error": str(e)}
        
    # 2. PNL para identificar campos específicos (usando regex)
    extracted_data = {}
    
    # Hacemos la búsqueda más tolerante a múltiples espacios
    clean_text_for_search = re.sub(r'\s+', ' ', text)
    
    for field, pattern in REGEX_PATTERNS.items():
        # Para el provider_name usamos el método mejorado
        if field == "provider_name":
            extracted_data[field] = extract_provider_name_enhanced(text)
            if extracted_data[field]:
                extraction_log += f"✅ Campo '{field}' extraído con valor: '{extracted_data[field]}'\n"
            else:
                extraction_log += f"❌ Campo '{field}' no encontrado.\n"
        
        # Para issue_date usamos el método mejorado
        elif field == "issue_date":
            extracted_data[field] = extract_issue_date_enhanced(text)
            if extracted_data[field]:
                extraction_log += f"✅ Campo '{field}' extraído con valor: '{extracted_data[field]}'\n"
            else:
                extraction_log += f"❌ Campo '{field}' no encontrado.\n"
        
        # Para total_amount usamos el método mejorado si el normal falla
        elif field == "total_amount":
            match = re.search(pattern, clean_text_for_search, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            if match:
                value = match.group(1).strip()
                extracted_data[field] = clean_and_convert(value)
                extraction_log += f"✅ Campo '{field}' extraído con valor: '{value}' -> {extracted_data[field]}\n"
            else:
                # Fallback al método mejorado
                extracted_data[field] = extract_total_amount_enhanced(text)
                if extracted_data[field]:
                    extraction_log += f"✅ Campo '{field}' extraído (fallback) con valor: {extracted_data[field]}\n"
                else:
                    extraction_log += f"❌ Campo '{field}' no encontrado.\n"
        
        else:
            # Para los demás campos, usamos el método original
            match = re.search(pattern, clean_text_for_search, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            if match:
                value = match.group(1).strip()
                
                # Conversión de información no estructurada a datos estructurados
                if field in ["taxes"]:
                    extracted_data[field] = clean_and_convert(value)
                elif field in ["due_date"]:  # issue_date ya se maneja arriba
                    extracted_data[field] = extract_date(value)
                else:
                    extracted_data[field] = value
                    
                extraction_log += f"✅ Campo '{field}' extraído con valor: '{value}' -> {extracted_data[field]}\n"
            else:
                extraction_log += f"❌ Campo '{field}' no encontrado.\n"
            
    # 4. Mecanismo de validación de datos extraídos
    required_fields = ["provider_name", "invoice_number", "issue_date", "total_amount", "taxes"]
    is_valid = all(extracted_data.get(field) for field in required_fields)
    
    if not is_valid:
        extraction_log += "⚠️ Falla de validación: Faltan campos obligatorios o son inválidos.\n"
        missing = [f for f in required_fields if not extracted_data.get(f)]
        extraction_log += f"Campos faltantes/inválidos: {', '.join(missing)}\n"
        extracted_data['status'] = STATUS_RECHAZADO
    else:
        extracted_data['status'] = STATUS_EN_PROCESO
        extraction_log += "✅ Validación básica superada. Datos listos para aprobación.\n"

    return {"data": extracted_data, "log": extraction_log, "error": None}