"""
Módulo de Cotización y Cálculo de Pedidos de WhatsApp.
Calcula precios, subtotales, totales y genera mensajes de respuesta
formateados específicamente para WhatsApp.
"""

import unicodedata
import sys
import os
from typing import List, Dict, Optional, Union, Tuple
from pydantic import BaseModel, Field


try:
    from core.ia_parser import ItemProducto, ExtraccionPedido
except ModuleNotFoundError:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from core.ia_parser import ItemProducto, ExtraccionPedido

# Configurar encoding UTF-8 en Windows para soporte seguro de emojis
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass



# =====================================================================
# 1. Catálogo Base de Productos y Precios (Simulado)
# =====================================================================

CATALOGO_PRECIOS_BASE: Dict[str, float] = {
    # Comidas rápidas y pizzas
    "pizza personal de pepperoni": 18000.0,
    "pizza personal hawaiana": 17000.0,
    "pizza personal de carnes": 19000.0,
    "pizza grande especial": 38000.0,
    "hamburguesa especial": 22000.0,
    "hamburguesa doble carne": 27000.0,
    "hamburguesa sencilla": 16000.0,
    "perro caliente especial": 15000.0,
    "porción de papas rústicas": 8000.0,
    "porción de papas a la francesa": 6000.0,
    "empanada de carne": 3500.0,
    "empanada de pollo": 3500.0,

    # Bebidas
    "gaseosa manzana postobón": 4500.0,
    "gaseosa coca-cola": 5000.0,
    "gaseosa coca-cola zero": 5000.0,
    "agua con gas": 4000.0,
    "agua sin gas": 3500.0,
    "jugo de maracuyá": 6000.0,
    "jugo de fresa": 6000.0,
}

COSTO_ENVIO_ESTANDAR: float = 5000.0


# =====================================================================
# 2. Modelos Pydantic para la Cotización
# =====================================================================

class ItemCotizado(BaseModel):
    nombre_original: str = Field(description="Nombre tal como fue detectado en el chat")
    producto_catalogo: str = Field(description="Nombre oficial emparejado en el catálogo")
    cantidad: int = Field(description="Cantidad de unidades", ge=1)
    precio_unitario: float = Field(description="Precio por unidad")
    subtotal: float = Field(description="Subtotal calculado (cantidad * precio_unitario)")
    encontrado_en_catalogo: bool = Field(
        description="Indica si el producto fue hallado en el catálogo oficial",
        default=True
    )


class ResumenCotizacion(BaseModel):
    items: List[ItemCotizado] = Field(default_factory=list)
    subtotal_productos: float = Field(default=0.0)
    costo_envio: float = Field(default=0.0)
    total_a_pagar: float = Field(default=0.0)
    items_no_disponibles: List[str] = Field(
        description="Lista de ítems que no pudieron ser cotizados en el catálogo",
        default_factory=list
    )
    mensaje_whatsapp: str = Field(
        description="Mensaje listo y formateado para enviar al cliente por WhatsApp",
        default=""
    )


# =====================================================================
# 3. Utilidades de Coincidencia de Productos
# =====================================================================

def _normalizar_texto(texto: str) -> str:
    """Convierte a minúsculas, elimina tildes y caracteres especiales para matching."""
    texto = texto.lower().strip()
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    for char in [",", ".", "-", "_", "/", "\\", "(", ")"]:
        texto = texto.replace(char, " ")
    return " ".join(texto.split())


