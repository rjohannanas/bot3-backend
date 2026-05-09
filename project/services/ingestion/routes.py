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
