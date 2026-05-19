import uuid
from langchain_google_vertexai import ChatVertexAI
import config
from db.vector_db_manager import VectorDbManager
from db.parent_store_manager import ParentStoreManager
from document_chunker import DocumentChunker
from rag_agent.tools import ToolFactory
from rag_agent.graph import create_agent_graph
from shared.agent.observability import Observability

class RAGSystem:

    def __init__(self, collection_name=config.CHILD_COLLECTION, normas_collection_name=config.NORMAS_COLLECTION):
        self.collection_name = collection_name
        self.normas_collection_name = normas_collection_name
        self.vector_db = VectorDbManager()
        self.parent_store = ParentStoreManager()
        self.chunker = DocumentChunker()
        self.observability = Observability()
        self.agent_graph = None
        self.recursion_limit = config.GRAPH_RECURSION_LIMIT

    def initialize(self):
        self.vector_db.create_collection(self.collection_name)
        self.vector_db.create_collection(self.normas_collection_name)
        collection = self.vector_db.get_collection(self.collection_name)
        normas_collection = self.vector_db.get_collection(self.normas_collection_name)

        llm = ChatVertexAI(
            model=config.LLM_MODEL,
            temperature=config.LLM_TEMPERATURE,
            project=config.GCP_PROJECT,
            location=config.GCP_LLM_LOCATION
        )
        tools = ToolFactory(collection, normas_collection).create_tools()
        self.agent_graph = create_agent_graph(llm, tools)

    def get_config(self, session_id: str):
        cfg = {"configurable": {"thread_id": session_id}, "recursion_limit": self.recursion_limit}
        handler = self.observability.get_handler()
        if handler:
            cfg["callbacks"] = [handler]
        return cfg

    def reset_thread(self, session_id: str):
        try:
            self.agent_graph.checkpointer.delete_thread(session_id)
        except Exception as e:
            print(f"Warning: Could not delete thread {session_id}: {e}")
        self.thread_id = str(uuid.uuid4())
