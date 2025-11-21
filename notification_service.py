# notification_service.py

import os
import yagmail
from dotenv import load_dotenv

# Cargar variables de entorno (EMAIL_USER, EMAIL_PASSWORD, APPROVER_EMAIL)
load_dotenv()

# Configuración del servidor de correo
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
APPROVER_EMAIL = os.environ.get("APPROVER_EMAIL")

if not EMAIL_USER or not APPROVER_EMAIL:
    print("ADVERTENCIA: Variables EMAIL_USER o APPROVER_EMAIL no configuradas en .env. El envío de correos fallará.")

def generate_email_body(invoice):
    """Genera el cuerpo HTML interactivo del correo para aprobación."""
    # URL base para los webhooks (asumiendo que Flask corre en localhost por ahora)
    BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000")
    
    # URLs de acción que activan el webhook en app.py
    approve_url = f"{BASE_URL}/api/v1/invoice/webhook?invoice_id={invoice.id}&action=approve"
    reject_url = f"{BASE_URL}/api/v1/invoice/webhook?invoice_id={invoice.id}&action=reject"
    
    # Diseño HTML simple
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif;">
        <h2>🔔 Solicitud de Aprobación de Factura</h2>
        <p>Se ha procesado una factura con éxito y requiere su revisión y aprobación:</p>
        
        <table border="1" style="border-collapse: collapse; width: 100%;">
            <tr><td style="padding: 8px; background-color: #f2f2f2;"><strong>ID Interno:</strong></td><td style="padding: 8px;">{invoice.id}</td></tr>
            <tr><td style="padding: 8px; background-color: #f2f2f2;"><strong>Número de Factura:</strong></td><td style="padding: 8px;">{invoice.invoice_number}</td></tr>
            <tr><td style="padding: 8px; background-color: #f2f2f2;"><strong>Proveedor:</strong></td><td style="padding: 8px;">{invoice.provider_name}</td></tr>
            <tr><td style="padding: 8px; background-color: #f2f2f2;"><strong>Fecha de Emisión:</strong></td><td style="padding: 8px;">{invoice.issue_date.strftime('%d/%m/%Y')}</td></tr>
            <tr><td style="padding: 8px; background-color: #f2f2f2;"><strong>Monto Total:</strong></td><td style="padding: 8px;">${invoice.total_amount:.2f}</td></tr>
        </table>
        
        <p style="margin-top: 20px;"><strong>Por favor, tome una decisión:</strong></p>
        
        <a href="{approve_url}" style="
            background-color: #4CAF50; 
            color: white; 
            padding: 10px 20px; 
            text-align: center; 
            text-decoration: none; 
            display: inline-block; 
            margin: 4px 2px; 
            cursor: pointer; 
            border-radius: 8px;
        ">APROBAR</a>
        
        <a href="{reject_url}" style="
            background-color: #f44336; 
            color: white; 
            padding: 10px 20px; 
            text-align: center; 
            text-decoration: none; 
            display: inline-block; 
            margin: 4px 2px; 
            cursor: pointer; 
            border-radius: 8px;
        ">RECHAZAR</a>
        
        <p style="margin-top: 20px; font-size: 12px; color: #888;">Este correo fue generado automáticamente. No responda a este email.</p>
    </body>
    </html>
    """
    return html_body

def send_approval_email(invoice):
    """
    Función principal para enviar el correo de notificación al aprobador.
    """
    if not EMAIL_USER or not EMAIL_PASSWORD or not APPROVER_EMAIL:
        print("ADVERTENCIA: No se pudo enviar el correo. Verifique las variables de entorno.")
        return False
        
    try:
        yag = yagmail.SMTP(EMAIL_USER, EMAIL_PASSWORD)
        
        subject = f"ACTION REQUERIDA: Aprobación de Factura #{invoice.invoice_number}"
        body_html = generate_email_body(invoice)
        
        yag.send(
            to=APPROVER_EMAIL,
            subject=subject,
            contents=body_html
        )
        print(f"✅ Notificación enviada para la factura ID {invoice.id} a {APPROVER_EMAIL}")
        return True
    except Exception as e:
        print(f"❌ Error al enviar el correo para la factura ID {invoice.id}: {e}")
        return False

# Inicializar un yagmail de ejemplo para verificar la conexión si es necesario
# if __name__ == '__main__':
#     print("Script de notificación listo.")