def _buscar_en_catalogo(
    nombre_item: str,
    catalogo: Dict[str, float]
) -> Optional[Tuple[str, float]]:

    """
    Busca un producto en el catálogo utilizando coincidencia exacta, parcial o de palabras clave.
    """
    nombre_norm = _normalizar_texto(nombre_item)
    palabras_item = set(nombre_norm.split())

    # 1. Coincidencia exacta con catálogo normalizado
    for prod_cat, precio in catalogo.items():
        if _normalizar_texto(prod_cat) == nombre_norm:
            return prod_cat, precio

    # 2. Coincidencia de contención o inclusión
    for prod_cat, precio in catalogo.items():
        cat_norm = _normalizar_texto(prod_cat)
        if nombre_norm in cat_norm or cat_norm in nombre_norm:
            return prod_cat, precio

    # 3. Coincidencia por intersección de palabras clave relevantes
    mejor_coincidencia = None
    max_palabras_comunes = 0

    palabras_stop = {"de", "la", "el", "en", "con", "sin", "por", "un", "una", "porción", "porcion"}
    palabras_clave_item = palabras_item - palabras_stop

    for prod_cat, precio in catalogo.items():
        cat_norm = _normalizar_texto(prod_cat)
        palabras_cat = set(cat_norm.split()) - palabras_stop
        interseccion = palabras_clave_item.intersection(palabras_cat)

        if len(interseccion) > max_palabras_comunes and len(interseccion) >= 1:
            max_palabras_comunes = len(interseccion)
            mejor_coincidencia = (prod_cat, precio)

    return mejor_coincidencia


def formatear_pesos(valor: float) -> str:
    """Formatea valores numéricos en formato de moneda colombiana: $45.000"""
    return f"${valor:,.0f}".replace(",", ".")


# =====================================================================
# 4. Generación del Mensaje de WhatsApp
# =====================================================================

def generar_mensaje_whatsapp(
    cotizacion: ResumenCotizacion,
    nombre_cliente: Optional[str] = None,
    direccion_entrega: Optional[str] = None,
    metodo_pago: Optional[str] = None,
) -> str:
    """
    Construye un mensaje profesional con formato Markdown de WhatsApp (*negrita*, emojis, etc.).
    """
    saludo_cliente = f" {nombre_cliente}" if nombre_cliente else ""
    lineas = [
        f"👋 ¡Hola{saludo_cliente}! Aquí tienes el resumen y cotización de tu pedido:\n",
        "📋 *DETALLE DE TU PEDIDO:*",
    ]

    for item in cotizacion.items:
        if item.encontrado_en_catalogo:
            detalles_unitario = f" ({formatear_pesos(item.precio_unitario)} c/u)" if item.cantidad > 1 else ""
            lineas.append(
                f"• {item.cantidad}x *{item.producto_catalogo.title()}* - {formatear_pesos(item.subtotal)}{detalles_unitario}"
            )
        else:
            lineas.append(f"• {item.cantidad}x _{item.nombre_original}_ - *(Precio por confirmar)*")

    lineas.append("")
    lineas.append("💵 *RESUMEN DE CUENTA:*")
    lineas.append(f"• *Subtotal:* {formatear_pesos(cotizacion.subtotal_productos)}")
    if cotizacion.costo_envio > 0:
        lineas.append(f"• *Envío a domicilio:* {formatear_pesos(cotizacion.costo_envio)}")
    else:
        lineas.append("• *Envío:* Gratis")
    lineas.append(f"💰 *TOTAL A PAGAR: {formatear_pesos(cotizacion.total_a_pagar)}*")

    if direccion_entrega:
        lineas.append(f"\n📍 *Dirección de entrega:* {direccion_entrega}")

    if metodo_pago:
        lineas.append(f"💳 *Método de pago preferido:* {metodo_pago}")

    if cotizacion.items_no_disponibles:
        lineas.append(
            f"\n⚠️ _Nota: Algunos productos no fueron encontrados en el catálogo automático: "
            f"{', '.join(cotizacion.items_no_disponibles)}. Un asesor te confirmará su valor._"
        )

    lineas.append("\n¿Deseas confirmar tu pedido para enviarlo de inmediato a preparación? 🚀✨")
    return "\n".join(lineas)


# =====================================================================
# 5. Función Principal del Cotizador
# =====================================================================

