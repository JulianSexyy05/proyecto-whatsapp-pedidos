import json
import logging
import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from integrations.gemini import ask_gemini
from integrations.whatsapp import mark_message_as_read, send_whatsapp_message

# Cargar variables de entorno desde el archivo .env
load_dotenv(override=True)

# Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("whatsapp-backend")

app = FastAPI(
    title="WhatsApp Orders API",
    description="Servidor backend para gestión de pedidos y mensajería con WhatsApp Business Cloud API e Inteligencia Artificial Gemini.",
    version="1.0.0",
)


def handle_incoming_message_with_gemini(sender: str, text_body: str, msg_id: Optional[str] = None):
    """
    Tarea en segundo plano:
    1. Marca el mensaje como leído en WhatsApp (doble check azul).
    2. Envía el texto recibido a Gemini API con GEMINI_API_KEY.
    3. Reenvía la respuesta generada por Gemini al remitente vía WhatsApp Graph API.
    """
    if msg_id:
        mark_message_as_read(msg_id)

    # 1. Enviar consulta a la API oficial de Gemini
    logger.info("Enviando consulta a Gemini AI para %s...", sender)
    gemini_reply = ask_gemini(prompt=text_body)

    # 2. Reenviar la respuesta generada a la API de WhatsApp
    logger.info("Reenviando respuesta de Gemini a WhatsApp (%s)...", sender)
    api_response = send_whatsapp_message(to=sender, text=gemini_reply)
    if api_response:
        logger.info("Mensaje de Gemini entregado exitosamente a WhatsApp (%s).", sender)
    else:
        logger.error("Fallo al entregar el mensaje de WhatsApp a %s.", sender)


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
    load_dotenv(override=True)
    verify_token = os.getenv("VERIFY_TOKEN", "")

    if not verify_token:
        logger.error("VERIFY_TOKEN no está definido en el entorno.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="VERIFY_TOKEN no está configurado en el servidor",
        )

    if hub_mode == "subscribe" and hub_verify_token == verify_token:
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


@app.post(
    "/webhook/whatsapp",
    status_code=status.HTTP_200_OK,
    summary="Recepción de eventos de WhatsApp Business y respuesta con Gemini",
    tags=["WhatsApp Webhook"],
)
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint para recibir eventos y mensajes entrantes de WhatsApp en formato JSON:
    1. Extrae el número del usuario (from) y el texto (text.body).
    2. Envía la consulta a Gemini AI en segundo plano.
    3. Reenvía la respuesta a WhatsApp Graph API.
    4. Retorna HTTP 200 inmediatamente a Meta para evitar timeouts.
    """
    try:
        payload = await request.json()
    except Exception as exc:
        logger.error("Error al procesar el cuerpo JSON de la petición: %s", exc)
        return {"status": "error", "message": "JSON inválido"}

    try:
        entries = payload.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                
                # Mapeo de nombres de contactos
                contacts = {
                    c.get("wa_id"): c.get("profile", {}).get("name")
                    for c in value.get("contacts", [])
                }

                messages = value.get("messages", [])
                for msg in messages:
                    sender = msg.get("from")  # Número de teléfono del usuario
                    msg_id = msg.get("id")
                    msg_type = msg.get("type")
                    sender_name = contacts.get(sender, "Cliente")
                    
                    text_body = ""
                    if msg_type == "text":
                        text_body = msg.get("text", {}).get("body", "")
                    elif msg_type == "interactive":
                        interactive = msg.get("interactive", {})
                        text_body = (
                            interactive.get("button_reply", {}).get("title")
                            or interactive.get("list_reply", {}).get("title", "")
                        )
                    else:
                        text_body = f"[{msg_type.upper()}]"

                    # 1. Impresión visual destacada en consola
                    print("\n" + "=" * 60)
                    print("📩 [WHATSAPP WEBHOOK] Mensaje recibido:")
                    print(f"👤 Remitente : {sender_name} ({sender})")
                    print(f"💬 Texto      : {text_body}")
                    print(f"🆔 Message ID : {msg_id}")
                    print(f"📦 Tipo       : {msg_type}")
                    print("🤖 Procesando respuesta con Gemini AI...")
                    print("=" * 60 + "\n")

                    logger.info(
                        "Mensaje procesado -> Remitente: %s (%s) | Texto: %s",
                        sender_name,
                        sender,
                        text_body,
                    )

                    # 2. Encolar tarea de consulta a Gemini y respuesta a WhatsApp
                    if sender and text_body:
                        background_tasks.add_task(
                            handle_incoming_message_with_gemini,
                            sender=sender,
                            text_body=text_body,
                            msg_id=msg_id,
                        )
                        logger.info("Tarea de respuesta con Gemini encolada en segundo plano para %s", sender)

    except Exception as err:
        logger.warning("Error durante la extracción o procesamiento del mensaje: %s", err)

    # Meta requiere responder 200 OK inmediatamente
    return {"status": "EVENT_RECEIVED"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
