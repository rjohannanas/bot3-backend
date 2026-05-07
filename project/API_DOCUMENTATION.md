# Documentación de la API (Agentic RAG)

Esta documentación está dirigida a los desarrolladores Frontend (React, Vue, Next.js, etc.) que necesiten integrarse con el backend de Inteligencia Artificial.

## 1. URLs Base y Swagger
- **Producción:** `https://agentic-rag-800690522557.us-central1.run.app`
- **Swagger / OpenAPI UI:** `https://agentic-rag-800690522557.us-central1.run.app/docs` (Contiene todos los esquemas técnicos y tipos de datos de Pydantic).

## 2. Seguridad y Autenticación (Firebase)
El backend está protegido mediante verificación JWT. No se aceptarán peticiones sin token.
1. Instala el SDK de Firebase en tu frontend (`npm install firebase`).
2. Una vez que el usuario inicie sesión (ya sea con Email, Google, o auth Anónima), obtén su token:
   ```javascript
   const idToken = await firebase.auth().currentUser.getIdToken(true);
   ```
3. Todas las peticiones al backend deben incluir la cabecera:
   `Authorization: Bearer <ID_TOKEN>`

## 3. Endpoint de Streaming SSE (RECOMENDADO ⭐)

Este es el endpoint principal para chatear. Devuelve la respuesta en tiempo real (Server-Sent Events) para lograr el "efecto máquina de escribir" y reducir la latencia percibida.

- **URL:** `POST /api/chat/stream`
- **Headers:**
  ```json
  {
    "Authorization": "Bearer <ID_TOKEN>",
    "Content-Type": "application/json"
  }
  ```
- **Body:**
  ```json
  {
      "session_id": "uuid-o-id-unico-de-chat",
      "message": "¿Qué dice el contrato sobre vacaciones?"
  }
  ```

### Ejemplo de Consumo Real en JS/TS (Fetch API)

Al recibir la respuesta del servidor, llegarán paquetes de texto en formato `data: <JSON>\n\n`. Existen tres tipos de eventos (`type`) que debes manejar: `status` (lo que está pensando el agente), `sources` (los documentos que leyó), y `token` (la respuesta final letra por letra).

```javascript
async function sendChatMessage(message, sessionId, idToken) {
  const response = await fetch('https://agentic-rag-800690522557.us-central1.run.app/api/chat/stream', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${idToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ session_id: sessionId, message: message })
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    // Decodificar el bloque de bytes a texto
    const chunk = decoder.decode(value, { stream: true });
    const lines = chunk.split('\n');

    for (const line of lines) {
      if (line.startsWith('data: [DONE]')) {
        console.log("Transmisión finalizada");
        return;
      }
      
      if (line.startsWith('data: ')) {
        const jsonStr = line.substring(6).trim();
        if (!jsonStr) continue;
        
        try {
          const data = JSON.parse(jsonStr);
          
          if (data.type === 'status') {
            // EJ: Mostrar un spinner que diga "Analizando consulta..."
            console.log('⏳ Estado:', data.message); 
            
          } else if (data.type === 'sources') {
            // EJ: Mostrar links a los documentos PDF referenciados
            console.log('📚 Fuentes:', data.docs); 
            
          } else if (data.type === 'token') {
            // EJ: Concatenar la letra al globo de texto del chat
            console.log('Letra:', data.content); 
          }
        } catch (e) {
          console.error("Error parseando chunk SSE:", e);
        }
      }
    }
  }
}
```

## 4. Endpoint Bloqueante (Alternativa simple)
Si no deseas implementar streaming (por ejemplo, para bots de Slack o llamadas de servidor a servidor), puedes usar el endpoint clásico que espera a que el agente termine (puede tardar 10-15s).
- **URL:** `POST /api/chat`
- **Body:** Igual que el anterior.
- **Respuesta:**
  ```json
  {
      "response": "El contrato estipula que..."
  }
  ```

## 5. Notas sobre Persistencia
No envíes el historial completo de la conversación en cada request. Solo envía la nueva pregunta y el `session_id`. El backend se encarga automáticamente de recuperar la memoria del chat utilizando PostgreSQL, validando que la sesión pertenezca al UID del usuario autenticado.
