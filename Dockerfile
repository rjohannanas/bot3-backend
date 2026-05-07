FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar utilidades básicas
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copiar dependencias e instalarlas
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Pre-descargar modelo BM25 sparse para evitar descarga en cold start
RUN python -c "from fastembed import SparseTextEmbedding; SparseTextEmbedding('Qdrant/bm25')"

# Copiar el proyecto
COPY project/ .

# Crear directorios para datos persistentes (punto de montaje GCS FUSE)
RUN mkdir -p /app/data/parent_store /app/data/markdown_docs

# Exponer el puerto por el cual uvicorn correrá (dictaminado por $PORT)
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8080}"]
