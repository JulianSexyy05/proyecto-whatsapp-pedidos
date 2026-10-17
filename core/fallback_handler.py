"""
Módulo de Gestión de Fallback y Recuperación Conversacional (core/fallback_handler.py).
Detecta información incompleta o baja confianza de extracción en ia_parser.py
y utiliza Gemini para redactar respuestas persuasivas y humanas solicitando
únicamente el dato faltante por WhatsApp.
"""

import sys
import os
import asyncio
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field
from google import genai
from google.genai import types, errors


# Compatibilidad de importación
try:
    from core.ia_parser import ExtraccionPedido, ItemProducto
except ModuleNotFoundError:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from core.ia_parser import ExtraccionPedido, ItemProducto

# Soporte de emojis en consola Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


# =====================================================================
# 1. Configuración de Umbrales y Modelos Pydantic
# =====================================================================

UMBRAL_CONFIANZA_DEFAULT: float = 0.75


class ResultadoFallback(BaseModel):
    necesita_fallback: bool = Field(
        description="True si la orden carece de datos obligatorios o la confianza es baja"
    )
    motivo: Optional[str] = Field(
        default=None,
        description="Razón por la cual se activó el fallback (campo faltante o baja confianza)"
    )
    campo_prioritario: Optional[str] = Field(
        default=None,
        description="Campo clave que debe solicitarse al cliente ('productos', 'direccion_entrega', 'metodo_pago' o 'aclaracion')"
    )
    campos_faltantes: List[str] = Field(
        default_factory=list,
        description="Lista completa de campos obligatorios que aún no se tienen"
    )
    mensaje_whatsapp: str = Field(
        description="Mensaje persuasivo y natural listo para ser enviado al cliente"
    )
    generado_por_ia: bool = Field(
        default=False,
        description="Indica si el mensaje fue generado mediante llamada a Gemini o por plantilla de respaldo"
    )


# =====================================================================
# 2. Prompts del Sistema para Fallback con Gemini
# =====================================================================

SYSTEM_PROMPT_FALLBACK = """
Eres un Asistente Senior de Atención y Ventas por WhatsApp para un negocio de comidas y delivery.
Tu tono es completamente natural, amable, cálido, empático y directo (estilo conversacional colombiano / latinoamericano).

Tu único objetivo es formular una respuesta breve de WhatsApp pidiéndole al cliente EXCLUSIVAMENTE el dato faltante para avanzar en su pedido, o pidiéndole una aclaración amable si la extracción fue ambigua o de baja certeza.

Reglas obligatorias:
1. Tono y Estilo: Habla de manera natural, amable y directa. Máximo 2 a 3 líneas. En WhatsApp los clientes valoran la agilidad y calidez.
2. Formato WhatsApp: Emplea *negritas* para palabras clave y 1 o 2 emojis atractivos (ej. 📍, 🍔, 🛵, 💳).
3. Personalización: Si se conoce el nombre del cliente, salúdalo por su nombre de forma cercana.
4. Reconocimiento: Si ya sabemos qué productos quiere, menciona brevemente que ya los tienes anotados para que el cliente se sienta escuchado.
5. Foco Exclusivo: Pide ÚNICAMENTE el dato prioritario faltante (si faltan dirección y pago, pide SOLO la dirección primero).
6. Cero lenguaje robótico: NUNCA digas 'Estimado usuario', 'Error de extracción' ni nada técnico. Habla como un asesor experto y servicial.
"""



# =====================================================================
# 3. Lógica de Evaluación de Faltantes
# =====================================================================

def evaluar_necesidad_fallback(
    extraccion: ExtraccionPedido,
    umbral_confianza: float = UMBRAL_CONFIANZA_DEFAULT
) -> Tuple[bool, Optional[str], List[str]]:
    """
    Evalúa si la extracción requiere fallback debido a baja confianza
    o ausencia de campos obligatorios (productos, dirección o pago).

    Returns:
        Tuple[bool, Optional[str], List[str]]:
            - necesita_fallback (bool)
            - campo_prioritario (Optional[str])
            - campos_faltantes (List[str])
    """
    faltantes: List[str] = []

    # 1. Verificar productos
    if not extraccion.productos or len(extraccion.productos) == 0:
        faltantes.append("productos")

    # 2. Verificar dirección
    if not extraccion.direccion_entrega or not extraccion.direccion_entrega.strip():
        faltantes.append("direccion_entrega")

    # 3. Verificar método de pago
    if not extraccion.metodo_pago or not extraccion.metodo_pago.strip():
        faltantes.append("metodo_pago")

    # 4. Verificar umbral de confianza
    if extraccion.confianza_extraccion < umbral_confianza:
        # Si la confianza es muy baja, la aclaración es prioritaria
        return True, "aclaracion", faltantes

    if faltantes:
        # Prioridad de solicitud secuencial de ventas:
        # 1° productos -> 2° dirección -> 3° método de pago
        if "productos" in faltantes:
            return True, "productos", faltantes
        elif "direccion_entrega" in faltantes:
            return True, "direccion_entrega", faltantes
        elif "metodo_pago" in faltantes:
            return True, "metodo_pago", faltantes

    return False, None, []


