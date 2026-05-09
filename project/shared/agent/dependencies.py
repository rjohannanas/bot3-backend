from shared.agent.rag_system import RAGSystem
from services.chat.interface import ChatInterface

# Singletons globales del proceso — se inicializan una sola vez en el lifespan de FastAPI
rag_system = RAGSystem()
chat_interface = ChatInterface(rag_system)
