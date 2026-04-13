# 📄 PDF to Excel Extractor (Multi-Provider)

Aplicación en Python para extraer información de PDFs comerciales (ofertas, presupuestos y facturas) y volcarla en un archivo Excel seleccionado por el usuario.

Este proyecto está diseñado para trabajar con múltiples proveedores, cada uno con su propio formato de documento, mediante una arquitectura modular basada en parsers independientes.

---

## 🚀 Estado del proyecto

🔧 **Fase 1 (actual):**

* Interfaz en Streamlit
* Subida de PDF
* Selección manual de proveedor
* Selección de Excel destino
* Arquitectura modular con parsers por proveedor
* Flujo preparado para extracción y escritura en Excel

📌 **Fases siguientes:**

* Parsing específico por proveedor
* Extracción estructurada de líneas de artículos
* Mejora de heurísticas de detección
* Validación y limpieza de datos

---

## 🧱 Estructura del proyecto

```
pdf_parser_app/
│
├── app.py
├── parser_base.py
├── parser_mavy.py
├── parser_metalicas_julio_garcia.py
├── parser_onelec.py
├── parser_jabad.py
├── excel_exporter.py
├── utils.py
├── requirements.txt
```

---

## 🧠 Concepto

Los PDFs comerciales no tienen un formato homogéneo.
Cada proveedor estructura sus documentos de forma distinta.

Por eso, en lugar de un parser genérico, el proyecto utiliza:

👉 **Un parser específico por proveedor**

Proveedores soportados actualmente:

* MAVY
* Metálicas Julio García
* ONELEC
* J.ABAD

Cada uno tiene su propio archivo `.py` y lógica independiente.

---

## ⚙️ Instalación

1. Clonar el repositorio:

```
git clone https://github.com/tu-usuario/pdf-parser-app.git
cd pdf-parser-app
```

2. Crear entorno virtual:

```
python -m venv venv
```

3. Activar entorno:

Windows:

```
venv\Scripts\activate
```

4. Instalar dependencias:

```
pip install -r requirements.txt
```

---

## ▶️ Ejecución

```
streamlit run app.py
```

Se abrirá automáticamente en el navegador.

---

## 🖥️ Uso

1. Subir un PDF comercial
2. Seleccionar el proveedor en el desplegable
3. Subir el Excel destino (.xlsx)
4. Pulsar "Procesar"
5. Visualizar resultados
6. Descargar Excel actualizado

---

## 📊 Comportamiento del Excel

* El usuario siempre proporciona el Excel destino
* Los datos se escriben a partir de la última fila con datos
* No se sobrescriben datos existentes
* No se duplican cabeceras
* Si el Excel está vacío:

  * se insertan directamente los datos sin añadir cabecera

---

## 🧩 Arquitectura

El sistema está diseñado para escalar fácilmente:

* `parser_base.py` → interfaz común
* `parser_*.py` → lógica específica por proveedor
* `app.py` → interfaz y orquestación
* `excel_exporter.py` → escritura en Excel

Añadir un nuevo proveedor implica:

1. Crear un nuevo parser
2. Integrarlo en el selector de la app

---

## 📦 Generar ejecutable (.exe)

Para crear un ejecutable en Windows:

1. Instalar PyInstaller:

```
pip install pyinstaller
```

2. Crear archivo `run_app.py`:

```python
import os

if __name__ == "__main__":
    os.system("streamlit run app.py")
```

3. Generar ejecutable:

```
pyinstaller --onefile --noconsole run_app.py
```

El ejecutable estará en:

```
dist/run_app.exe
```

---

## 🧪 Tecnologías utilizadas

* Python
* Streamlit
* pdfplumber (lectura de PDFs)
* pandas
* openpyxl
* PyInstaller

---

## 💡 Notas

* Este proyecto está pensado como herramienta interna para automatización
* El foco está en robustez y adaptabilidad a múltiples formatos de PDF
* La lógica de parsing se desarrollará progresivamente por proveedor

---

## 📌 Roadmap

* [ ] Parser MAVY completo
* [ ] Parser Metálicas Julio García
* [ ] Parser ONELEC
* [ ] Parser J.ABAD
* [ ] Mejora de UI
* [ ] Validación de datos
* [ ] Logs y trazabilidad

---

## 👤 Autor

Rosalía Contreras Moreira
[LinkedIn / Web si quieres añadirlo]

---

## 📄 Licencia

Uso interno / pendiente de definir