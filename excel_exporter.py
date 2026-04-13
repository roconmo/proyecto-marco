"""
excel_exporter.py
Lógica de escritura del output en el archivo Excel seleccionado por el usuario.

Reglas de escritura:
- Usar siempre el Excel proporcionado por el usuario
- Escribir a partir de la última fila con datos (sin sobrescribir)
- No duplicar cabeceras si ya existen
- Si la hoja está vacía, escribir directamente los datos (sin cabecera duplicada)
"""

import io
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from typing import List, Dict, Any, Optional


# Nombre de la hoja destino por defecto
HOJA_DESTINO = "Datos"


def exportar_a_excel(
    filas: List[Dict[str, Any]],
    excel_bytes: bytes,
    hoja: str = HOJA_DESTINO,
) -> bytes:
    """
    Escribe las filas extraídas en el Excel proporcionado por el usuario.

    Comportamiento:
    - Carga el Excel existente desde bytes
    - Si la hoja no existe, la crea
    - Si la hoja tiene datos, añade a continuación sin sobrescribir ni duplicar cabeceras
    - Si la hoja está vacía, escribe cabeceras y datos desde la primera fila
    - Devuelve el Excel modificado como bytes (para descarga desde Streamlit)

    Args:
        filas:       Lista de filas devuelta por el parser (lista de dicts)
        excel_bytes: Contenido del Excel original en bytes
        hoja:        Nombre de la hoja destino (por defecto "Datos")

    Returns:
        Bytes del Excel actualizado, listo para st.download_button
    """

    if not filas:
        # Si no hay filas que escribir, devolvemos el Excel sin cambios
        return excel_bytes

    df_nuevo = pd.DataFrame(filas)

    # --- Cargar el workbook existente ---
    wb = load_workbook(io.BytesIO(excel_bytes))

    # Crear la hoja si no existe
    if hoja not in wb.sheetnames:
        ws = wb.create_sheet(title=hoja)
        _escribir_con_cabecera(ws, df_nuevo)
    else:
        ws = wb[hoja]
        ultima_fila = find_last_row(ws)

        if ultima_fila == 0:
            # La hoja existe pero está vacía → escribir con cabecera
            _escribir_con_cabecera(ws, df_nuevo)
        else:
            # La hoja tiene datos → añadir filas a continuación sin duplicar cabecera
            _append_filas(ws, df_nuevo, fila_inicio=ultima_fila + 1)

    # Ajustar ancho de columnas automáticamente
    _ajustar_columnas(ws)

    # --- Serializar el workbook a bytes ---
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.read()


# ---------------------------------------------------------------------------
# Funciones auxiliares de escritura
# ---------------------------------------------------------------------------

def find_last_row(ws) -> int:
    """
    Devuelve el número de la última fila que contiene algún valor real.
    Devuelve 0 si la hoja está completamente vacía.

    Nota: ws.max_row puede mentir cuando hay celdas con formato pero sin valor
    (p.ej. si el usuario aplicó estilos a filas vacías). Esta función recorre
    en orden inverso y para en cuanto encuentra la primera fila con datos reales,
    lo que la hace fiable independientemente del formato.
    """
    for row in reversed(range(1, ws.max_row + 1)):
        if any(cell.value for cell in ws[row]):
            return row
    return 0


def _escribir_con_cabecera(ws, df: pd.DataFrame):
    """
    Escribe cabecera (fila 1) y datos (desde fila 2) en una hoja vacía.
    Aplica estilo a la cabecera.
    """
    columnas = list(df.columns)

    # Escribir cabecera en fila 1
    for col_idx, nombre_col in enumerate(columnas, start=1):
        celda = ws.cell(row=1, column=col_idx, value=nombre_col)
        _aplicar_estilo_cabecera(celda)

    # Escribir datos desde fila 2
    for row_idx, row_data in enumerate(df.itertuples(index=False), start=2):
        for col_idx, valor in enumerate(row_data, start=1):
            ws.cell(row=row_idx, column=col_idx, value=valor)


def _append_filas(ws, df: pd.DataFrame, fila_inicio: int):
    """
    Añade filas de datos a partir de fila_inicio, sin tocar las filas previas.
    No escribe cabecera.
    """
    for row_idx, row_data in enumerate(df.itertuples(index=False), start=fila_inicio):
        for col_idx, valor in enumerate(row_data, start=1):
            ws.cell(row=row_idx, column=col_idx, value=valor)


def _aplicar_estilo_cabecera(celda):
    """Aplica formato visual a las celdas de cabecera."""
    celda.font = Font(bold=True, color="FFFFFF")
    celda.fill = PatternFill(start_color="2E75B6", end_color="2E75B6", fill_type="solid")
    celda.alignment = Alignment(horizontal="center", vertical="center")


def _ajustar_columnas(ws):
    """
    Ajusta el ancho de cada columna al contenido más largo de esa columna.
    Aplica un mínimo de 10 y un máximo de 60 caracteres.
    """
    for col_cells in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col_cells[0].column)
        for cell in col_cells:
            try:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            except Exception:
                pass
        ancho = min(max(max_len + 2, 10), 60)
        ws.column_dimensions[col_letter].width = ancho


# ---------------------------------------------------------------------------
# Función de creación de Excel vacío de partida (utilidad de apoyo)
# ---------------------------------------------------------------------------

def crear_excel_vacio() -> bytes:
    """
    Crea un Excel vacío con la hoja destino ya creada.
    Útil si el usuario no dispone de un Excel previo y quiere uno nuevo limpio.

    Returns:
        Bytes de un Excel nuevo con la hoja HOJA_DESTINO vacía
    """
    wb = load_workbook(io.BytesIO(_excel_base_bytes()))
    if HOJA_DESTINO not in wb.sheetnames:
        wb.create_sheet(title=HOJA_DESTINO)
    # Eliminar la hoja por defecto "Sheet" si existe
    if "Sheet" in wb.sheetnames and len(wb.sheetnames) > 1:
        del wb["Sheet"]
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.read()


def _excel_base_bytes() -> bytes:
    """Genera los bytes de un workbook mínimo de openpyxl."""
    from openpyxl import Workbook
    wb = Workbook()
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
