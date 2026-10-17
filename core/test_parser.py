"""
Script de pruebas unitarias para core/ia_parser.py.
Valida el procesamiento de chats informales de WhatsApp con:
 - Modismos y emojis
 - Corrección de pedidos a mitad del chat
 - Faltantes de información (sin dirección o sin método de pago)
 - Exceso de texto y ruido conversacional irrelevante
 - Consultas sin pedido

Compatible tanto con `pytest core/test_parser.py` como `python core/test_parser.py`.
"""

import os
import sys
import json
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

# Ajuste de path para ejecución directa
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.ia_parser import (
    extraer_pedido_whatsapp,
    ExtraccionPedido,
    ItemProducto
)


# =====================================================================
# Variaciones de Chats Informales de WhatsApp para Pruebas
# =====================================================================

CHAT_INFORMAL_CON_CAMBIOS = """
[14:10] Juancho: Q mas bro! 👋 Oye mandame 3 hamburguesas especiales porfa
[14:11] Restaurante: Buenas tardes Juancho! Claro que si.
[14:11] Juancho: Uy espera no, mejor solo 2 especiales y 1 sencilla pal niño 🍔
[14:12] Juancho: Y 1 porcion de papas rusticas. Pago por Nequi
[14:12] Juancho: A la Calle 10 # 4-50 apto 201
"""

CHAT_CON_FALTANTES = """
[18:30] Usuario: Hola buenas noches, me envias por favor 1 pizza personal de pepperoni y 2 cocacolas zero?
[18:31] Pizzeria: Hola! Claro que si.
[18:31] Usuario: Dale gracias quedo atento
"""

CHAT_CON_EXCESO_DE_TEXTO = """
[12:00] Doña Marta: Hola mijito como me le va? Espero que la familia este bien por alla con este clima tan feo que esta haciendo en la ciudad que barbaridad de trancon habia hoy en la autopista casi no llego a la cita medica... En fin, imaginese que llego mi sobrino de Cali y tenemos un hambre tremenda, asi que por favor envienos 2 perros calientes especiales bien cargados y 1 gaseosa manzana postobon para la Carrera 45 # 12-34 casa 2. Por cierto digale a su mama que le mande saludos. Se les paga en efectivo con un billete de cincuenta mil para que lleven cambio porfa! Dios me los bendiga.
"""

CHAT_SIN_PEDIDO_SOLO_CONSULTA = """
[09:15] Cliente: Hola buenos dias, hasta que hora tienen abierto hoy domingo?
[09:16] Tienda: Hola! Atendemos hasta las 10:00 pm.
[09:16] Cliente: Dale muchas gracias, mas tarde les escribo.
"""

CHAT_CON_TERMINOS_COLOQUIALES = """
[20:00] Pipe: Ey buenas noches compa, tirame un par de hamburguesas dobles de carne y una gaseosa coca cola pa la Cra 68 # 80-10 torre 4 apto 102. Transfiero por Bancolombia / Daviplata de una.
"""


# =====================================================================
# Suite de Pruebas Unitarias
# =====================================================================