def cotizar_pedido(
    productos: Union[List[ItemProducto], List[dict], ExtraccionPedido],
    catalogo: Optional[Dict[str, float]] = None,
    costo_envio: float = COSTO_ENVIO_ESTANDAR,
    nombre_cliente: Optional[str] = None,
    direccion_entrega: Optional[str] = None,
    metodo_pago: Optional[str] = None,
) -> ResumenCotizacion:
    """
    Recibe la lista de productos (o el objeto ExtraccionPedido completo) y calcula la cotización.

    Args:
        productos: Instancia de ExtraccionPedido, lista de ItemProducto o lista de diccionarios.
        catalogo: Diccionario opcional de producto -> precio. Usa CATALOGO_PRECIOS_BASE por defecto.
        costo_envio: Valor del flete o envío a domicilio.
        nombre_cliente: Opcional, para personalizar el mensaje.
        direccion_entrega: Opcional, para incluir en el mensaje.
        metodo_pago: Opcional, para incluir en el mensaje.

    Returns:
        ResumenCotizacion: Objeto con subtotales, totales, lista de ítems cotizados y mensaje listo.
    """
    cat = catalogo or CATALOGO_PRECIOS_BASE
    lista_items: List[ItemProducto] = []

    # Manejo polimórfico si se pasa ExtraccionPedido completo
    if isinstance(productos, ExtraccionPedido):
        lista_items = productos.productos
        nombre_cliente = nombre_cliente or productos.nombre_cliente
        direccion_entrega = direccion_entrega or productos.direccion_entrega
        metodo_pago = metodo_pago or productos.metodo_pago
    elif isinstance(productos, list):
        for item in productos:
            if isinstance(item, ItemProducto):
                lista_items.append(item)
            elif isinstance(item, dict):
                lista_items.append(ItemProducto(**item))

    items_cotizados: List[ItemCotizado] = []
    subtotal_total = 0.0
    items_no_encontrados: List[str] = []

    for item in lista_items:
        coincidencia = _buscar_en_catalogo(item.nombre, cat)
        if coincidencia:
            nombre_cat, precio_unit = coincidencia
            subtotal_item = precio_unit * item.cantidad
            subtotal_total += subtotal_item
            items_cotizados.append(
                ItemCotizado(
                    nombre_original=item.nombre,
                    producto_catalogo=nombre_cat,
                    cantidad=item.cantidad,
                    precio_unitario=precio_unit,
                    subtotal=subtotal_item,
                    encontrado_en_catalogo=True
                )
            )
        else:
            items_no_encontrados.append(item.nombre)
            items_cotizados.append(
                ItemCotizado(
                    nombre_original=item.nombre,
                    producto_catalogo=item.nombre,
                    cantidad=item.cantidad,
                    precio_unitario=0.0,
                    subtotal=0.0,
                    encontrado_en_catalogo=False
                )
            )

    total_final = subtotal_total + (costo_envio if subtotal_total > 0 else 0.0)

    resumen = ResumenCotizacion(
        items=items_cotizados,
        subtotal_productos=subtotal_total,
        costo_envio=costo_envio if subtotal_total > 0 else 0.0,
        total_a_pagar=total_final,
        items_no_disponibles=items_no_encontrados
    )

    # Generamos el mensaje listo para WhatsApp
    resumen.mensaje_whatsapp = generar_mensaje_whatsapp(
        cotizacion=resumen,
        nombre_cliente=nombre_cliente,
        direccion_entrega=direccion_entrega,
        metodo_pago=metodo_pago
    )

    return resumen


# =====================================================================
# 6. Bloque de Ejecución Directa para Pruebas
# =====================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("PRUEBA DEL MÓDULO COTIZADOR DE PEDIDOS DE WHATSAPP")
    print("=" * 70)

    # Ejemplo simulado de productos extraídos por ia_parser.py
    productos_simulados = [
        ItemProducto(nombre="pizza personal pepperoni", cantidad=2),
        ItemProducto(nombre="gaseosa manzana postobon", cantidad=1),
        ItemProducto(nombre="agua con gas", cantidad=2),
    ]

    cotizacion = cotizar_pedido(
        productos=productos_simulados,
        nombre_cliente="Laura Gómez",
        direccion_entrega="Carrera 15 # 85-40, Apto 501, Barrio El Chicó",
        metodo_pago="Nequi",
        costo_envio=5000.0
    )

    print("\n--- RESUMEN EN OBJETO PYDANTIC ---")
    print(f"Subtotal: {formatear_pesos(cotizacion.subtotal_productos)}")
    print(f"Envío:    {formatear_pesos(cotizacion.costo_envio)}")
    print(f"Total:    {formatear_pesos(cotizacion.total_a_pagar)}")

    print("\n--- MENSAJE FINAL PARA WHATSAPP ---")
    print(cotizacion.mensaje_whatsapp)
