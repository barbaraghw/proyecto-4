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
    y su estado actual. [cite: 24]
    """
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    
    # Módulo 1: Campos obligatorios extraídos [cite: 16, 17, 18, 19, 20, 21]
    provider_name = Column(String) 
    invoice_number = Column(String, unique=True)
    issue_date = Column(DateTime)
    total_amount = Column(Float)
    taxes = Column(Float)
    due_date = Column(DateTime, nullable=True) # Valor opcional [cite: 21]

    # Módulo 2: Gestión de Estados 
    status = Column(String, default=STATUS_EN_PROCESO)
    
    # Módulo 2: Metadatos y Auditoría [cite: 26, 27, 28]
    extraction_log = Column(String) # Almacenamiento de metadatos del proceso de extracción
    
    # Registro de auditoría/historial [cite: 26, 48]
    created_at = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Comentarios y Justificaciones [cite: 28]
    decision_justification = Column(String, nullable=True) 
    
def init_db():
    """Inicializa la base de datos (crea la tabla si no existe)."""
    Base.metadata.create_all(bind=Engine)

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