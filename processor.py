# processor.py

import pytesseract
from PIL import Image
import re
from datetime import datetime
import os

# Importar constantes de estado del módulo de la base de datos
try:
    from database import STATUS_EN_PROCESO, STATUS_RECHAZADO
except ImportError:
    # Definiciones de respaldo si database.py no está en el mismo nivel
    STATUS_EN_PROCESO = "En Proceso"
    STATUS_RECHAZADO = "Rechazado"

# -------------------------------------------------------------------------
# CONFIGURACIÓN CRÍTICA DE TESSERACT (AJUSTAR PARA TU RUTA EN WINDOWS)
# -------------------------------------------------------------------------
# Si Tesseract no está en el PATH del sistema, DESCOMENTA y ajusta la siguiente línea:
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# -------------------------------------------------------------------------
# EXPRESIONES REGULARES DE MÁXIMA ROBUSTEZ Y FLEXIBILIDAD
# -------------------------------------------------------------------------
REGEX_PATTERNS = {
    # 1. NÚMERO DE FACTURA: Mantener el patrón flexible que ya funcionó.
    "invoice_number": r"(?:Nro\.\s*de\s*Factura|FACTURA|N[°O\.]|NUMERO|CÓDIGO)\s*[:\s]*([^\s\n]+)",
    
    # 2. MONTO TOTAL: CRÍTICO. Usamos una NEGLACIÓN (?!.*Subtotal) para asegurar que la coincidencia no contenga la palabra Subtotal.
    # Esto aísla el TOTAL final y evita que capture el Subtotal Neto.
    "total_amount": r"(?!.*Subtotal)(?:IMPORTE\s*Total|MONTO|VALOR|TOTAL)\s*[\s\S]*?(?:FINAL|NETO|PAGAR)?\s*[:\s]*([\$€]?\s*[\d\.\,]+)",

    # 3. IMPUESTOS (IVA): Simplificado y enfocado en la palabra 'IVA' para ignorar 'Monto IVA'.
    "taxes": r"(?:Monto\s*IVA|IVA|IMPUESTO)[^\n]*([\d\.\,]+)", 
    
    # 4. FECHA DE EMISIÓN: Mantener el patrón flexible de fechas con separadores flexibles.
    "issue_date": r"(?:FECHA\s*DE\s*EMISIÓN|FECHA|DATE|EMISIÓN)[\s:]*(\d{2}[.\-/]\d{2}[.\-/]\d{2,4})",
    
    # 5. NOMBRE DEL PROVEEDOR
    "provider_name": r"^(.*?)\n", 
    
    # 6. FECHA DE VENCIMIENTO
    "due_date": r"(?:VENCIMIENTO|DUE\s*DATE|VENCE)[:\s]*(\d{2}[.\-/]\d{2}[.\-/]\d{2,4})", 
}

# -------------------------------------------------------------------------
# FUNCIONES DE CONVERSIÓN Y LIMPIEZA
# -------------------------------------------------------------------------

def clean_and_convert(text):
    """Limpia el texto extraído (elimina comas, monedas) y lo convierte a float."""
    if text:
        # 1. Quita símbolos de moneda y espacio en blanco
        text = text.replace('€', '').replace('$', '').strip()
        
        # 2. Manejo de separador de miles/decimales (Más simple y menos propenso a errores de OCR)
        # Si el texto contiene coma (,) y el OCR la usa como separador decimal.
        if ',' in text:
            # Reemplaza el punto por nada (asume que es un separador de miles)
            text = text.replace('.', '')
            # Reemplaza la coma por punto (asume que es el separador decimal)
            text = text.replace(',', '.')
        else:
            # Si solo hay puntos o ninguno, se asume el punto como decimal. 
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
                return datetime.strptime(text_clean, fmt)
            except ValueError:
                continue
    return None

# -------------------------------------------------------------------------
# FUNCIÓN PRINCIPAL DE PROCESAMIENTO (Esta parte no requiere cambios)
# -------------------------------------------------------------------------

def process_invoice_file(file_path):
    """
    Implementa el Módulo 1: OCR, Extracción de PNL (simplificada) y Validación.
    
    :param file_path: Ruta del archivo de factura (imagen/PDF).
    :return: Diccionario con los datos extraídos y logs.
    """
    
    extraction_log = f"Iniciando OCR en: {file_path}\n"
    
    # 1. OCR para extracción de texto
    try:
        # Tesseract detecta automáticamente el tipo de archivo (PDF/imagen)
        text = pytesseract.image_to_string(Image.open(file_path), lang='spa+eng')
        extraction_log += "OCR completado con éxito.\n"
        extraction_log += "--- Texto Extraído ---\n" + text[:500] + "...\n----------------------\n"
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
            elif field == "provider_name":
                # Asegura que el nombre del proveedor no capture la primera línea vacía si existe.
                name_match = re.match(r"^(.*?)\n", text.strip(), re.MULTILINE)
                extracted_data[field] = name_match.group(1).strip() if name_match else value
            else:
                extracted_data[field] = value
                
            extraction_log += f"✅ Campo '{field}' extraído con valor: '{value}' -> {extracted_data[field]}\n"
        else:
            extraction_log += f"❌ Campo '{field}' no encontrado.\n"
            
    # 4. Mecanismo de validación de datos extraídos
    # Comprueba que los campos obligatorios existen y son válidos (no None)
    required_fields = ["provider_name", "invoice_number", "issue_date", "total_amount", "taxes"]
    is_valid = all(extracted_data.get(field) for field in required_fields)
    
    if not is_valid:
        extraction_log += "⚠️ Falla de validación: Faltan campos obligatorios o son inválidos.\n"
        # Identificar qué campos fallaron para el log
        missing = [f for f in required_fields if not extracted_data.get(f)]
        extraction_log += f"Campos faltantes/inválidos: {', '.join(missing)}\n"
        extracted_data['status'] = STATUS_RECHAZADO # Rechazo automático si la extracción es crítica
    else:
        extracted_data['status'] = STATUS_EN_PROCESO
        extraction_log += "✅ Validación básica superada. Datos listos para aprobación.\n"

    return {"data": extracted_data, "log": extraction_log, "error": None}