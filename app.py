"""
app.py
Aplicación principal — interfaz Streamlit para extracción de datos desde PDFs comerciales.

Flujo:
1. Usuario sube el PDF
2. Usuario selecciona el proveedor manualmente
3. Usuario sube el Excel destino (con "Hoja1" ya existente)
4. Se procesa el PDF con el parser del proveedor elegido
5. El output se escribe en las columnas correctas de "Hoja1"
6. El usuario descarga el Excel actualizado
"""

import streamlit as st
import streamlit.components.v1 as components

from utils import (
    get_parser,
    get_proveedores_disponibles,
    nombre_clase_parser,
    formatear_lista_errores,
    extract_text,
    confirmar_proveedor_en_pdf,
)
from excel_exporter import exportar_a_excel, inspeccionar_cabecera, HOJA_DESTINO
from verificar import verificar, discrepancias_a_dataframe


# ---------------------------------------------------------------------------
# Configuración de la página
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Extractor de PDFs Comerciales",
    page_icon="📄",
    layout="centered",
)


# ---------------------------------------------------------------------------
# Inicializar estado de sesión (debe hacerse antes de cualquier uso)
# ---------------------------------------------------------------------------

if "resultado" not in st.session_state:
    st.session_state.resultado = None
if "descargado" not in st.session_state:
    st.session_state.descargado = False
if "form_key" not in st.session_state:
    st.session_state.form_key = 0
if "scroll_top" not in st.session_state:
    st.session_state.scroll_top = False


# ---------------------------------------------------------------------------
# Título y descripción
# ---------------------------------------------------------------------------

# Scroll al inicio si se acaba de reiniciar el formulario
if st.session_state.scroll_top:
    st.session_state.scroll_top = False
    components.html("<script>window.parent.scrollTo({top: 0, behavior: 'instant'});</script>", height=0)

st.title("Extractor de PDFs Comerciales")
st.markdown(
    "Sube un PDF de proveedor, selecciona el proveedor y el Excel destino. "
    f"La aplicación escribirá los datos extraídos en la hoja **{HOJA_DESTINO}** "
    "de tu plantilla, respetando todas las demás columnas existentes."
)
st.divider()


# ---------------------------------------------------------------------------
# Sección 1 — Subida del PDF
# ---------------------------------------------------------------------------

st.subheader("1. Selecciona el PDF")

pdf_file = st.file_uploader(
    label="Sube el PDF del proveedor",
    type=["pdf"],
    help="Archivo PDF con el albarán o factura del proveedor.",
    key=f"pdf_uploader_{st.session_state.form_key}",
)


# ---------------------------------------------------------------------------
# Sección 2 — Selección del proveedor
# ---------------------------------------------------------------------------

st.subheader("2. Selecciona el proveedor")

proveedor_seleccionado = st.selectbox(
    label="Proveedor",
    options=get_proveedores_disponibles(),
    help="Selecciona el proveedor al que corresponde el PDF subido.",
    key=f"proveedor_{st.session_state.form_key}",
)

# Validación inmediata: si hay PDF y proveedor seleccionado, confirmar coincidencia
if proveedor_seleccionado and pdf_file is not None:
    _pdf_bytes_check = pdf_file.read()
    pdf_file.seek(0)
    _ok, _msg = confirmar_proveedor_en_pdf(proveedor_seleccionado, _pdf_bytes_check)
    if _ok:
        st.success(_msg)
    else:
        st.error(_msg)


# ---------------------------------------------------------------------------
# Sección 3 — Selección del Excel destino
# ---------------------------------------------------------------------------

st.subheader("3. Selecciona el Excel destino")

excel_file = st.file_uploader(
    label=f"Sube el archivo Excel con la hoja '{HOJA_DESTINO}' ya preparada (.xlsx)",
    type=["xlsx"],
    help=(
        f"El resultado se escribirá en la hoja '{HOJA_DESTINO}' de tu plantilla, "
        "solo en las columnas objetivo, sin alterar el resto."
    ),
    key=f"excel_uploader_{st.session_state.form_key}",
)

