# processor.py

import pytesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
from PIL import Image
import re
from datetime import datetime
from database import STATUS_EN_PROCESO, STATUS_RECHAZADO

# Definición de las expresiones regulares simples para extracción de campos
# NOTA: Estas regex son muy simples y deben ajustarse a los formatos de factura reales.
REGEX_PATTERNS = {
    # Hacemos que la búsqueda de N° de factura sea más flexible ante espacios y caracteres especiales como °.
    # Ahora busca 'FACTURA', 'N', 'No', 'N°' y captura cualquier secuencia de caracteres alfanuméricos/guiones.
    "invoice_number": r"(?:FACTURA\s*N[°O]?:|N\s*O:\s*)\s*(\S+)",
    
    # Hacemos el patrón MÁS EXCLUSIVO para TOTAL A PAGAR para evitar ambigüedades.
    "total_amount": r"TOTAL\s*A\s*PAGAR:\s*(?:[\$€]?)\s*([\d\.\,]+)",

    # Hacemos el patrón de IVA más flexible, buscando la palabra 'IMPUESTO' o 'IVA' seguida de la cantidad.
    "taxes": r"(?:IVA|IMPUESTO)[^\d]*([\d\.\,]+)", 
    
    # Las demás permanecen (parecen funcionar para las fechas y el proveedor):
    "issue_date": r"(?:FECHA|DATE)\s*[:]\s*(\d{2}[-/]\d{2}[-/]\d{2,4})",
    "provider_name": r"^(.*?)\n", 
    "due_date": r"(?:VENCIMIENTO|DUE\s*DATE)\s*[:]\s*(\d{2}[-/]\d{2}[-/]\d{2,4})", 
}

def clean_and_convert(text):
    """Limpia el texto extraído (elimina comas, convierte a punto) y lo convierte a float."""
    if text:
        text = text.replace(',', '').replace('€', '').replace('$', '').strip()
        try:
            return float(text)
        except ValueError:
            return None
    return None

def extract_date(text):
    """Intenta convertir el texto extraído a un objeto datetime."""
    if text:
        for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d', '%Y-%m-%d', '%d/%m/%y', '%d-%m-%y'):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None

def process_invoice_file(file_path):
    """
    Implementa el Módulo 1: OCR, Extracción de PNL (simplificada) y Validación.
    
    :param file_path: Ruta del archivo de factura (imagen/PDF).
    :return: Diccionario con los datos extraídos y logs.
    """
    
    extraction_log = f"Iniciando OCR en: {file_path}\n"
    
    # 1. OCR para extracción de texto [cite: 11]
    try:
        text = pytesseract.image_to_string(Image.open(file_path), lang='spa+eng')
        extraction_log += "OCR completado.\n"
    except Exception as e:
        extraction_log += f"Fallo de OCR: {e}\n"
        return {"data": {}, "log": extraction_log, "error": str(e)}

    # 2. PNL para identificar campos específicos (usando regex) [cite: 12]
    extracted_data = {}
    
    for field, pattern in REGEX_PATTERNS.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            
            # 3. Conversión de información no estructurada a datos estructurados [cite: 14]
            if field in ["total_amount", "taxes"]:
                extracted_data[field] = clean_and_convert(value)
            elif field in ["issue_date", "due_date"]:
                extracted_data[field] = extract_date(value)
            elif field == "provider_name":
                 # El patrón de nombre de proveedor toma la primera línea, ajustamos la extracción
                name_match = re.match(r"^(.*?)\n", text, re.MULTILINE)
                extracted_data[field] = name_match.group(1).strip() if name_match else value
            else:
                extracted_data[field] = value
                
            extraction_log += f"Campo '{field}' extraído con valor: {value} -> {extracted_data[field]}\n"
        else:
            extraction_log += f"Campo '{field}' no encontrado.\n"
            
    # 4. Mecanismo de validación de datos extraídos [cite: 13]
    # Comprueba que los campos obligatorios existen y son válidos
    required_fields = ["provider_name", "invoice_number", "issue_date", "total_amount", "taxes"]
    is_valid = all(extracted_data.get(field) for field in required_fields)
    
    if not is_valid:
        extraction_log += "⚠️ Falla de validación: Faltan campos obligatorios.\n"
        extracted_data['status'] = STATUS_RECHAZADO # Rechazo automático si la extracción es crítica
    else:
        extracted_data['status'] = STATUS_EN_PROCESO
        extraction_log += "✅ Validación básica superada.\n"

    return {"data": extracted_data, "log": extraction_log, "error": None}