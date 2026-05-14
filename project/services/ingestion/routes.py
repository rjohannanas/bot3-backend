import os
import shutil
import tempfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Header
from shared.agent.dependencies import rag_system
from services.ingestion.manager import DocumentManager

router = APIRouter(prefix="/api/documents", tags=["Documents"])

def verify_api_key(x_api_key: str = Header(None)):
    """Verifica que el scraper envíe la clave correcta en los headers."""
    expected_key = os.environ.get("ADMIN_API_KEY")
    
    if not expected_key:
        raise HTTPException(
            status_code=500, 
            detail="El servidor no tiene configurada la variable ADMIN_API_KEY"
        )
        
    if x_api_key != expected_key:
        raise HTTPException(
            status_code=401, 
            detail="API Key inválida. Acceso denegado."
        )
    return x_api_key

@router.post("/upload")
async def upload_documents(
    files: List[UploadFile] = File(...),
    api_key: str = Depends(verify_api_key)
):
    """
    Endpoint para que el Scraper suba PDFs de forma automatizada.
    Guarda los archivos en Cloud Storage (vía FUSE), los vectoriza y actualiza Qdrant.
    """
    if not rag_system.agent_graph:
        rag_system.initialize()

    doc_manager = DocumentManager(rag_system)
    temp_dir = tempfile.mkdtemp()
    temp_paths = []

    try:
        for file in files:
            if not file.filename:
                continue
            temp_path = Path(temp_dir) / file.filename
            with open(temp_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            temp_paths.append(str(temp_path))

        added, skipped, rejected = doc_manager.add_documents(temp_paths)

        return {
            "status": "success",
            "message": "Archivos procesados correctamente",
            "stats": {
                "added": added,
                "skipped": skipped,
                "rejected": rejected
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno procesando documentos: {str(e)}")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────────
# Paso 1: El frontend autenticado solicita un token de descarga
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/token")
async def request_download_token(
    filename: str,
    user: dict = Depends(get_current_user),
):
    """
    Genera un token de descarga de un solo uso (TTL: 30 min) para un archivo
    específico. Solo usuarios autenticados con Firebase pueden obtenerlo.

    Flujo:
      1. Frontend llama a POST /api/documents/token?filename=X.pdf  (con Bearer)
      2. Backend devuelve { "token": "...", "url": "..." }
      3. Frontend abre la URL en nueva pestaña — el navegador no necesita enviar
         el Bearer header, el token va en la query string.
    """
    base_dir = Path(config.PDF_DIR).resolve()
    pdf_path = (base_dir / filename).resolve()

    if not pdf_path.is_file() or not str(pdf_path).startswith(str(base_dir)):
        raise HTTPException(status_code=404, detail=f"Archivo no encontrado: {filename}")

    _purge_expired_tokens()

    token = secrets.token_urlsafe(32)
    expires_at = time.monotonic() + DOWNLOAD_TOKEN_TTL_SECONDS
    _download_tokens[token] = (filename, expires_at)

    return {
        "token": token,
        "filename": filename,
        "expires_in_seconds": DOWNLOAD_TOKEN_TTL_SECONDS,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Paso 2: El navegador canjea el token y recibe el PDF
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/files/{filename}")
async def get_document(
    filename: str,
    token: str = Query(..., description="Token de descarga obtenido de POST /token"),
):
    """
    Sirve el PDF si el token es válido, pertenece a este archivo y no expiró.
    El token se invalida inmediatamente tras el primer uso (one-time use).
    """
    _purge_expired_tokens()

    entry = _download_tokens.get(token)
    if not entry:
        raise HTTPException(status_code=401, detail="Token inválido o expirado.")

    token_filename, expires_at = entry
    if time.monotonic() > expires_at:
        _download_tokens.pop(token, None)
        raise HTTPException(status_code=401, detail="Token expirado.")

    if token_filename != filename:
        raise HTTPException(status_code=403, detail="El token no corresponde a este archivo.")

    # Invalidar el token tras el primer uso exitoso
    _download_tokens.pop(token, None)

    base_dir = Path(config.PDF_DIR).resolve()
    pdf_path = (base_dir / filename).resolve()

    if not pdf_path.is_file() or not str(pdf_path).startswith(str(base_dir)):
        raise HTTPException(status_code=404, detail=f"Archivo no encontrado: {filename}")

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=filename,
        headers={
            # Abre en el visor del navegador (nueva pestaña), no descarga
            "Content-Disposition": f"inline; filename=\"{filename}\"",
        }
    )

