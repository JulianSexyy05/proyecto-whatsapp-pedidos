"""
Pruebas de endpoints del servidor FastAPI (app.py).
"""

import unittest
from unittest.mock import AsyncMock, patch
from starlette.testclient import TestClient

from app import app
from core.ia_parser import ExtraccionPedido, ItemProducto
from core.ocr_pagos import ComprobantePago, EstadoValidacion


class TestFastAPIApp(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_root_endpoint(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "online")
        self.assertEqual(data["service"], "WhatsApp Pedidos IA Engine")

    @patch("app.extraer_pedido_whatsapp", new_callable=AsyncMock)
    def test_webhook_whatsapp_pedido_incompleto(self, mock_extraer):
        mock_extraer.return_value = ExtraccionPedido(
            nombre_cliente="Carlos",
            productos=[ItemProducto(nombre="hamburguesa especial", cantidad=2)],
            direccion_entrega=None,
            metodo_pago=None
        )

        response = self.client.post(
            "/webhook/whatsapp",
            json={
                "chat_id": "test_chat_001",
                "mensaje_texto": "Quiero 2 hamburguesas especiales"
            }
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["chat_id"], "test_chat_001")
        self.assertEqual(data["estado_actual"], "ESPERO_DIRECCION")
        self.assertTrue(len(data["respuesta_whatsapp"]) > 0)
        self.assertIsNone(data["orden_confirmada"])

    @patch("app.procesar_comprobante_pago", new_callable=AsyncMock)
    def test_validar_comprobante_endpoint(self, mock_ocr):
        mock_ocr.return_value = ComprobantePago(
            banco_emisor="Nequi",
            numero_referencia="M12345678",
            monto_pagado=50000.0,
            estado_validacion=EstadoValidacion.EXITOSO
        )

        fake_image = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
        response = self.client.post(
            "/api/pagos/validar-comprobante",
            files={"file": ("comprobante.png", fake_image, "image/png")}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["banco_emisor"], "Nequi")
        self.assertEqual(data["numero_referencia"], "M12345678")
        self.assertEqual(data["monto_pagado"], 50000.0)
        self.assertEqual(data["estado_validacion"], "exitoso")


if __name__ == "__main__":
    unittest.main()
