"""
Script de Integración del Pipeline Completo de Pedidos de WhatsApp (core/test_pipeline.py).
Simula una conversación conversacional de múltiples mensajes desde el saludo inicial
hasta la confirmación de la orden, validando que el payload final cumpla con el esquema
estructurado listo para la integración con el Socio 2 (Base de Datos / Cocina / Despacho).

Compatible con:
  - pytest core/test_pipeline.py -v
  - python core/test_pipeline.py
"""

import os
import sys
import json
import unittest
from datetime import datetime

# Ajuste de path para importaciones
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.ia_parser import ExtraccionPedido, ItemProducto
from core.conversation_state import (
    EstadoFlujo,
    SesionPedido,
    GestorConversaciones,
    OrdenSocio2,
    ItemOrdenSocio2
)
from core.cotizador import formatear_pesos

# Soporte de emojis en consola Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


class TestPipelineIntegracionSocio2(unittest.TestCase):

    def setUp(self):
        self.gestor = GestorConversaciones()
        self.chat_id_cliente = "573129876543"

    def test_pipeline_completo_multi_turno(self):
        """
        Simula los 5 turnos de conversación de un cliente real y valida
        las transiciones de estado y la generación del esquema final para el Socio 2.
        """
        print("\n" + "=" * 70)
        print("INICIANDO SIMULACIÓN DE INTEGRACIÓN DEL PIPELINE DE VENTAS (SOCIO 2)")
        print("=" * 70)

        # -------------------------------------------------------------
        # TURNO 1: Saludo inicial del cliente (sin productos)
        # -------------------------------------------------------------
        msg_1 = "Hola buenas tardes! Quisiera hacer un pedido por favor. Mi nombre es Valentina Ríos."
        ext_1 = ExtraccionPedido(
            nombre_cliente="Valentina Ríos",
            productos=[],
            direccion_entrega=None,
            metodo_pago=None,
            confianza_extraccion=0.9
        )
        estado_1, bot_resp_1 = self.gestor.procesar_extraccion(self.chat_id_cliente, ext_1, msg_1)

        print(f"\n[TURNO 1]")
        print(f"Cliente: \"{msg_1}\"")
        print(f"-> Estado Máquina: {estado_1.value}")
        print(f"-> Respuesta Bot: {bot_resp_1}")

        self.assertEqual(estado_1, EstadoFlujo.ESPERO_PRODUCTOS)
        self.assertIn("Valentina Ríos", bot_resp_1)

        # -------------------------------------------------------------
        # TURNO 2: Cliente indica productos iniciales
        # -------------------------------------------------------------
        msg_2 = "Me gustaría pedir 2 hamburguesas especiales y 1 porción de papas rústicas por favor."
        ext_2 = ExtraccionPedido(
            productos=[
                ItemProducto(nombre="hamburguesa especial", cantidad=2),
                ItemProducto(nombre="porción de papas rústicas", cantidad=1)
            ],
            confianza_extraccion=0.98
        )
        estado_2, bot_resp_2 = self.gestor.procesar_extraccion(self.chat_id_cliente, ext_2, msg_2)

        print(f"\n[TURNO 2]")
        print(f"Cliente: \"{msg_2}\"")
        print(f"-> Estado Máquina: {estado_2.value}")
        print(f"-> Respuesta Bot: {bot_resp_2}")

        self.assertEqual(estado_2, EstadoFlujo.ESPERO_DIRECCION)
        self.assertIn("dirección", bot_resp_2.lower())

        # -------------------------------------------------------------
        # TURNO 3: Cliente corrige pedido (1 doble carne, 1 especial, papas y 2 cocacolas)
        # -------------------------------------------------------------
        msg_3 = "Ah espera, cámbiame 1 hamburguesa especial por una hamburguesa doble carne y añade 2 Coca-Colas Zero."
        ext_3 = ExtraccionPedido(
            productos=[
                ItemProducto(nombre="hamburguesa especial", cantidad=1),
                ItemProducto(nombre="hamburguesa doble carne", cantidad=1),
                ItemProducto(nombre="porción de papas rústicas", cantidad=1),
                ItemProducto(nombre="gaseosa coca-cola zero", cantidad=2)
            ],
            confianza_extraccion=0.99
        )
        estado_3, bot_resp_3 = self.gestor.procesar_extraccion(self.chat_id_cliente, ext_3, msg_3)

        print(f"\n[TURNO 3]")
        print(f"Cliente: \"{msg_3}\"")
        print(f"-> Estado Máquina: {estado_3.value}")
        print(f"-> Respuesta Bot: {bot_resp_3}")

        # Sigue esperando dirección pero con los productos actualizados
        self.assertEqual(estado_3, EstadoFlujo.ESPERO_DIRECCION)
        sesion = self.gestor.obtener_o_crear_sesion(self.chat_id_cliente)
        self.assertEqual(len(sesion.productos), 4)
        self.assertEqual(sum(p.cantidad for p in sesion.productos), 5)

        # -------------------------------------------------------------
        # TURNO 4: Cliente proporciona dirección de entrega
        # -------------------------------------------------------------
        msg_4 = "Es para enviar a la Carrera 11 # 93-25 Apto 401, Barrio Chico."
        ext_4 = ExtraccionPedido(
            direccion_entrega="Carrera 11 # 93-25 Apto 401, Barrio Chico",
            confianza_extraccion=0.98
        )
        estado_4, bot_resp_4 = self.gestor.procesar_extraccion(self.chat_id_cliente, ext_4, msg_4)

        print(f"\n[TURNO 4]")
        print(f"Cliente: \"{msg_4}\"")
        print(f"-> Estado Máquina: {estado_4.value}")
        print(f"-> Respuesta Bot:\n{bot_resp_4}")

        self.assertEqual(estado_4, EstadoFlujo.ESPERO_PAGO)
        self.assertIn("Carrera 11 # 93-25", bot_resp_4)
        self.assertIn("pago", bot_resp_4.lower())

        # -------------------------------------------------------------
        # TURNO 5: Cliente define método de pago -> CIERRE DE VENTA
        # -------------------------------------------------------------
        msg_5 = "Voy a pagar por Nequi cuando me pasen los datos."
        ext_5 = ExtraccionPedido(
            metodo_pago="Nequi",
            confianza_extraccion=0.99
        )
        estado_5, bot_resp_5 = self.gestor.procesar_extraccion(self.chat_id_cliente, ext_5, msg_5)

        print(f"\n[TURNO 5]")
        print(f"Cliente: \"{msg_5}\"")
        print(f"-> Estado Máquina: {estado_5.value}")
        print(f"-> Respuesta Bot:\n{bot_resp_5}")

        self.assertEqual(estado_5, EstadoFlujo.COMPLETADO)
        self.assertIn("confirmado", bot_resp_5.lower())

        # -------------------------------------------------------------
        # VALIDACIÓN DEL ESQUEMA FINAL PARA EL SOCIO 2
        # -------------------------------------------------------------
        orden_socio2 = sesion.generar_orden_socio2()

        print("\n" + "=" * 70)
        print("ORDEN ESTRUCTURADA GENERADA PARA EL SOCIO 2 (BACKEND / COCINA)")
        print("=" * 70)
        print(orden_socio2.model_dump_json(indent=2))

        # Aserciones exhaustivas sobre el contrato de datos del Socio 2
        self.assertIsInstance(orden_socio2, OrdenSocio2)
        self.assertTrue(orden_socio2.id_orden.startswith("ORD-"))
        self.assertEqual(orden_socio2.chat_id, self.chat_id_cliente)
        self.assertEqual(orden_socio2.cliente, "Valentina Ríos")
        self.assertEqual(orden_socio2.direccion_entrega, "Carrera 11 # 93-25 Apto 401, Barrio Chico")
        self.assertEqual(orden_socio2.metodo_pago, "Nequi")
        self.assertEqual(orden_socio2.estado_orden, "CONFIRMADA_COCINA")

        # Validación de productos
        self.assertEqual(len(orden_socio2.productos), 4)
        self.assertEqual(orden_socio2.total_unidades, 5)

        # Validación de cálculos financieros
        # 1x Hamburguesa especial (22000) + 1x Hamburguesa doble (27000) + 1x Papas rústicas (8000) + 2x Coca-Cola (10000) = 67000
        # Costo envío = 5000 -> Total = 72000
        self.assertEqual(orden_socio2.subtotal_productos, 67000.0)
        self.assertEqual(orden_socio2.costo_envio, 5000.0)
        self.assertEqual(orden_socio2.total_a_pagar, 72000.0)

        # Validación de serialización JSON libre de errores
        json_dict = json.loads(orden_socio2.model_dump_json())
        self.assertIn("id_orden", json_dict)
        self.assertIn("productos", json_dict)
        self.assertIn("total_a_pagar", json_dict)
        self.assertIsInstance(json_dict["productos"], list)
        self.assertGreater(len(json_dict["productos"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
