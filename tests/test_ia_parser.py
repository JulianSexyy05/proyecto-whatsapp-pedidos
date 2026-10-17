"""
Pruebas unitarias para core/ia_parser.py
"""

import unittest
from core.ia_parser import ExtraccionPedido, ItemProducto


class TestExtraccionPedido(unittest.TestCase):

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


if __name__ == "__main__":
    unittest.main()
