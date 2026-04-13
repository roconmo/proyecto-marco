"""
parser_onelec.py
Parser específico para el proveedor ONELEC.

FASE 1: Estructura preparada. El método parse() devuelve datos de prueba.
FASE 2: Implementar extracción real desde el PDF de ONELEC.
"""

from typing import List, Dict, Any
from parser_base import BaseParser


class OnelecParser(BaseParser):
    """
    Parser para facturas / albaranes del proveedor ONELEC.

    Estructura esperada del documento ONELEC:
    - TODO: documentar formato en fase 2
    """

    PROVEEDOR = "ONELEC"

    def parse(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Extrae las líneas de artículos del PDF de ONELEC.

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
                "Parser ONELEC en fase 1: devolviendo datos de prueba."
            )

            filas_prueba = [
                {
                    "Descripción": "Material eléctrico de prueba 1",
                    "Marca": "",
                    "Modelo": "ONE-001",
                    "Medidas": "",
                    "Cantidad": 50,
                    "Coste vigente": "",
                    "Coste unitario (DL)": 1.20,
                    "Precio venta excl. IVA": "",
                    "% Descuento línea": "",
                    "Margen": "",
                    "Importe": 60.00,
                    "Importe línea excl. IVA": "",
                },
                {
                    "Descripción": "Cable de prueba 2",
                    "Marca": "",
                    "Modelo": "ONE-002",
                    "Medidas": "",
                    "Cantidad": 100,
                    "Coste vigente": "",
                    "Coste unitario (DL)": 0.85,
                    "Precio venta excl. IVA": "",
                    "% Descuento línea": "",
                    "Margen": "",
                    "Importe": 85.00,
                    "Importe línea excl. IVA": "",
                },
            ]

            return filas_prueba

        except Exception as e:
            self._registrar_error(f"Error inesperado en OnelecParser.parse(): {e}")
            return []
