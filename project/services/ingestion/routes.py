import os
import shutil
import tempfile
import secrets
import time
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Header, Query, Form
from fastapi.responses import FileResponse

import config
from shared.agent.auth import get_current_user
from shared.agent.dependencies import rag_system
from services.ingestion.manager import DocumentManager
from services.ingestion.tokens import _download_tokens, DOWNLOAD_TOKEN_TTL_SECONDS, purge_expired_tokens

router = APIRouter(prefix="/api/documents", tags=["Documents"])

# ─────────────────────────────────────────────────────────────────────────────
# API Key para el scraper externo
# ─────────────────────────────────────────────────────────────────────────────
def verify_api_key(x_api_key: str = Header(None)):
    """Verifica que el scraper envíe la clave correcta en los headers."""
    expected_key = os.environ.get("ADMIN_API_KEY")
    if not expected_key:
        raise HTTPException(status_code=500, detail="ADMIN_API_KEY no configurada en el servidor.")
    if x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="API Key inválida. Acceso denegado.")
    return x_api_key

# ─────────────────────────────────────────────────────────────────────────────
# Subida de documentos (scraper)
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/upload")
async def upload_documents(
    files: List[UploadFile] = File(...),
    metadata_urls: str = Form(None),
    source_collection: str = Form(default=None),
    api_key: str = Depends(verify_api_key)
):
    """
    Guarda los archivos en Cloud Storage (vía FUSE), los vectoriza y actualiza Qdrant.
    """
    if not rag_system.agent_graph:
        rag_system.initialize()

    doc_manager = DocumentManager(rag_system, source_collection=source_collection)
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

        added, skipped, rejected = doc_manager.add_documents(temp_paths, metadata_urls)

        return {
            "status": "success",
            "message": "Archivos procesados correctamente",
            "stats": {"added": added, "skipped": skipped, "rejected": rejected}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")
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
    """Genera un token de descarga de un solo uso (TTL: 30 min)."""
    base_dir = Path(config.PDF_DIR).resolve()
    pdf_path = (base_dir / filename).resolve()

    if not pdf_path.is_file() or not str(pdf_path).startswith(str(base_dir)):
        raise HTTPException(status_code=404, detail=f"Archivo no encontrado: {filename}")

    purge_expired_tokens()

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
    token: str = Query(..., description="Token de descarga"),
):
    """Sirve el PDF si el token es válido."""
    purge_expired_tokens()

    entry = _download_tokens.get(token)
    if not entry:
        raise HTTPException(status_code=401, detail="Token inválido o expirado.")

    token_filename, expires_at = entry
    if time.monotonic() > expires_at:
        _download_tokens.pop(token, None)
        raise HTTPException(status_code=401, detail="Token expirado.")

    if token_filename != filename:
        raise HTTPException(status_code=403, detail="Token incorrecto para este archivo.")

    # _download_tokens.pop(token, None) # Comentado: Ya no es de un solo uso

    base_dir = Path(config.PDF_DIR).resolve()
    pdf_path = (base_dir / filename).resolve()

    if not pdf_path.is_file() or not str(pdf_path).startswith(str(base_dir)):
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=filename,
        headers={
            # Muestra en visor del navegador (no fuerza descarga)
            "Content-Disposition": f"inline; filename=\"{filename}\"",
            # Permite que un iframe de otro origen (frontend) embeba este PDF
            "Access-Control-Allow-Origin": "*",
            # Elimina restricción de framing para permitir paneles laterales
            "X-Frame-Options": "ALLOWALL",
            # Política de seguridad de contenido que permite framing desde cualquier origen
            "Content-Security-Policy": "frame-ancestors *",
        }
    )
