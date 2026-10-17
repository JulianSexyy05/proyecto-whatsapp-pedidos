"""
Módulo de Extracción de Pedidos de WhatsApp con Gemini API y Pydantic.
Implementado con el SDK oficial Google GenAI (`google-genai`).
"""

import os
import json
import asyncio
from typing import List, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types


# =====================================================================
# 1. Esquema Validado con Pydantic
# =====================================================================

class ItemProducto(BaseModel):
    nombre: str = Field(
        description="Nombre o descripción clara del producto pedido por el cliente"
    )
    cantidad: int = Field(
        description="Cantidad de unidades del producto. Debe ser un entero positivo mayor o igual a 1",
        ge=1,
        default=1
    )


class ExtraccionPedido(BaseModel):
    nombre_cliente: Optional[str] = Field(
        description="Nombre del cliente que realiza el pedido, si se menciona en el chat",
        default=None
    )
    productos: List[ItemProducto] = Field(
        description="Lista de productos solicitados con sus cantidades definitivas",
        default_factory=list
    )
    direccion_entrega: Optional[str] = Field(
        description="Dirección física completa para el despacho (incluye calle, carrera, número, barrio, apto o referencias)",
        default=None
    )
    metodo_pago: Optional[str] = Field(
        description="Método de pago preferido indicado por el cliente (ej. Efectivo, Nequi, Daviplata, Tarjeta, Transferencia)",
        default=None
    )
    confianza_extraccion: float = Field(
        description="Indicador numérico de confianza de la extracción entre 0.0 (muy baja certeza / ambiguo) y 1.0 (certeza total y completa)",
        ge=0.0,
        le=1.0,
        default=1.0
    )


# =====================================================================
# 2. Instrucciones del Sistema para el Modelo
# =====================================================================

SYSTEM_PROMPT = """
Eres un Asistente Experto en procesamiento y extracción estructurada de pedidos comerciales provenientes de chats de WhatsApp.
Tu misión es interpretar la conversación (incluso con lenguaje coloquial, abreviaturas, mensajes múltiples o correcciones) y extraer la información en formato JSON según el esquema especificado.

Instrucciones clave:
1. Nombre del cliente: Identifica el nombre de quien hace el pedido.
2. Productos y Cantidades: Identifica el pedido definitivo. Si el cliente modifica o cancela un producto durante la charla, consolida el pedido final. Las cantidades deben ser enteros >= 1.
3. Dirección de entrega: Captura la dirección completa con cualquier indicación relevante (torre, apartamento, casa, punto de referencia).
4. Método de pago: Identifica si pagará con Efectivo, Nequi, Daviplata, Tarjeta o Transferencia.
5. Indicador de confianza: Asigna un valor flotante entre 0.0 y 1.0 que refleje la certeza de los datos extraídos (ej. 1.0 si todos los campos requeridos están claros y explícitos; 0.7 si faltan datos o hay ambigüedad menor; 0.4 si es una conversación muy incompleta).
"""


# =====================================================================
# 3. Función Asíncrona de Extracción
# =====================================================================

async def extraer_pedido_whatsapp(
    chat_text: str,
    client: Optional[genai.Client] = None,
    api_key: Optional[str] = None
) -> ExtraccionPedido:
    """
    Función asíncrona que procesa texto plano de un chat de WhatsApp y extrae
    la información estructurada del pedido utilizando Gemini 2.5 Flash.

    Args:
        chat_text (str): Texto plano de la conversación de WhatsApp.
        client (Optional[genai.Client]): Cliente de Google GenAI ya instanciado.
        api_key (Optional[str]): Gemini API Key. Si no se pasa, se lee de la variable de entorno GEMINI_API_KEY.

    Returns:
        ExtraccionPedido: Objeto validado con Pydantic con los datos del pedido y el nivel de confianza.
    """
    if client is None:
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError(
                "No se encontró GEMINI_API_KEY. Configúrala en las variables de entorno o pásala a la función."
            )
        client = genai.Client(api_key=key)

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=ExtraccionPedido,
        temperature=0.1,  # Baja temperatura para consistencia determinista
    )

    # Invocación asíncrona con el modelo gemini-2.5-flash
    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=chat_text,
        config=config,
    )

    # Validación y parsing estricto a través de Pydantic
    return ExtraccionPedido.model_validate_json(response.text)


# =====================================================================
# 4. Bloque de Ejecución Directa para Pruebas
# =====================================================================

async def _main():
    chat_ejemplo = """
    [11:05 a. m., 17/10/2026] Laura Gómez: Buenas tardes, me gustaría hacer un pedido a domicilio.
    [11:05 a. m., 17/10/2026] Restaurante: ¡Hola Laura! Con gusto. ¿Qué te gustaría ordenar hoy?
    [11:06 a. m., 17/10/2026] Laura Gómez: Por favor envíame 2 pizzas personales de pepperoni y 3 gaseosas Manzana Postobón.
    [11:06 a. m., 17/10/2026] Laura Gómez: Espera, mejor sólo 1 gaseosa Manzana y 2 aguas con gas.
    [11:07 a. m., 17/10/2026] Restaurante: Entendido: 2 pizzas personales de pepperoni, 1 gaseosa Manzana y 2 aguas con gas. ¿Para dónde sería el envío?
    [11:08 a. m., 17/10/2026] Laura Gómez: Es para la Carrera 15 # 85-40, Apto 501, Barrio El Chicó.
    [11:08 a. m., 17/10/2026] Restaurante: Perfecto. ¿Cómo deseas pagar?
    [11:09 a. m., 17/10/2026] Laura Gómez: Pago por transferencia Nequi contra entrega.
    [11:09 a. m., 17/10/2026] Restaurante: ¡Listo Laura! Tu pedido entrará a cocina de inmediato.
    """

    print("=" * 70)
    print("EJECUTANDO EXTRACCIÓN ASÍNCRONA DE PEDIDO DE WHATSAPP (GEMINI 2.5 FLASH)")
    print("=" * 70)

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        print("\n[INFO] GEMINI_API_KEY no detectada en variables de entorno.")
        print("Para ejecutar la llamada real a la API, define tu API Key:")
        print("  Windows (PowerShell): $env:GEMINI_API_KEY='tu_api_key'")
        print("  Linux/Mac:            export GEMINI_API_KEY='tu_api_key'\n")
        print("Demostración de estructura validada con Pydantic:")
        pedido_mock = ExtraccionPedido(
            nombre_cliente="Laura Gómez",
            productos=[
                ItemProducto(nombre="Pizza personal de pepperoni", cantidad=2),
                ItemProducto(nombre="Gaseosa Manzana Postobón", cantidad=1),
                ItemProducto(nombre="Agua con gas", cantidad=2),
            ],
            direccion_entrega="Carrera 15 # 85-40, Apto 501, Barrio El Chicó",
            metodo_pago="Nequi",
            confianza_extraccion=0.98,
        )
        print(pedido_mock.model_dump_json(indent=2))
    else:
        try:
            pedido = await extraer_pedido_whatsapp(chat_ejemplo)
            print("\nPedido extraído exitosamente:")
            print(pedido.model_dump_json(indent=2))
            print(f"\nTipo de retorno verificado: {type(pedido)}")
            print(f"Confianza de extracción: {pedido.confianza_extraccion * 100:.1f}%")
        except Exception as err:
            print(f"\n[ERROR] Ocurrió una excepción durante la llamada: {err}")


if __name__ == "__main__":
    asyncio.run(_main())
