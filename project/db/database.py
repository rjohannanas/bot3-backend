import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from google.cloud.sql.connector import Connector, IPTypes
from db.models import Base

# Variables de entorno extraídas de .env
DB_USER = os.environ.get("DB_USER")
DB_PASS = os.environ.get("DB_PASS")
DB_NAME = os.environ.get("DB_NAME")
INSTANCE_CONNECTION_NAME = os.environ.get("INSTANCE_CONNECTION_NAME")

# Singleton del conector — se crea UNA sola vez por proceso,
# no en cada llamada al pool (evita fugas de recursos bajo carga)
_connector: Connector | None = None

def _get_connector() -> Connector:
    global _connector
    if _connector is None:
        _connector = Connector()
    return _connector

def getconn():
    """Crea una conexión reutilizando el conector singleton."""
    conn = _get_connector().connect(
        INSTANCE_CONNECTION_NAME,
        "pg8000",
        user=DB_USER,
        password=DB_PASS,
        db=DB_NAME,
        ip_type=IPTypes.PUBLIC  # O IPTypes.PRIVATE si configuraste VPC en tu nube
    )
    return conn

# Configuración del Connection Pool de SQLAlchemy para producción
if INSTANCE_CONNECTION_NAME and DB_USER:
    engine = create_engine(
        "postgresql+pg8000://",
        creator=getconn,
        pool_size=5,
        max_overflow=2,
        pool_timeout=30,
        pool_recycle=1800 # Renovar conexiones cada 30 min para evitar desconexiones de Cloud SQL
    )
else:
    # Fallback de emergencia por si faltan variables de entorno (guarda localmente)
    print("⚠️ Variables de DB no encontradas. Usando SQLite en memoria como fallback.")
    engine = create_engine("sqlite:///./local_chat.db", connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Dependency para inyectar la sesión de DB en los endpoints de FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Crea las tablas en la base de datos si no existen"""
    Base.metadata.create_all(bind=engine)
