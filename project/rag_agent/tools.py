from typing import List
from langchain_core.tools import tool
from db.parent_store_manager import ParentStoreManager

class ToolFactory:
    
    def __init__(self, collection, normas_collection=None):
        self.collection = collection
        self.normas_collection = normas_collection
        self.parent_store_manager = ParentStoreManager()
    
    def _search_child_chunks(self, query: str, limit: int) -> str:
        """Search in manually uploaded documents (PDFs, technical manuals, reports).
        Use this tool for general document queries not related to Peruvian legal norms.
        
        Args:
            query: Search query string
            limit: Maximum number of results to return
        """
        try:
            results = self.collection.similarity_search(query, k=limit)
            if not results:
                return "NO_RELEVANT_CHUNKS"

            return "\n\n".join([
                f"Parent ID: {doc.metadata.get('parent_id', '')}\n"
                f"File Name: {doc.metadata.get('source', '')}\n"
                f"Content: {doc.page_content.strip()}"
                for doc in results
            ])            

        except Exception as e:
            return f"RETRIEVAL_ERROR: {str(e)}"

    def _search_normas_chunks(self, query: str, limit: int) -> str:
        """Search exclusively in legal norms from El Peruano (Decretos Supremos,
        Resoluciones Ministeriales, Leyes, Ordenanzas, etc.).
        Use this tool when the user asks about Peruvian legislation, regulations,
        ministerial entities (MINEM, MINAM, MEF, etc.), or publication dates.

        Args:
            query: Search query string
            limit: Maximum number of results to return
        """
        if not self.normas_collection:
            return "NORMAS_COLLECTION_NOT_CONFIGURED"
        try:
            results = self.normas_collection.similarity_search(query, k=limit)
            if not results:
                return "NO_RELEVANT_NORMAS"

            return "\n\n".join([
                f"Parent ID: {doc.metadata.get('parent_id', '')}\n"
                f"Fuente: {doc.metadata.get('source', '')}\n"
                f"Entidad: {doc.metadata.get('entidad_nombre', 'N/A')}\n"
                f"Tipo: {doc.metadata.get('tipo_dispositivo', 'N/A')}\n"
                f"Fecha: {doc.metadata.get('fecha_publicacion', 'N/A')}\n"
                f"Content: {doc.page_content.strip()}"
                for doc in results
            ])

        except Exception as e:
            return f"RETRIEVAL_ERROR: {str(e)}"
    
    def _retrieve_many_parent_chunks(self, parent_ids: List[str]) -> str:
        """Retrieve full parent chunks by their IDs.
    
        Args:
            parent_ids: List of parent chunk IDs to retrieve
        """
        try:
            ids = [parent_ids] if isinstance(parent_ids, str) else list(parent_ids)
            raw_parents = self.parent_store_manager.load_content_many(ids)
            if not raw_parents:
                return "NO_PARENT_DOCUMENTS"

            return "\n\n".join([
                f"Parent ID: {doc.get('parent_id', 'n/a')}\n"
                f"File Name: {doc.get('metadata', {}).get('source', 'unknown')}\n"
                f"Content: {doc.get('content', '').strip()}"
                for doc in raw_parents
            ])            

        except Exception as e:
            return f"PARENT_RETRIEVAL_ERROR: {str(e)}"
    
    def _retrieve_parent_chunks(self, parent_id: str) -> str:
        """Retrieve full parent chunks by their IDs.
    
        Args:
            parent_id: Parent chunk ID to retrieve
        """
        try:
            parent = self.parent_store_manager.load_content(parent_id)
            if not parent:
                return "NO_PARENT_DOCUMENT"

            return (
                f"Parent ID: {parent.get('parent_id', 'n/a')}\n"
                f"File Name: {parent.get('metadata', {}).get('source', 'unknown')}\n"
                f"Content: {parent.get('content', '').strip()}"
            )          

        except Exception as e:
            return f"PARENT_RETRIEVAL_ERROR: {str(e)}"
    
    def create_tools(self) -> List:
        """Create and return the list of tools."""
        search_tool = tool("search_child_chunks")(self._search_child_chunks)
        search_normas_tool = tool("search_normas_chunks")(self._search_normas_chunks)
        retrieve_tool = tool("retrieve_parent_chunks")(self._retrieve_many_parent_chunks)
        
        return [search_tool, search_normas_tool, retrieve_tool]