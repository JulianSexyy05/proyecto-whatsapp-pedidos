"""
Pruebas unitarias para core/conversation_state.py
"""

import unittest
from core.ia_parser import ExtraccionPedido, ItemProducto
from core.conversation_state import (
    EstadoFlujo,
    SesionPedido,
    GestorConversaciones
)


class TestConversationState(unittest.TestCase):

    def setUp(self):
        self.gestor = GestorConversaciones()
        self.chat_id = "573001234567"

    def test_flujo_progresivo_estandar(self):
        # 1. Solo saludo
        ext_1 = ExtraccionPedido(nombre_cliente="Mateo", productos=[])
        estado, msg = self.gestor.procesar_extraccion(self.chat_id, ext_1)
        self.assertEqual(estado, EstadoFlujo.ESPERO_PRODUCTOS)
        self.assertIn("Mateo", msg)

        # 2. Indica productos
        ext_2 = ExtraccionPedido(
            productos=[ItemProducto(nombre="hamburguesa especial", cantidad=1)]
        )
        estado, msg = self.gestor.procesar_extraccion(self.chat_id, ext_2)
        self.assertEqual(estado, EstadoFlujo.ESPERO_DIRECCION)
        self.assertIn("dirección", msg.lower())

        # 3. Indica dirección
        ext_3 = ExtraccionPedido(direccion_entrega="Calle 123 # 45-67")
        estado, msg = self.gestor.procesar_extraccion(self.chat_id, ext_3)
        self.assertEqual(estado, EstadoFlujo.ESPERO_PAGO)
        self.assertIn("Calle 123 # 45-67", msg)

        # 4. Indica método de pago
        ext_4 = ExtraccionPedido(metodo_pago="Efectivo")
        estado, msg = self.gestor.procesar_extraccion(self.chat_id, ext_4)
        self.assertEqual(estado, EstadoFlujo.COMPLETADO)
        self.assertIn("confirmado", msg.lower())

    def test_orden_completa_en_un_solo_mensaje(self):
        ext_completa = ExtraccionPedido(
            nombre_cliente="Camila",
            productos=[ItemProducto(nombre="pizza personal hawaiana", cantidad=1)],
            direccion_entrega="Carrera 7 # 32-10",
            metodo_pago="Daviplata"
        )
        estado, msg = self.gestor.procesar_extraccion("573009998877", ext_completa)
        self.assertEqual(estado, EstadoFlujo.COMPLETADO)
        self.assertIn("Camila", msg)
        self.assertIn("Carrera 7 # 32-10", msg)
        self.assertIn("Daviplata", msg)

    def test_cambio_de_productos_actualiza_cotizacion(self):
        sesion = SesionPedido(chat_id="chat_prueba")

        # Pedido inicial: 1 hamburguesa
        ext_1 = ExtraccionPedido(productos=[ItemProducto(nombre="hamburguesa sencilla", cantidad=1)])
        sesion.actualizar_con_extraccion(ext_1)
        subtotal_1 = sesion.resumen_cotizacion.subtotal_productos

        # Corrección: 2 hamburguesas dobles
        ext_2 = ExtraccionPedido(productos=[ItemProducto(nombre="hamburguesa doble carne", cantidad=2)])
        sesion.actualizar_con_extraccion(ext_2)
        subtotal_2 = sesion.resumen_cotizacion.subtotal_productos

        self.assertGreater(subtotal_2, subtotal_1)
        self.assertEqual(len(sesion.productos), 1)
        self.assertEqual(sesion.productos[0].cantidad, 2)

    def test_multiples_sesiones_independientes(self):
        chat_1 = "user_1"
        chat_2 = "user_2"

        # User 1 pide hamburguesas
        self.gestor.procesar_extraccion(
            chat_1,
            ExtraccionPedido(productos=[ItemProducto(nombre="hamburguesa sencilla", cantidad=1)])
        )

        # User 2 solo saluda
        self.gestor.procesar_extraccion(
            chat_2,
            ExtraccionPedido(nombre_cliente="Andrés", productos=[])
        )

        sesion_1 = self.gestor.obtener_o_crear_sesion(chat_1)
        sesion_2 = self.gestor.obtener_o_crear_sesion(chat_2)

        self.assertEqual(sesion_1.estado, EstadoFlujo.ESPERO_DIRECCION)
        self.assertEqual(sesion_2.estado, EstadoFlujo.ESPERO_PRODUCTOS)
        self.assertEqual(sesion_2.nombre_cliente, "Andrés")
        self.assertIsNone(sesion_1.nombre_cliente)


if __name__ == "__main__":
    unittest.main()
