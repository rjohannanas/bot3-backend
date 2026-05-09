#!/bin/bash
set -e

echo "🚀 Iniciando despliegue de Agentic RAG a Cloud Run..."

PROJECT_ID="servicios-492716"
REGION="us-central1"
IMAGE="us-central1-docker.pkg.dev/${PROJECT_ID}/agentic-rag/agentic-rag:latest"
SERVICE_NAME="agentic-rag"
BUCKET_NAME="recs-chb-seteloee"

# Obtenemos las variables del archivo .env si existe
if [ -f "project/.env" ]; then
    export $(grep -v '^#' project/.env | xargs)
fi

# Fallback API key por si no hay .env
API_KEY=${QDRANT_API_KEY:-"cf882ba35a01e29ba5a43ed853be3e3fa528c3c761a47ed03f566cb3565840cf"}

echo "📦 1/2 Construyendo la imagen de Docker..."
gcloud builds submit --tag $IMAGE --project=$PROJECT_ID

echo "☁️ 2/2 Desplegando en Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE \
  --region $REGION \
  --project $PROJECT_ID \
  --memory 4Gi \
  --cpu 4 \
  --timeout 300 \
  --min-instances 1 \
  --max-instances 5 \
  --concurrency 10 \
  --set-env-vars QDRANT_API_KEY=$API_KEY \
  --set-env-vars PARENT_STORE_PATH=/app/data/parent_store \
  --set-env-vars MARKDOWN_DIR=/app/data/markdown_docs \
  --set-env-vars ENABLE_GRADIO_UI=true \
  --set-env-vars DB_USER=${DB_USER} \
  --set-env-vars DB_PASS=${DB_PASS} \
  --set-env-vars DB_NAME=${DB_NAME} \
  --set-env-vars INSTANCE_CONNECTION_NAME=${INSTANCE_CONNECTION_NAME} \
  --set-env-vars FIREBASE_PROJECT_ID=${FIREBASE_PROJECT_ID} \
  --add-volume name=gcs-data,type=cloud-storage,bucket=$BUCKET_NAME \
  --add-volume-mount volume=gcs-data,mount-path=/app/data \
  --startup-probe httpGet.path=/health,initialDelaySeconds=5,timeoutSeconds=10,periodSeconds=10,failureThreshold=20 \
  --allow-unauthenticated

echo "✅ ¡Despliegue completado con éxito!"
