"""
parser_mavy.py
Parser específico para el proveedor MAVY.

Formato de línea de producto esperado en el PDF:
  {código 4-6 dígitos} {descripción} {cantidad} {precio X,XX} [dto X,XX[%]] EUR {importe X,XX}

Ejemplos reales:
  05780 TKROM GOLD VERDE GALICIA 4LT 1 28,59 EUR 28,59
  05685 TKROM GOLD BLANCO BRILLO 4LT 1 34,78 EUR 34,78
  08816 CEDRIA DEKOR LASUR NOGAL 4 LT 2 54,42 EUR 108,84

Cabecera real del PDF:
  Código Comments Artículo BaseAtCard Cantidad Precio Dto. Importe

Fin de tabla marcado por:
  Total Importe  /  Base Imponible  /  IVA  /  Forma de Pago  /  TOTAL:
"""

import io
import re
from typing import Any, Dict, List, Optional, Union

import pdfplumber

from parser_base import BaseParser


# ===========================================================================
# Función auxiliar de extracción de medidas
# ===========================================================================

def extract_medidas(descripcion: str) -> str:
    """
    Extrae la medida o formato comercial desde el texto de la descripción.

    Orden de prioridad:
      1. Dimensiones compuestas  → "34CM X 22.5 MT",  "240 CM X 22.5 MT"
      2. Formatos simples        → "4LT", "25 LT", "10KG", "750ML", "5M"
      3. Referencias tipo N      → "N28", "N 28"  →  devuelve "N28"

    Reglas:
      · Si no se detecta ningún patrón → devuelve "".
      · La medida NO se elimina de la descripción original.
      · No se inventan datos; ante ambigüedad → "".

    Ejemplos:
        extract_medidas("DECARPLAST 34CM X 22.5 MT")   → "34CM X 22.5 MT"
        extract_medidas("TKROM GOLD VERDE GALICIA 4LT") → "4LT"
        extract_medidas("CEDRIA DEKOR LASUR NOGAL 4 LT")→ "4LT"
        extract_medidas("PINCEL REDOND N28 CASTOR N 28")→ "N28"
        extract_medidas("PRODUCTO SIN MEDIDA")          → ""
    """
    if not descripcion:
        return ""

    desc = descripcion.upper().strip()

    # ------------------------------------------------------------------
    # 1. Dimensiones compuestas: {número}[espacio]{unidad} X {número}[espacio]{unidad}
    #    Cubre: "34CM X 22.5 MT" | "240 CM X 22.5 MT" | "1,5M X 10MT"
    # ------------------------------------------------------------------
    _RE_COMPUESTA = re.compile(
        r'(\d+[\.,]?\d*'           # primer número
        r'\s*(?:CM|MM|MTS?|M)'     # primera unidad
        r'\s+[Xx]\s+'              # separador X
        r'\d+[\.,]?\d*'            # segundo número
        r'\s*(?:CM|MM|MTS?|M))'    # segunda unidad
    )
    m = _RE_COMPUESTA.search(desc)
    if m:
        return re.sub(r'\s+', ' ', m.group(1).strip())

    # ------------------------------------------------------------------
    # 2. Formatos simples: número + unidad (pegada o con un espacio)
    #    Cubre: "4LT" | "25 LT" | "4 LTS" | "10KG" | "750ML" | "5M"
    # ------------------------------------------------------------------
    _RE_SIMPLE = re.compile(
        r'\b(\d+[\.,]?\d*'
        r'\s*'
        r'(?:LTS?|KGS?|GRS?|MLS?|CMS?|MTS?'
        r'|(?<![A-Z])M(?![A-Z])'        # M sola, no parte de palabra
        r'|(?<![A-Z])L(?![A-Z])))'      # L sola, no parte de palabra
        r'\b',
    )
    m = _RE_SIMPLE.search(desc)
    if m:
        # Eliminar espacio entre número y unidad: "4 LT" → "4LT"
        return re.sub(r'\s+', '', m.group(1).strip())

    # ------------------------------------------------------------------
    # 3. Referencia tipo N: "N28" o "N 28"  →  normaliza a "N{numero}"
    # ------------------------------------------------------------------
    _RE_N = re.compile(r'\bN\s*(\d{1,3})\b')
    m = _RE_N.search(desc)
    if m:
        return f"N{m.group(1)}"

    return ""


# ===========================================================================
# Parser MAVY
# ===========================================================================

