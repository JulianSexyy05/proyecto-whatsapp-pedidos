"""
Pruebas unitarias para core/ia_parser.py
"""

import unittest
from unittest.mock import AsyncMock, MagicMock
from core.ia_parser import (
    ExtraccionPedido,
    ItemProducto,
    GeminiParserError,
    _limpiar_json_markdown,
    extraer_pedido_whatsapp
)


class TestExtraccionPedido(unittest.IsolatedAsyncioTestCase):

    def test_schema_validation_valid(self):
        data = {
            "nombre_cliente": "Pedro Pérez",
            "productos": [
                {"nombre": "Empanada de carne", "cantidad": 5},
                {"nombre": "Jugo de maracuyá", "cantidad": 2}
            ],
            "direccion_entrega": "Avenida Siempre Viva 742",
            "metodo_pago": "Efectivo",
            "confianza_extraccion": 0.95
        }
        pedido = ExtraccionPedido.model_validate(data)
        self.assertEqual(pedido.nombre_cliente, "Pedro Pérez")
        self.assertEqual(len(pedido.productos), 2)
        self.assertEqual(pedido.productos[0].cantidad, 5)
        self.assertEqual(pedido.metodo_pago, "Efectivo")
        self.assertAlmostEqual(pedido.confianza_extraccion, 0.95)

    def test_schema_defaults(self):
        data = {}
        pedido = ExtraccionPedido.model_validate(data)
        self.assertIsNone(pedido.nombre_cliente)
        self.assertEqual(pedido.productos, [])
        self.assertIsNone(pedido.direccion_entrega)
        self.assertIsNone(pedido.metodo_pago)
        self.assertEqual(pedido.confianza_extraccion, 1.0)

    def test_limpiar_json_markdown(self):
        con_bloque = "```json\n{\"cliente\": \"Juan\"}\n```"
        sin_bloque = "{\"cliente\": \"Juan\"}"
        self.assertEqual(_limpiar_json_markdown(con_bloque), sin_bloque)
        self.assertEqual(_limpiar_json_markdown(sin_bloque), sin_bloque)

    async def test_respuesta_vacia_levanta_gemini_parser_error(self):
        mock_response = MagicMock()
        mock_response.text = ""

        mock_generate_content = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = mock_generate_content

        with self.assertRaises(GeminiParserError):
            await extraer_pedido_whatsapp("Hola", client=mock_client)

    async def test_error_api_levanta_gemini_parser_error(self):
        mock_generate_content = AsyncMock(side_effect=RuntimeError("Connection timeout"))
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = mock_generate_content

        with self.assertRaises(GeminiParserError):
            await extraer_pedido_whatsapp("Hola", client=mock_client)

    def test_extraer_pedido_whatsapp_sync(self):
        from core.ia_parser import extraer_pedido_whatsapp_sync
        mock_response = MagicMock()
        mock_response.text = '{"nombre_cliente": "Sara", "productos": [{"nombre": "pizza", "cantidad": 1}], "direccion_entrega": "Calle 1", "metodo_pago": "Nequi", "confianza_extraccion": 0.99}'

        mock_generate_content = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = mock_generate_content

        resultado = extraer_pedido_whatsapp_sync("Quiero 1 pizza", client=mock_client)
        self.assertEqual(resultado.nombre_cliente, "Sara")
        self.assertEqual(len(resultado.productos), 1)


if __name__ == "__main__":
    unittest.main()

