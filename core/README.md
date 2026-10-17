# 🧠 Módulo Core: Motor de Inteligencia Artificial para WhatsApp Pedidos

Este paquete constituye el núcleo de procesamiento inteligente, cotización automatizada, auditoría financiera de transferencias y recuperación conversacional para la recepción de pedidos comerciales por WhatsApp.

Construido sobre el SDK oficial **`google-genai`**, aprovecha las capacidades multimodales de **`gemini-2.5-flash`** con salidas estructuradas estrictamente validadas mediante **Pydantic v2**.

---

## 📁 Arquitectura del Módulo `core/`

| Archivo | Responsabilidad Principal | Modelo / Tecnología |
| :--- | :--- | :--- |
| **[`ia_parser.py`](file:///C:/Users/Inge/.gemini/antigravity/scratch/proyecto-whatsapp-pedidos/core/ia_parser.py)** | Extracción estructurada de chats informales de WhatsApp | `gemini-2.5-flash` + Pydantic |
| **[`cotizador.py`](file:///C:/Users/Inge/.gemini/antigravity/scratch/proyecto-whatsapp-pedidos/core/cotizador.py)** | Cotización, matching de catálogo y mensaje formateado | Algoritmo de matching + Pydantic |
| **[`ocr_pagos.py`](file:///C:/Users/Inge/.gemini/antigravity/scratch/proyecto-whatsapp-pedidos/core/ocr_pagos.py)** | OCR multimodal y auditoría de comprobantes bancarios | `gemini-2.5-flash` (Multimodal) |
| **[`fallback_handler.py`](file:///C:/Users/Inge/.gemini/antigravity/scratch/proyecto-whatsapp-pedidos/core/fallback_handler.py)** | Recuperación conversacional persuasiva de datos faltantes | `gemini-2.5-flash` + Pydantic |
| **[`conversation_state.py`](file:///C:/Users/Inge/.gemini/antigravity/scratch/proyecto-whatsapp-pedidos/core/conversation_state.py)** | Máquina de estados de ventas y exportación para Socio 2 | State Machine + Pydantic |

---

## 🚀 Requisitos y Configuración de Entorno

Instala las dependencias del proyecto:

```bash
pip install -r requirements.txt
```

Configura tu clave de API de Gemini:

```bash
# Windows (PowerShell)
$env:GEMINI_API_KEY = "tu_api_key_aqui"

# Linux / macOS
export GEMINI_API_KEY="tu_api_key_aqui"
```

---

## 📦 Importación Centralizada de Funciones

Gracias a `core/__init__.py`, puedes importar todas las funciones asíncronas, modelos y utilidades directamente desde `core`:

```python
from core import (
    # Extracción de pedidos
    extraer_pedido_whatsapp,
    ExtraccionPedido,
    ItemProducto,
    GeminiParserError,
    
    # Cotización y catálogo
    cotizar_pedido,
    formatear_pesos,
    ResumenCotizacion,
    
    # OCR de comprobantes bancarios
    procesar_comprobante_pago,
    procesar_comprobante_pago_sync,
    ComprobantePago,
    EstadoValidacion,
    GeminiOCRError,
    
    # Recuperación conversacional (Fallback)
    evaluar_necesidad_fallback,
    generar_respuesta_fallback,
    ResultadoFallback,
    
    # Máquina de estados y Socio 2
    EstadoFlujo,
    SesionPedido,
    GestorConversaciones,
    gestor_conversaciones,
    OrdenSocio2,
)
```

---

## 🛠️ Guía Técnica de Funciones Asíncronas

### 1. `ia_parser.py` — `extraer_pedido_whatsapp`

Procesa texto plano de una conversación informal de WhatsApp y devuelve una instancia validada de `ExtraccionPedido`.

```python
import asyncio
from core import extraer_pedido_whatsapp

async def demo_ia_parser():
    chat = """
    [10:14] Carlos: Hola! Me mandas 2 hamburguesas especiales sin cebolla porfa.
    [10:15] Carlos: Y añade 1 porción de papas rústicas y 2 Coca-Colas Zero.
    [10:16] Carlos: A la Calle 45 # 12-34 Apto 302. Pago por Nequi.
    """
    
    pedido = await extraer_pedido_whatsapp(chat)
    print(f"Cliente:   {pedido.nombre_cliente}")
    print(f"Productos: {[f'{p.cantidad}x {p.nombre}' for p in pedido.productos]}")
    print(f"Dirección: {pedido.direccion_entrega}")
    print(f"Método:    {pedido.metodo_pago}")
    print(f"Certeza:   {pedido.confianza_extraccion * 100:.1f}%")

if __name__ == "__main__":
    asyncio.run(demo_ia_parser())
```

---

### 2. `cotizador.py` — `cotizar_pedido`

Calcula subtotales, costo de envío y total final cruzando los productos extraídos con el catálogo de precios, generando el mensaje listo para enviar al cliente por WhatsApp con formato Markdown.

```python
from core import cotizar_pedido, ItemProducto

items = [
    ItemProducto(nombre="pizza personal pepperoni", cantidad=2),
    ItemProducto(nombre="gaseosa manzana postobon", cantidad=1)
]

cotizacion = cotizar_pedido(
    productos=items,
    nombre_cliente="Laura Gómez",
    direccion_entrega="Cra 15 # 85-40 Apto 501",
    metodo_pago="Nequi",
    costo_envio=5000.0
)

print(f"Subtotal: {cotizacion.subtotal_productos}")
print(f"Total:    {cotizacion.total_a_pagar}")
print("\n--- Mensaje listo para WhatsApp ---\n")
print(cotizacion.mensaje_whatsapp)
```

---

### 3. `ocr_pagos.py` — `procesar_comprobante_pago`

Función asíncrona que procesa capturas de transferencias bancarias (Nequi, Daviplata, Bancolombia, etc.) usando la visión multimodal de `gemini-2.5-flash`. Acepta rutas de archivo (`str` / `Path`) o `bytes` directos de la imagen.

```python
import asyncio
from core import procesar_comprobante_pago

async def demo_ocr():
    # Puede recibir una ruta de archivo o bytes crudos de la imagen
    comprobante = await procesar_comprobante_pago("comprobante_transferencia.jpg")
    
    print(f"Banco:       {comprobante.banco_emisor}")
    print(f"Referencia:  {comprobante.numero_referencia}")
    print(f"Monto:       ${comprobante.monto_pagado:,.0f} {comprobante.moneda}")
    print(f"Fecha/Hora:  {comprobante.fecha_hora}")
    print(f"Validación:  {comprobante.estado_validacion.value}")
    print(f"Confianza:   {comprobante.confianza_ocr * 100:.1f}%")

if __name__ == "__main__":
    asyncio.run(demo_ocr())
```

---

### 4. `fallback_handler.py` — `generar_respuesta_fallback`

Recibe el objeto Pydantic `ExtraccionPedido`. Si faltan campos obligatorios (`productos`, `direccion_entrega` o `metodo_pago`) o si la confianza es baja ($< 0.75$), solicita a Gemini formular una respuesta breve, cálida y directa pidiendo **exclusivamente el dato faltante prioritario**.

```python
import asyncio
from core import ExtraccionPedido, ItemProducto, generar_respuesta_fallback

async def demo_fallback():
    # Pedido con productos pero sin dirección ni método de pago
    pedido_incompleto = ExtraccionPedido(
        nombre_cliente="Andrés",
        productos=[ItemProducto(nombre="pizza personal hawaiana", cantidad=2)],
        direccion_entrega=None,
        metodo_pago=None
    )
    
    fallback = await generar_respuesta_fallback(
        extraccion=pedido_incompleto,
        chat_reciente="Quiero 2 pizzas hawaianas por favor"
    )
    
    if fallback.necesita_fallback:
        print(f"Dato prioritario a pedir: {fallback.campo_prioritario}")
        print("\n--- Respuesta para WhatsApp ---\n")
        print(fallback.mensaje_whatsapp)

if __name__ == "__main__":
    asyncio.run(demo_fallback())
```

---

## ⚡ Implementación en Servidor FastAPI

A continuación se presenta un ejemplo completo y listo para producción de cómo integrar estos módulos en un servidor **FastAPI** (`app.py`), implementando:
1. **Webhook de WhatsApp:** Recepción y procesamiento en tiempo real con máquina de estados y fallback.
2. **Endpoint REST de Extracción:** API para probar extracción y cotización directa desde un dashboard.
3. **Endpoint OCR de Comprobantes:** Subida de imagen (`multipart/form-data`) para validar pagos bancarios.

### Código de `app.py`:

```python
"""
Servidor FastAPI para el Motor de IA de Pedidos por WhatsApp.
Integra ia_parser, cotizador, ocr_pagos, fallback_handler y conversation_state.
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, status
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
# Modelos Pydantic de Request y Response para la API
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
        # Aquí se puede despachar la orden hacia base de datos, RabbitMQ o webhook de cocina

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
```

### Ejecución del Servidor FastAPI con Uvicorn:

```bash
# Iniciar servidor de desarrollo con recarga en vivo
uvicorn app:app --reload --port 8000
```

Accede a la documentación interactiva Swagger en:
👉 `http://127.0.0.1:8000/docs`

---

## 🧪 Ejecución de Pruebas Unitarias e Integración

Para validar la suite completa de pruebas:

```bash
# Ejecutar todas las pruebas del proyecto (32 tests)
pytest -v

# Ejecutar integración del pipeline multi-turno para Socio 2
python core/test_pipeline.py

# Validar manejo de chats informales y con faltantes
pytest core/test_parser.py -v
```
