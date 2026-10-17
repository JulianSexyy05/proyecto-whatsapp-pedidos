"""
Pruebas unitarias para core/cotizador.py
"""

import unittest
from core.ia_parser import ItemProducto, ExtraccionPedido
from core.cotizador import cotizar_pedido, ResumenCotizacion, CATALOGO_PRECIOS_BASE


class TestCotizador(unittest.TestCase):

    def test_cotizacion_calculo_exacto(self):
        items = [
            ItemProducto(nombre="pizza personal de pepperoni", cantidad=2),  # 18000 * 2 = 36000
            ItemProducto(nombre="gaseosa coca-cola zero", cantidad=1),       # 5000 * 1 = 5000
        ]
        resumen = cotizar_pedido(
            productos=items,
            costo_envio=5000.0,
            nombre_cliente="Juan",
            direccion_entrega="Calle 100 # 20-30",
            metodo_pago="Efectivo"
        )
        self.assertIsInstance(resumen, ResumenCotizacion)
        self.assertEqual(resumen.subtotal_productos, 41000.0)
        self.assertEqual(resumen.costo_envio, 5000.0)
        self.assertEqual(resumen.total_a_pagar, 46000.0)
        self.assertIn("Juan", resumen.mensaje_whatsapp)
        self.assertIn("Calle 100 # 20-30", resumen.mensaje_whatsapp)
        self.assertIn("Efectivo", resumen.mensaje_whatsapp)
        self.assertIn("$46.000", resumen.mensaje_whatsapp)

    def test_cotizacion_desde_extraccion_pedido(self):
        pedido = ExtraccionPedido(
            nombre_cliente="Carlos",
            productos=[
                ItemProducto(nombre="hamburguesa doble carne", cantidad=1), # 27000
                ItemProducto(nombre="papas rusticas", cantidad=1),          # 8000 (matching parcial)
            ],
            direccion_entrega="Av 68 # 45-10",
            metodo_pago="Nequi",
            confianza_extraccion=0.9
        )
        resumen = cotizar_pedido(pedido, costo_envio=4000.0)
        self.assertEqual(resumen.subtotal_productos, 35000.0)
        self.assertEqual(resumen.total_a_pagar, 39000.0)
        self.assertIn("Carlos", resumen.mensaje_whatsapp)
        self.assertIn("Nequi", resumen.mensaje_whatsapp)

    def test_item_no_encontrado_en_catalogo(self):
        items = [
            ItemProducto(nombre="ceviche de camaron", cantidad=1)
        ]
        resumen = cotizar_pedido(items, costo_envio=5000.0)
        self.assertEqual(len(resumen.items_no_disponibles), 1)
        self.assertIn("ceviche de camaron", resumen.items_no_disponibles)
        self.assertIn("Precio por confirmar", resumen.mensaje_whatsapp)


if __name__ == "__main__":
    unittest.main()
