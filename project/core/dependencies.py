from core.rag_system import RAGSystem
from core.chat_interface import ChatInterface

# Inicializamos el sistema globalmente de forma 'lazy'
# (No se carga en memoria hasta que se hace la primera petición)
rag_system = RAGSystem()
chat_interface = ChatInterface(rag_system)
