"""
parser_metalicas_julio_garcia.py
Parser específico para el proveedor Metálicas Julio García.

FASE 1: Estructura preparada. El método parse() devuelve datos de prueba.
FASE 2: Implementar extracción real desde el PDF de Metálicas Julio García.
"""

from typing import List, Dict, Any
from parser_base import BaseParser


class MetalicasJulioGarciaParser(BaseParser):
    """
    Parser para facturas / albaranes del proveedor Metálicas Julio García.

    Estructura esperada del documento:
    - TODO: documentar formato en fase 2
    """

    PROVEEDOR = "Metálicas Julio García"

    def parse(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Extrae las líneas de artículos del PDF de Metálicas Julio García.

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
                "Parser Metálicas Julio García en fase 1: devolviendo datos de prueba."
            )

            filas_prueba = [
                {
                    "Descripción": "Perfil metálico de prueba 1",
                    "Marca": "",
                    "Modelo": "MJG-001",
                    "Medidas": "",
                    "Cantidad": 20,
                    "Coste vigente": "",
                    "Coste unitario (DL)": 8.75,
                    "Precio venta excl. IVA": "",
                    "% Descuento línea": "",
                    "Margen": "",
                    "Importe": 175.00,
                    "Importe línea excl. IVA": "",
                },
                {
                    "Descripción": "Chapa de prueba 2",
                    "Marca": "",
                    "Modelo": "MJG-002",
                    "Medidas": "",
                    "Cantidad": 5,
                    "Coste vigente": "",
                    "Coste unitario (DL)": 22.00,
                    "Precio venta excl. IVA": "",
                    "% Descuento línea": "",
                    "Margen": "",
                    "Importe": 110.00,
                    "Importe línea excl. IVA": "",
                },
            ]

            return filas_prueba

        except Exception as e:
            self._registrar_error(
                f"Error inesperado en MetalicasJulioGarciaParser.parse(): {e}"
            )
            return []