def _generar_mensaje_plantilla(
    campo_prioritario: str,
    extraccion: ExtraccionPedido
) -> str:
    """Generador de respaldo determinista y persuasivo si la API no está disponible."""
    nombre = f" {extraccion.nombre_cliente}" if extraccion.nombre_cliente else ""

    if campo_prioritario == "productos":
        return (
            f"👋 ¡Hola{nombre}! Bienvenido a nuestro chat de pedidos. "
            f"¿Qué delicia se te antoja ordenar hoy? Contamos con hamburguesas artesanales, pizzas y bebidas frías. 🍕🍔"
        )
    elif campo_prioritario == "direccion_entrega":
        cant = sum(p.cantidad for p in extraccion.productos) if extraccion.productos else 0
        return (
            f"📋 ¡Excelente{nombre}! Ya tenemos anotado tu pedido de {cant} productos. "
            f"Para llevártelo calientito, ¿a qué *dirección y barrio* te lo enviamos? 📍🛵"
        )
    elif campo_prioritario == "metodo_pago":
        return (
            f"📍 ¡Anotada tu dirección{nombre}! Para terminar de coordinar tu despacho, "
            f"¿cuál sería tu método de pago preferido? Recibimos *Nequi, Daviplata o Efectivo contra entrega*. 💳💵"
        )
    else:
        return (
            f"👋 ¡Hola{nombre}! No alcancé a captar con total claridad los detalles de tu orden. "
            f"¿Me podrías confirmar cuántas unidades y qué productos deseas pedir? Con gusto te los alisto. 😊"
        )


# =====================================================================
# 4. Generación con Gemini 2.5 Flash
# =====================================================================

async def generar_mensaje_fallback(
    extraccion: ExtraccionPedido,
    chat_reciente: Optional[str] = None,
    umbral_confianza: float = UMBRAL_CONFIANZA_DEFAULT,
    client: Optional[genai.Client] = None,
    api_key: Optional[str] = None
) -> ResultadoFallback:
    """
    Función asíncrona que evalúa el resultado de ia_parser.py y, si se requiere,
    solicita a Gemini 2.5 Flash redactar una respuesta persuasiva y natural.

    Args:
        extraccion: Objeto ExtraccionPedido obtenido de ia_parser.py.
        chat_reciente: Último mensaje o transcripción del cliente (opcional).
        umbral_confianza: Umbral numérico mínimo para considerar válida la extracción.
        client: Cliente genai opcional.
        api_key: Clave Gemini opcional.

    Returns:
        ResultadoFallback: Diagnóstico de faltantes y mensaje listo para WhatsApp.
    """
    necesita, campo_prioritario, faltantes = evaluar_necesidad_fallback(
        extraccion, umbral_confianza
    )

    if not necesita:
        return ResultadoFallback(
            necesita_fallback=False,
            motivo="Orden completa con alta confianza",
            campo_prioritario=None,
            campos_faltantes=[],
            mensaje_whatsapp="",
            generado_por_ia=False
        )

    # Intentar generar con Gemini si hay cliente o API Key
    key = api_key or os.getenv("GEMINI_API_KEY")
    if client is None and key:
        client = genai.Client(api_key=key)

    if client is not None:
        try:
            prompt_contexto = (
                f"SITUACIÓN ACTUAL DEL PEDIDO:\n"
                f"- Nombre cliente: {extraccion.nombre_cliente or 'No detectado'}\n"
                f"- Productos detectados: {[f'{p.cantidad}x {p.nombre}' for p in extraccion.productos]}\n"
                f"- Dirección detectada: {extraccion.direccion_entrega or 'Falta'}\n"
                f"- Método de pago detectado: {extraccion.metodo_pago or 'Falta'}\n"
                f"- Confianza de extracción: {extraccion.confianza_extraccion:.2f}\n"
                f"- DATO PRIORITARIO QUE DEBES PEDIR AHORA: {campo_prioritario}\n"
            )
            if chat_reciente:
                prompt_contexto += f"- Último mensaje del cliente: \"{chat_reciente}\"\n"

            prompt_contexto += "\nRedacta el mensaje de WhatsApp según las instrucciones del sistema:"

            response = await client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt_contexto,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT_FALLBACK,
                    temperature=0.3,
                )
            )

            if response.text and response.text.strip():
                mensaje_ia = response.text.strip()
                return ResultadoFallback(
                    necesita_fallback=True,
                    motivo=f"Falta {campo_prioritario}" if campo_prioritario != "aclaracion" else "Baja confianza de extracción",
                    campo_prioritario=campo_prioritario,
                    campos_faltantes=faltantes,
                    mensaje_whatsapp=mensaje_ia,
                    generado_por_ia=True
                )
        except (errors.APIError, Exception):
            # Fallback seguro y transparente a plantilla si la llamada a Gemini falla o devuelve vacío
            pass


    # Generación determinista si no hay conexión o no hay API Key
    mensaje_plantilla = _generar_mensaje_plantilla(campo_prioritario, extraccion)
    return ResultadoFallback(
        necesita_fallback=True,
        motivo=f"Falta {campo_prioritario}" if campo_prioritario != "aclaracion" else "Baja confianza de extracción",
        campo_prioritario=campo_prioritario,
        campos_faltantes=faltantes,
        mensaje_whatsapp=mensaje_plantilla,
        generado_por_ia=False
    )


