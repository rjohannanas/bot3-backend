from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
import json
import asyncio

from db.database import get_db
from db.models import ChatMessage, ChatSession
from core.auth import get_current_user
from core.dependencies import rag_system, chat_interface

# Instanciamos el router
router = APIRouter(prefix="/api/chat", tags=["Chat"])

def ensure_session(db: Session, session_id: str, user_id: str):
    """Asegura que la sesión exista en la base de datos antes de insertar mensajes."""
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        session = ChatSession(id=session_id, user_id=user_id)
        db.add(session)
        try:
            db.commit()
        except Exception:
            db.rollback()

class ChatRequest(BaseModel):
    session_id: str = "default_session"
    message: str
    history: list = [] # Opcional si permitimos que el cliente envíe su historia (aunque ya no es necesario con DB)

class ChatResponse(BaseModel):
    response: str

@router.post("", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest, 
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Endpoint bloqueante autenticado.
    Recibe la petición, guarda en DB, espera al Agente y devuelve la respuesta.
    """
    # La inicialización ahora ocurre en el startup de FastAPI (server.py)
    
    # 0. Asegurar que la sesión de chat existe
    user_id = user.get("uid", "anonymous")
    await asyncio.to_thread(ensure_session, db, request.session_id, user_id)

    # 1. Guardar pregunta del usuario en base de datos
    user_msg = ChatMessage(session_id=request.session_id, role="user", content=request.message)
    db.add(user_msg)
    await asyncio.to_thread(db.commit)

    def run_chat():
        final_msgs = None
        for chunk in chat_interface.chat(request.message, request.history, request.session_id):
            final_msgs = chunk
        return final_msgs

    # Ejecutar el chat sincrónico en un hilo separado
    final_messages = await asyncio.to_thread(run_chat)
        
    response_text = ""
    if isinstance(final_messages, list) and len(final_messages) > 0:
        response_text = final_messages[-1].get("content", "")
    else:
        response_text = str(final_messages)
        
    # 2. Guardar respuesta del asistente en base de datos
    ai_msg = ChatMessage(session_id=request.session_id, role="assistant", content=response_text)
    db.add(ai_msg)
    await asyncio.to_thread(db.commit)

    return ChatResponse(response=response_text)

@router.post("/stream")
async def chat_stream_endpoint(
    request: ChatRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Endpoint de Streaming SSE autenticado (No bloqueante).
    """
    # 0. Asegurar que la sesión de chat existe
    user_id = user.get("uid", "anonymous")
    await asyncio.to_thread(ensure_session, db, request.session_id, user_id)

    # 1. Guardar pregunta del usuario
    user_msg = ChatMessage(session_id=request.session_id, role="user", content=request.message)
    db.add(user_msg)
    await asyncio.to_thread(db.commit)

    async def event_generator():
        response_text = ""
        last_len = 0
        last_msg_idx = -1
        
        # 2. Iterar generador ASÍNCRONO para no bloquear el loop
        async for chunk in chat_interface.achat(request.message, request.history, request.session_id):
            if not isinstance(chunk, list) or not chunk:
                continue
                
            idx = len(chunk) - 1
            msg = chunk[-1]
            content = msg.get("content", "")
            
            # Reiniciar cursor si pasamos a un nuevo mensaje en el array
            if idx != last_msg_idx:
                last_len = 0
                last_msg_idx = idx
                
            # Emitir Eventos de Estado
            if "metadata" in msg:
                title = msg["metadata"].get("title", "Procesando...")
                yield f"data: {json.dumps({'type': 'status', 'message': title})}\n\n"
                
                # Emitir Fuentes si vemos un resultado de herramienta
                if "```" in content:
                    yield f"data: {json.dumps({'type': 'sources', 'docs': [{'title': 'Base de Conocimiento RAG', 'url': '#'}]})}\n\n"
            
            # Emitir Tokens de texto
            else:
                if len(content) > last_len:
                    delta = content[last_len:]
                    yield f"data: {json.dumps({'type': 'token', 'content': delta})}\n\n"
                    last_len = len(content)
                response_text = content

        # 3. Guardar respuesta final en BD una vez que terminó el streaming
        if response_text:
            ai_msg = ChatMessage(session_id=request.session_id, role="assistant", content=response_text)
            db.add(ai_msg)
            await asyncio.to_thread(db.commit)

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
