"""
Módulo de Gestión de Estado de Conversación y Máquina de Estados para Ventas en WhatsApp.
Permite rastrear y actualizar progresivamente el pedido de cada cliente
a medida que llegan nuevos mensajes extraídos por ia_parser.py.
"""

import sys
import os
import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Tuple
from pydantic import BaseModel, Field

# Compatibilidad de importación
try:
    from core.ia_parser import ExtraccionPedido, ItemProducto
    from core.cotizador import cotizar_pedido, ResumenCotizacion, formatear_pesos
except ModuleNotFoundError:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from core.ia_parser import ExtraccionPedido, ItemProducto
    from core.cotizador import cotizar_pedido, ResumenCotizacion, formatear_pesos

# Configuración de consola para emojis en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


# =====================================================================
# 1. Estados de la Máquina de Ventas
# =====================================================================

class EstadoFlujo(str, Enum):
    INICIAL = "INICIAL"
    ESPERO_PRODUCTOS = "ESPERO_PRODUCTOS"
    ESPERO_DIRECCION = "ESPERO_DIRECCION"
    ESPERO_PAGO = "ESPERO_PAGO"
    COMPLETADO = "COMPLETADO"
    CANCELADO = "CANCELADO"


# =====================================================================
# 2. Modelo de Sesión de Conversación
# =====================================================================

