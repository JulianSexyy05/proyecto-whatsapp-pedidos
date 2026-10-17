"""
Módulo de OCR y Validación de Comprobantes de Pago con Gemini API.
Analiza capturas de pantalla y comprobantes de transferencias bancarias
(Nequi, Daviplata, Bancolombia, etc.) utilizando gemini-2.5-flash y Pydantic.
"""

import os
import sys
import json
import asyncio
import mimetypes
from enum import Enum
from pathlib import Path
from typing import Optional, Union
from pydantic import BaseModel, Field
from google import genai
from google.genai import types, errors

# Configuración de encoding para consola Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


class GeminiOCRError(Exception):
    """Excepción personalizada para errores en el procesamiento de OCR con Gemini API."""
    pass


def _limpiar_json_markdown(texto: str) -> str:
    """Elimina delimitadores markdown ```json y ``` si están presentes en la respuesta."""
    limpio = texto.strip()
    if limpio.startswith("```json"):
        limpio = limpio[7:]
    elif limpio.startswith("```"):
        limpio = limpio[3:]
    if limpio.endswith("```"):
        limpio = limpio[:-3]
    return limpio.strip()



# =====================================================================
# 1. Esquema Validado con Pydantic
# =====================================================================

class EstadoValidacion(str, Enum):
    EXITOSO = "exitoso"
    PENDIENTE = "pendiente"
    RECHAZADO = "rechazado"
    DUDOSO_O_ILEGIBLE = "dudoso_o_ilegible"
    POSIBLE_ADULTERACION = "posible_adulteracion"


class ComprobantePago(BaseModel):
    banco_emisor: Optional[str] = Field(
        description="Nombre de la entidad bancaria o billetera digital emisora (ej. Nequi, Daviplata, Bancolombia, BBVA, Davivienda, Mercado Pago, etc.)",
        default=None
    )
    numero_referencia: Optional[str] = Field(
        description="Número de referencia, comprobante, ID de transacción o código de aprobación único",
        default=None
    )
    monto_pagado: Optional[float] = Field(
        description="Monto exacto transferido o pagado como valor numérico flotante (sin signos ni letras)",
        default=None
    )
    moneda: Optional[str] = Field(
        description="Código de moneda de la transacción (ej. COP, USD)",
        default="COP"
    )
    fecha_hora: Optional[str] = Field(
        description="Fecha y hora registradas en el comprobante (ej. '17/10/2026 14:20' o '17 de Octubre de 2026, 02:20 PM')",
        default=None
    )
    cuenta_destino: Optional[str] = Field(
        description="Número de cuenta bancaria o número de teléfono del destinatario visible en el comprobante",
        default=None
    )
    nombre_destinatario: Optional[str] = Field(
        description="Nombre de la persona o comercio destinatario si aparece en la imagen",
        default=None
    )
    estado_validacion: EstadoValidacion = Field(
        description="Estado preliminar de validación de la transacción según la evidencia visual del comprobante",
        default=EstadoValidacion.EXITOSO
    )
    confianza_ocr: float = Field(
        description="Nivel de confianza en la nitidez, legibilidad y consistencia visual del comprobante (de 0.0 a 1.0)",
        ge=0.0,
        le=1.0,
        default=1.0
    )
    observaciones: Optional[str] = Field(
        description="Observaciones sobre la legibilidad, coherencia tipográfica o anomalías visuales detectadas",
        default=None
    )


# =====================================================================
# 2. Instrucciones del Sistema para OCR de Pagos
# =====================================================================

SYSTEM_PROMPT_OCR = """
Eres un Asistente Senior especializado en Auditoría Financiera, OCR y Validación de Comprobantes de Pago bancarios.
Tu labor es inspeccionar imágenes de comprobantes o capturas de transferencias digitales (especialmente Nequi, Daviplata, Bancolombia, Bre-B, Transfiya y bancos colombianos e internacionales) y extraer con precisión quirúrgica los datos en JSON estructurado.

Pautas de extracción y validación:
1. Banco emisor: Identifica con precisión la aplicación o entidad (ej. Nequi, Daviplata, Bancolombia, etc.).
2. Referencia / Comprobante: Localiza el número de referencia oficial (en Nequi suele empezar por 'M', en Bancolombia suele ser un número de 6 o más dígitos).
3. Monto exacto: Extrae únicamente el valor numérico transferido. Omite el símbolo de moneda ($) y puntos de miles en el campo flotante.
4. Fecha y hora: Extrae la estampa temporal tal como aparece en el comprobante.
5. Estado de validación preliminar:
   - 'exitoso': Si el comprobante muestra claramente 'Envío exitoso', 'Transferencia realizada', 'Transacción aprobada' y tipografía consistente.
   - 'pendiente': Si dice 'En proceso' o 'Pendiente de confirmación'.
   - 'rechazado': Si indica 'Fallida', 'Rechazada' o 'Transacción cancelada'.
   - 'posible_adulteracion': Si detectas fuentes de texto desalineadas, tipografía sobrepuesta, diferencias de píxeles o señales claras de edición gráfica fraudulenta.
   - 'dudoso_o_ilegible': Si la imagen está demasiado borrosa, cortada o no permite verificar los números con certeza.
"""


# =====================================================================
# 3. Funciones de Procesamiento OCR
# =====================================================================

def _determinar_mime_type(ruta_o_bytes: Union[str, bytes, Path], mime_declarado: Optional[str] = None) -> str:
    """Detecta el tipo MIME de la imagen."""
    if mime_declarado:
        return mime_declarado

    if isinstance(ruta_o_bytes, (str, Path)):
        mime, _ = mimetypes.guess_type(str(ruta_o_bytes))
        if mime:
            return mime

    # Detección por bytes iniciales (magic numbers)
    if isinstance(ruta_o_bytes, bytes):
        if ruta_o_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        elif ruta_o_bytes.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        elif ruta_o_bytes.startswith(b"RIFF") and b"WEBP" in ruta_o_bytes[:16]:
            return "image/webp"

    return "image/jpeg"


