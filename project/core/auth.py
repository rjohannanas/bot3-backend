import os
import firebase_admin
from firebase_admin import credentials, auth
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

def init_firebase():
    """Inicializa la app de Firebase Admin SDK de forma perezosa."""
    if not firebase_admin._apps:
        # Usamos ApplicationDefaultCredentials de Google Cloud
        project_id = os.environ.get("FIREBASE_PROJECT_ID")
        if project_id:
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred, {'projectId': project_id})
        else:
            # Fallback a inicialización estándar sin credenciales explícitas (funciona en GCP)
            firebase_admin.initialize_app()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Middleware/Dependencia de FastAPI.
    Extrae el token Bearer de los headers, lo verifica contra Firebase Auth
    y devuelve el payload del usuario (uid, email, etc).
    """
    init_firebase()
    token = credentials.credentials
    try:
        # Verifica el JWT usando las claves públicas de Firebase
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        print(f"⚠️ Auth Error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido, expirado o de otro proyecto.",
            headers={"WWW-Authenticate": "Bearer"},
        )
