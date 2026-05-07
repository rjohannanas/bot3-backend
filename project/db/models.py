from datetime import datetime
import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class ChatSession(Base):
    """Representa una conversación/hilo de un usuario específico."""
    __tablename__ = 'chat_sessions'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, index=True, nullable=False) # UUID proporcionado por Firebase Auth
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relación uno-a-muchos con los mensajes
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

class ChatMessage(Base):
    """Representa un mensaje individual dentro de una sesión de chat."""
    __tablename__ = 'chat_messages'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey('chat_sessions.id'), nullable=False)
    role = Column(String, nullable=False) # 'user' o 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relación inversa a la sesión
    session = relationship("ChatSession", back_populates="messages")
