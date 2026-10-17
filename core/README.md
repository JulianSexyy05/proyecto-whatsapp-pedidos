# 🧠 Módulo Core: Motor de Inteligencia Artificial para WhatsApp Pedidos

Este paquete constituye el núcleo de procesamiento inteligente, cotización automatizada, auditoría financiera y recuperación conversacional para la recepción de pedidos comerciales por WhatsApp.

Está construido sobre el SDK oficial **`google-genai`**, aprovechando las capacidades del modelo multimodal **`gemini-2.5-flash`** con salidas estructuradas estrictamente validadas mediante **Pydantic v2**.

---

## 📁 Arquitectura del Módulo `core/`

| Archivo | Responsabilidad Principal | Modelo / Tecnología |
| :--- | :--- | :--- |
| **`ia_parser.py`** | Extracción estructurada de chats informales de WhatsApp | `gemini-2.5-flash` + Pydantic |
| **`cotizador.py`** | Cotización, matching de catálogo y mensaje para WhatsApp | Algoritmo de matching + Pydantic |
| **`ocr_pagos.py`** | OCR multimodal y auditoría de comprobantes bancarios | `gemini-2.5-flash` (Multimodal) |
| **`fallback_handler.py`** | Recuperación conversacional persuasiva de faltantes | `gemini-2.5-flash` + Pydantic |
| **`conversation_state.py`** | Máquina de estados de ventas y exportación para Socio 2 | State Machine + Pydantic |

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

## 🛠️ Guía Técnica y Ejemplos de Uso

### 1. `ia_parser.py` — Extracción Asíncrona de Pedidos

Analiza texto plano de conversaciones informales de WhatsApp (incluso con modismos, emojis, cancelaciones a mitad de chat o notas de entrega) y devuelve una instancia tipada de `ExtraccionPedido`.

#### Esquema de Salida (`ExtraccionPedido`):
* `nombre_cliente`: `Optional[str]`
* `productos`: `List[ItemProducto]` (cada uno con `nombre: str` y `cantidad: int`)
* `direccion_entrega`: `Optional[str]`
* `metodo_pago`: `Optional[str]`
* `confianza_extraccion`: `float` ($0.0 \le \text{confianza} \le 1.0$)

#### Ejemplo Rápido de Código:

```python
import asyncio
from core.ia_parser import extraer_pedido_whatsapp

async def main():
    chat_whatsapp = """
    [10:15] Carlos: Hola! Me mandas 2 hamburguesas especiales sin cebolla porfa.
    [10:16] Carlos: Y añade 1 porción de papas rústicas y 2 Coca-Colas Zero.
    [10:17] Carlos: A la Calle 45 # 12-34 Apto 302. Pago por Nequi.
    """
    
    pedido = await extraer_pedido_whatsapp(chat_whatsapp)
    
    print(f"Cliente: {pedido.nombre_cliente}")
    print(f"Productos: {[f'{p.cantidad}x {p.nombre}' for p in pedido.productos]}")
    print(f"Dirección: {pedido.direccion_entrega}")
    print(f"Método de pago: {pedido.metodo_pago}")
    print(f"Confianza de IA: {pedido.confianza_extraccion * 100:.1f}%")

if __name__ == "__main__":
    asyncio.run(main())
```

---

### 2. `cotizador.py` — Cotización y Formateo para WhatsApp

Empareja los productos pedidos con el catálogo de precios oficial mediante coincidencia difusa normalizada, calcula subtotales, costo de envío y genera el mensaje listo con formato Markdown de WhatsApp (`*negrita*`, emojis y saltos de línea).

#### Esquema de Salida (`ResumenCotizacion`):
* `items`: `List[ItemCotizado]` (subtotales y precios unitarios por línea)
* `subtotal_productos`: `float`
* `costo_envio`: `float`
* `total_a_pagar`: `float`
* `items_no_disponibles`: `List[str]`
* `mensaje_whatsapp`: `str`

#### Ejemplo Rápido de Código:

```python
from core.cotizador import cotizar_pedido
from core.ia_parser import ItemProducto

productos = [
    ItemProducto(nombre="pizza personal pepperoni", cantidad=2),
    ItemProducto(nombre="gaseosa manzana postobon", cantidad=1)
]

cotizacion = cotizar_pedido(
    productos=productos,
    nombre_cliente="Laura Gómez",
    direccion_entrega="Cra 15 # 85-40 Apto 501",
    metodo_pago="Nequi",
    costo_envio=5000.0
)

print(f"Total: ${cotizacion.total_a_pagar:,.0f}")
print("\n--- Mensaje listo para WhatsApp ---\n")
print(cotizacion.mensaje_whatsapp)
```

---

### 3. `ocr_pagos.py` — OCR y Validación de Comprobantes Bancarios