class SesionPedido(BaseModel):
    chat_id: str = Field(description="Identificador único del chat o número de teléfono del cliente")
    estado: EstadoFlujo = Field(default=EstadoFlujo.ESPERO_PRODUCTOS, description="Estado actual de la máquina de estados")
    nombre_cliente: Optional[str] = Field(default=None, description="Nombre del cliente")
    productos: List[ItemProducto] = Field(default_factory=list, description="Lista acumulada de productos del pedido")
    direccion_entrega: Optional[str] = Field(default=None, description="Dirección confirmada para el envío")
    metodo_pago: Optional[str] = Field(default=None, description="Método de pago seleccionado")
    resumen_cotizacion: Optional[ResumenCotizacion] = Field(default=None, description="Última cotización calculada")
    historial_mensajes: List[str] = Field(default_factory=list, description="Historial de mensajes procesados en la sesión")

    def actualizar_con_extraccion(self, extraccion: ExtraccionPedido) -> Tuple[EstadoFlujo, str]:
        """
        Incorpora progresivamente los datos extraídos de un nuevo mensaje
        y determina la transición del estado de la venta y la respuesta sugerida.

        Args:
            extraccion: Objeto ExtraccionPedido obtenido de ia_parser.py.

        Returns:
            Tuple[EstadoFlujo, str]: Nuevo estado y mensaje sugerido de respuesta para WhatsApp.
        """
        # 1. Actualización progresiva de campos no vacíos
        if extraccion.nombre_cliente and not self.nombre_cliente:
            self.nombre_cliente = extraccion.nombre_cliente

        if extraccion.productos:
            # Si llegan productos nuevos o corregidos, actualizamos la lista
            self.productos = extraccion.productos
            # Recalcular cotización con los productos actuales
            self.resumen_cotizacion = cotizar_pedido(
                productos=self.productos,
                nombre_cliente=self.nombre_cliente,
                direccion_entrega=self.direccion_entrega,
                metodo_pago=self.metodo_pago
            )

        if extraccion.direccion_entrega:
            self.direccion_entrega = extraccion.direccion_entrega

        if extraccion.metodo_pago:
            self.metodo_pago = extraccion.metodo_pago

        # 2. Máquina de transición de estados según la información acumulada
        estado_anterior = self.estado

        # Caso A: No hay productos definidos aún
        if not self.productos:
            self.estado = EstadoFlujo.ESPERO_PRODUCTOS
            nombre = f" {self.nombre_cliente}" if self.nombre_cliente else ""
            respuesta = (
                f"👋 ¡Hola{nombre}! Bienvenido a nuestro servicio de pedidos por WhatsApp. "
                f"¿Qué te gustaría ordenar hoy? Contamos con hamburguesas, pizzas, bebidas y más. 🍕🍔"
            )

        # Caso B: Hay productos, pero falta la dirección de entrega
        elif not self.direccion_entrega:
            self.estado = EstadoFlujo.ESPERO_DIRECCION
            nombre = f" {self.nombre_cliente}" if self.nombre_cliente else ""
            cant_prods = sum(p.cantidad for p in self.productos)
            respuesta = (
                f"📋 ¡Excelente{nombre}! Hemos tomado nota de tu pedido ({cant_prods} productos). "
                f"Por favor indícanos: ¿a qué *dirección y barrio* te lo enviamos? 📍"
            )

        # Caso C: Hay productos y dirección, pero falta el método de pago
        elif not self.metodo_pago:
            self.estado = EstadoFlujo.ESPERO_PAGO
            # Aseguramos cotización actualizada con dirección
            if self.resumen_cotizacion:
                total_str = formatear_pesos(self.resumen_cotizacion.total_a_pagar)
                respuesta = (
                    f"📍 Dirección registrada: *{self.direccion_entrega}*.\n\n"
                    f"💵 El total de tu pedido con domicilio es de *{total_str}*.\n"
                    f"¿Cómo prefieres realizar el pago? Aceptamos *Nequi, Daviplata, Efectivo contra entrega o Tarjeta*. 💳"
                )
            else:
                respuesta = (
                    f"📍 Dirección registrada: *{self.direccion_entrega}*.\n"
                    f"¿Con qué método prefieres pagar? (Nequi, Daviplata o Efectivo contra entrega) 💳"
                )

        # Caso D: Todos los datos están completos
        else:
            self.estado = EstadoFlujo.COMPLETADO
            total_str = formatear_pesos(self.resumen_cotizacion.total_a_pagar) if self.resumen_cotizacion else ""
            nombre = f" {self.nombre_cliente}" if self.nombre_cliente else ""
            respuesta = (
                f"🎉 ¡Tu pedido ha sido confirmado con éxito{nombre}!\n\n"
                f"📋 *Resumen final:*\n"
                f"• *Productos:* {sum(p.cantidad for p in self.productos)} unidades\n"
                f"• *Dirección:* {self.direccion_entrega}\n"
                f"• *Método de pago:* {self.metodo_pago}\n"
                f"• *Total a pagar:* {total_str}\n\n"
                f"👨‍🍳 Tu orden ya ingresó a cocina y saldrá pronto a reparto. ¡Muchas gracias por tu compra! 🚀"
            )

        return self.estado, respuesta

    def generar_orden_socio2(self) -> "OrdenSocio2":
        """
        Genera el payload consolidado y validado de la orden en el esquema
        estructurado requerido para el backend/base de datos del Socio 2.
        """
        if self.estado != EstadoFlujo.COMPLETADO:
            raise ValueError(
                f"No se puede generar la orden para Socio 2 porque la sesión está en estado '{self.estado.value}'. "
                "Debe estar en estado 'COMPLETADO'."
            )

        items_socio = []
        if self.resumen_cotizacion and self.resumen_cotizacion.items:
            for item in self.resumen_cotizacion.items:
                items_socio.append(
                    ItemOrdenSocio2(
                        nombre=item.producto_catalogo,
                        cantidad=item.cantidad,
                        precio_unitario=item.precio_unitario,
                        subtotal=item.subtotal
                    )
                )
        else:
            for p in self.productos:
                items_socio.append(
                    ItemOrdenSocio2(
                        nombre=p.nombre,
                        cantidad=p.cantidad,
                        precio_unitario=0.0,
                        subtotal=0.0
                    )
                )

        subtotal = self.resumen_cotizacion.subtotal_productos if self.resumen_cotizacion else 0.0
        envio = self.resumen_cotizacion.costo_envio if self.resumen_cotizacion else 0.0
        total = self.resumen_cotizacion.total_a_pagar if self.resumen_cotizacion else 0.0

        return OrdenSocio2(
            id_orden=f"ORD-{uuid.uuid4().hex[:8].upper()}",
            chat_id=self.chat_id,
            fecha_confirmacion=datetime.now().isoformat(),
            estado_orden="CONFIRMADA_COCINA",
            cliente=self.nombre_cliente or "Cliente WhatsApp",
            direccion_entrega=self.direccion_entrega or "Por definir",
            metodo_pago=self.metodo_pago or "No especificado",
            productos=items_socio,
            subtotal_productos=subtotal,
            costo_envio=envio,
            total_a_pagar=total,
            total_unidades=sum(i.cantidad for i in items_socio),
            mensaje_confirmacion_cliente=(
                f"🎉 ¡Tu pedido ha sido confirmado con éxito!\n"
                f"• Productos: {sum(i.cantidad for i in items_socio)} unidades\n"
                f"• Dirección: {self.direccion_entrega}\n"
                f"• Método de pago: {self.metodo_pago}\n"
                f"• Total a pagar: {formatear_pesos(total)}"
            )
        )


# =====================================================================
# 3. Esquema Estructurado de Orden para Socio 2
# =====================================================================

class ItemOrdenSocio2(BaseModel):
    nombre: str = Field(description="Nombre del producto en catálogo")
    cantidad: int = Field(description="Unidades ordenadas", ge=1)
    precio_unitario: float = Field(description="Precio unitario")
    subtotal: float = Field(description="Subtotal de la línea de producto")


