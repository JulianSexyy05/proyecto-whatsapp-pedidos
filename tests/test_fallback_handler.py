"""
Pruebas unitarias para core/fallback_handler.py
"""

import unittest
from unittest.mock import AsyncMock, MagicMock

from core.ia_parser import ExtraccionPedido, ItemProducto
from core.fallback_handler import (
    evaluar_necesidad_fallback,
    generar_mensaje_fallback,
    generar_mensaje_fallback_sync,
    ResultadoFallback
)


class TestFallbackHandler(unittest.IsolatedAsyncioTestCase):

    def test_evaluar_falta_productos(self):
        ext = ExtraccionPedido(nombre_cliente="Ana", productos=[])
        necesita, prioritario, faltantes = evaluar_necesidad_fallback(ext)
        self.assertTrue(necesita)
        self.assertEqual(prioritario, "productos")
        self.assertIn("productos", faltantes)

    def test_evaluar_falta_direccion(self):
        ext = ExtraccionPedido(
            nombre_cliente="Ana",
            productos=[ItemProducto(nombre="pizza personal", cantidad=1)],
            direccion_entrega=None,
            metodo_pago=None
        )
        necesita, prioritario, faltantes = evaluar_necesidad_fallback(ext)
        self.assertTrue(necesita)
        self.assertEqual(prioritario, "direccion_entrega")
        self.assertIn("direccion_entrega", faltantes)
        self.assertIn("metodo_pago", faltantes)

    def test_evaluar_falta_pago(self):
        ext = ExtraccionPedido(
            nombre_cliente="Ana",
            productos=[ItemProducto(nombre="pizza personal", cantidad=1)],
            direccion_entrega="Calle 10 # 20-30",
            metodo_pago=None
        )
        necesita, prioritario, faltantes = evaluar_necesidad_fallback(ext)
        self.assertTrue(necesita)
        self.assertEqual(prioritario, "metodo_pago")
        self.assertEqual(faltantes, ["metodo_pago"])

    def test_evaluar_baja_confianza(self):
        ext = ExtraccionPedido(
            nombre_cliente="Ana",
            productos=[ItemProducto(nombre="algo", cantidad=1)],
            direccion_entrega="Calle 10 # 20-30",
            metodo_pago="Efectivo",
            confianza_extraccion=0.5
        )
        necesita, prioritario, faltantes = evaluar_necesidad_fallback(ext, umbral_confianza=0.75)
        self.assertTrue(necesita)
        self.assertEqual(prioritario, "aclaracion")

    def test_evaluar_orden_completa_alta_confianza(self):
        ext = ExtraccionPedido(
            nombre_cliente="Ana",
            productos=[ItemProducto(nombre="pizza", cantidad=1)],
            direccion_entrega="Calle 10 # 20-30",
            metodo_pago="Efectivo",
            confianza_extraccion=0.95
        )
        necesita, prioritario, faltantes = evaluar_necesidad_fallback(ext)
        self.assertFalse(necesita)
        self.assertIsNone(prioritario)
        self.assertEqual(faltantes, [])

    async def test_generar_mensaje_fallback_con_mock_gemini(self):
        ext = ExtraccionPedido(
            nombre_cliente="Carlos",
            productos=[ItemProducto(nombre="hamburguesa especial", cantidad=2)],
            direccion_entrega=None
        )

        mock_response = MagicMock()
        mock_response.text = "¡Hola Carlos! Ya tengo anotadas tus 2 hamburguesas especiales. ¿A qué dirección te las llevamos? 📍"

        mock_generate_content = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = mock_generate_content

        resultado = await generar_mensaje_fallback(
            extraccion=ext,
            client=mock_client
        )

        self.assertIsInstance(resultado, ResultadoFallback)
        self.assertTrue(resultado.necesita_fallback)
        self.assertEqual(resultado.campo_prioritario, "direccion_entrega")
        self.assertTrue(resultado.generado_por_ia)
        self.assertIn("Carlos", resultado.mensaje_whatsapp)
        self.assertIn("dirección", resultado.mensaje_whatsapp.lower())

    def test_generar_mensaje_fallback_sync_plantilla(self):
        ext = ExtraccionPedido(
            nombre_cliente="Diana",
            productos=[ItemProducto(nombre="empanada", cantidad=3)],
            direccion_entrega="Cra 15 # 45-20",
            metodo_pago=None
        )
        resultado = generar_mensaje_fallback_sync(ext, client=None, api_key=None)
        self.assertTrue(resultado.necesita_fallback)
        self.assertEqual(resultado.campo_prioritario, "metodo_pago")
        self.assertFalse(resultado.generado_por_ia)
        self.assertIn("Diana", resultado.mensaje_whatsapp)
        self.assertIn("Nequi", resultado.mensaje_whatsapp)


if __name__ == "__main__":
    unittest.main()
