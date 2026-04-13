"""
parser_mavy.py
Parser específico para el proveedor MAVY.

FASE 1: Estructura preparada. El método parse() devuelve datos de prueba.
FASE 2: Implementar extracción real desde el PDF de MAVY.
"""

from typing import List, Dict, Any
from parser_base import BaseParser


class MavyParser(BaseParser):
    """
    Parser para facturas / albaranes del proveedor MAVY.

    Estructura esperada del documento MAVY:
    - TODO: documentar formato en fase 2

    Columnas específicas de MAVY que se añadan en fases futuras
    deben extender COLUMNAS de BaseParser.
    """

    PROVEEDOR = "MAVY"

    def parse(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Extrae las líneas de artículos del PDF de MAVY.

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
            # Por ahora devolvemos filas de ejemplo para validar el flujo completo.
            # ------------------------------------------------------------------

            self._registrar_advertencia(
                "Parser MAVY en fase 1: devolviendo datos de prueba."
            )

            filas_prueba = [
                {
                    "Descripción": "Artículo de prueba MAVY 1",
                    "Marca": "",
                    "Modelo": "MAV-001",
                    "Medidas": "",
                    "Cantidad": 10,
                    "Coste vigente": "",
                    "Coste unitario (DL)": 5.50,
                    "Precio venta excl. IVA": "",
                    "% Descuento línea": "",
                    "Margen": "",
                    "Importe": 55.00,
                    "Importe línea excl. IVA": "",
                },
                {
                    "Descripción": "Artículo de prueba MAVY 2",
                    "Marca": "",
                    "Modelo": "MAV-002",
                    "Medidas": "",
                    "Cantidad": 3,
                    "Coste vigente": "",
                    "Coste unitario (DL)": 12.00,
                    "Precio venta excl. IVA": "",
                    "% Descuento línea": "",
                    "Margen": "",
                    "Importe": 36.00,
                    "Importe línea excl. IVA": "",
                },
            ]

            return filas_prueba

        except Exception as e:
            self._registrar_error(f"Error inesperado en MavyParser.parse(): {e}")
            return []
