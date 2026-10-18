import logging
import os
from typing import Any, Dict, Optional
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("whatsapp-service")

GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v18.0")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")


def get_headers() -> Dict[str, str]:
    """Genera las cabeceras requeridas para autenticarse con Meta Graph API."""
    load_dotenv(override=True)
    token = os.getenv("WHATSAPP_TOKEN", WHATSAPP_TOKEN)
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def send_whatsapp_message(to: str, text: str) -> Optional[Dict[str, Any]]:
    """
    Envía un mensaje de texto a un usuario a través de la API oficial de WhatsApp Cloud.

    :param to: Número de teléfono destinatario en formato internacional (sin el signo +). Ej: '573001234567'
    :param text: Contenido del mensaje de texto a enviar.
    :return: Respuesta JSON de Meta o None si ocurrió un error.
    """
    phone_id = os.getenv("WHATSAPP_PHONE_ID", WHATSAPP_PHONE_ID)
    token = os.getenv("WHATSAPP_TOKEN", WHATSAPP_TOKEN)

    if not phone_id or not token:
        logger.error(
            "Faltan credenciales: WHATSAPP_PHONE_ID o WHATSAPP_TOKEN no están configurados en el entorno."
        )
        return None

    version = os.getenv("GRAPH_API_VERSION", "v18.0")
    url = f"https://graph.facebook.com/{version}/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": text,
        },
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=get_headers(),
            timeout=10,
        )
        data = response.json()

        if response.status_code == 200:
            logger.info("Mensaje enviado exitosamente a %s. Response: %s", to, data)
            return data
        else:
            logger.error(
                "Error de Meta API al enviar mensaje a %s. Status: %s. Detalle: %s",
                to,
                response.status_code,
                data,
            )
            return data
    except requests.RequestException as exc:
        logger.error("Excepción de red al enviar mensaje de WhatsApp a %s: %s", to, exc)
        return None


def mark_message_as_read(message_id: str) -> bool:
    """
    Marca un mensaje entrante como leído en WhatsApp (doble check azul).
    """
    phone_id = os.getenv("WHATSAPP_PHONE_ID", WHATSAPP_PHONE_ID)
    if not phone_id or not message_id:
        return False

    version = os.getenv("GRAPH_API_VERSION", "v18.0")
    url = f"https://graph.facebook.com/{version}/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=get_headers(),
            timeout=5,
        )
        return response.status_code == 200
    except requests.RequestException as exc:
        logger.warning("No se pudo marcar el mensaje %s como leído: %s", message_id, exc)
        return False
