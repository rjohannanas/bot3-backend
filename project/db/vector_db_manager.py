import config
from langchain_google_vertexai import VertexAIEmbeddings
from langchain_qdrant import QdrantVectorStore, FastEmbedSparse, RetrievalMode
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

class VectorDbManager:
    __client: QdrantClient
    __dense_embeddings: VertexAIEmbeddings
    __sparse_embeddings: FastEmbedSparse
    
    def __init__(self):
        self.__client = None
        self.__dense_embeddings = None
        self.__sparse_embeddings = None

    def _ensure_initialized(self):
        if self.__client is None:
            print("🚀 [LazyLoad] Descargando/Cargando Modelos Embeddings...")
            self.__client = QdrantClient(
                url=config.QDRANT_URL,
                api_key=config.QDRANT_API_KEY or None
            )
            self.__dense_embeddings = VertexAIEmbeddings(
                model_name=config.DENSE_MODEL,
                project=config.GCP_PROJECT,
                location=config.GCP_LOCATION
            )
            self.__sparse_embeddings = FastEmbedSparse(model_name=config.SPARSE_MODEL)
            print("✅ Modelos de Embeddings listos.")

    def create_collection(self, collection_name):
        self._ensure_initialized()
        if not self.__client.collection_exists(collection_name):
            print(f"Creating collection: {collection_name}...")
            self.__client.create_collection(
                collection_name=collection_name,
                vectors_config=qmodels.VectorParams(size=len(self.__dense_embeddings.embed_query("test")), distance=qmodels.Distance.COSINE),
                sparse_vectors_config={config.SPARSE_VECTOR_NAME: qmodels.SparseVectorParams()},
            )
            print(f"✓ Collection created: {collection_name}")
        else:
            print(f"✓ Collection already exists: {collection_name}")

    def delete_collection(self, collection_name):
        self._ensure_initialized()
        try:
            if self.__client.collection_exists(collection_name):
                print(f"Removing existing Qdrant collection: {collection_name}")
                self.__client.delete_collection(collection_name)
        except Exception as e:
            print(f"Warning: could not delete collection {collection_name}: {e}")

    def get_collection(self, collection_name) -> QdrantVectorStore:
        self._ensure_initialized()
        try:
            return QdrantVectorStore(
                    client=self.__client,
                    collection_name=collection_name,
                    embedding=self.__dense_embeddings,
                    sparse_embedding=self.__sparse_embeddings,
                    retrieval_mode=RetrievalMode.HYBRID,
                    sparse_vector_name=config.SPARSE_VECTOR_NAME
                )
        except Exception as e:
            print(f"❌ Unable to get collection {collection_name}: {e}")
            raise