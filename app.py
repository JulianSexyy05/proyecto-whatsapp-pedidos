"""
Servidor FastAPI para el Motor de IA de Pedidos por WhatsApp.
Expone endpoints para recepción de webhooks, extracción directa y OCR de pagos.
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from core import (
    extraer_pedido_whatsapp,
    cotizar_pedido,
    procesar_comprobante_pago,
    generar_respuesta_fallback,
    gestor_conversaciones,
    EstadoFlujo,
    ExtraccionPedido,
    ResumenCotizacion,
    ComprobantePago,
    OrdenSocio2,
    GeminiParserError,
    GeminiOCRError,
)

app = FastAPI(
    title="WhatsApp Pedidos IA Engine API",
    description="Backend asíncrono para atención, cotización, OCR y gestión de pedidos de WhatsApp con Gemini API.",
    version="1.0.0"
)


# =====================================================================
# Modelos Pydantic de Request y Response
# =====================================================================

class WebhookWhatsAppRequest(BaseModel):
    chat_id: str = Field(description="Identificador o número de teléfono de WhatsApp del remitente")
    mensaje_texto: str = Field(description="Contenido textual del mensaje recibido")


class WebhookWhatsAppResponse(BaseModel):
    chat_id: str
    estado_actual: str
    respuesta_whatsapp: str
    orden_confirmada: Optional[OrdenSocio2] = None


class ExtraccionRequest(BaseModel):
    chat_text: str = Field(description="Transcripción de la conversación para analizar")


class ExtraccionResponse(BaseModel):
    pedido_extraido: ExtraccionPedido
    cotizacion: Optional[ResumenCotizacion] = None


# =====================================================================
# Endpoints de la API
# =====================================================================

@app.get("/", tags=["Health"])
async def root():
    return {
        "status": "online",
        "service": "WhatsApp Pedidos IA Engine",
        "docs": "/docs"
    }


@app.post(
    "/webhook/whatsapp",
    response_model=WebhookWhatsAppResponse,
    summary="Webhook principal para mensajes de WhatsApp",
    tags=["WhatsApp"]
)
async def webhook_whatsapp(payload: WebhookWhatsAppRequest):
    """
    Recibe un mensaje de WhatsApp, extrae la información con Gemini,
    evalúa si se requiere fallback persuasivo, actualiza la máquina de estados
    y, si la orden se completa, emite el payload listo para el Socio 2.
    """
    try:
        # 1. Extracción con Gemini 2.5 Flash
        extraccion = await extraer_pedido_whatsapp(payload.mensaje_texto)
    except GeminiParserError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Fallo en el motor de IA: {e}"
        )

    # 2. Evaluación de Fallback si faltan datos o hay baja confianza
    fallback = await generar_respuesta_fallback(
        extraccion=extraccion,
        chat_reciente=payload.mensaje_texto
    )

    # 3. Actualización de la máquina de estados conversacional
    estado, respuesta_maquina = gestor_conversaciones.procesar_extraccion(
        chat_id=payload.chat_id,
        extraccion=extraccion,
        mensaje_original=payload.mensaje_texto
    )

    # Si hay fallback prioritario y el estado aún no está completado,
    # utilizamos la respuesta persuasiva formulada por Gemini
    if fallback.necesita_fallback and estado != EstadoFlujo.COMPLETADO:
        mensaje_a_enviar = fallback.mensaje_whatsapp
    else:
        mensaje_a_enviar = respuesta_maquina

    # 4. Verificación de Cierre de Venta para el Socio 2
    orden_socio2 = None
    if estado == EstadoFlujo.COMPLETADO:
        sesion = gestor_conversaciones.obtener_o_crear_sesion(payload.chat_id)
        orden_socio2 = sesion.generar_orden_socio2()

    return WebhookWhatsAppResponse(
        chat_id=payload.chat_id,
        estado_actual=estado.value,
        respuesta_whatsapp=mensaje_a_enviar,
        orden_confirmada=orden_socio2
    )


@app.post(
    "/api/pedidos/extraer",
    response_model=ExtraccionResponse,
    summary="Extracción estructurada y cotización directa",
    tags=["Pedidos"]
)
async def api_extraer_pedido(payload: ExtraccionRequest):
    """Extrae datos estructurados de un chat y calcula la cotización si hay productos."""
    try:
        extraccion = await extraer_pedido_whatsapp(payload.chat_text)
    except GeminiParserError as e:
        raise HTTPException(status_code=502, detail=str(e))

    cotizacion = None
    if extraccion.productos:
        cotizacion = cotizar_pedido(extraccion)

    return ExtraccionResponse(
        pedido_extraido=extraccion,
        cotizacion=cotizacion
    )


@app.post(
    "/api/pagos/validar-comprobante",
    response_model=ComprobantePago,
    summary="OCR multimodal de comprobantes bancarios",
    tags=["Pagos"]
)
async def api_validar_comprobante(
    file: UploadFile = File(..., description="Imagen del comprobante (JPEG, PNG o WEBP)")
):
    """
    Procesa una imagen de comprobante bancario (Nequi, Daviplata, Bancolombia, etc.)
    mediante OCR con Gemini 2.5 Flash y valida monto, referencia y autenticidad.
    """
    if not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo proporcionado debe ser una imagen válida."
        )

    try:
        contenido_bytes = await file.read()
        resultado_ocr = await procesar_comprobante_pago(
            origen_imagen=contenido_bytes,
            mime_type=file.content_type
        )
        return resultado_ocr
    except GeminiOCRError as e:
        raise HTTPException(status_code=502, detail=f"Error en OCR de pago: {e}")
    finally:
        await file.close()


@app.get(
    "/api/sesiones/{chat_id}",
    summary="Consultar estado de sesión activa de un cliente",
    tags=["Sesiones"]
)
async def consultar_sesion(chat_id: str):
    """Obtiene el estado actual y los productos acumulados de un chat de WhatsApp."""
    sesion = gestor_conversaciones.obtener_o_crear_sesion(chat_id)
    return {
        "chat_id": sesion.chat_id,
        "estado": sesion.estado.value,
        "cliente": sesion.nombre_cliente,
        "productos": [p.model_dump() for p in sesion.productos],
        "direccion": sesion.direccion_entrega,
        "metodo_pago": sesion.metodo_pago,
        "total_a_pagar": sesion.resumen_cotizacion.total_a_pagar if sesion.resumen_cotizacion else 0.0
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