# Cuando el usuario sube un Excel, mostrar las columnas que tiene "Hoja1"
# para que pueda verificar antes de procesar
if excel_file is not None:
    try:
        excel_preview_bytes = excel_file.read()
        excel_file.seek(0)  # Rebobinar para que el procesamiento posterior funcione
        cols_en_hoja = inspeccionar_cabecera(excel_preview_bytes, HOJA_DESTINO)
        if cols_en_hoja:
            with st.expander(
                f"Columnas detectadas en '{HOJA_DESTINO}' ({len(cols_en_hoja)} columnas)",
                expanded=False,
            ):
                st.write(cols_en_hoja)
        else:
            st.warning(
                f"La hoja '{HOJA_DESTINO}' existe pero no tiene cabecera en la fila 1, "
                "o la hoja no existe aún en ese Excel."
            )
    except Exception:
        pass  # Si falla la previsualización no bloqueamos al usuario


# ---------------------------------------------------------------------------
# Zona de debug (expandible, opcional)
# ---------------------------------------------------------------------------

with st.expander("Información de debug — configuración actual", expanded=False):
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**PDF subido:**")
        st.code(pdf_file.name if pdf_file else "— ninguno —")

        st.markdown("**Proveedor seleccionado:**")
        st.code(proveedor_seleccionado)

    with col2:
        st.markdown("**Parser que se usará:**")
        st.code(nombre_clase_parser(proveedor_seleccionado))

        st.markdown("**Excel destino:**")
        st.code(excel_file.name if excel_file else "— ninguno —")

        st.markdown("**Hoja destino:**")
        st.code(HOJA_DESTINO)


# ---------------------------------------------------------------------------
# Sección 4 — Botón de procesamiento
# ---------------------------------------------------------------------------


st.divider()

# --- Si ya se descargó, mostrar mensaje final y no el botón ---
if st.session_state.descargado:
    st.success("Proceso finalizado. Puedes cerrar esta ventana o subir un nuevo PDF.")
    if st.button("Procesar otro PDF", use_container_width=True):
        st.session_state.resultado = None
        st.session_state.descargado = False
        st.session_state.form_key += 1
        st.session_state.scroll_top = True
        st.rerun()
    st.stop()

# --- Si ya se procesó pero aún no se descargó, mostrar resultados y descarga ---
if st.session_state.resultado is not None:
    res = st.session_state.resultado

    if res.get("columnas_faltantes"):
        st.warning(
            f"Las siguientes columnas objetivo **no se encontraron** en la "
            f"hoja '{HOJA_DESTINO}' y no se han escrito:\n"
            + formatear_lista_errores(res["columnas_faltantes"])
        )

    filas_escritas = res["filas_escritas"]
    if filas_escritas > 0:
        st.success(
            f"Procesamiento completado — "
            f"**{filas_escritas}** fila(s) escritas en '{HOJA_DESTINO}' | "
            f"Proveedor: **{res['proveedor']}**"
        )
    else:
        st.info("El parser no devolvió datos para este PDF. El Excel no ha sido modificado.")

    if res.get("advertencias_parser"):
        st.warning("Advertencias del parser:\n" + formatear_lista_errores(res["advertencias_parser"]))

    if res.get("df_preview") is not None:
        st.subheader("Vista previa de los datos extraídos")
        st.dataframe(res["df_preview"], use_container_width=True)

    if res.get("discrepancias") is not None:
        st.subheader("Verificación PDF vs Excel generado")
        for msg in res["resumen_verificacion"]:
            if "✔" in msg:
                st.success(msg)
            else:
                st.warning(msg)
        if res["discrepancias"]:
            st.dataframe(discrepancias_a_dataframe(res["discrepancias"]), use_container_width=True)

    st.divider()
    st.subheader("Descargar Excel actualizado")
    descargado = st.download_button(
        label="Descargar Excel con los datos escritos",
        data=res["excel_bytes_resultado"],
        file_name=res["nombre_excel"],
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
    )
    if descargado:
        st.session_state.descargado = True
        st.rerun()

    st.stop()

