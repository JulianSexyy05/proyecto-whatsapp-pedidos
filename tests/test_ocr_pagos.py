"""
Pruebas unitarias para core/ocr_pagos.py
"""

import os
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from core.ocr_pagos import (
    ComprobantePago,
    EstadoValidacion,
    procesar_comprobante_pago,
    _determinar_mime_type
)


class TestOCRPagos(unittest.IsolatedAsyncioTestCase):

    def test_schema_comprobante_valido(self):
        data = {
            "banco_emisor": "Nequi",
            "numero_referencia": "M98765432",
            "monto_pagado": 48500.0,
            "moneda": "COP",
            "fecha_hora": "17/10/2026 14:15",
            "cuenta_destino": "3001234567",
            "nombre_destinatario": "Tienda WhatsApp",
            "estado_validacion": "exitoso",
            "confianza_ocr": 0.98,
            "observaciones": "Comprobante auténtico"
        }
        comprobante = ComprobantePago.model_validate(data)
        self.assertEqual(comprobante.banco_emisor, "Nequi")
        self.assertEqual(comprobante.numero_referencia, "M98765432")
        self.assertEqual(comprobante.monto_pagado, 48500.0)
        self.assertEqual(comprobante.estado_validacion, EstadoValidacion.EXITOSO)
        self.assertAlmostEqual(comprobante.confianza_ocr, 0.98)

    def test_schema_estados_validacion(self):
        for estado in ["exitoso", "pendiente", "rechazado", "posible_adulteracion", "dudoso_o_ilegible"]:
            comprobante = ComprobantePago(estado_validacion=EstadoValidacion(estado))
            self.assertEqual(comprobante.estado_validacion.value, estado)

    def test_deteccion_mime_type(self):
        self.assertEqual(_determinar_mime_type("comprobante.png"), "image/png")
        self.assertEqual(_determinar_mime_type("recibo.jpg"), "image/jpeg")
        self.assertEqual(_determinar_mime_type("recibo.jpeg"), "image/jpeg")
        self.assertEqual(_determinar_mime_type("captura.webp"), "image/webp")
        # Bytes PNG
        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00"
        self.assertEqual(_determinar_mime_type(png_bytes), "image/png")

    async def test_procesar_comprobante_con_mock(self):
        mock_data = {
            "banco_emisor": "Bancolombia",
            "numero_referencia": "0001238475",
            "monto_pagado": 125000.0,
            "moneda": "COP",
            "fecha_hora": "17/10/2026 13:45",
            "cuenta_destino": "987-654321-00",
            "nombre_destinatario": "Comercio Asociado",
            "estado_validacion": "exitoso",
            "confianza_ocr": 0.99,
            "observaciones": "Transferencia QR Bancolombia verificada"
        }

        mock_response = MagicMock()
        mock_response.text = json.dumps(mock_data)

        mock_generate_content = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = mock_generate_content

        fake_image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50

        resultado = await procesar_comprobante_pago(
            origen_imagen=fake_image_bytes,
            client=mock_client
        )

        self.assertIsInstance(resultado, ComprobantePago)
        self.assertEqual(resultado.banco_emisor, "Bancolombia")
        self.assertEqual(resultado.numero_referencia, "0001238475")
        self.assertEqual(resultado.monto_pagado, 125000.0)
        self.assertEqual(resultado.estado_validacion, EstadoValidacion.EXITOSO)

    async def test_archivo_no_existente_levanta_error(self):
        with self.assertRaises(FileNotFoundError):
            await procesar_comprobante_pago("ruta/inexistente/no_existe.png")

    async def test_respuesta_vacia_levanta_gemini_ocr_error(self):
        from core.ocr_pagos import GeminiOCRError
        mock_response = MagicMock()
        mock_response.text = ""

        mock_generate_content = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = mock_generate_content

        fake_image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        with self.assertRaises(GeminiOCRError):
            await procesar_comprobante_pago(fake_image_bytes, client=mock_client)

    async def test_error_api_levanta_gemini_ocr_error(self):
        from core.ocr_pagos import GeminiOCRError
        mock_generate_content = AsyncMock(side_effect=RuntimeError("Google GenAI Server Error"))
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = mock_generate_content

        fake_image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        with self.assertRaises(GeminiOCRError):
            await procesar_comprobante_pago(fake_image_bytes, client=mock_client)


if __name__ == "__main__":
    unittest.main()

