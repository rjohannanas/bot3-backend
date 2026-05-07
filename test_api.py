import os
import json
import requests
from dotenv import load_dotenv

# Cargar la API key desde el .env
load_dotenv("project/.env")
API_KEY = os.environ.get("FIREBASE_API_KEY")

print("1. 🔑 Autenticándose en Firebase (Modo Anónimo)...")
auth_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={API_KEY}"
resp = requests.post(auth_url, json={"returnSecureToken": True})
token_data = resp.json()

id_token = token_data.get("idToken")
if not id_token:
    print("❌ Error al obtener token:", token_data)
    exit(1)

print("✅ Token obtenido con éxito.")
print("2. 🚀 Enviando petición al backend en CLOUD RUN (/api/chat/stream)...\n")

headers = {
    "Authorization": f"Bearer {id_token}",
    "Content-Type": "application/json"
}

payload = {
    "session_id": "sesion_cloud_run_1",
    "message": "Hola agente, ¿estás vivo en Cloud Run?"
}

try:
    # Apuntamos a la URL real de Cloud Run y al endpoint de STREAMING
    api_url = "https://agentic-rag-800690522557.us-central1.run.app/api/chat/stream"
    
    print("🤖 Recibiendo Streaming (Fase 2)...\n")
    
    with requests.post(api_url, headers=headers, json=payload, stream=True) as chat_resp:
        for line in chat_resp.iter_lines():
            if not line: continue
            
            decoded = line.decode('utf-8')
            # DEBUG: Imprimir la línea cruda para ver qué llega
            # print(f"DEBUG RECV: {decoded[:50]}...") 
            
            if decoded.startswith("data: [DONE]"): 
                print("\n🏁 Streaming finalizado por el servidor.")
                break
            
            if decoded.startswith("data: "):
                try:
                    content_json = decoded[6:].strip()
                    data = json.loads(content_json)
                    
                    event_type = data.get("type")
                    if event_type == "status":
                        print(f"\n⏳ [{data.get('message', 'Procesando...')}]")
                    elif event_type == "sources":
                        print(f"\n📚 Fuentes consultadas: {len(data.get('docs', []))}")
                    elif event_type == "token":
                        # Solo imprimimos el nuevo token sin saltos de línea
                        print(data.get("content", ""), end="", flush=True)
                        
                except Exception as e:
                    print(f"\n⚠️ Error parseando JSON: {e}")
                    continue
                
    print("\n\n✅ ¡Prueba completada!")
    
except Exception as e:
    print(f"❌ Error general: {e}")