Procesa capturas de transferencias digitales (Nequi, Daviplata, Bancolombia, etc.) utilizando visión multimodal en `gemini-2.5-flash`. Extrae entidad bancaria, referencia, monto, estampa temporal y valida la autenticidad visual.

#### Esquema de Salida (`ComprobantePago`):
* `banco_emisor`: `Optional[str]`
* `numero_referencia`: `Optional[str]`
* `monto_pagado`: `Optional[float]`
* `fecha_hora`: `Optional[str]`
* `estado_validacion`: `EstadoValidacion` (`exitoso`, `pendiente`, `rechazado`, `posible_adulteracion`, `dudoso_o_ilegible`)
* `confianza_ocr`: `float`

#### Ejemplo Rápido de Código:

```python
import asyncio
from core.ocr_pagos import procesar_comprobante_pago

async def main():
    # Acepta ruta de archivo (str/Path) o bytes de la imagen recibida por WhatsApp
    comprobante = await procesar_comprobante_pago("comprobante_nequi.jpg")
    
    print(f"Banco:       {comprobante.banco_emisor}")
    print(f"Referencia:  {comprobante.numero_referencia}")
    print(f"Monto:       ${comprobante.monto_pagado:,.0f}")
    print(f"Validación:  {comprobante.estado_validacion.value}")
    print(f"Confianza:   {comprobante.confianza_ocr * 100:.1f}%")

if __name__ == "__main__":
    asyncio.run(main())
```

---

### 4. `fallback_handler.py` — Recuperación Conversacional Persuasiva

Si faltan campos obligatorios (`productos`, `direccion_entrega` o `metodo_pago`) o si la confianza es baja ($< 0.75$), interactúa con Gemini para redactar un mensaje breve, cálido y persuasivo solicitando **únicamente el dato prioritario faltante** sin abrumar al cliente.

#### Esquema de Salida (`ResultadoFallback`):
* `necesita_fallback`: `bool`
* `campo_prioritario`: `Optional[str]` (`productos`, `direccion_entrega`, `metodo_pago` o `aclaracion`)
* `campos_faltantes`: `List[str]`
* `mensaje_whatsapp`: `str`
* `generado_por_ia`: `bool`

#### Ejemplo Rápido de Código:

```python
import asyncio
from core.ia_parser import ExtraccionPedido, ItemProducto
from core.fallback_handler import generar_mensaje_fallback

async def main():
    # Pedido donde el cliente eligió productos pero no indicó dirección ni pago
    extraccion = ExtraccionPedido(
        nombre_cliente="Andrés",
        productos=[ItemProducto(nombre="pizza personal hawaiana", cantidad=2)],
        direccion_entrega=None,
        metodo_pago=None
    )
    
    fallback = await generar_mensaje_fallback(
        extraccion=extraccion,
        chat_reciente="Quiero 2 pizzas hawaianas"
    )
    
    if fallback.necesita_fallback:
        print(f"Falta solicitar: {fallback.campo_prioritario}")
        print("\n--- Respuesta persuasiva sugerida para WhatsApp ---")
        print(fallback.mensaje_whatsapp)

if __name__ == "__main__":
    asyncio.run(main())
```

---

### 5. `conversation_state.py` — Máquina de Estados y Salida para Socio 2

Orquesta la conversación completa a través de una máquina de estados finita:
$$\text{ESPERO\_PRODUCTOS} \longrightarrow \text{ESPERO\_DIRECCION} \longrightarrow \text{ESPERO\_PAGO} \longrightarrow \text{COMPLETADO}$$

Al alcanzar el estado `COMPLETADO`, emite el payload estructurado **`OrdenSocio2`** listo para ser consumido por el backend, base de datos o módulo de despacho del **Socio 2**:

```python
from core.conversation_state import GestorConversaciones

gestor = GestorConversaciones()
chat_id = "573101234567"

# Procesa progresivamente cada mensaje con ia_parser
estado, respuesta_bot = gestor.procesar_extraccion(chat_id, extraccion_ia)

if estado.value == "COMPLETADO":
    sesion = gestor.obtener_o_crear_sesion(chat_id)
    orden_para_socio_2 = sesion.generar_orden_socio2()
    # Payload validado listo para la API / base de datos del Socio 2
    payload_json = orden_para_socio_2.model_dump_json(indent=2)
```

---

## 🧪 Ejecución de Pruebas Unitarias e Integración

Para validar la suite completa de pruebas del core:

```bash
# Ejecutar toda la suite de pruebas
pytest -v

# Ejecutar script de pipeline de integración multi-turno
python core/test_pipeline.py

# Ejecutar pruebas de chats informales y variaciones
pytest core/test_parser.py -v
```
