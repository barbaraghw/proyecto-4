# database.py

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

# Configuración de la DB
DATABASE_URL = "sqlite:///invoices.db"
Engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=Engine)

# Definición de Estados 
STATUS_EN_PROCESO = "En Proceso"
STATUS_APROBADO = "Aprobado"
STATUS_RECHAZADO = "Rechazado"

class Invoice(Base):
    """
    Modelo de Base de Datos para almacenar la información de las facturas
    y su estado actual.
    """
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    
    # Módulo 1: Campos obligatorios extraídos
    provider_name = Column(String) 
    invoice_number = Column(String, unique=True)
    issue_date = Column(DateTime)
    total_amount = Column(Float)
    taxes = Column(Float)
    due_date = Column(DateTime, nullable=True) 

    # Módulo 2: Gestión de Estados 
    status = Column(String, default=STATUS_EN_PROCESO)
    
    # Módulo 2: Metadatos y Auditoría
    extraction_log = Column(String) 
    
    # Registro de auditoría/historial
    created_at = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Comentarios y Justificaciones
    decision_justification = Column(String, nullable=True) 
    
def init_db():
    """Inicializa la base de datos (crea la tabla si no existe)."""
    Base.metadata.create_all(bind=Engine)

# -------------------------------------------------------------
# FUNCIÓN AGREGADA PARA LA GESTIÓN DE ESTADOS (WEBHOOK)
# -------------------------------------------------------------
def update_invoice_status(db, invoice_id, new_status, justification=None):
    """
    Actualiza el estado de una factura y registra el timestamp de la actualización.
    
    :param db: Sesión de la base de datos.
    :param invoice_id: ID de la factura a actualizar.
    :param new_status: Nuevo estado (STATUS_APROBADO o STATUS_RECHAZADO).
    :param justification: Comentario/razón de la decisión.
    :return: El objeto Invoice actualizado o None si no se encontró.
    """
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    
    if invoice:
        # Solo actualiza si hay cambio de estado
        if invoice.status != new_status:
            invoice.status = new_status
            invoice.last_updated = datetime.utcnow() # Registra el timestamp del cambio
            if justification:
                invoice.decision_justification = justification
            
            db.add(invoice)
            db.commit()
            db.refresh(invoice)
        return invoice
    return None

# Función de utilidad para obtener una sesión de DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

if __name__ == '__main__':
    init_db()
    print("Base de datos 'invoices.db' inicializada.")