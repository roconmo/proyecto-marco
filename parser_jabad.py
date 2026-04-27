"""
parser_jabad.py
Parser específico para J.ABAD COMERCIAL DEL COBRE SAU.

Estructura del PDF:
  · Columnas: Marca | Código | Descripción | Cantidad | Precio | Descuento | RAEE(*) | Importe
  · La columna RAEE es opcional y solo aparece en algunos productos.
  · Casos especiales de solapado:
      - CREARPLAS: marca y código fusionados en un solo token (ej. "CREARPLAS200700")
      - TUBO COBRE: la "E" final se solapa con el código → aparece como "TUBO COBR" + "FRIGO12,7/0,80T"
  · Las descripciones pueden ser multilinea.
"""

from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional, Tuple

import pdfplumber

from parser_base import BaseParser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _a_float(valor: Any) -> Any:
    """Convierte número con formato europeo a float; devuelve '' si falla."""
    if valor is None:
        return ""
    s = str(valor).strip()
    if not s:
        return ""
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return ""


def extract_medidas(descripcion: str) -> str:
    """Extrae una medida/formato comercial desde la descripción."""
    if not descripcion:
        return ""
    patrones = [
        r"\b\d+[\.,]?\d*\s*[xX]\s*\d+[\.,]?\d*(?:\s*[xX]\s*\d+[\.,]?\d*)?\s*(?:mm|cm|m)?\b",
        r"\bø\s*\d+[\.,]?\d*\s*(?:m|cm|mm)\b",
        r"\b\d+[\.,]?\d*\s*(?:V|A|mA|kV|W|Lux|lm|h)\b",
        r"\b\d+P\+?N?\+?T?\b",
        r"\bIP\d{2}\b",
        r'\b\d+(?:[.,]\d+)?["″]',
    ]
    for patron in patrones:
        m = re.search(patron, descripcion, flags=re.IGNORECASE)
        if m:
            return re.sub(r"\s+", " ", m.group(0).strip())
    return ""


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class JabadParser(BaseParser):
    """Parser para ofertas / presupuestos de J.ABAD COMERCIAL DEL COBRE SAU."""

    PROVEEDOR = "J.ABAD"

    # Cortes de columna (puntos PDF medidos en el PDF real)
    _X_MARCA_MAX = 70
    _X_CODIGO_MIN = 70
    _X_CODIGO_MAX = 140
    _X_DESC_MIN = 140
    _X_DESC_MAX = 337
    _X_CANTIDAD_MIN = 337
    _X_CANTIDAD_MAX = 420
    _X_PRECIO_MIN = 410
    _X_PRECIO_MAX = 448
    _X_DESCUENTO_MIN = 448
    _X_DESCUENTO_MAX = 475
    _X_RAEE_MIN = 475
    _X_RAEE_MAX = 545
    _X_IMPORTE_MIN = 545

    # Números con formato europeo: 1,00 / 188,200 / 0,35
    _RE_NUM = re.compile(r"^\d{1,3}(?:\.\d{3})*,\d+$")
    # El código de J.ABAD puede incluir coma y barra (ej: FRIGO12,7/0,80T)
    _RE_CODIGO = re.compile(r"^[A-Z0-9][A-Z0-9\-./,]*$")
    _RE_PAGINA = re.compile(r"^\d+\s+de\s*\d+$", re.IGNORECASE)

    _RE_INICIO_TABLA = re.compile(
        r"Marca\s+C[óo]digo\s+Descripci[óo]n\s+Cantidad",
        re.IGNORECASE,
    )
    _RE_FIN_DOC = re.compile(
        r"\bObservaciones\b"
        r"|\bImporte\s+Neto\b"
        r"|\(\*\)\s*Tarifa\s+por\s+unidad",
        re.IGNORECASE,
    )
    _RE_FOOTER = re.compile(
        r"NIF/CIF:"
        r"|Tel[eé]fono:"
        r"|Fax:"
        r"|Tomo\s+\d"
        r"|C\.I\.F\."
        r"|Validez\s+de\s+la\s+oferta"
        r"|Precios\s+v[áa]lidos"
        r"|Todos\s+los\s+precios"
        r"|TRANSFERENCIA",
        re.IGNORECASE,
    )
    _RE_RUIDO_CABECERA = re.compile(
        r"Cl\s+Torneros"
        r"|Getafe\s*\(Madrid\)"
        r"|28906"
        r"|Direcci[óo]n\s+Env[íi]o"
        r"|REDONDO\s+Y\s+GARCIA"
        r"|CL\s+SERRANIA"
        r"|28320\s+PINTO"
        r"|Telf:"
        r"|E-mail:"
        r"|\b\d{2}/\d{2}/\d{4}\b"   # filas con fecha (cabecera de albarán)
        r"|\bMADRID\b",              # fila de ciudad en bloque de dirección
        re.IGNORECASE,
    )

    # ---------------------------------------------------------------------------
    # Entrada pública
    # ---------------------------------------------------------------------------

    def parse(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        """Extrae artículos del PDF de J.ABAD por filas reconstruidas del layout."""
        self.errores = []
        self.advertencias = []

        if not pdf_bytes:
            self._registrar_error("JabadParser: bytes vacíos recibidos.")
            return []

        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                return self._parse_pdf(pdf)
        except Exception as e:
            self._registrar_error(f"JabadParser: error al leer el PDF: {e}")
            return []

    # ---------------------------------------------------------------------------
    # Parsing principal
    # ---------------------------------------------------------------------------

    def _parse_pdf(self, pdf: pdfplumber.PDF) -> List[Dict[str, Any]]:
        productos: List[Dict[str, Any]] = []
        pending_desc: List[str] = []
        current_product: Optional[Dict[str, Any]] = None
        fin_documento = False

        for page in pdf.pages:
            logical_rows = self._build_logical_rows(page)

            for row in logical_rows:
                row_text = " ".join(w["text"] for w in row["words"]).strip()

                if self._RE_INICIO_TABLA.search(row_text):
                    continue
                if self._RE_FIN_DOC.search(row_text):
                    fin_documento = True
                    break
                if self._es_basura(row_text):
                    continue

                parsed = self._parse_product_row(row)
                if parsed:
                    if current_product:
                        productos.append(self._to_base_row(current_product))

                    descripcion = self._join_texts(
                        pending_desc + [parsed.get("descripcion_inline", "")]
                    )
                    pending_desc = []
                    current_product = {
                        "marca": parsed["marca"],
                        "codigo": parsed["codigo"],
                        "descripcion": descripcion,
                        "cantidad": _a_float(parsed.get("cantidad", "")),
                        "precio": _a_float(parsed.get("precio", "")),
                        "descuento": _a_float(parsed.get("descuento", "")) if parsed.get("descuento") else "",
                        "importe": _a_float(parsed.get("importe", "")),
                        "advertencia": parsed.get("advertencia", False),
                    }
                else:
                    fragmento = self._desc_de_row_continuacion(row)
                    if fragmento:
                        if current_product is None:
                            pending_desc.append(fragmento)
                        else:
                            current_product["descripcion"] = self._join_texts(
                                [current_product["descripcion"], fragmento]
                            )

            if fin_documento:
                break

        if current_product:
            productos.append(self._to_base_row(current_product))

        if not productos:
            self._registrar_advertencia(
                "JabadParser: no se extrajeron productos del PDF."
            )

        return productos

    # ---------------------------------------------------------------------------
    # Reconstrucción de filas lógicas
    # ---------------------------------------------------------------------------

    def _build_logical_rows(self, page: pdfplumber.page.Page) -> List[Dict[str, Any]]:
        words = page.extract_words(
            x_tolerance=2,
            y_tolerance=2,
            keep_blank_chars=False,
            use_text_flow=False,
        )
        groups: List[Dict[str, Any]] = []
        for word in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
            text = str(word.get("text", "")).strip()
            if not text:
                continue
            if not groups or abs(word["top"] - groups[-1]["top_ref"]) > 2.5:
                groups.append({"top_ref": word["top"], "words": [word]})
            else:
                groups[-1]["words"].append(word)
                groups[-1]["top_ref"] = min(groups[-1]["top_ref"], word["top"])

        return [
            {
                "top": g["top_ref"],
                "words": sorted(g["words"], key=lambda w: w["x0"]),
            }
            for g in groups
        ]

    # ---------------------------------------------------------------------------
    # Parseo de una fila de producto
    # ---------------------------------------------------------------------------

    def _parse_product_row(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        words = row["words"]

        marca_words = [w for w in words if w["x0"] < self._X_MARCA_MAX]
        codigo_words = [w for w in words if self._X_CODIGO_MIN <= w["x0"] < self._X_CODIGO_MAX]
        desc_words = [w for w in words if self._X_DESC_MIN <= w["x0"] < self._X_DESC_MAX]
        cant_words = [w for w in words if self._X_CANTIDAD_MIN <= w["x0"] < self._X_CANTIDAD_MAX]
        precio_words = [w for w in words if self._X_PRECIO_MIN <= w["x0"] < self._X_PRECIO_MAX]
        desc_words2 = [w for w in words if self._X_DESCUENTO_MIN <= w["x0"] < self._X_DESCUENTO_MAX]
        importe_words = [w for w in words if w["x0"] >= self._X_IMPORTE_MIN]

        cantidad = self._first_numeric(cant_words)
        precio = self._first_numeric(precio_words)
        descuento = self._first_numeric(desc_words2)
        importe = self._first_numeric(importe_words)

        if not (marca_words and cantidad and precio and importe):
            return None

        marca, codigo, advertencia = self._parse_marca_codigo(marca_words, codigo_words)
        if not marca:
            return None

        descripcion_inline = self._join_words(desc_words)
        return {
            "marca": marca,
            "codigo": codigo,
            "descripcion_inline": descripcion_inline,
            "cantidad": cantidad,
            "precio": precio,
            "descuento": descuento,
            "importe": importe,
            "advertencia": advertencia,
        }

    def _parse_marca_codigo(
        self,
        marca_words: List[Dict[str, Any]],
        codigo_words: List[Dict[str, Any]],
    ) -> Tuple[str, str, bool]:
        """Devuelve (marca, codigo, advertencia)."""
        if not marca_words:
            return "", "", False

        textos = [str(w["text"]).strip() for w in sorted(marca_words, key=lambda w: w["x0"])]
        first = textos[0].upper()

        # Caso especial: CREARPLAS + código numérico fusionados en una sola palabra
        # Ej. "CREARPLAS200700" → marca="CREARPLAS", código="200700"
        if first.startswith("CREARPLAS"):
            codigo = first[len("CREARPLAS"):]
            codigo = re.sub(r"[^A-Z0-9]", "", codigo)
            return "CREARPLAS", codigo, False

        # Caso especial: TUBO COBRE con la E solapada en el código
        # Ej. ["TUBO", "COBR"] + código "FRIGO12,7/0,80T" → "TUBO COBRE"
        if first == "TUBO" and len(textos) > 1 and textos[1].upper().startswith("COBR"):
            codigo = self._first_text(codigo_words)
            return "TUBO COBRE", codigo, False

        # Caso general: marca = todas las palabras en zona izquierda, código separado
        marca = " ".join(textos).strip().upper()
        codigo = self._first_text(codigo_words).upper()

        if not marca:
            return "", "", False

        if codigo and not self._RE_CODIGO.match(codigo):
            return marca, codigo, True  # código dudoso → advertencia

        return marca, codigo, False

    # ---------------------------------------------------------------------------
    # Descripción de filas de continuación
    # ---------------------------------------------------------------------------

    def _desc_de_row_continuacion(self, row: Dict[str, Any]) -> str:
        words = row["words"]
        desc_words = [w for w in words if self._X_DESC_MIN <= w["x0"] < self._X_DESC_MAX]
        if desc_words:
            return self._join_words(desc_words)
        return ""

    # ---------------------------------------------------------------------------
    # Filtros de basura
    # ---------------------------------------------------------------------------

    def _es_basura(self, texto: str) -> bool:
        s = texto.strip()
        if not s:
            return True
        if self._RE_PAGINA.match(s):
            return True
        if self._RE_FOOTER.search(s):
            return True
        if self._RE_RUIDO_CABECERA.search(s):
            return True
        if any(tok in s for tok in [
            "J.ABAD COMERCIAL",
            "Fecha Prefactura",
            "Forma de Pago",
            "Marca Código",
            "Agente",
        ]):
            return True
        return False

    # ---------------------------------------------------------------------------
    # Conversión al formato base
    # ---------------------------------------------------------------------------

    def _to_base_row(self, product: Dict[str, Any]) -> Dict[str, Any]:
        descripcion = re.sub(r"\s+", " ", product.get("descripcion", "")).strip()
        precio = product.get("precio", "")
        importe = product.get("importe", "")
        return {
            "Descripción": descripcion,
            "Marca": product.get("marca", ""),
            "Modelo": product.get("codigo", ""),
            "Medidas": extract_medidas(descripcion),
            "Cantidad": product.get("cantidad", ""),
            "Coste vigente": precio,
            "Coste unitario (DL)": precio,
            "Precio venta excl. IVA": precio,
            "% Descuento línea": product.get("descuento", ""),
            "Margen": "",
            "Importe": importe,
            "Importe línea excl. IVA": importe,
            "_advertencia": product.get("advertencia", False),
        }

    # ---------------------------------------------------------------------------
    # Utilidades
    # ---------------------------------------------------------------------------

    @staticmethod
    def _join_words(words: List[Dict[str, Any]]) -> str:
        sorted_words = [w for w in sorted(words, key=lambda w: w["x0"]) if str(w["text"]).strip()]
        if not sorted_words:
            return ""

        # Detectar y colapsar texto espaciado letra a letra:
        # si el hueco entre dos tokens consecutivos es < 12pt y ambos son cortos (≤3 chars),
        # se unen sin espacio.
        parts: List[str] = []
        current = str(sorted_words[0]["text"]).strip()
        for i in range(1, len(sorted_words)):
            prev = sorted_words[i - 1]
            curr = sorted_words[i]
            gap = curr["x0"] - prev.get("x1", prev["x0"] + len(str(prev["text"])) * 5)
            prev_short = len(str(prev["text"]).strip()) <= 3
            curr_short = len(str(curr["text"]).strip()) <= 3
            if prev_short and curr_short and gap < 12:
                current += str(curr["text"]).strip()
            else:
                parts.append(current)
                current = str(curr["text"]).strip()
        parts.append(current)

        return re.sub(r"\s+", " ", " ".join(parts)).strip()

    @staticmethod
    def _join_texts(texts: List[str]) -> str:
        limpio = [str(t).strip() for t in texts if str(t).strip()]
        return re.sub(r"\s+", " ", " ".join(limpio)).strip()

    @staticmethod
    def _first_numeric(words: List[Dict[str, Any]]) -> str:
        _RE = re.compile(r"^\d{1,3}(?:\.\d{3})*,\d+$")
        for w in sorted(words, key=lambda w: w["x0"]):
            if _RE.match(str(w["text"]).strip()):
                return str(w["text"]).strip()
        return ""

    @staticmethod
    def _first_text(words: List[Dict[str, Any]]) -> str:
        for w in sorted(words, key=lambda w: w["x0"]):
            t = str(w["text"]).strip()
            if t:
                return t
        return ""
