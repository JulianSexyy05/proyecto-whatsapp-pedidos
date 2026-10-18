import logging
import os
from typing import Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(override=True)
logger = logging.getLogger("gemini-service")

SYSTEM_INSTRUCTION = (
    "Eres un asistente virtual cordial, profesional y eficiente para un negocio de pedidos por WhatsApp. "
    "Responde a los mensajes de los clientes de manera concisa, clara y orientada a brindar soporte sobre productos, "
    "pedidos y medios de pago. Mantén las respuestas breves y legibles para WhatsApp (sin Markdown complejo)."
)


def get_gemini_client() -> Optional[genai.Client]:
    """Obtiene una instancia del cliente de Google GenAI con la API Key del entorno."""
    load_dotenv(override=True)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY no está configurada en las variables de entorno.")
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception as exc:
        logger.error("Error al inicializar el cliente de Gemini: %s", exc)
        return None


def ask_gemini(prompt: str, system_instruction: Optional[str] = None) -> str:
    """
    Envía una consulta al modelo Gemini y retorna el texto de la respuesta generada.

    :param prompt: Mensaje o texto recibido del usuario.
    :param system_instruction: Instrucciones de contexto del sistema (opcional).
    :return: Texto de la respuesta generada por Gemini o mensaje amigable de contingencia.
    """
    client = get_gemini_client()
    if not client:
        return (
            "¡Hola! Hemos recibido tu mensaje. Actualmente nuestro sistema de asistencia inteligente "
            "se encuentra en configuración. En breve un asesor humano se comunicará contigo."
        )

    primary_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    fallback_models = [primary_model, "gemini-3.1-flash-lite", "gemini-flash-latest"]
    # Eliminar duplicados manteniendo orden
    models_to_try = list(dict.fromkeys(fallback_models))
    instruction = system_instruction or SYSTEM_INSTRUCTION

    last_error = None
    for model_name in models_to_try:
        try:
            logger.info("Enviando mensaje a Gemini (%s): '%s'", model_name, prompt)
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=instruction,
                    temperature=0.7,
                ),
            )

            if response and response.text:
                cleaned_text = response.text.strip()
                logger.info("Respuesta obtenida de Gemini (%s): '%s'", model_name, cleaned_text)
                return cleaned_text

            logger.warning("Gemini (%s) retornó una respuesta vacía.", model_name)
        except Exception as exc:
            last_error = exc
            logger.warning("Fallo temporal con modelo %s: %s. Probando siguiente modelo si está disponible...", model_name, exc)

    logger.error("Todos los modelos de Gemini fallaron. Último error: %s", last_error)
    return "Disculpa, tuvimos un inconveniente temporal procesando tu mensaje. Un asesor te responderá pronto."