def generar_mensaje_fallback_sync(
    extraccion: ExtraccionPedido,
    chat_reciente: Optional[str] = None,
    umbral_confianza: float = UMBRAL_CONFIANZA_DEFAULT,
    client: Optional[genai.Client] = None,
    api_key: Optional[str] = None
) -> ResultadoFallback:
    """Wrapper síncrono para generar_mensaje_fallback."""
    return asyncio.run(
        generar_mensaje_fallback(
            extraccion=extraccion,
            chat_reciente=chat_reciente,
            umbral_confianza=umbral_confianza,
            client=client,
            api_key=api_key
        )
    )


# Aliases intuitivos de conveniencia
generar_respuesta_fallback = generar_mensaje_fallback
generar_respuesta_fallback_sync = generar_mensaje_fallback_sync



# =====================================================================
# 5. Bloque de Ejecución Directa para Pruebas
# =====================================================================

async def _main():
    print("=" * 70)
    print("DEMOSTRACIÓN DEL FALLBACK HANDLER PARA WHATSAPP CON GEMINI")
    print("=" * 70)

    # 1. Caso: Faltan productos
    print("\n[CASO 1: Faltan productos]")
    ext_1 = ExtraccionPedido(nombre_cliente="Carolina", productos=[])
    res_1 = await generar_mensaje_fallback(ext_1)
    print(f"¿Requiere Fallback?: {res_1.necesita_fallback}")
    print(f"Campo Prioritario:  {res_1.campo_prioritario}")
    print(f"Mensaje WhatsApp:\n{res_1.mensaje_whatsapp}\n")

    # 2. Caso: Hay productos, pero falta la dirección
    print("[CASO 2: Faltan dirección]")
    ext_2 = ExtraccionPedido(
        nombre_cliente="Andrés",
        productos=[ItemProducto(nombre="pizza personal hawaiana", cantidad=2)]
    )
    res_2 = await generar_mensaje_fallback(ext_2)
    print(f"¿Requiere Fallback?: {res_2.necesita_fallback}")
    print(f"Campo Prioritario:  {res_2.campo_prioritario}")
    print(f"Mensaje WhatsApp:\n{res_2.mensaje_whatsapp}\n")

    # 3. Caso: Hay productos y dirección, pero falta método de pago
    print("[CASO 3: Falta método de pago]")
    ext_3 = ExtraccionPedido(
        nombre_cliente="Andrés",
        productos=[ItemProducto(nombre="pizza personal hawaiana", cantidad=2)],
        direccion_entrega="Calle 100 # 15-20"
    )
    res_3 = await generar_mensaje_fallback(ext_3)
    print(f"¿Requiere Fallback?: {res_3.necesita_fallback}")
    print(f"Campo Prioritario:  {res_3.campo_prioritario}")
    print(f"Mensaje WhatsApp:\n{res_3.mensaje_whatsapp}\n")

    # 4. Caso: Baja confianza de extracción
    print("[CASO 4: Baja confianza de extracción (0.45)]")
    ext_4 = ExtraccionPedido(
        nombre_cliente="Felipe",
        productos=[ItemProducto(nombre="algo de comer", cantidad=1)],
        confianza_extraccion=0.45
    )
    res_4 = await generar_mensaje_fallback(ext_4)
    print(f"¿Requiere Fallback?: {res_4.necesita_fallback}")
    print(f"Campo Prioritario:  {res_4.campo_prioritario}")
    print(f"Mensaje WhatsApp:\n{res_4.mensaje_whatsapp}\n")

    # 5. Caso: Orden completa (no requiere fallback)
    print("[CASO 5: Orden completa y con alta confianza]")
    ext_5 = ExtraccionPedido(
        nombre_cliente="Felipe",
        productos=[ItemProducto(nombre="hamburguesa especial", cantidad=1)],
        direccion_entrega="Cra 7 # 45-12",
        metodo_pago="Nequi",
        confianza_extraccion=0.99
    )
    res_5 = await generar_mensaje_fallback(ext_5)
    print(f"¿Requiere Fallback?: {res_5.necesita_fallback}")
    print(f"Motivo:             {res_5.motivo}")


if __name__ == "__main__":
    asyncio.run(_main())
