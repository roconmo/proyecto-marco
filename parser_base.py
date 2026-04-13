"""
parser_base.py
Clase base abstracta que define el contrato común para todos los parsers de proveedor.
Cada parser específico debe heredar de BaseParser e implementar el método parse().
"""

from abc import ABC, abstractmethod
import pandas as pd
from typing import List, Dict, Any


class BaseParser(ABC):
    """
    Clase base abstracta para todos los parsers de proveedor.

    Todos los parsers deben:
    - Heredar de esta clase
    - Implementar el método parse()
    - Devolver siempre una lista de diccionarios con estructura homogénea
    """

    # Nombre del proveedor — cada subclase debe sobreescribir este atributo
    PROVEEDOR: str = "Desconocido"

    # Columnas que debe tener el output — estructura fija para todos los proveedores
    COLUMNAS: List[str] = [
        "Descripción",
        "Marca",
        "Modelo",
        "Medidas",
        "Cantidad",
        "Coste vigente",
        "Coste unitario (DL)",
        "Precio venta excl. IVA",
        "% Descuento línea",
        "Margen",
        "Importe",
        "Importe línea excl. IVA",
    ]

    def __init__(self):
        self.errores: List[str] = []  # Errores acumulados durante el parsing
        self.advertencias: List[str] = []  # Advertencias no fatales

    @abstractmethod
    def parse(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Método principal de extracción de datos desde el PDF.

        Args:
            pdf_bytes: Contenido del PDF en bytes (tal como llega de st.file_uploader)

        Returns:
            Lista de filas como diccionarios.
            Cada fila debe contener al menos las claves definidas en COLUMNAS.
            Si no hay datos, devuelve lista vacía [].
        """
        pass

    def to_dataframe(self, filas: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        Convierte la lista de filas en un DataFrame de pandas.
        Rellena con None las columnas ausentes para garantizar estructura homogénea.

        Args:
            filas: Lista de diccionarios devuelta por parse()

        Returns:
            DataFrame con las columnas definidas en COLUMNAS
        """
        if not filas:
            return pd.DataFrame(columns=self.COLUMNAS)

        df = pd.DataFrame(filas)

        # Aseguramos que todas las columnas esperadas existen
        for col in self.COLUMNAS:
            if col not in df.columns:
                df[col] = None

        # Devolvemos solo las columnas definidas, en el orden correcto
        return df[self.COLUMNAS]

    def get_errores(self) -> List[str]:
        """Devuelve la lista de errores registrados durante el parsing."""
        return self.errores

    def get_advertencias(self) -> List[str]:
        """Devuelve la lista de advertencias registradas durante el parsing."""
        return self.advertencias

    def _registrar_error(self, mensaje: str):
        """Añade un error a la lista interna."""
        self.errores.append(mensaje)

    def _registrar_advertencia(self, mensaje: str):
        """Añade una advertencia a la lista interna."""
        self.advertencias.append(mensaje)

    def __repr__(self):
        return f"<Parser proveedor='{self.PROVEEDOR}'>"
