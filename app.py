# app.py

import os
import uuid
import tempfile
from datetime import datetime
from flask import Flask, request, jsonify, redirect, url_for, render_template
from dotenv import load_dotenv

# Módulos del Proyecto
from database import (
    SessionLocal, 
    Invoice, 
    update_invoice_status,
    STATUS_EN_PROCESO,
    STATUS_APROBADO,
    STATUS_RECHAZADO
)
from processor import process_invoice_file
from notification_service import send_approval_email

# Cargar variables de entorno del archivo .env
load_dotenv()

# Configuración de Flask
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads' # Directorio para guardar archivos subidos
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'pdf'}

# Asegurar que el directorio de subida exista
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

def allowed_file(filename):
    """Verifica que el archivo tenga una extensión permitida."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# -------------------------------------------------------------------------
# ENDPOINT PRINCIPAL: Subida y Procesamiento de Factura (Módulo 4 y Módulo 1)
# -------------------------------------------------------------------------
@app.route('/', methods=['GET'])
def index():
    """Sirve la plantilla HTML para subir archivos."""
    return render_template('index.html')

@app.route('/api/v1/invoice/upload', methods=['POST'])
def upload_invoice():
    if 'file' not in request.files:
        return jsonify({"message": "No se encontró el archivo"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"message": "Nombre de archivo inválido"}), 400

    if file and allowed_file(file.filename):
        # 1. Guarda temporalmente el archivo para el OCR
        temp_file_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()) + file.filename)
        file.save(temp_file_path)

        # 2. Procesa la factura (Llamada al Módulo 1: OCR y Extracción)
        processing_result = process_invoice_file(temp_file_path)
        
        # ===================================================================
        # LÍNEAS DE DEBUGGING AGREGADAS: Muestra el log de extracción en la consola
        # ===================================================================
        print("\n=======================================================")
        print("    DIAGNÓSTICO DETALLADO DE OCR Y EXTRACCIÓN (Módulo 1)")
        print("=======================================================")
        print(processing_result.get("log", "Log de procesamiento no disponible."))
        print("=======================================================\n")
        # ===================================================================

        extracted_data = processing_result.get("data", {})
        extraction_error = processing_result.get("error")

        # 3. Manejo de Errores Críticos (Fallo de OCR)
        if extraction_error:
            os.remove(temp_file_path)
            return jsonify({
                "message": "Fallo al procesar el archivo por error de OCR.",
                "error": extraction_error
            }), 500

        # 4. Inicia la sesión de DB (Módulo 2)
        db = SessionLocal()
        
        try:
            invoice_number = extracted_data.get("invoice_number")

            # 5. Verificación de duplicados
            existing_invoice = db.query(Invoice).filter(Invoice.invoice_number == invoice_number).first()
            if existing_invoice:
                db.close()
                os.remove(temp_file_path)
                return jsonify({
                    "message": f"La factura con número {invoice_number} ya existe en la base de datos.",
                    "status": existing_invoice.status
                }), 409 # Código 409 Conflict

            # 6. Creación del nuevo registro en la DB
            new_invoice = Invoice(
                invoice_number=invoice_number,
                provider_name=extracted_data.get("provider_name"),
                issue_date=extracted_data.get("issue_date"),
                due_date=extracted_data.get("due_date"),
                total_amount=extracted_data.get("total_amount"),
                taxes=extracted_data.get("taxes"),
                status=extracted_data.get("status", STATUS_RECHAZADO), # Usa el estado determinado por el Módulo 1
                extraction_log=processing_result.get("log")
            )
            db.add(new_invoice)
            db.commit()
            db.refresh(new_invoice)
            
            # 7. Si el estado es "En Proceso", enviar notificación (Módulo 3)
            if new_invoice.status == STATUS_EN_PROCESO:
                send_approval_email(new_invoice)

            # 8. Mueve el archivo a la carpeta final si fue procesado (opcional, para auditoría)
            # Aquí podrías renombrar el archivo y moverlo a app.config['UPLOAD_FOLDER']
            os.remove(temp_file_path) # Eliminamos el archivo temporal por simplicidad

            return jsonify({
                "message": "Factura subida y procesada correctamente",
                "invoice_id": new_invoice.id,
                "status": new_invoice.status,
                "extracted_data": {
                    k: (v.isoformat() if isinstance(v, datetime) else v) 
                    for k, v in extracted_data.items()
                }
            }), 200

        except Exception as e:
            db.rollback()
            print(f"Error interno al manejar la DB o notificar: {e}")
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            return jsonify({"message": "Error interno del servidor", "error": str(e)}), 500
        finally:
            db.close()
    
    return jsonify({"message": "Tipo de archivo no permitido"}), 400

# -------------------------------------------------------------------------
# ENDPOINT DE WEBHOOK: Respuesta del Correo (Módulo 3)
# -------------------------------------------------------------------------

@app.route('/api/v1/invoice/webhook', methods=['GET'])
def webhook_handler():
    # Obtiene parámetros de la URL enviados por el botón del correo
    invoice_id = request.args.get('invoice_id', type=int)
    action = request.args.get('action') # 'approve' o 'reject'
    
    if not invoice_id or action not in ['approve', 'reject']:
        return "Parámetros inválidos", 400
    
    new_status = STATUS_APROBADO if action == 'approve' else STATUS_RECHAZADO
    justification = f"Decisión tomada por webhook/email: {new_status}"
    
    db = SessionLocal()
    try:
        updated_invoice = update_invoice_status(db, invoice_id, new_status, justification)
        
        if updated_invoice:
            print(f"\n--- WEBHOOK ACTIVADO ---")
            print(f"Factura ID {invoice_id} ha sido marcada como: {new_status}")
            print("------------------------\n")
            # Redirige a una página de confirmación simple
            return f"<h1>Confirmación: Factura {invoice_id} {new_status}</h1><p>El proceso ha finalizado correctamente.</p>", 200
        else:
            return "Factura no encontrada", 404
    except Exception as e:
        db.rollback()
        return f"Error al actualizar la base de datos: {e}", 500
    finally:
        db.close()


# -------------------------------------------------------------------------
# ENDPOINT DE CONSULTA DE ESTADO (Módulo 2)
# -------------------------------------------------------------------------

@app.route('/api/v1/invoice/<int:invoice_id>/status', methods=['GET'])
def get_invoice_status(invoice_id):
    db = SessionLocal()
    try:
        invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if invoice:
            return jsonify({
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "current_status": invoice.status,
                "total_amount": invoice.total_amount,
                "last_updated": invoice.last_updated.isoformat()
            }), 200
        else:
            return jsonify({"message": "Factura no encontrada"}), 404
    finally:
        db.close()


if __name__ == '__main__':
    # Usar el puerto del .env o 5000 por defecto
    port = int(os.environ.get("FLASK_RUN_PORT", 5000))
    app.run(debug=True, port=port)