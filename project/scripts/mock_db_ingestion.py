import os
import tempfile
import requests
import psycopg2
from pathlib import Path

# ==========================================
# CONFIGURACIÓN (Variables de entorno recomendadas)
# ==========================================
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_NAME = os.environ.get("DB_NAME", "postgres")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASS = os.environ.get("DB_PASS", "password")
DB_PORT = os.environ.get("DB_PORT", "5432")

# Tu API de RAG
API_URL = os.environ.get("API_URL", "http://localhost:8080/api/documents/upload")
API_KEY = os.environ.get("ADMIN_API_KEY", "tu_api_key_secreta")  # Asegúrate de poner la real

# ==========================================
# 1. EXTRACCIÓN (EXTRACT)
# ==========================================
def fetch_normas_from_db():
    """
    Se conecta a PostgreSQL y obtiene los datos.
    Si hay error de conexión, devuelve un MOCK para pruebas.
    """
    print(f"Intentando conectar a PostgreSQL en {DB_HOST}...")
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            port=DB_PORT
        )
        cur = conn.cursor()
        # Ajusta esta query a los nombres reales de tu tabla y columnas
        cur.execute("SELECT id, url_pdf, texto_completo FROM normas LIMIT 10")
        rows = cur.fetchall()
        
        normas = []
        for row in rows:
            normas.append({
                "id": str(row[0]),
                "url_pdf": str(row[1]),
                "texto_completo": str(row[2])
            })
            
        cur.close()
        conn.close()
        return normas

    except psycopg2.Error as e:
        print(f"⚠️ No se pudo conectar a PostgreSQL (¿credenciales incorrectas?): {e}")
        print("Cargando datos MOCK de prueba...\n")
        return [
            {
                "id": "norma_mock_001",
                "url_pdf": "https://storage.googleapis.com/tu-bucket/norma_001.pdf",
                "texto_completo": "# Norma Simulada 1\n\nTexto de prueba extraído desde DB."
            },
            {
                "id": "norma_mock_002",
                "url_pdf": "https://storage.googleapis.com/tu-bucket/norma_002.pdf",
                "texto_completo": "# Norma Simulada 2\n\nRegulaciones ambientales 2026."
            }
        ]

# ==========================================
# 2. TRANSFORMACIÓN & CARGA (TRANSFORM & LOAD)
# ==========================================
def ingest_to_api(normas):
    if not normas:
        print("No hay normas para ingestar.")
        return

    print(f"Preparando {len(normas)} normas para enviar a la API...")
    temp_dir = Path(tempfile.mkdtemp())
    
    try:
        archivos_generados = []
        metadata_dict = {}
        
        # Transformación: DB -> Markdown temporal
        for norma in normas:
            file_name = f"{norma['id']}.md"
            file_path = temp_dir / file_name
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(norma['texto_completo'])
                
            archivos_generados.append(str(file_path))
            # Asociamos el nombre del archivo con su URL real
            metadata_dict[file_name] = norma['url_pdf']
            print(f"  -> Archivo generado: {file_name}")

        # Carga: Enviar por POST multipart a tu API
        print(f"\nEnviando archivos a {API_URL}...")
        
        files_payload = []
        for file_path in archivos_generados:
            files_payload.append(
                ('files', (Path(file_path).name, open(file_path, 'rb'), 'text/markdown'))
            )
            
        headers = {
            "x-api-key": API_KEY
        }
        
        import json
        
        # Hacemos la petición a tu proyecto `agentic-rag`
        try:
            data_payload = {
                "metadata_urls": json.dumps(metadata_dict)
            }
            response = requests.post(API_URL, files=files_payload, data=data_payload, headers=headers)
            if response.status_code == 200:
                print("✅ ¡Subida exitosa!")
                print(response.json())
            else:
                print(f"❌ Error en la subida (Status {response.status_code}):")
                print(response.text)
        except requests.exceptions.ConnectionError:
            print(f"❌ Error: No se pudo conectar a la API en {API_URL}.")
            print("¿Está corriendo el servidor FastAPI (uvicorn server:app)?")

    finally:
        # Cerramos los buffers abiertos y limpiamos
        for _, file_tuple in files_payload:
            file_tuple[1].close() # cerramos el open()
            
        import shutil
        shutil.rmtree(temp_dir)
        print("\n🧹 Limpieza temporal completada.")

# ==========================================
# EJECUCIÓN PRINCIPAL
# ==========================================
if __name__ == "__main__":
    datos_db = fetch_normas_from_db()
    ingest_to_api(datos_db)