async def procesar_comprobante_pago(
    origen_imagen: Union[str, bytes, Path],
    mime_type: Optional[str] = None,
    client: Optional[genai.Client] = None,
    api_key: Optional[str] = None
) -> ComprobantePago:
    """
    Función asíncrona que procesa una imagen de comprobante de pago mediante OCR con Gemini 2.5 Flash
    y retorna la información estructurada y validada con Pydantic.

    Args:
        origen_imagen: Ruta al archivo de imagen (str / Path) o contenido binario de la imagen (bytes).
        mime_type: Tipo MIME explícito (opcional, ej. 'image/png', 'image/jpeg').
        client: Instancia opcional de genai.Client.
        api_key: Clave de API de Gemini opcional. Si no se pasa, se lee de GEMINI_API_KEY.

    Returns:
        ComprobantePago: Objeto Pydantic con la información estructurada del pago y estado preliminar.
    """
    # 1. Obtención de bytes y MIME type
    if isinstance(origen_imagen, (str, Path)):
        path = Path(origen_imagen)
        if not path.is_file():
            raise FileNotFoundError(f"No se encontró el archivo de imagen en la ruta: {path}")
        image_bytes = path.read_bytes()
        detected_mime = _determinar_mime_type(path, mime_type)
    elif isinstance(origen_imagen, bytes):
        image_bytes = origen_imagen
        detected_mime = _determinar_mime_type(image_bytes, mime_type)
    else:
        raise TypeError("origen_imagen debe ser una ruta de archivo (str, Path) o bytes de imagen.")

    # 2. Inicialización del cliente Google GenAI
    if client is None:
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError(
                "No se encontró GEMINI_API_KEY. Configúrala en las variables de entorno o pásala a la función."
            )
        client = genai.Client(api_key=key)

    # 3. Preparación del input multimodal para Gemini 2.5 Flash
    part_imagen = types.Part.from_bytes(data=image_bytes, mime_type=detected_mime)

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT_OCR,
        response_mime_type="application/json",
        response_schema=ComprobantePago,
        temperature=0.1,  # Máxima precisión factual para OCR financiero
    )

    prompt = (
        "Examina este comprobante de pago con atención a los detalles numéricos, fecha, banco, "
        "referencia y autenticidad visual. Extrae el resultado en el esquema JSON solicitado."
    )

    try:
        # Invocación asíncrona a Gemini 2.5 Flash
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=[part_imagen, prompt],
            config=config,
        )

        if not response.text or not response.text.strip():
            raise GeminiOCRError(
                "La API de Gemini devolvió una respuesta vacía o la imagen no pudo ser procesada."
            )

        # Validación y conversión a modelo Pydantic
        texto_limpio = _limpiar_json_markdown(response.text)
        return ComprobantePago.model_validate_json(texto_limpio)

    except (errors.APIError, Exception) as err:
        if isinstance(err, (FileNotFoundError, TypeError, ValueError, GeminiOCRError)):
            raise
        raise GeminiOCRError(f"Fallo en Gemini API durante el OCR del comprobante: {err}") from err



def procesar_comprobante_pago_sync(
    origen_imagen: Union[str, bytes, Path],
    mime_type: Optional[str] = None,
    client: Optional[genai.Client] = None,
    api_key: Optional[str] = None
) -> ComprobantePago:
    """Wrapper síncrono para procesar_comprobante_pago."""
    return asyncio.run(
        procesar_comprobante_pago(
            origen_imagen=origen_imagen,
            mime_type=mime_type,
            client=client,
            api_key=api_key
        )
    )


# =====================================================================
# 4. Bloque de Ejecución Directa para Pruebas
# =====================================================================

async def _main():
    print("=" * 70)
    print("OCR Y VALIDACIÓN DE COMPROBANTES DE PAGO CON GEMINI 2.5 FLASH")
    print("=" * 70)

    # Si se pasó una ruta de imagen como argumento en la terminal
    if len(sys.argv) > 1:
        ruta_archivo = sys.argv[1]
        print(f"\nProcesando archivo: {ruta_archivo}")
        try:
            resultado = await procesar_comprobante_pago(ruta_archivo)
            print("\nResultado extraído con éxito:")
            print(resultado.model_dump_json(indent=2))
        except Exception as e:
            print(f"\n[ERROR] Falló el procesamiento de la imagen: {e}")
        return

    # Si no se pasó imagen, mostramos demostración de capacidades y esquema
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("\n[INFO] GEMINI_API_KEY no detectada.")
        print("Para procesar comprobantes reales, configura tu clave:")
        print("  $env:GEMINI_API_KEY='tu_api_key'")
        print("  python core/ocr_pagos.py <ruta_a_la_imagen.jpg>\n")
        print("Ejemplo de estructura extraída y validada con Pydantic:")

    ejemplo_comprobante = ComprobantePago(
        banco_emisor="Nequi",
        numero_referencia="M12849502",
        monto_pagado=53500.0,
        moneda="COP",
        fecha_hora="17/10/2026 14:19",
        cuenta_destino="3101234567",
        nombre_destinatario="Pizzería & Burgers Gourmet",
        estado_validacion=EstadoValidacion.EXITOSO,
        confianza_ocr=0.99,
        observaciones="Comprobante nítido, tipografía oficial de Nequi sin signos de alteración."
    )
    print(ejemplo_comprobante.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
