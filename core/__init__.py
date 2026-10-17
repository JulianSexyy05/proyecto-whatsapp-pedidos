"""
Módulo Core del Motor de IA para WhatsApp Pedidos.
Exporta las interfaces principales para extracción, cotización, OCR,
máquina de estados de conversación y recuperación de faltantes.
"""

from core.ia_parser import (
    extraer_pedido_whatsapp,
    ExtraccionPedido,
    ItemProducto,
    GeminiParserError,
)
from core.cotizador import (
    cotizar_pedido,
    formatear_pesos,
    ResumenCotizacion,
    ItemCotizado,
    CATALOGO_PRECIOS_BASE,
)
from core.ocr_pagos import (
    procesar_comprobante_pago,
    procesar_comprobante_pago_sync,
    ComprobantePago,
    EstadoValidacion,
    GeminiOCRError,
)
from core.fallback_handler import (
    evaluar_necesidad_fallback,
    generar_mensaje_fallback,
    generar_mensaje_fallback_sync,
    ResultadoFallback,
)
from core.conversation_state import (
    EstadoFlujo,
    SesionPedido,
    GestorConversaciones,
    gestor_conversaciones,
    OrdenSocio2,
    ItemOrdenSocio2,
)

__all__ = [
    # ia_parser
    "extraer_pedido_whatsapp",
    "ExtraccionPedido",
    "ItemProducto",
    "GeminiParserError",
    # cotizador
    "cotizar_pedido",
    "formatear_pesos",
    "ResumenCotizacion",
    "ItemCotizado",
    "CATALOGO_PRECIOS_BASE",
    # ocr_pagos
    "procesar_comprobante_pago",
    "procesar_comprobante_pago_sync",
    "ComprobantePago",
    "EstadoValidacion",
    "GeminiOCRError",
    # fallback_handler
    "evaluar_necesidad_fallback",
    "generar_mensaje_fallback",
    "generar_mensaje_fallback_sync",
    "ResultadoFallback",
    # conversation_state
    "EstadoFlujo",
    "SesionPedido",
    "GestorConversaciones",
    "gestor_conversaciones",
    "OrdenSocio2",
    "ItemOrdenSocio2",
]
