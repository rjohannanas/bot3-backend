from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
import json
import asyncio
import re

from db.database import get_db
from db.models import ChatMessage, ChatSession
from shared.agent.auth import get_current_user
from shared.agent.dependencies import rag_system, chat_interface

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
    history: list = []

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
    user_id = user.get("uid", "anonymous")
    await asyncio.to_thread(ensure_session, db, request.session_id, user_id)

    user_msg = ChatMessage(session_id=request.session_id, role="user", content=request.message)
    db.add(user_msg)
    await asyncio.to_thread(db.commit)

    def run_chat():
        final_msgs = None
        for chunk in chat_interface.chat(request.message, request.history, request.session_id):
            final_msgs = chunk
        return final_msgs

    final_messages = await asyncio.to_thread(run_chat)
        
    response_text = ""
    if isinstance(final_messages, list) and len(final_messages) > 0:
        response_text = final_messages[-1].get("content", "")
    else:
        response_text = str(final_messages)
        
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
    user_id = user.get("uid", "anonymous")
    await asyncio.to_thread(ensure_session, db, request.session_id, user_id)

    user_msg = ChatMessage(session_id=request.session_id, role="user", content=request.message)
    db.add(user_msg)
    await asyncio.to_thread(db.commit)

    async def event_generator():
        response_text = ""
        last_len = 0
        last_msg_idx = -1
        
        async for chunk in chat_interface.achat(request.message, request.history, request.session_id):
            if not isinstance(chunk, list) or not chunk:
                continue
                
            idx = len(chunk) - 1
            msg = chunk[-1]
            content = msg.get("content", "")
            
            if idx != last_msg_idx:
                last_len = 0
                last_msg_idx = idx
                
            if "metadata" in msg:
                title = msg["metadata"].get("title", "Procesando...")
                yield f"data: {json.dumps({'type': 'status', 'message': title})}\n\n"
            
            else:
                if len(content) > last_len:
                    delta = content[last_len:]
                    yield f"data: {json.dumps({'type': 'token', 'content': delta})}\n\n"
                    last_len = len(content)
                response_text = content

        if response_text:
            ai_msg = ChatMessage(session_id=request.session_id, role="assistant", content=response_text)
            db.add(ai_msg)
            await asyncio.to_thread(db.commit)
            
            docs = []
            if "**Fuentes:**" in response_text or "**Sources:**" in response_text:
                parts = re.split(r'\*\*Fuentes:\*\*|\*\*Sources:\*\*', response_text)
                if len(parts) > 1:
                    sources_section = parts[-1]
                    for line in sources_section.split('\n'):
                        line = line.strip()
                        if line.startswith('* ') or line.startswith('- '):
                            fname = line[2:].strip()
                            docs.append({
                                "title": fname, 
                                "url": f"https://storage.googleapis.com/recs-chb-seteloee/pdf_docs/{fname}"
                            })
            
            if docs:
                yield f"data: {json.dumps({'type': 'sources', 'docs': docs})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ─────────────────────────────────────────────
#  Endpoints de Gestión de Sesiones (Historial)
# ─────────────────────────────────────────────

class SessionSummary(BaseModel):
    """Resumen de una sesión para mostrar en la barra lateral del frontend."""
    id: str
    title: str
    created_at: int   # Unix timestamp en milisegundos
    updated_at: int   # Unix timestamp en milisegundos

class MessageResponse(BaseModel):
    """Un mensaje individual del historial de una sesión."""
    id: str
    role: str
    content: str
    timestamp: int    # Unix timestamp en milisegundos


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Devuelve todas las sesiones de chat del usuario autenticado,
    ordenadas de la más reciente a la más antigua.
    El título de cada sesión es el primer mensaje que envió el usuario.
    """
    user_id = user.get("uid", "anonymous")

    sessions = await asyncio.to_thread(
        lambda: db.query(ChatSession)
                  .filter(ChatSession.user_id == user_id)
                  .order_by(ChatSession.created_at.desc())
                  .all()
    )

    result = []
    for s in sessions:
        # Obtener el primer mensaje del usuario para usar como título
        first_msg = await asyncio.to_thread(
            lambda sid=s.id: db.query(ChatMessage)
                               .filter(ChatMessage.session_id == sid, ChatMessage.role == "user")
                               .order_by(ChatMessage.created_at.asc())
                               .first()
        )
        title = first_msg.content[:60] + ("..." if first_msg and len(first_msg.content) > 60 else "") \
                if first_msg else "Nueva conversación"

        result.append(SessionSummary(
            id=s.id,
            title=title,
            created_at=int(s.created_at.timestamp() * 1000),
            updated_at=int(s.created_at.timestamp() * 1000),
        ))

    return result


@router.get("/sessions/{session_id}", response_model=list[MessageResponse])
async def get_session_messages(
    session_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Devuelve todos los mensajes de una sesión específica.
    Valida que la sesión pertenezca al usuario autenticado.
    """
    user_id = user.get("uid", "anonymous")

    # Verificar propiedad de la sesión (seguridad: un usuario no puede ver chats de otro)
    session = await asyncio.to_thread(
        lambda: db.query(ChatSession).filter(ChatSession.id == session_id).first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para ver esta sesión")

    messages = await asyncio.to_thread(
        lambda: db.query(ChatMessage)
                  .filter(ChatMessage.session_id == session_id)
                  .order_by(ChatMessage.created_at.asc())
                  .all()
    )

    return [
        MessageResponse(
            id=m.id,
            role=m.role,
            content=m.content,
            timestamp=int(m.created_at.timestamp() * 1000),
        )
        for m in messages
    ]


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Elimina una sesión y todos sus mensajes en cascada.
    Valida que la sesión pertenezca al usuario autenticado.
    """
    user_id = user.get("uid", "anonymous")

    session = await asyncio.to_thread(
        lambda: db.query(ChatSession).filter(ChatSession.id == session_id).first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para eliminar esta sesión")

    await asyncio.to_thread(lambda: (db.delete(session), db.commit()))
