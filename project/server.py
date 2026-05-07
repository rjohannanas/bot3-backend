from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import gradio as gr
import os
import json

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from ui.gradio_app import create_gradio_ui
from core.dependencies import rag_system, chat_interface
from api.chat_routes import router as chat_router
from db.database import init_db
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicialización en caliente (Warm-up) del sistema RAG."""
    try:
        print("\n🚀 [Startup] Inicializando sistema RAG y compilando grafo...")
        rag_system.initialize()
        print("✅ [Startup] Sistema RAG listo para recibir peticiones\n")
    except Exception as e:
        print(f"\n⚠️ [Startup] Error inicializando RAG: {e}\n")
    yield

app = FastAPI(
    title="Agentic RAG API", 
    description="API RESTful para interactuar con el sistema Agentic RAG",
    version="1.0.0",
    lifespan=lifespan
)

# Configurar CORS (Fase 1)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # En producción cambiar por la URL del frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", tags=["System"])
def health_check():
    """Health check para Cloud Run startup/liveness probes."""
    return {"status": "ok"}

# Inicializar la base de datos (crear tablas si no existen)
try:
    init_db()
    print("✅ Base de datos inicializada")
except Exception as e:
    print(f"⚠️ Aviso: Error inicializando la BD (¿Falta IP/Credenciales?): {e}")

# Registrar las rutas del chat (con Auth y DB)
app.include_router(chat_router)  # /api/chat y /api/chat/stream


# Montar la UI antigua de Gradio como sub-módulo
print("\n🔨 Creando UI RAG (Gradio)...")
demo = create_gradio_ui(rag_system)
app = gr.mount_gradio_app(app, demo, path="/ui")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    print(f"\n🚀 Levantando servidor en puerto {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
