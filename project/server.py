from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import gradio as gr
import os

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from ui.gradio_app import create_gradio_ui
from shared.agent.dependencies import rag_system
from services.chat.routes import router as chat_router
from services.ingestion.routes import router as ingestion_router
from db.database import init_db
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicialización controlada en el startup del servidor."""
    # 1. Inicializar la base de datos
    try:
        init_db()
        print("✅ [Startup] Base de datos inicializada")
    except Exception as e:
        print(f"⚠️ [Startup] Error inicializando la BD (continuando sin BD): {e}")

    # 2. Inicializar el sistema RAG (warm-up)
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", tags=["System"])
def health_check():
    """Health check para Cloud Run startup/liveness probes."""
    return {"status": "ok"}

# --- Registrar servicios ---
app.include_router(chat_router)       # /api/chat, /api/chat/stream
app.include_router(ingestion_router)  # /api/documents/upload

# --- UI de Gradio (solo si está habilitada) ---
if os.environ.get("ENABLE_GRADIO_UI", "false").lower() == "true":
    print("\n🔨 [Dev] Creando UI RAG (Gradio)...")
    demo = create_gradio_ui(rag_system)
    app = gr.mount_gradio_app(app, demo, path="/ui")
    print("✅ [Dev] Gradio disponible en /ui")
else:
    print("ℹ️ [Prod] Gradio UI desactivada (ENABLE_GRADIO_UI != true)")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    print(f"\n🚀 Levantando servidor en puerto {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