class OrdenSocio2(BaseModel):
    id_orden: str = Field(description="Identificador único para trazabilidad y cocina")
    chat_id: str = Field(description="Número de WhatsApp o identificador del cliente")
    fecha_confirmacion: str = Field(description="Marca de tiempo ISO de confirmación del pedido")
    estado_orden: str = Field(default="CONFIRMADA_COCINA", description="Estado operativo de la orden")
    cliente: str = Field(description="Nombre completo del cliente")
    direccion_entrega: str = Field(description="Dirección física completa para despacho")
    metodo_pago: str = Field(description="Método de pago confirmado")
    productos: List[ItemOrdenSocio2] = Field(description="Lista detallada de productos")
    subtotal_productos: float = Field(description="Subtotal de los productos")
    costo_envio: float = Field(description="Costo de transporte a domicilio")
    total_a_pagar: float = Field(description="Total liquidado a pagar")
    total_unidades: int = Field(description="Total de unidades ordenadas")
    mensaje_confirmacion_cliente: str = Field(description="Resumen de confirmación emitido hacia el cliente")


class GestorConversaciones:
    """
    Administra en memoria el estado y la máquina de ventas de múltiples
    chats de WhatsApp simultáneos.
    """

    def __init__(self):
        self._sesiones: Dict[str, SesionPedido] = {}

    def obtener_o_crear_sesion(self, chat_id: str) -> SesionPedido:
        """Obtiene la sesión activa de un cliente o crea una nueva si no existe."""
        if chat_id not in self._sesiones:
            self._sesiones[chat_id] = SesionPedido(chat_id=chat_id)
        return self._sesiones[chat_id]

    def procesar_extraccion(
        self,
        chat_id: str,
        extraccion: ExtraccionPedido,
        mensaje_original: Optional[str] = None
    ) -> Tuple[EstadoFlujo, str]:
        """
        Actualiza el estado del chat indicado con la extracción de IA y retorna
        el nuevo estado junto con la respuesta sugerida para WhatsApp.
        """
        sesion = self.obtener_o_crear_sesion(chat_id)
        if mensaje_original:
            sesion.historial_mensajes.append(mensaje_original)
        return sesion.actualizar_con_extraccion(extraccion)

    def reiniciar_sesion(self, chat_id: str) -> None:
        """Reinicia la sesión de un chat (ej. al finalizar o cancelar un pedido)."""
        if chat_id in self._sesiones:
            del self._sesiones[chat_id]


# Instancia singleton predeterminada
gestor_conversaciones = GestorConversaciones()


# =====================================================================
# 4. Bloque de Ejecución Directa para Pruebas
# =====================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("SIMULACIÓN DE MÁQUINA DE ESTADOS PROGRESIVA PARA VENTAS DE WHATSAPP")
    print("=" * 70)

    gestor = GestorConversaciones()
    chat_id_demo = "573101234567"

    # --- Paso 1: Cliente saluda pero no da productos ---
    print("\n[PASO 1] Cliente saluda:")
    ext_1 = ExtraccionPedido(nombre_cliente="Santiago", productos=[])
    estado, respuesta = gestor.procesar_extraccion(chat_id_demo, ext_1, "Hola buenas tardes!")
    print(f"-> Estado: {estado.value}")
    print(f"-> Respuesta Bot:\n{respuesta}\n")

    # --- Paso 2: Cliente elige productos ---
    print("[PASO 2] Cliente indica productos:")
    ext_2 = ExtraccionPedido(
        productos=[
            ItemProducto(nombre="pizza personal de pepperoni", cantidad=2),
            ItemProducto(nombre="gaseosa coca-cola zero", cantidad=2)
        ]
    )
    estado, respuesta = gestor.procesar_extraccion(chat_id_demo, ext_2, "Quiero 2 pizzas de pepperoni y 2 cocacolas zero")
    print(f"-> Estado: {estado.value}")
    print(f"-> Respuesta Bot:\n{respuesta}\n")

    # --- Paso 3: Cliente proporciona dirección ---
    print("[PASO 3] Cliente entrega dirección de despacho:")
    ext_3 = ExtraccionPedido(
        direccion_entrega="Calle 85 # 11-53, Apto 402, Chico Norte"
    )
    estado, respuesta = gestor.procesar_extraccion(chat_id_demo, ext_3, "Es para la Calle 85 # 11-53 apto 402 Chico Norte")
    print(f"-> Estado: {estado.value}")
    print(f"-> Respuesta Bot:\n{respuesta}\n")

    # --- Paso 4: Cliente define método de pago ---
    print("[PASO 4] Cliente selecciona método de pago:")
    ext_4 = ExtraccionPedido(
        metodo_pago="Nequi"
    )
    estado, respuesta = gestor.procesar_extraccion(chat_id_demo, ext_4, "Pago por Nequi")
    print(f"-> Estado: {estado.value}")
    print(f"-> Respuesta Bot:\n{respuesta}\n")