# --- Estado inicial: mostrar botón Procesar ---
procesar = st.button("Procesar", type="primary", use_container_width=True)

if procesar:

    # --- Validaciones previas al procesamiento ---
    errores_validacion = []

    if pdf_file is None:
        errores_validacion.append("Debes subir un archivo PDF.")

    if not proveedor_seleccionado:
        errores_validacion.append("Debes seleccionar un proveedor.")

    if excel_file is None:
        errores_validacion.append(
            f"Debes subir el archivo Excel destino con la hoja '{HOJA_DESTINO}' preparada."
        )

    # Confirmar que el PDF coincide con el proveedor antes de procesar
    if pdf_file is not None and proveedor_seleccionado:
        _pdf_bytes_val = pdf_file.read()
        pdf_file.seek(0)
        _ok_val, _msg_val = confirmar_proveedor_en_pdf(proveedor_seleccionado, _pdf_bytes_val)
        if not _ok_val:
            errores_validacion.append(_msg_val)

    if errores_validacion:
        for msg in errores_validacion:
            st.error(msg)
        st.stop()

    # --- Procesamiento ---
    with st.spinner(f"Procesando PDF con el parser de {proveedor_seleccionado}..."):

        try:
            # 1. Leer bytes del PDF
            pdf_bytes = pdf_file.read()

            # 2. Extraer texto plano para debug
            texto_extraido = extract_text(pdf_bytes)
            with st.expander("DEBUG TEXT — texto extraído del PDF", expanded=False):
                st.text_area(
                    label=f"Texto completo extraído por pdfplumber ({len(texto_extraido)} caracteres)",
                    value=texto_extraido if texto_extraido else "(sin texto extraído)",
                    height=500,
                    disabled=True,
                )

            # 3. Parser y extracción
            parser = get_parser(proveedor_seleccionado)
            filas = parser.parse(pdf_bytes)
            advertencias_parser = parser.get_advertencias()
            errores_parser = parser.get_errores()

            if errores_parser:
                st.error("Errores durante el parsing:\n" + formatear_lista_errores(errores_parser))
                st.stop()

            # 4. Exportar a Excel
            excel_bytes_origen = excel_file.read()
            nombre_excel_salida = excel_file.name

            if filas:
                excel_bytes_resultado, columnas_faltantes = exportar_a_excel(
                    filas=filas,
                    excel_bytes=excel_bytes_origen,
                )
                filas_escritas = len(filas)
            else:
                excel_bytes_resultado = excel_bytes_origen
                columnas_faltantes = []
                filas_escritas = 0

            # 5. Verificación
            discrepancias, resumen_verificacion = (
                verificar(filas, excel_bytes_resultado, filas_escritas)
                if filas and filas_escritas > 0
                else (None, None)
            )

            # 6. Guardar todo en session_state
            st.session_state.resultado = {
                "proveedor": proveedor_seleccionado,
                "filas_escritas": filas_escritas,
                "excel_bytes_resultado": excel_bytes_resultado,
                "nombre_excel": nombre_excel_salida,
                "columnas_faltantes": columnas_faltantes,
                "advertencias_parser": advertencias_parser,
                "df_preview": parser.to_dataframe(filas) if filas else None,
                "discrepancias": discrepancias,
                "resumen_verificacion": resumen_verificacion,
            }
            st.rerun()

        except ValueError as e:
            st.error(f"Error de configuración: {e}")
        except Exception as e:
            st.error(f"Error inesperado durante el procesamiento: {e}")
            raise