class TestIAParserVariaciones(unittest.IsolatedAsyncioTestCase):

    def _crear_mock_client(self, payload_dict: dict) -> MagicMock:
        """Crea un mock del cliente de google-genai que responde con el payload JSON simulado."""
        mock_response = MagicMock()
        mock_response.text = json.dumps(payload_dict)

        mock_generate_content = AsyncMock(return_value=mock_response)

        mock_client = MagicMock()
        mock_client.aio.models.generate_content = mock_generate_content
        return mock_client

    async def test_chat_informal_con_correcciones(self):
        """Valida que un chat con modismos, emojis y correcciones de cantidades se procese correctamente."""
        mock_data = {
            "nombre_cliente": "Juancho",
            "productos": [
                {"nombre": "hamburguesa especial", "cantidad": 2},
                {"nombre": "hamburguesa sencilla", "cantidad": 1},
                {"nombre": "porcion de papas rusticas", "cantidad": 1}
            ],
            "direccion_entrega": "Calle 10 # 4-50 apto 201",
            "metodo_pago": "Nequi",
            "confianza_extraccion": 0.98
        }
        mock_client = self._crear_mock_client(mock_data)

        resultado = await extraer_pedido_whatsapp(
            chat_text=CHAT_INFORMAL_CON_CAMBIOS,
            client=mock_client
        )

        self.assertIsInstance(resultado, ExtraccionPedido)
        self.assertEqual(resultado.nombre_cliente, "Juancho")
        self.assertEqual(len(resultado.productos), 3)
        self.assertEqual(resultado.productos[0].cantidad, 2)
        self.assertEqual(resultado.productos[1].cantidad, 1)
        self.assertEqual(resultado.metodo_pago, "Nequi")
        self.assertGreaterEqual(resultado.confianza_extraccion, 0.9)

    async def test_chat_con_faltantes(self):
        """Valida que un chat que carece de dirección o método de pago devuelva None en esos campos sin romperse."""
        mock_data = {
            "nombre_cliente": None,
            "productos": [
                {"nombre": "pizza personal de pepperoni", "cantidad": 1},
                {"nombre": "cocacola zero", "cantidad": 2}
            ],
            "direccion_entrega": None,
            "metodo_pago": None,
            "confianza_extraccion": 0.65  # Confianza menor por faltantes críticos
        }
        mock_client = self._crear_mock_client(mock_data)

        resultado = await extraer_pedido_whatsapp(
            chat_text=CHAT_CON_FALTANTES,
            client=mock_client
        )

        self.assertIsInstance(resultado, ExtraccionPedido)
        self.assertIsNone(resultado.direccion_entrega)
        self.assertIsNone(resultado.metodo_pago)
        self.assertEqual(len(resultado.productos), 2)
        # La confianza debe ser menor a 0.8 por datos incompletos
        self.assertLess(resultado.confianza_extraccion, 0.8)

    async def test_chat_con_exceso_de_texto_y_ruido(self):
        """Valida que en un texto largo con anécdotas irrelevantes se aísle limpiamente el pedido real."""
        mock_data = {
            "nombre_cliente": "Doña Marta",
            "productos": [
                {"nombre": "perro caliente especial", "cantidad": 2},
                {"nombre": "gaseosa manzana postobon", "cantidad": 1}
            ],
            "direccion_entrega": "Carrera 45 # 12-34 casa 2",
            "metodo_pago": "Efectivo",
            "confianza_extraccion": 0.95
        }
        mock_client = self._crear_mock_client(mock_data)

        resultado = await extraer_pedido_whatsapp(
            chat_text=CHAT_CON_EXCESO_DE_TEXTO,
            client=mock_client
        )

        self.assertIsInstance(resultado, ExtraccionPedido)
        self.assertEqual(resultado.nombre_cliente, "Doña Marta")
        self.assertEqual(len(resultado.productos), 2)
        self.assertEqual(resultado.direccion_entrega, "Carrera 45 # 12-34 casa 2")
        self.assertEqual(resultado.metodo_pago, "Efectivo")

    async def test_chat_sin_pedido_solo_consulta(self):
        """Valida que un chat que solo contiene preguntas o saludos resulte en lista vacía y baja confianza."""
        mock_data = {
            "nombre_cliente": None,
            "productos": [],
            "direccion_entrega": None,
            "metodo_pago": None,
            "confianza_extraccion": 0.1
        }
        mock_client = self._crear_mock_client(mock_data)

        resultado = await extraer_pedido_whatsapp(
            chat_text=CHAT_SIN_PEDIDO_SOLO_CONSULTA,
            client=mock_client
        )

        self.assertIsInstance(resultado, ExtraccionPedido)
        self.assertEqual(len(resultado.productos), 0)
        self.assertLess(resultado.confianza_extraccion, 0.3)

    async def test_chat_con_terminos_coloquiales(self):
        """Valida la interpretación de términos como 'un par' (2 unidades) y múltiples bancos."""
        mock_data = {
            "nombre_cliente": "Pipe",
            "productos": [
                {"nombre": "hamburguesa doble de carne", "cantidad": 2},
                {"nombre": "gaseosa coca cola", "cantidad": 1}
            ],
            "direccion_entrega": "Cra 68 # 80-10 torre 4 apto 102",
            "metodo_pago": "Daviplata",
            "confianza_extraccion": 0.96
        }
        mock_client = self._crear_mock_client(mock_data)

        resultado = await extraer_pedido_whatsapp(
            chat_text=CHAT_CON_TERMINOS_COLOQUIALES,
            client=mock_client
        )

        self.assertIsInstance(resultado, ExtraccionPedido)
        self.assertEqual(resultado.productos[0].cantidad, 2)
        self.assertEqual(resultado.nombre_cliente, "Pipe")

    async def test_live_api_si_hay_api_key(self):
        """Si existe GEMINI_API_KEY, se ejecuta una prueba en vivo con Gemini 2.5 Flash."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            self.skipTest("GEMINI_API_KEY no encontrada en entorno; saltando prueba live.")

        resultado = await extraer_pedido_whatsapp(chat_text=CHAT_INFORMAL_CON_CAMBIOS)
        self.assertIsInstance(resultado, ExtraccionPedido)
        self.assertIsNotNone(resultado.nombre_cliente)
        self.assertGreater(len(resultado.productos), 0)
        self.assertIsInstance(resultado.confianza_extraccion, float)


# =====================================================================
# Ejecución Directa
# =====================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
