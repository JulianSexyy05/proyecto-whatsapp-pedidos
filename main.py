import json
import logging
import os
from typing import Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("whatsapp-backend")

# Token de verificación configurado para Meta Webhook
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "mi_token_secreto_whatsapp")

# Configuración de Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
gemini_client = None
if GEMINI_API_KEY:
    try:
        from google import genai
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("Cliente Gemini inicializado correctamente (modelo: %s)", GEMINI_MODEL)
    except Exception as e:
        logger.error("Error inicializando cliente Gemini: %s", e)
        gemini_client = None
else:
    logger.warning("GEMINI_API_KEY no está configurado. La integración con Gemini no funcionará.")

# Configuración de WhatsApp Business Cloud API
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v21.0")
WHATSAPP_API_URL = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{WHATSAPP_PHONE_ID}/messages" if WHATSAPP_PHONE_ID else None

app = FastAPI(
    title="WhatsApp Orders API",
    description="Servidor backend para gestión de pedidos y mensajería con WhatsApp Business Cloud API.",
    version="1.0.0",
)


@app.get("/", summary="Health Check", tags=["General"])
def read_root():
    """Endpoint básico de salud del servicio."""
    return {"status": "ok", "app": "WhatsApp Orders API", "version": "1.0.0"}


@app.get(
    "/webhook/whatsapp",
    response_class=PlainTextResponse,
    summary="Verificación del Webhook de Meta",
    tags=["WhatsApp Webhook"],
)
def verify_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """
    Endpoint para responder al reto (challenge) de verificación de Meta for Developers.

    Meta envía:
    - hub.mode: Debe ser 'subscribe'.
    - hub.verify_token: Token secreto configurado en el panel de Meta.
    - hub.challenge: Cadena alfanumérica que se debe retornar tal cual en texto plano.
    """
    if not VERIFY_TOKEN:
        logger.error("VERIFY_TOKEN no está definido en el entorno.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="VERIFY_TOKEN no está configurado en el servidor",
        )

    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        logger.info("Verificación exitosa del Webhook de WhatsApp.")
        return PlainTextResponse(content=hub_challenge or "", status_code=status.HTTP_200_OK)

    logger.warning(
        "Fallo de autenticación en Webhook: hub.mode=%s, hub.verify_token=%s",
        hub_mode,
        hub_verify_token,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Token de verificación incorrecto o modo inválido",
    )


async def send_whatsapp_message(to: str, text: str) -> dict:
    """
    Envía un mensaje de texto a través de la WhatsApp Business Cloud API.
    """
    if not WHATSAPP_TOKEN or not WHATSAPP_API_URL:
        logger.error("WHATSAPP_TOKEN o WHATSAPP_PHONE_ID no están configurados.")
        return {"error": "Configuración de WhatsApp incompleta"}

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }

    try:
        response = requests.post(WHATSAPP_API_URL, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Mensaje enviado exitosamente a %s: %s", to, response.json())
        return response.json()
    except requests.RequestException as e:
        logger.error("Error enviando mensaje a WhatsApp: %s", e)
        if hasattr(e, 'response') and e.response is not None:
            logger.error("Respuesta de error: %s", e.response.text)
        return {"error": str(e)}


async def get_gemini_response(user_message: str) -> str:
    """
    Envía el mensaje del usuario a Gemini y retorna la respuesta.
    """
    if not gemini_client:
        return "Lo siento, la integración con Gemini no está configurada correctamente."

    try:
        # Contexto del sistema para el bot de pedidos
        system_prompt = (
            "Eres un asistente virtual para una tienda de comida. "
            "Responde de forma amable y concisa en español. "
            "Ayuda al cliente con sus pedidos, consultas del menú, precios y horarios."
        )

        # Enviar mensaje a Gemini usando el cliente oficial google-genai
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=f"{system_prompt}\n\nUsuario: {user_message}",
        )

        return response.text.strip() if response.text else "Lo siento, no pude generar una respuesta."
    except Exception as e:
        logger.error("Error obteniendo respuesta de Gemini: %s", e)
        return "Lo siento, hubo un error procesando tu mensaje. Intenta de nuevo más tarde."


@app.post(
    "/webhook/whatsapp",
    status_code=status.HTTP_200_OK,
    summary="Recepción de eventos de WhatsApp Business",
    tags=["WhatsApp Webhook"],
)
async def receive_webhook(request: Request):
    """
    Endpoint para recibir eventos y mensajes entrantes de WhatsApp en formato JSON.
    Procesa el mensaje, consulta a Gemini y responde al usuario.
    """
    try:
        payload = await request.json()
    except Exception as exc:
        logger.error("Error al procesar el cuerpo JSON de la petición: %s", exc)
        return {"status": "error", "message": "JSON inválido"}

    # Registrar el payload completo para depuración
    logger.info(
        "Payload entrante:\n%s",
        json.dumps(payload, indent=2, ensure_ascii=True),
    )

    # Registro y parsing de alto nivel del mensaje
    try:
        entries = payload.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                val = change.get("value", {})
                messages = val.get("messages", [])
                for msg in messages:
                    sender = msg.get("from")
                    msg_type = msg.get("type")
                    text_content = (
                        msg.get("text", {}).get("body") if msg_type == "text" else None
                    )
                    logger.info(
                        "Mensaje recibido de: %s | Tipo: %s | Contenido: %s",
                        sender,
                        msg_type,
                        text_content,
                    )

                    # Procesar solo mensajes de texto
                    if msg_type == "text" and text_content and sender:
                        # Obtener respuesta de Gemini
                        logger.info("Enviando mensaje a Gemini: %s", text_content)
                        gemini_response = await get_gemini_response(text_content)
                        logger.info("Respuesta de Gemini: %s", gemini_response)

                        # Enviar respuesta por WhatsApp
                        await send_whatsapp_message(sender, gemini_response)
    except Exception as err:
        logger.warning("Error extrayendo datos del payload de WhatsApp: %s", err)

    # Meta requiere responder 200 OK rápidamente
    return {"status": "EVENT_RECEIVED"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)