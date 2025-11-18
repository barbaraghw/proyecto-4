# app.py

from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from os.path import join, dirname, realpath
import os
from datetime import datetime

# Importar nuestros módulos
from database import init_db, get_db, Invoice, STATUS_APROBADO, STATUS_RECHAZADO, STATUS_EN_PROCESO
from processor import process_invoice_file
from mailer import send_invoice_notification

load_dotenv()
app = Flask(__name__)
# Inicializar la DB al iniciar la app
with app.app_context():
    init_db()

# Directorio para guardar temporalmente las facturas subidas
UPLOAD_FOLDER = join(dirname(realpath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Endpoints de la API REST  ---

@app.route('/api/v1/invoice/upload', methods=['POST'])
def upload_invoice():
    """
    API REST para subida y procesamiento de facturas. 
    """
    if 'file' not in request.files:
        return jsonify({"message": "No se encontró la parte del archivo 'file'"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"message": "Nombre de archivo no seleccionado"}), 400

    if file:
        # 1. Sistema de recepción de archivos [cite: 10]
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)

        # 2. Procesamiento Inteligente [cite: 8]
        processing_result = process_invoice_file(filepath)
        extracted_data = processing_result['data']
        extraction_log = processing_result['log']
        
        db: Session = next(get_db())
        
        # Validación de duplicidad (por número de factura)
        existing_invoice = db.query(Invoice).filter(Invoice.invoice_number == extracted_data.get('invoice_number')).first()
        if existing_invoice:
            # Manejo de errores - Factura duplicada [cite: 76, 78]
            return jsonify({
                "message": "Factura ya existe en la base de datos",
                "invoice_id": existing_invoice.id,
                "status": existing_invoice.status
            }), 409

        # 3. Almacenamiento y Gestión de Estados [cite: 22, 47]
        try:
            # Crear nueva instancia de la factura con los datos extraídos
            new_invoice = Invoice(
                provider_name=extracted_data.get('provider_name'),
                invoice_number=extracted_data.get('invoice_number'),
                issue_date=extracted_data.get('issue_date'),
                total_amount=extracted_data.get('total_amount'),
                taxes=extracted_data.get('taxes'),
                due_date=extracted_data.get('due_date'),
                status=extracted_data.get('status', STATUS_RECHAZADO), # Fallback si falla la validación
                extraction_log=extraction_log
            )
            
            db.add(new_invoice)
            db.commit()
            db.refresh(new_invoice)

            # 4. Notificación y Flujo de Trabajo
            if new_invoice.status == STATUS_EN_PROCESO:
                # Se asume un email de revisor simple por simplicidad
                reviewer_email = os.getenv("MAIL_USERNAME") 
                send_invoice_notification(new_invoice, reviewer_email)
            
            return jsonify({
                "message": "Factura subida y procesada correctamente",
                "invoice_id": new_invoice.id,
                "status": new_invoice.status,
                "extracted_data": extracted_data
            }), 200

        except Exception as e:
            db.rollback()
            # Manejo elegante de fallos [cite: 76, 78]
            return jsonify({"message": f"Error interno al guardar la factura: {e}", "log": extraction_log}), 500

@app.route('/api/v1/invoice/<int:invoice_id>/status', methods=['GET'])
def get_invoice_status(invoice_id):
    """
    Endpoint para consulta de estado y historial. [cite: 45]
    """
    db: Session = next(get_db())
    invoice = db.query(Invoice).get(invoice_id)

    if not invoice:
        return jsonify({"message": "Factura no encontrada"}), 404

    # Registro de historial (simple, solo datos de la tabla Invoice) [cite: 58]
    return jsonify({
        "invoice_id": invoice.id,
        "provider_name": invoice.provider_name,
        "invoice_number": invoice.invoice_number,
        "current_status": invoice.status,
        "last_updated": invoice.last_updated.isoformat(),
        "decision_justification": invoice.decision_justification,
        "extraction_log_snippet": invoice.extraction_log[:100] + "..." 
    }), 200

# --- Webhooks para Procesar Decisiones  ---

@app.route('/api/v1/webhook/invoice/<int:invoice_id>/<string:action>', methods=['GET', 'POST'])
def process_webhook_decision(invoice_id, action):
    """
    Mecanismo de procesamiento de respuestas (webhooks) para 'Aprobar'.
    El 'GET' se usa para el enlace directo del correo. [cite: 35]
    """
    db: Session = next(get_db())
    invoice = db.query(Invoice).get(invoice_id)
    
    if not invoice:
        return f"Factura ID {invoice_id} no encontrada.", 404

    if action == 'approve':
        # 1. Correcta transición entre estados [cite: 56]
        if invoice.status != STATUS_APROBADO:
            invoice.status = STATUS_APROBADO
            invoice.decision_justification = "Aprobado vía correo electrónico interactivo."
            db.commit()
            # 2. Sistema de registro de auditoría [cite: 48]
            return "✅ **Factura APROBADA con éxito!** La base de datos ha sido actualizada.", 200
        else:
            return "Factura ya estaba APROBADA.", 200
            
    elif action == 'reject':
        # Este endpoint 'reject' es usado si el usuario envía comentarios desde el formulario
        justification = request.args.get('comment') or request.form.get('comment')
        
        if not justification:
            return "❌ Rechazo fallido: Justificación (comment) requerida.", 400

        if invoice.status != STATUS_RECHAZADO:
            invoice.status = STATUS_RECHAZADO
            invoice.decision_justification = justification
            db.commit()
            return f"❌ **Factura RECHAZADA con éxito!** Justificación registrada: {justification}", 200
        else:
            return "Factura ya estaba RECHAZADA.", 200
            
    else:
        return "Acción no válida.", 400

@app.route('/api/v1/webhook/reject_form/<int:invoice_id>', methods=['GET'])
def reject_form(invoice_id):
    """
    Simulación de formulario integrado para comentarios de rechazo. [cite: 40]
    """
    # HTML simple para capturar comentarios para rechazos [cite: 34]
    form_html = f"""
    <h2>Rechazar Factura #{invoice_id}</h2>
    <p>Por favor, ingrese el comentario/justificación del rechazo.</p>
    <form action="{os.getenv('BASE_URL')}/api/v1/webhook/invoice/{invoice_id}/reject" method="GET">
        <textarea name="comment" rows="5" cols="50" required placeholder="Escribe tu justificación aquí..."></textarea><br><br>
        <button type="submit">Enviar Rechazo</button>
    </form>
    """
    return render_template_string(form_html)


if __name__ == '__main__':
    # Usar un puerto diferente si es necesario
    app.run(debug=True, host='0.0.0.0', port=5000)