import os

# --- Directory Configuration ---
_BASE_DIR = os.path.dirname(os.path.dirname(__file__))

MARKDOWN_DIR = os.environ.get("MARKDOWN_DIR", os.path.join(_BASE_DIR, "markdown_docs"))
PDF_DIR = os.environ.get("PDF_DIR", os.path.join(_BASE_DIR, "pdf_docs"))
PARENT_STORE_PATH = os.environ.get("PARENT_STORE_PATH", os.path.join(_BASE_DIR, "parent_store"))

# --- GCP Config ---
GCP_PROJECT = os.environ.get("GCP_PROJECT", "servicios-492716")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "us-central1")
GCP_LLM_LOCATION = os.environ.get("GCP_LLM_LOCATION", "global")

# --- Qdrant Configuration ---
CHILD_COLLECTION = "document_child_chunks"
NORMAS_COLLECTION = "normas_child_chunks"
NORMAS_MARKDOWN_DIR = os.environ.get("NORMAS_MARKDOWN_DIR", os.path.join(_BASE_DIR, "normas_markdown_docs"))
SPARSE_VECTOR_NAME = "sparse"

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")

# --- Model Configuration ---
DENSE_MODEL = "text-embedding-004"
LLM_MODEL = "gemini-2.5-flash"
SPARSE_MODEL = "Qdrant/bm25"
LLM_TEMPERATURE = 0

# --- Agent Configuration ---
MAX_TOOL_CALLS = 8
MAX_ITERATIONS = 10
GRAPH_RECURSION_LIMIT = 50
BASE_TOKEN_THRESHOLD = 2000
TOKEN_GROWTH_FACTOR = 0.9

# --- Text Splitter Configuration ---
CHILD_CHUNK_SIZE = 500
CHILD_CHUNK_OVERLAP = 100
MIN_PARENT_SIZE = 2000
MAX_PARENT_SIZE = 4000
HEADERS_TO_SPLIT_ON = [
    ("#", "H1"),
    ("##", "H2"),
    ("###", "H3")
]

# --- Langfuse Observability ---
LANGFUSE_ENABLED = os.environ.get("LANGFUSE_ENABLED", "false").lower() == "true"
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "")
LANGFUSE_BASE_URL = os.environ.get("LANGFUSE_BASE_URL", "http://localhost:3000")
