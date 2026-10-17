import json
import logging
import os
from typing import Optional

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


@app.post(
    "/webhook/whatsapp",
    status_code=status.HTTP_200_OK,
    summary="Recepción de eventos de WhatsApp Business",
    tags=["WhatsApp Webhook"],
)
async def receive_webhook(request: Request):
    """
    Endpoint para recibir eventos y mensajes entrantes de WhatsApp en formato JSON.
    Imprime en consola el contenido recibido y retorna HTTP 200 inmediatamente
    para evitar reintentos automáticos de Meta.
    """
    try:
        payload = await request.json()
    except Exception as exc:
        logger.error("Error al procesar el cuerpo JSON de la petición: %s", exc)
        return {"status": "error", "message": "JSON inválido"}

    # Imprimir en consola con formato JSON legible
    print("\n" + "=" * 60)
    print("📩 [WHATSAPP WEBHOOK] Mensaje/Evento entrante recibido:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("=" * 60 + "\n")

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
    except Exception as err:
        logger.warning("Error extrayendo datos del payload de WhatsApp: %s", err)

    # Meta requiere responder 200 OK rápidamente
    return {"status": "EVENT_RECEIVED"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
