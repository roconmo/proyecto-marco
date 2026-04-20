"""
parser_onelec.py
Parser específico para el proveedor ONELEC.

En los PDFs de ONELEC el texto suele estar maquetado en columnas y algunas
marcas (especialmente SCHNEIDER ELECTRIC) aparecen solapadas con el código
cuando se extrae texto plano. Por eso este parser NO trabaja línea a línea
sobre extract_text(), sino por filas reconstruidas desde coordenadas del PDF.

Casos soportados:
  · Descripción multilinea antes de la línea técnica
  · Línea completa con marca + código + descripción + números
  · Descuento en la misma fila o en una microfila inmediatamente inferior
  · Productos repetidos: se conservan como líneas distintas
  · Ruido de cabeceras / pies de página concatenado al final de una descripción
"""

from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional, Tuple, Union

import pdfplumber

from parser_base import BaseParser


# ===========================================================================
# Helpers de módulo
# ===========================================================================


def _a_float(valor: str) -> Union[float, str]:
    """Convierte número europeo a float; devuelve "" si falla."""
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
    """
    Extrae una medida/formato comercial simple desde la descripción.
    No elimina el texto original de la descripción.
    """
    if not descripcion:
        return ""

    patrones = [
        r"\b\d+[\.,]?\d*\s*[xX]\s*\d+[\.,]?\d*(?:\s*[xX]\s*\d+[\.,]?\d*)?\s*(?:mm|cm|m)?\b",
        r"\bø\s*\d+[\.,]?\d*\s*(?:m|cm|mm)\b",
        r"\b\d+[\.,]?\d*\s*(?:V|A|mA|kV|Lux|lm|h)\b",
        r"\b\d+P\+?N?\+?T?\b",
        r"\bIP\d{2}\b",
    ]
    for patron in patrones:
        m = re.search(patron, descripcion, flags=re.IGNORECASE)
        if m:
            return re.sub(r"\s+", " ", m.group(0).strip())
    return ""


# ===========================================================================
# Parser ONELEC
# ===========================================================================


