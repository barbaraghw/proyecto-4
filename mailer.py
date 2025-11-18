# mailer.py

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from os import getenv
from dotenv import load_dotenv

load_dotenv()

# Variables de entorno
MAIL_USERNAME = getenv("MAIL_USERNAME")
MAIL_PASSWORD = getenv("MAIL_PASSWORD")
MAIL_SERVER = getenv("MAIL_SERVER")
MAIL_PORT = int(getenv("MAIL_PORT", 587))
BASE_URL = getenv("BASE_URL")

def create_interactive_email_html(invoice_data):
    """
    Diseña una plantilla HTML profesional y responsive con botones interactivos
    y tabla de información clave. [cite: 37, 38, 39, 40, 41]
    
    :param invoice_data: Objeto Invoice de SQLAlchemy.
    :return: Cadena HTML del cuerpo del correo.
    """
    
    # Formatear datos para la tabla
    invoice_info = {
        "Proveedor": invoice_data.provider_name,
        "Número de Factura": invoice_data.invoice_number,
        "Fecha de Emisión": invoice_data.issue_date.strftime("%Y-%m-%d"),
        "Monto Total": f"${invoice_data.total_amount:.2f}",
        "Impuestos": f"${invoice_data.taxes:.2f}",
        "Fecha de Vencimiento": invoice_data.due_date.strftime("%Y-%m-%d") if invoice_data.due_date else "N/A"
    }

    # Crear filas de la tabla
    table_rows = "".join([
        f"""
        <tr>
            <td style="padding: 10px; border: 1px solid #ddd;">{key}</td>
            <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">{value}</td>
        </tr>
        """
        for key, value in invoice_info.items()
    ])

    # Enlaces directos para la acción [cite: 39]
    approve_url = f"{BASE_URL}/api/v1/webhook/invoice/{invoice_data.id}/approve"
    # Para el rechazo, usaremos un enlace que abre una página de comentarios más simple [cite: 40]
    reject_url = f"{BASE_URL}/api/v1/webhook/reject_form/{invoice_data.id}" 

    html_content = f"""
    <html>
    <head>
        <style>
            .button {{
                display: inline-block;
                padding: 10px 20px;
                text-align: center;
                text-decoration: none;
                border-radius: 5px;
                font-weight: bold;
                color: white !important;
                margin: 5px;
            }}
            .approve-btn {{ background-color: #4CAF50; }}
            .reject-btn {{ background-color: #f44336; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
            th, td {{ text-align: left; padding: 8px; border: 1px solid #ddd; }}
        </style>
    </head>
    <body>
        <h2>📊 Solicitud de Aprobación de Factura</h2>
        <p>Por favor, revise la información de la factura y tome una decisión. La información contextual completa para la toma de decisiones está a continuación. [cite: 41]</p>

        <table>
            <thead>
                <tr style="background-color: #f2f2f2;">
                    <th>Campo</th>
                    <th>Valor Extraído</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>

        <h3>Acciones Requeridas:</h3>
        <a href="{approve_url}" class="button approve-btn">✅ Aprobar Factura</a>
        
        <a href="{reject_url}" class="button reject-btn">❌ Rechazar Factura (con Comentarios)</a>

        <p><small>Nota: Los botones envían una solicitud directa al sistema para registrar su decisión.</small></p>
    </body>
    </html>
    """
    return html_content

def send_invoice_notification(invoice_data, recipient_email):
    """
    Servicio de envío de correos electrónicos automatizados. [cite: 31]
    """
    if not all([MAIL_USERNAME, MAIL_PASSWORD, BASE_URL]):
        print("Error: Configuración de correo incompleta. No se pudo enviar el correo.")
        return False
        
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"FACTURA PENDIENTE DE APROBACIÓN - No. {invoice_data.invoice_number}"
    msg['From'] = MAIL_USERNAME
    msg['To'] = recipient_email

    # Crear el cuerpo HTML interactivo
    html_body = create_interactive_email_html(invoice_data)
    
    part = MIMEText(html_body, 'html')
    msg.attach(part)

    try:
        # Conexión y envío vía SMTP
        server = smtplib.SMTP(MAIL_SERVER, MAIL_PORT)
        server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.sendmail(MAIL_USERNAME, recipient_email, msg.as_string())
        server.quit()
        print(f"Correo enviado a {recipient_email} para la factura ID {invoice_data.id}.")
        return True
    except Exception as e:
        print(f"Fallo al enviar el correo: {e}")
        return False