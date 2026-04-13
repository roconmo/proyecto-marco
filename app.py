"""
app.py
Aplicación principal — interfaz Streamlit para extracción de datos desde PDFs comerciales.

Flujo:
1. Usuario sube el PDF
2. Usuario selecciona el proveedor manualmente
3. Usuario sube el Excel destino
4. Se procesa el PDF con el parser del proveedor elegido
5. El output se escribe en el Excel proporcionado
6. El usuario descarga el Excel actualizado
"""

import streamlit as st
import io

from utils import get_parser, get_proveedores_disponibles, nombre_clase_parser, formatear_lista_errores, extract_text
from excel_exporter import exportar_a_excel, crear_excel_vacio


# ---------------------------------------------------------------------------
# Configuración de la página
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Extractor de PDFs Comerciales",
    page_icon="📄",
    layout="centered",
)


# ---------------------------------------------------------------------------
# Título y descripción
# ---------------------------------------------------------------------------

st.title("Extractor de PDFs Comerciales")
st.markdown(
    "Sube un PDF de proveedor, selecciona el proveedor y el Excel destino. "
    "La aplicación extraerá los datos y los escribirá en tu Excel."
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
)


# ---------------------------------------------------------------------------
# Sección 2 — Selección del proveedor
# ---------------------------------------------------------------------------

st.subheader("2. Selecciona el proveedor")

proveedor_seleccionado = st.selectbox(
    label="Proveedor",
    options=get_proveedores_disponibles(),
    help="Selecciona el proveedor al que corresponde el PDF subido.",
)


# ---------------------------------------------------------------------------
# Sección 3 — Selección del Excel destino
# ---------------------------------------------------------------------------

st.subheader("3. Selecciona el Excel destino")

excel_file = st.file_uploader(
    label="Sube el archivo Excel donde se escribirán los datos (.xlsx)",
    type=["xlsx"],
    help=(
        "El resultado se añadirá al final de los datos existentes, "
        "sin sobrescribir ni duplicar cabeceras."
    ),
)

# Opción alternativa: usar un Excel nuevo vacío si el usuario no tiene uno
usar_excel_nuevo = st.checkbox(
    "No tengo un Excel destino — crear uno nuevo",
    value=False,
    help="Si marcas esta opción se generará un Excel nuevo limpio como destino.",
)


# ---------------------------------------------------------------------------
# Zona de debug (expandible, opcional)
# ---------------------------------------------------------------------------

with st.expander("Información de debug", expanded=False):
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
        if excel_file:
            st.code(excel_file.name)
        elif usar_excel_nuevo:
            st.code("Excel nuevo (generado automáticamente)")
        else:
            st.code("— ninguno —")


# ---------------------------------------------------------------------------
# Sección 4 — Botón de procesamiento
# ---------------------------------------------------------------------------

st.divider()

procesar = st.button("Procesar", type="primary", use_container_width=True)

if procesar:
    # --- Validaciones previas al procesamiento ---
    errores_validacion = []

    if pdf_file is None:
        errores_validacion.append("Debes subir un archivo PDF.")

    if not usar_excel_nuevo and excel_file is None:
        errores_validacion.append(
            "Debes subir un archivo Excel destino o marcar la opción de crear uno nuevo."
        )

    if errores_validacion:
        for msg in errores_validacion:
            st.error(msg)
        st.stop()

    # --- Procesamiento ---
    with st.spinner(f"Procesando PDF con el parser de {proveedor_seleccionado}..."):

        try:
            # 1. Obtener los bytes del PDF
            pdf_bytes = pdf_file.read()

            # 2. Extraer texto plano para debug (antes de parsear)
            texto_extraido = extract_text(pdf_bytes)
            with st.expander("DEBUG TEXT — texto extraído del PDF", expanded=False):
                st.text_area(
                    label="Primeros 2000 caracteres del texto extraído por pdfplumber",
                    value=texto_extraido[:2000] if texto_extraido else "(sin texto extraído)",
                    height=300,
                    disabled=True,
                )

            # 3. Instanciar el parser correcto según el proveedor
            parser = get_parser(proveedor_seleccionado)

            # 4. Ejecutar el parsing
            filas = parser.parse(pdf_bytes)

            # 5. Obtener advertencias y errores del parser
            advertencias = parser.get_advertencias()
            errores_parser = parser.get_errores()

            # 6. Mostrar advertencias del parser (no fatales)
            if advertencias:
                st.warning(
                    "Advertencias del parser:\n" + formatear_lista_errores(advertencias)
                )

            # 7. Si hay errores fatales del parser, detener
            if errores_parser:
                st.error(
                    "Errores durante el parsing:\n" + formatear_lista_errores(errores_parser)
                )
                st.stop()

            # 8. Preparar el Excel destino
            if usar_excel_nuevo:
                excel_bytes_origen = crear_excel_vacio()
                nombre_excel_salida = "resultado_nuevo.xlsx"
            else:
                excel_bytes_origen = excel_file.read()
                nombre_excel_salida = excel_file.name

            # 9. Escribir el output en el Excel
            if filas:
                excel_bytes_resultado = exportar_a_excel(
                    filas=filas,
                    excel_bytes=excel_bytes_origen,
                )
                filas_escritas = len(filas)
            else:
                # El parser no devolvió datos
                excel_bytes_resultado = excel_bytes_origen
                filas_escritas = 0

            # --- Resultado del procesamiento ---
            st.success(
                f"Procesamiento completado. "
                f"Filas extraídas: **{filas_escritas}** | "
                f"Proveedor: **{proveedor_seleccionado}**"
            )

            # 9. Mostrar preview de los datos extraídos
            if filas:
                st.subheader("Vista previa de los datos extraídos")
                df_preview = parser.to_dataframe(filas)
                st.dataframe(df_preview, use_container_width=True)
            else:
                st.info("El parser no devolvió datos para este PDF.")

            # 10. Botón de descarga del Excel actualizado
            st.divider()
            st.subheader("Descargar Excel actualizado")
            st.download_button(
                label="Descargar Excel con los datos extraídos",
                data=excel_bytes_resultado,
                file_name=nombre_excel_salida,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
            )

        except ValueError as e:
            st.error(f"Error de configuración: {e}")
        except Exception as e:
            st.error(f"Error inesperado durante el procesamiento: {e}")
            raise  # En desarrollo es útil ver el traceback completo en la consola