class MavyParser(BaseParser):
    """
    Parser para albaranes y facturas del proveedor MAVY.

    El PDF contiene una tabla precedida por:
      Código  [Comments]  Artículo  [BaseAtCard]  Cantidad  Precio  Dto.  Importe

    Cada línea de producto sigue el formato:
      {código}  {descripción}  {cantidad}  {precio}  [descuento]  EUR  {importe}

    El bloque termina al detectar "Total Importe", "Base Imponible", IVA, etc.
    """

    PROVEEDOR = "MAVY"

    # -----------------------------------------------------------------------
    # Expresiones regulares — líneas de producto
    # -----------------------------------------------------------------------

    # Línea SIN descuento:
    #   05780 TKROM GOLD VERDE GALICIA 4LT 1 28,59 EUR 28,59
    #   08816 CEDRIA DEKOR LASUR NOGAL 4 LT 2 54,42 EUR 108,84
    _RE_SIN_DTO = re.compile(
        r'^(\d{4,6})'               # G1 → código (4-6 dígitos)
        r'\s+'
        r'(.+?)'                    # G2 → descripción (lazy: cede al resto)
        r'\s+'
        r'(\d+)'                    # G3 → cantidad (entero, sin unidad pegada)
        r'\s+'
        r'(\d{1,6}[,\.]\d{2})'     # G4 → precio unitario   ej: 28,59
        r'\s+EUR\s+'
        r'(\d{1,8}[,\.]\d{2})'     # G5 → importe total     ej: 108,84
        r'\s*$',
        re.IGNORECASE,
    )

    # Línea CON descuento:
    #   05780 TKROM GOLD 4LT 5 28,59 10,00 EUR 128,66
    #   05780 TKROM GOLD 4LT 5 28,59 10% EUR 128,66
    _RE_CON_DTO = re.compile(
        r'^(\d{4,6})'               # G1 → código
        r'\s+'
        r'(.+?)'                    # G2 → descripción (lazy)
        r'\s+'
        r'(\d+)'                    # G3 → cantidad
        r'\s+'
        r'(\d{1,6}[,\.]\d{2})'     # G4 → precio unitario
        r'\s+'
        r'(\d{1,3}[,\.]\d{0,2})'   # G5 → descuento (ej: 10,00 o 10)
        r'\s*%?'                    # signo % opcional
        r'\s+EUR\s+'
        r'(\d{1,8}[,\.]\d{2})'     # G6 → importe total
        r'\s*$',
        re.IGNORECASE,
    )

    # -----------------------------------------------------------------------
    # Marcadores de sección
    # -----------------------------------------------------------------------

    # Inicio de tabla: busca "Código" + "Artículo" + "Cantidad" en la misma línea.
    # Tolerante: acepta variantes con columnas extra (Comments, BaseAtCard, etc.)
    _RE_INICIO_TABLA = re.compile(
        r'C[oó]digo'
        r'.{0,60}'                  # columnas extra intermedias (Comments, etc.)
        r'Art[ií]culo'
        r'.{0,60}'
        r'Cantidad',
        re.IGNORECASE,
    )

    # Fin de tabla: cualquiera de estos patrones indica el bloque de totales
    _RE_FIN_TABLA = re.compile(
        r'Total\s+Importe'
        r'|Base\s+Imponible'
        r'|I\.?\s*V\.?\s*A\.?'
        r'|Forma\s+de\s+Pago'
        r'|TOTAL\s*:'
        r'|Subtotal'
        r'|Notas?\s*:'
        r'|Observaciones?\s*:',
        re.IGNORECASE,
    )

    # -----------------------------------------------------------------------
    # Interfaz pública (contrato de BaseParser)
    # -----------------------------------------------------------------------

    def parse(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Extrae las líneas de artículos del PDF de MAVY.

        1. Extrae texto del PDF con pdfplumber (todas las páginas).
        2. Localiza el bloque de artículos entre cabecera y totales.
        3. Parsea cada línea con los dos patrones (con/sin descuento).
        4. Devuelve lista de dicts con las 12 columnas objetivo.

        Args:
            pdf_bytes: Bytes del PDF (de st.file_uploader).

        Returns:
            Lista de dicts. Lista vacía si no hay artículos o hay error.
        """
        self.errores = []
        self.advertencias = []

        if not pdf_bytes:
            self._registrar_error("MavyParser: bytes vacíos recibidos.")
            return []

        pdf_text = self._extraer_texto(pdf_bytes)

        if not pdf_text or not pdf_text.strip():
            self._registrar_error(
                "MavyParser: no se pudo extraer texto del PDF. "
                "El archivo puede estar protegido o ser imagen escaneada."
            )
            return []

        try:
            return self._parse_texto(pdf_text)
        except Exception as e:
            self._registrar_error(f"MavyParser: error inesperado: {e}")
            return []

    # -----------------------------------------------------------------------
    # Extracción de texto
    # -----------------------------------------------------------------------

    def _extraer_texto(self, pdf_bytes: bytes) -> str:
        """
        Extrae el texto de todas las páginas del PDF usando pdfplumber.
        Registra advertencia por cada página sin texto (puede ser imagen).
        """
        partes: List[str] = []
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for num_pag, page in enumerate(pdf.pages, start=1):
                    texto = page.extract_text()
                    if texto:
                        partes.append(texto)
                    else:
                        self._registrar_advertencia(
                            f"MavyParser: página {num_pag} sin texto extraíble "
                            "(puede ser imagen)."
                        )
        except Exception as e:
            self._registrar_error(
                f"MavyParser: error al leer el PDF con pdfplumber: {e}"
            )
        return "\n".join(partes)

    # -----------------------------------------------------------------------
    # Lógica principal de parsing
    # -----------------------------------------------------------------------

    def _parse_texto(self, pdf_text: str) -> List[Dict[str, Any]]:
        """
        Recorre el texto línea a línea y extrae filas de artículos.

        · Ignora todo hasta encontrar la cabecera de tabla.
        · Lee líneas de producto hasta encontrar el bloque de totales.
        · Cada línea se prueba primero con el patrón CON descuento
          (más restrictivo) y luego SIN descuento.
        """
        filas: List[Dict[str, Any]] = []
        en_seccion = False

        for linea in pdf_text.splitlines():
            linea_strip = linea.strip()
            if not linea_strip:
                continue

            # Detectar inicio de tabla
            if not en_seccion:
                if self._RE_INICIO_TABLA.search(linea_strip):
                    en_seccion = True
                continue  # Salta la línea de cabecera

            # Detectar fin de tabla
            if self._RE_FIN_TABLA.search(linea_strip):
                break

            # Intentar parsear como artículo
            fila = self._parsear_linea(linea_strip)
            if fila:
                filas.append(fila)

        # Advertencias de resultado
        if not en_seccion:
            self._registrar_advertencia(
                "MavyParser: no se encontró la cabecera de tabla "
                "('Código ... Artículo ... Cantidad'). "
                "Verifica que el PDF corresponde a MAVY y tiene texto seleccionable."
            )
        elif not filas:
            self._registrar_advertencia(
                "MavyParser: cabecera detectada pero sin artículos extraídos. "
                "Puede que el formato de las líneas haya cambiado."
            )

        return filas

    # -----------------------------------------------------------------------
    # Parseo de una línea individual
    # -----------------------------------------------------------------------

    def _parsear_linea(self, linea: str) -> Optional[Dict[str, Any]]:
        """
        Intenta parsear una línea como artículo MAVY.

        Estrategia:
          1. Prueba _RE_CON_DTO (más restrictivo: requiere número extra antes de EUR).
          2. Si falla, prueba _RE_SIN_DTO.
          3. Si ninguno encaja → None (línea ignorada).
        """
        # Intentar CON descuento primero
        m = self._RE_CON_DTO.match(linea)
        if m:
            codigo, desc, cant, precio, dto, importe = m.groups()
            return self._construir_fila(
                codigo=codigo,
                descripcion=desc.strip(),
                cantidad=cant,
                precio=precio,
                dto=dto,
                importe=importe,
            )

        # Intentar SIN descuento
        m = self._RE_SIN_DTO.match(linea)
        if m:
            codigo, desc, cant, precio, importe = m.groups()
            return self._construir_fila(
                codigo=codigo,
                descripcion=desc.strip(),
                cantidad=cant,
                precio=precio,
                dto="",
                importe=importe,
            )

        return None

    # -----------------------------------------------------------------------
    # Construcción del dict de salida
    # -----------------------------------------------------------------------

    def _construir_fila(
        self,
        codigo: str,
        descripcion: str,
        cantidad: str,
        precio: str,
        dto: str,
        importe: str,
    ) -> Dict[str, Any]:
        """
        Construye el dict con las 12 columnas objetivo.

        Mapeo PDF → Excel:
          Código   → Modelo
          Artículo → Descripción
          Cantidad → Cantidad
          Precio   → Coste vigente  +  Precio venta excl. IVA
          Dto.     → % Descuento línea  (vacío si no existe)
          Importe  → Importe  +  Importe línea excl. IVA
          (fijo)   → Marca = "MAVY"
          (auto)   → Medidas ← extract_medidas(descripción)

        Nota: "Cód. concepto" y "Nº" son calculados por el exportador
              según la lógica de lookup, no por el parser.
        """
        precio_f  = _a_float(precio)
        importe_f = _a_float(importe)
        dto_val   = _a_float(dto) if dto else ""

        return {
            "Descripción":             descripcion,
            "Marca":                   "MAVY",
            "Modelo":                  codigo.strip(),
            "Medidas":                 extract_medidas(descripcion),
            "Cantidad":                int(cantidad),
            "Coste vigente":           precio_f,
            "Coste unitario (DL)":     "",
            "Precio venta excl. IVA":  precio_f,
            "% Descuento línea":       dto_val,
            "Margen":                  "",
            "Importe":                 importe_f,
            "Importe línea excl. IVA": importe_f,
        }


# ===========================================================================
# Helpers de módulo
# ===========================================================================

def _a_float(valor: str) -> Union[float, str]:
    """
    Convierte cadena numérica (coma o punto decimal) a float.
    Devuelve "" si el valor está vacío o no es convertible.

        "28,59"  → 28.59
        "10,00"  → 10.0
        "108,84" → 108.84
        ""       → ""
    """
    if not valor or not valor.strip():
        return ""
    try:
        return float(valor.strip().replace(",", "."))
    except ValueError:
        return ""
