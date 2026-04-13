"""
utils.py
Funciones auxiliares compartidas por el resto del proyecto.
"""

import io
import pdfplumber
from typing import Dict, Type
from parser_base import BaseParser
from parser_mavy import MavyParser
from parser_metalicas_julio_garcia import MetalicasJulioGarciaParser
from parser_onelec import OnelecParser
from parser_jabad import JabadParser


# ---------------------------------------------------------------------------
# Registro de parsers disponibles
# ---------------------------------------------------------------------------

# Mapa de nombre visible (para el selectbox) → clase parser correspondiente
PARSERS: Dict[str, Type[BaseParser]] = {
    "MAVY": MavyParser,
    "Metálicas Julio García": MetalicasJulioGarciaParser,
    "ONELEC": OnelecParser,
    "J.ABAD": JabadParser,
}


def get_parser(proveedor: str) -> BaseParser:
    """
    Devuelve una instancia del parser correspondiente al proveedor seleccionado.

    Args:
        proveedor: Nombre del proveedor tal como aparece en el selectbox

    Returns:
        Instancia del parser correspondiente

    Raises:
        ValueError: Si el proveedor no está registrado en PARSERS
    """
    if proveedor not in PARSERS:
        raise ValueError(
            f"Proveedor '{proveedor}' no reconocido. "
            f"Proveedores disponibles: {list(PARSERS.keys())}"
        )
    return PARSERS[proveedor]()


def get_proveedores_disponibles() -> list:
    """
    Devuelve la lista de nombres de proveedores disponibles para el selectbox.
    """
    return list(PARSERS.keys())


def nombre_clase_parser(proveedor: str) -> str:
    """
    Devuelve el nombre de la clase parser asociada al proveedor.
    Útil para mostrar info de debug en la interfaz.

    Args:
        proveedor: Nombre del proveedor

    Returns:
        Nombre de la clase como string, p.ej. 'MavyParser'
    """
    if proveedor not in PARSERS:
        return "Desconocido"
    return PARSERS[proveedor].__name__


def extract_text(pdf_file) -> str:
    """
    Extrae el texto completo de un PDF usando pdfplumber.

    Acepta tanto un objeto file-like (BytesIO, UploadedFile de Streamlit)
    como bytes directos.

    Args:
        pdf_file: Objeto file-like con el contenido del PDF, o bytes

    Returns:
        String con el texto completo del PDF (todas las páginas concatenadas)
    """
    text = ""
    # pdfplumber.open acepta file-like objects; si nos pasan bytes los envolvemos
    if isinstance(pdf_file, bytes):
        pdf_file = io.BytesIO(pdf_file)
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text


def formatear_lista_errores(errores: list) -> str:
    """
    Formatea una lista de errores/advertencias como texto con viñetas.

    Args:
        errores: Lista de strings

    Returns:
        String formateado con saltos de línea
    """
    if not errores:
        return ""
    return "\n".join(f"• {e}" for e in errores)
