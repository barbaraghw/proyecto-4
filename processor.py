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
# EXPRESIONES REGULARES FINALES Y DEFINITIVAS
# -------------------------------------------------------------------------
REGEX_PATTERNS = {
    # 1. NÚMERO DE FACTURA (Sin cambios)
    "invoice_number": r"(?:Nro\.\s*de\s*Factura|FACTURA|N[°O\.]|N[UÚ]MERO|Documento\s*Fiscal|C[OÓ]DIGO)\s*[:\s]*([^\s\n]+)",
    
    # 2. MONTO TOTAL: ARREGLADO para capturar 4.500,99 e ignorar la etiqueta Subtotal.
    # Usamos lookahead negativo (?!\s*Neto) para asegurar que no capture 'Subtotal Neto'.
    "total_amount": r"(?<!Sub)(?:Importe\s*Total|TOTAL\s*A\s*PAGAR|TOTAL)(?!\s*Neto)\s*[\s\S]*?(?:FINAL|GRAL)?\s*[:\s]*([\$€]?\s*[\d\.\,]+)",

    # 3. IMPUESTOS (IVA) (Sin cambios)
    "taxes": r"(?:Impuesto|IVA|TAX|Monto\s*de\s*Impuestos)[^\n]*?\)*\s*[:\s]*([\$€]?\s*[\d\.\,]+)", 
    
    # 4. FECHA DE EMISIÓN (Sin cambios)
    "issue_date": r"(?:FECHA\s*DE\s*EMISI[OÓ]N|Fecha\s*del\s*Documento|Fecha)[:\s]*(\d{2}[.\-/]\d{2}[.\-/]\d{2,4})",
    
    # 5. NOMBRE DEL PROVEEDOR: SOLUCIÓN FINAL (Busca la primera línea de texto legible)
    # Busca 0 o más saltos de línea (\n*) seguidos por la primera secuencia de texto (.*?) hasta el siguiente salto de línea.
     "provider_name": r"^([A-ZÑÁÉÍÓÚ\s]+(?:C\.A\.|S\.A\.|S\.R\.L\.|LTDA|INC|CORP)?)[\s\n]*$",
    
    # 6. FECHA DE VENCIMIENTO (Sin cambios)
    "due_date": r"(?:VENCIMIENTO|Vence|Fecha\s*Limite\s*de\s*Pago|DUE\s*DATE)[:\s]*(\d{2}[.\-/]\d{2}[.\-/]\d{2,4})", 
}
# -------------------------------------------------------------------------
# FUNCIONES DE CONVERSIÓN Y LIMPIEZA
# -------------------------------------------------------------------------

def clean_and_convert(text):
    """Limpia el texto extraído (elimina comas, monedas) y lo convierte a float."""
    if text:
        # 1. Quita símbolos de moneda y espacio en blanco
        text = text.replace('€', '').replace('$', '').strip()
        
        # 2. Manejo de separador de miles/decimales (Robusto para formatos latinos y anglosajones)
        if ',' in text and text.rfind(',') > text.rfind('.'):
            # Formato Latino (coma como decimal): 4.500,99 -> 4500.99
            text = text.replace('.', '')
            text = text.replace(',', '.')
        elif ',' in text and '.' in text and text.rfind('.') > text.rfind(','):
            # Formato Anglosajón (punto como decimal): 4,500.99 -> 4500.99
            text = text.replace(',', '')
        elif ',' not in text and '.' in text:
            # Formato simple con punto decimal o punto de miles (solo se asume punto decimal para el float)
            # Ejemplo: 2500.50 (Tipo 2)
            pass

        try:
            return float(text)
        except ValueError:
            return None
    return None

def extract_date(text):
    """Intenta convertir el texto extraído a un objeto datetime, manejando separadores flexibles."""
    if text:
        # Limpia el texto para estandarizar el separador antes de intentar el parseo
        text_clean = text.replace('.', '-').replace('/', '-')
        
        # Formatos comunes con guiones como separador estandarizado
        for fmt in ('%d-%m-%Y', '%Y-%m-%d', '%d-%m-%y'):
            try:
                # Intenta el parseo
                dt_obj = datetime.strptime(text_clean, fmt)
                
                # Manejo simple de año corto (ej: 25 -> 2025)
                if dt_obj.year < 100 and dt_obj.year < datetime.now().year - 2000 + 10: 
                    # Si el año es '25', lo pone en el siglo 21 (2025)
                    return dt_obj.replace(year=dt_obj.year + 2000)
                return dt_obj
            except ValueError:
                continue
    return None

# -------------------------------------------------------------------------
# FUNCIÓN PRINCIPAL DE PROCESAMIENTO (Esta parte no requiere cambios)
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
        extraction_log += "--- Texto Extraído ---\n" + text[:1000] + "...\n----------------------\n"
    
    except Exception as e:
        extraction_log += f"🚨 Fallo crítico de OCR: {e}\n"
        return {"data": {}, "log": extraction_log, "error": str(e)}
        
    # 2. PNL para identificar campos específicos (usando regex)
    extracted_data = {}
    
    # Hacemos la búsqueda más tolerante a múltiples espacios
    clean_text_for_search = re.sub(r'\s+', ' ', text)
    
    for field, pattern in REGEX_PATTERNS.items():
        # Usamos re.DOTALL para que '.' incluya saltos de línea en la búsqueda compleja
        match = re.search(pattern, clean_text_for_search, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if match:
            value = match.group(1).strip()
            
            # 3. Conversión de información no estructurada a datos estructurados
            if field in ["total_amount", "taxes"]:
                extracted_data[field] = clean_and_convert(value)
            elif field in ["issue_date", "due_date"]:
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