class OnelecParser(BaseParser):
    """Parser para ofertas / presupuestos de ONELEC."""

    PROVEEDOR = "ONELEC"

    # Marcas vistas en el PDF real y frecuentes en este proveedor.
    _MARCAS = [
        "SCHNEIDER ELECTRIC",
        "TUB.INDUSTRIAL",
        "NORMALUX",
        "LEGRAND",
        "TUPERSA",
        "SOFAMEL",
        "LAPAFIL",
        "SOLERA",
        "THEBEN",
        "ORBIS",
        "BARPA",
        "SIMON",
        "UNEX",
        "IDE",
        "JSL",
    ]

    # Corte de columnas aproximado del PDF ONELEC (en puntos PDF).
    _X_MARCA_CODIGO_MAX = 130
    _X_DESCRIPCION_MIN = 130
    _X_DESCRIPCION_MAX = 330
    _X_CANTIDAD_MIN = 330
    _X_CANTIDAD_MAX = 390
    _X_PRECIO_MIN = 395
    _X_PRECIO_MAX = 442
    _X_DESCUENTO_MIN = 442
    _X_DESCUENTO_MAX = 500
    _X_IMPORTE_MIN = 500

    _RE_NUM = re.compile(r"^\d{1,3}(?:\.\d{3})*(?:,\d+)?$")
    _RE_CODIGO = re.compile(r"^[A-Z0-9][A-Z0-9\-./]*$")
    _RE_PAGINA = re.compile(r"^\d+\s+de\s*\d+$", re.IGNORECASE)
    _RE_FOOTER = re.compile(
        r"Reg\.\s*Merc\."
        r"|N\.I\.F\."
        r"|Cl[áa]usula\s+clientes"
        r"|LOPD"
        r"|VENDEDOR\s+EXTERNO",
        re.IGNORECASE,
    )
    _RE_INICIO_TABLA = re.compile(
        r"Marca\s+C[óo]digo\s+Descripci[óo]n\s+Cantidad",
        re.IGNORECASE,
    )
    _RE_CABECERA_FRAGMENTO = re.compile(
        r"\b(?:Marca|C[óo]digo|Descripci[óo]n|Cantidad|RAEE\*?|Precio|Descuento|Importe)\b",
        re.IGNORECASE,
    )
    _RE_FIN_DOC = re.compile(
        r"\bAtentamente\b"
        r"|\bObservaciones\b"
        r"|\bVALIDEZ\s+DE\s+LA\s+OFERTA\b"
        r"|\bBase\s+Imponible\b"
        r"|\bTOTAL\s+€\b",
        re.IGNORECASE,
    )
    _RE_RUIDO_DIRECCION = re.compile(
        r"(?:Cl\s+Daza\s+Valdes"
        r"|Leganes\s*\(Madrid\)"
        r"|Tel\.:"
        r"|Fax:"
        r"|info@on-elec\.es"
        r"|Direcci[óo]n\s+Env[ií]o\s+Oferta"
        r"|REDONDO\s+Y\s+GARCIA"
        r"|CL\s+SERRANIA\s+DE\s+RONDA"
        r"|28320\s+PINTO"
        r"|Madrid\b"
        r"|Telf:"
        r"|E-mail:"
        r"|00495\b"
        r"|A28021350\b"
        r"|28914\s+Leganes)",
        re.IGNORECASE,
    )

    def parse(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        """Extrae artículos del PDF de ONELEC por filas reconstruidas del layout."""
        self.errores = []
        self.advertencias = []

        if not pdf_bytes:
            self._registrar_error("OnelecParser: bytes vacíos recibidos.")
            return []

        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                filas = self._parse_pdf(pdf)
        except Exception as e:
            self._registrar_error(f"OnelecParser: error al leer el PDF con pdfplumber: {e}")
            return []

        if not filas and not self.errores:
            self._registrar_advertencia(
                "OnelecParser: no se han extraído artículos. Puede que el formato haya cambiado."
            )
        return filas

    # ------------------------------------------------------------------
    # Parsing principal por páginas/filas
    # ------------------------------------------------------------------

    def _parse_pdf(self, pdf: pdfplumber.PDF) -> List[Dict[str, Any]]:
        productos: List[Dict[str, Any]] = []
        pending_description_lines: List[str] = []
        current_product: Optional[Dict[str, Any]] = None
        se_encontro_linea_tecnica = False
        fin_documento = False

        for _num_pag, page in enumerate(pdf.pages, start=1):
            logical_rows = self._build_logical_rows(page)
            if not logical_rows:
                continue

            for row in logical_rows:
                row_text = self._clean_inline_noise(row.get("text", ""))
                if not row_text:
                    continue

                # Cabecera clásica o cabecera fragmentada: se ignora.
                if self._RE_INICIO_TABLA.search(row_text) or self._parece_fragmento_cabecera(row_text):
                    continue

                if self._es_fila_basura(row_text):
                    continue

                if self._RE_FIN_DOC.search(row_text):
                    fin_documento = True
                    break

                parsed = self._parse_logical_row(row)
                if parsed:
                    se_encontro_linea_tecnica = True
                    if current_product:
                        current_product["descripcion"] = self._join_texts(
                            [current_product.get("descripcion", "")]
                        )
                        productos.append(self._to_base_row(current_product))

                    descripcion = self._join_texts(
                        pending_description_lines + [parsed.get("descripcion_inline", "")]
                    )
                    pending_description_lines = []

                    current_product = {
                        "marca": parsed.get("marca", ""),
                        "codigo": parsed.get("codigo", ""),
                        "descripcion": descripcion,
                        "cantidad": _a_float(parsed.get("cantidad", "")),
                        "precio": _a_float(parsed.get("precio", "")),
                        "descuento": _a_float(parsed.get("descuento", "")) if parsed.get("descuento", "") else "",
                        "importe": _a_float(parsed.get("importe", "")),
                        "advertencia": parsed.get("advertencia", False),
                    }
                else:
                    # No es línea técnica: continuación de descripción.
                    fragmento = self._descripcion_de_row_no_tecnica(row)
                    if not fragmento:
                        continue

                    if current_product is None:
                        pending_description_lines.append(fragmento)
                    else:
                        current_product["descripcion"] = self._join_texts(
                            [current_product.get("descripcion", ""), fragmento]
                        )

            if fin_documento:
                break

            # Entre páginas no se cierra el producto. Puede continuar.

        if current_product:
            current_product["descripcion"] = self._join_texts([current_product.get("descripcion", "")])
            productos.append(self._to_base_row(current_product))

        if not se_encontro_linea_tecnica:
            self._registrar_advertencia(
                "OnelecParser: no se detectó ninguna línea técnica de producto en ONELEC."
            )

        return productos

    # ------------------------------------------------------------------
    # Reconstrucción de filas lógicas desde coordenadas PDF
    # ------------------------------------------------------------------

    def _build_logical_rows(self, page: pdfplumber.page.Page) -> List[Dict[str, Any]]:
        words = page.extract_words(
            x_tolerance=1,
            y_tolerance=1,
            keep_blank_chars=False,
            use_text_flow=False,
        )

        # Agrupar microfilas por top muy próximo (p.ej. técnica + descuento separado 0.8pt)
        groups: List[Dict[str, Any]] = []
        for word in sorted(words, key=lambda w: (round(w["top"], 2), w["x0"])):
            text = str(word.get("text", "")).strip()
            if not text:
                continue

            if not groups or abs(word["top"] - groups[-1]["top_ref"]) > 1.25:
                groups.append({"top_ref": word["top"], "words": [word]})
            else:
                groups[-1]["words"].append(word)
                groups[-1]["top_ref"] = min(groups[-1]["top_ref"], word["top"])

        logical_rows: List[Dict[str, Any]] = []
        for g in groups:
            row_words = sorted(g["words"], key=lambda w: w["x0"])
            text = " ".join(w["text"] for w in row_words).strip()
            logical_rows.append(
                {
                    "top": g["top_ref"],
                    "words": row_words,
                    "text": re.sub(r"\s+", " ", text).strip(),
                }
            )
        return logical_rows

    # ------------------------------------------------------------------
    # Parseo de una fila lógica
    # ------------------------------------------------------------------

    def _parse_logical_row(self, row: Dict[str, Any]) -> Optional[Dict[str, str]]:
        words = row["words"]
        left_words = [w for w in words if w["x0"] < self._X_MARCA_CODIGO_MAX]
        desc_words = [w for w in words if self._X_DESCRIPCION_MIN <= w["x0"] < self._X_DESCRIPCION_MAX]
        qty_words = [w for w in words if self._X_CANTIDAD_MIN <= w["x0"] < self._X_CANTIDAD_MAX]
        precio_words = [w for w in words if self._X_PRECIO_MIN <= w["x0"] < self._X_PRECIO_MAX]
        descuento_words = [w for w in words if self._X_DESCUENTO_MIN <= w["x0"] < self._X_DESCUENTO_MAX]
        importe_words = [w for w in words if w["x0"] >= self._X_IMPORTE_MIN]

        cantidad = self._first_numeric(qty_words)
        precio = self._first_numeric(precio_words)
        descuento = self._first_numeric(descuento_words)
        importe = self._first_numeric(importe_words)

        if not (left_words and cantidad and precio and importe):
            return None

        marca, codigo, advertencia = self._parse_left_brand_code(left_words)
        if not marca:
            return None

        descripcion_inline = self._clean_inline_noise(self._join_words(desc_words))
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

    def _parse_left_brand_code(self, left_words: List[Dict[str, Any]]) -> Tuple[str, str, bool]:
        """Devuelve (marca, codigo, advertencia). advertencia=True indica detección insegura."""
        textos = [
            str(w["text"]).strip()
            for w in sorted(left_words, key=lambda w: w["x0"])
            if str(w["text"]).strip()
        ]
        if not textos:
            return "", "", False

        # Caso especial crítico: SCHNEIDER ELECTRIC con código solapado.
        # Ejemplo real: ["SCHNEIDERA", "E9LRE6C0T2R25IC"]
        if textos[0].startswith("SCHNEIDER"):
            spill = textos[0][len("SCHNEIDER"):]
            second = textos[1] if len(textos) > 1 else ""
            codigo = self._remove_subsequence(spill + second, "ELECTRIC")
            codigo = re.sub(r"[^A-Z0-9\-./]", "", codigo.upper())
            if codigo and self._RE_CODIGO.match(codigo):
                return "SCHNEIDER ELECTRIC", codigo, False

        # Caso especial: TUB.INDUSTRIAL con código solapado.
        # Ejemplo real: ["TUB.INDUSTPREIAGLM16"] → marca=TUB.INDUSTRIAL, código=PEGM16
        if textos[0].startswith("TUB.INDUST"):
            codigo = self._remove_subsequence(textos[0], "TUB.INDUSTRIAL")
            codigo = re.sub(r"[^A-Z0-9\-./]", "", codigo.upper())
            if codigo and self._RE_CODIGO.match(codigo):
                return "TUB.INDUSTRIAL", codigo, False

        # Caso especial: CONDUCTO[R] con código solapado.
        # Ejemplo real: ["CONDUCTORUTP6LH"] → marca=CONDUCTOR, código=UTP6LH
        if textos[0].upper().startswith("CONDUCTO"):
            codigo = self._remove_subsequence(textos[0], "CONDUCTOR")
            codigo = re.sub(r"[^A-Z0-9\-./]", "", codigo.upper())
            if codigo and self._RE_CODIGO.match(codigo):
                return "CONDUCTOR", codigo, True  # advertencia: marca no completamente legible

        # Resto de marcas: normalmente salen limpias como [MARCA, CODIGO]
        for marca in self._MARCAS:
            marca_tokens = marca.split()
            if len(marca_tokens) == 1:
                if textos[0].upper() == marca.upper():
                    if len(textos) == 1:
                        return marca, "", False
                    codigo = textos[1].upper()
                    if codigo and self._RE_CODIGO.match(codigo):
                        return marca, codigo, False
            else:
                if len(textos) >= len(marca_tokens):
                    cand = " ".join(textos[: len(marca_tokens)]).upper()
                    if cand == marca.upper():
                        codigo = textos[len(marca_tokens)].upper() if len(textos) > len(marca_tokens) else ""
                        if codigo and self._RE_CODIGO.match(codigo):
                            return marca, codigo, False

        # Fallback suave: primera palabra = marca, segunda = código si parece código.
        # Detección insegura → advertencia=True
        if len(textos) >= 2:
            codigo = textos[1].upper()
            if self._RE_CODIGO.match(codigo):
                return textos[0].upper(), codigo, True

        return "", "", False

    # ------------------------------------------------------------------
    # Clasificación / limpieza
    # ------------------------------------------------------------------

    def _es_fila_basura(self, texto: str) -> bool:
        s = texto.strip()
        if not s:
            return True
        if self._RE_PAGINA.match(s):
            return True
        if self._RE_FOOTER.search(s):
            return True
        if s in {"HABITUALES", "Ref. Auxiliar", "Oferta Nº: 6111003"}:
            return True
        if any(
            token in s
            for token in [
                "ONELEC SUMINISTROS ELEC.",
                "Dirección Envío Oferta",
                "Fecha Cliente Referencia",
                "Forma de Pago",
                "C.I.F.",
                "Agente",
                "Página",
                "Marca Código Descripción Cantidad",
                "Conforme:",
            ]
        ):
            return True
        # Si toda la fila es básicamente una cabecera/pie contaminado, fuera.
        if self._RE_RUIDO_DIRECCION.search(s) and len(s) > 40 and not self._parece_texto_producto(s):
            return True
        return False

    def _descripcion_de_row_no_tecnica(self, row: Dict[str, Any]) -> str:
        words = row["words"]
        desc_words = [w for w in words if self._X_DESCRIPCION_MIN <= w["x0"] < self._X_DESCRIPCION_MAX]

        # Algunas descripciones muy largas en ONELEC pueden seguir entrando en la
        # columna izquierda si el fabricante no se repite; en ese caso, si no hay
        # números técnicos y casi todo el texto está a la izquierda/centro, lo tomamos.
        if desc_words:
            return self._clean_inline_noise(self._join_words(desc_words))

        non_numeric = [str(w["text"]).strip() for w in words if not self._RE_NUM.match(str(w["text"]).strip())]
        texto = self._clean_inline_noise(self._join_texts(non_numeric))
        if self._parece_descripcion(texto):
            return texto
        return ""

    @staticmethod
    def _parece_descripcion(texto: str) -> bool:
        if not texto:
            return False
        t = texto.strip()
        if len(t) < 3:
            return False
        if re.fullmatch(r"[\d\s,\.]+", t):
            return False
        return True

    def _parece_fragmento_cabecera(self, texto: str) -> bool:
        """
        Detecta microfilas de cabecera repetidas por página.
        Se ignoran solo si parecen realmente cabecera y no descripción.
        """
        t = texto.strip()
        if not t:
            return False
        matches = self._RE_CABECERA_FRAGMENTO.findall(t)
        if len(matches) >= 2:
            return True
        if t in {"Ref. Auxiliar", "Oferta Nº: 6111003", "HABITUALES"}:
            return True
        return False

    def _clean_inline_noise(self, texto: str) -> str:
        """
        Elimina ruido típico de cabecera/pie cuando queda concatenado al final
        de una descripción al cambiar de página.
        """
        if not texto:
            return ""
        t = re.sub(r"\s+", " ", texto).strip()
        m = self._RE_RUIDO_DIRECCION.search(t)
        if m:
            t = t[: m.start()].strip()
        # Cortes extra por fragmentos de cabecera si se pegaron al final.
        for marker in [
            "ONELEC SUMINISTROS ELEC.",
            "Dirección Envío Oferta",
            "Fecha Cliente Referencia",
            "Marca Código Descripción Cantidad",
            "Oferta Nº",
            "HABITUALES",
        ]:
            pos = t.find(marker)
            if pos != -1:
                t = t[:pos].strip()
        return re.sub(r"\s+", " ", t).strip()

    @staticmethod
    def _parece_texto_producto(texto: str) -> bool:
        palabras_producto = [
            "Interruptor",
            "Conmutador",
            "Contactor",
            "Relé",
            "Detector",
            "Base",
            "Caja",
            "Canal",
            "Moldura",
            "Cable",
            "Clavija",
            "Luminaria",
            "Pértiga",
            "Guantes",
            "Alfombra",
            "Pantalla",
            "Taco",
            "Brida",
            "Abrazadera",
            "Temporizador",
        ]
        return any(p.lower() in texto.lower() for p in palabras_producto)

    # ------------------------------------------------------------------
    # Conversión al formato base
    # ------------------------------------------------------------------

    def _to_base_row(self, product: Dict[str, Any]) -> Dict[str, Any]:
        descripcion = self._clean_inline_noise(
            self._join_texts([str(product.get("descripcion", ""))])
        )
        precio = product.get("precio", "")
        importe = product.get("importe", "")
        return {
            "Descripción": descripcion,
            "Marca": product.get("marca", ""),
            "Modelo": product.get("codigo", ""),
            "Medidas": extract_medidas(descripcion),
            "Cantidad": product.get("cantidad", "") if product.get("cantidad") is not None else "",
            "Coste vigente": precio,
            "Coste unitario (DL)": precio,
            "Precio venta excl. IVA": precio,
            "% Descuento línea": product.get("descuento", "") if product.get("descuento") is not None else "",
            "Margen": "",
            "Importe": importe,
            "Importe línea excl. IVA": importe,
            "_advertencia": product.get("advertencia", False),
        }

    # ------------------------------------------------------------------
    # Utilidades de texto
    # ------------------------------------------------------------------

    @staticmethod
    def _join_words(words: List[Dict[str, Any]]) -> str:
        return OnelecParser._join_texts([str(w["text"]).strip() for w in sorted(words, key=lambda w: w["x0"])])

    @staticmethod
    def _join_texts(texts: List[str]) -> str:
        limpio = [str(t).strip() for t in texts if str(t).strip()]
        return re.sub(r"\s+", " ", " ".join(limpio)).strip()

    @staticmethod
    def _first_numeric(words: List[Dict[str, Any]]) -> str:
        for w in sorted(words, key=lambda w: w["x0"]):
            txt = str(w["text"]).strip()
            if OnelecParser._RE_NUM.match(txt):
                return txt
        return ""

    @staticmethod
    def _remove_subsequence(text: str, subseq: str) -> str:
        """Elimina una subsecuencia conocida en orden y devuelve el resto."""
        res: List[str] = []
        j = 0
        for ch in text:
            if j < len(subseq) and ch.upper() == subseq[j].upper():
                j += 1
            else:
                res.append(ch)
        return "".join(res)
