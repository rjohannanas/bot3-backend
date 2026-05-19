# scripts/etl_normas_to_rag.py
"""
ETL: PostgreSQL (normas) → API RAG con metadata enriquecida.
Usa cursor en DB para sincronización incremental.
"""
import os
import json
import tempfile
import shutil
import requests
import psycopg2
from pathlib import Path
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────────────────
DB_HOST  = os.environ["DB_HOST"]
DB_NAME  = os.environ["DB_NAME"]
DB_USER  = os.environ["DB_USER"]
DB_PASS  = os.environ["DB_PASS"]
DB_PORT  = os.environ.get("DB_PORT", "5432")

API_URL  = os.environ.get("API_URL", "http://localhost:8080/api/documents/upload")
API_KEY  = os.environ["ADMIN_API_KEY"]

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "20"))

# ── Cursor de sincronización ────────────────────────────────────────────────
# Tabla mínima para guardar hasta dónde llegamos (crear una vez):
# CREATE TABLE IF NOT EXISTS rag_sync_cursor (
#     id SERIAL PRIMARY KEY,
#     last_op VARCHAR(100),
#     last_run TIMESTAMP DEFAULT NOW()
# );
CURSOR_TABLE = "rag_sync_cursor"

def get_last_cursor(cur):
    cur.execute(f"SELECT last_op FROM {CURSOR_TABLE} ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    return row[0] if row else None

def save_cursor(cur, last_op):
    cur.execute(
        f"INSERT INTO {CURSOR_TABLE} (last_op, last_run) VALUES (%s, %s)",
        (last_op, datetime.utcnow())
    )

# ── Extracción ───────────────────────────────────────────────────────────────
def fetch_normas(cur, last_op):
    if last_op:
        cur.execute("""
            SELECT n.op, n.texto_completo, n.url_pdf, n.url_web,
                   n.tipo_dispositivo, n.fecha_publicacion, n.fuente,
                   e.codigo_peruano AS entidad_id, e.nombre AS entidad_nombre
            FROM normas n
            JOIN entidades e ON e.codigo_peruano = n.entidad_id
            WHERE n.op > %s
              AND n.texto_completo IS NOT NULL
              AND n.texto_completo != ''
            ORDER BY n.op
            LIMIT %s
        """, (last_op, BATCH_SIZE))
    else:
        cur.execute("""
            SELECT n.op, n.texto_completo, n.url_pdf, n.url_web,
                   n.tipo_dispositivo, n.fecha_publicacion, n.fuente,
                   e.codigo_peruano AS entidad_id, e.nombre AS entidad_nombre
            FROM normas n
            JOIN entidades e ON e.codigo_peruano = n.entidad_id
            WHERE n.texto_completo IS NOT NULL
              AND n.texto_completo != ''
            ORDER BY n.op
            LIMIT %s
        """, (BATCH_SIZE,))
    
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]

# ── Carga ────────────────────────────────────────────────────────────────────
def ingest_batch(normas):
    temp_dir = Path(tempfile.mkdtemp())
    files_payload = []
    metadata_dict = {}

    try:
        for norma in normas:
            file_name = f"{norma['op']}.md"
            file_path = temp_dir / file_name

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(norma["texto_completo"])

            # Metadata enriquecida — llega a Qdrant como filtros
            metadata_dict[file_name] = {
                "source_url": norma["url_web"] or norma["url_pdf"] or norma["op"],
                "entidad_id": norma["entidad_id"],
                "entidad_nombre": norma["entidad_nombre"],
                "tipo_dispositivo": norma["tipo_dispositivo"] or "Desconocido",
                "fecha_publicacion": str(norma["fecha_publicacion"]) if norma["fecha_publicacion"] else None,
                "fuente": norma["fuente"] or "desconocida",
                "op": norma["op"],
            }

        for file_path in temp_dir.glob("*.md"):
            files_payload.append(
                ("files", (file_path.name, open(file_path, "rb"), "text/markdown"))
            )

        response = requests.post(
            API_URL,
            files=files_payload,
            data={"metadata_urls": json.dumps(metadata_dict)},
            headers={"x-api-key": API_KEY},
            timeout=120,
        )

        if response.status_code == 200:
            print(f"✅ Batch OK: {response.json()['stats']}")
            return True
        else:
            print(f"❌ Error API ({response.status_code}): {response.text}")
            return False

    finally:
        for _, ft in files_payload:
            ft[1].close()
        shutil.rmtree(temp_dir)

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    conn = psycopg2.connect(
        host=DB_HOST, database=DB_NAME,
        user=DB_USER, password=DB_PASS, port=DB_PORT
    )
    conn.autocommit = False
    cur = conn.cursor()

    try:
        last_op = get_last_cursor(cur)
        print(f"▶ Iniciando desde op='{last_op or 'inicio'}'")

        normas = fetch_normas(cur, last_op)
        if not normas:
            print("ℹ️  No hay normas nuevas para ingestar.")
            return

        print(f"📦 {len(normas)} normas encontradas, enviando a RAG...")
        success = ingest_batch(normas)

        if success:
            save_cursor(cur, normas[-1]["op"])
            conn.commit()
            print(f"💾 Cursor actualizado → op='{normas[-1]['op']}'")
        else:
            conn.rollback()
            print("⚠️  Cursor NO actualizado por error en API.")

    except Exception as e:
        conn.rollback()
        print(f"❌ Error fatal: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
