"""
parser_jabad.py
Parser específico para el proveedor J.ABAD.

FASE 1: Estructura preparada. El método parse() devuelve datos de prueba.
FASE 2: Implementar extracción real desde el PDF de J.ABAD.
"""

from typing import List, Dict, Any
from parser_base import BaseParser


class JabadParser(BaseParser):
    """
    Parser para facturas / albaranes del proveedor J.ABAD.

    Estructura esperada del documento J.ABAD:
    - TODO: documentar formato en fase 2
    """

    PROVEEDOR = "J.ABAD"

    def parse(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Extrae las líneas de artículos del PDF de J.ABAD.

        Args:
            pdf_bytes: Contenido del PDF en bytes

        Returns:
            Lista de filas como diccionarios con la estructura de BaseParser.COLUMNAS
        """
        self.errores = []
        self.advertencias = []

        try:
            # ------------------------------------------------------------------
            # FASE 1 — Placeholder
            # Aquí se implementará la extracción real en fases posteriores.
            # ------------------------------------------------------------------

            self._registrar_advertencia(
                "Parser J.ABAD en fase 1: devolviendo datos de prueba."
            )

            filas_prueba = [
                {
                    "Descripción": "Artículo de prueba J.ABAD 1",
                    "Marca": "",
                    "Modelo": "JAB-001",
                    "Medidas": "",
                    "Cantidad": 15,
                    "Coste vigente": "",
                    "Coste unitario (DL)": 3.40,
                    "Precio venta excl. IVA": "",
                    "% Descuento línea": "",
                    "Margen": "",
                    "Importe": 51.00,
                    "Importe línea excl. IVA": "",
                },
                {
                    "Descripción": "Artículo de prueba J.ABAD 2",
                    "Marca": "",
                    "Modelo": "JAB-002",
                    "Medidas": "",
                    "Cantidad": 8,
                    "Coste vigente": "",
                    "Coste unitario (DL)": 18.50,
                    "Precio venta excl. IVA": "",
                    "% Descuento línea": "",
                    "Margen": "",
                    "Importe": 148.00,
                    "Importe línea excl. IVA": "",
                },
            ]

            return filas_prueba

        except Exception as e:
            self._registrar_error(f"Error inesperado en JabadParser.parse(): {e}")
            return []
