"""
parser_metalicas_julio_garcia.py
Parser específico para el proveedor Metálicas Julio García (MJG).

Formato de línea de producto:
  {CÓDIGO} {DESCRIPCIÓN} {CANT} {PRECIO} {DTO%} {IMPORTE}
  — todos los números usan coma como separador decimal.

Ejemplos reales (4 números al final = con descuento):
  1000AD10 Señal Adhesiva 10x10cm Troquelada - Riesgo Electrico 1,00 1,00 50,00 0,50
  1000AD15 Señal Adhesiva 15x15cm Troquelada - Riesgo Electrico 1,00 1,70 50,00 0,85
  PERSO-ADH Adhesivo - Señal TROQUELADA de medida: 70x70mm 1,00 1,10 50,00 0,55
  SA-1000-A4AL Señal ALUM 21x29cm - Riesgo eléctrico 2,00 5,98 50,00 5,98

Casos especiales manejados:
  · Multilinea 3+:   descripción partida en varias líneas de PDF
  · Código pegado:   SA-1000-40X30ALSeñal ALUM → sep. en SA-1000-40X30AL + Señal ALUM
  · Palabras fusionadas: SeñalAdhesiva → Señal Adhesiva

Líneas que deben excluirse:
  PETT Portes mercancias agencias CTT EXPRESS 1,00 4,00 4,00
  PLAZO6 Plazo de entrega 6/7 días habiles + agencia de tptes
  CERRADO CERRADO POR FESTIVOS DEL 2 AL 6 DE ABRIL
"""

import io
import re
from typing import Any, Dict, List, Optional, Tuple, Union

import pdfplumber

from parser_base import BaseParser


# ===========================================================================
# Función auxiliar — extracción de medidas dimensionales
# ===========================================================================

def extract_medidas(descripcion: str) -> str:
    """
    Extrae la medida dimensional desde la descripción del artículo.

    Patrones soportados:
      · NxNmm   → "10x10mm", "70x70mm", "200x15mm"
      · NxNcm   → "10x10cm", "21x29cm", "30x40cm", "150x100cm"
      · NxNm    → "2x3m"
      · Con espacios alrededor de 'x': "10 x 10 cm"  → normalizado a "10x10cm"

    Reglas:
      · Devuelve la medida normalizada sin espacios extra.
      · Si no detecta ningún patrón → devuelve "".
      · NO elimina la medida de la descripción original.

    Ejemplos:
        extract_medidas("Señal Adhesiva 10x10cm Troquelada")   → "10x10cm"
        extract_medidas("Señal TROQUELADA de medida: 70x70mm") → "70x70mm"
        extract_medidas("Señal ALUM 21x29cm - Riesgo")         → "21x29cm"
        extract_medidas("Perfil sin medidas")                   → ""
    """
    if not descripcion:
        return ""

    _RE_DIM = re.compile(
        r'(\d+[\.,]?\d*'        # primer número (puede tener decimal)
        r'\s*[xX]\s*'           # separador x (case-insensitive)
        r'\d+[\.,]?\d*'         # segundo número
        r'\s*(?:mm|cm|m)\b)',   # unidad de medida
        re.IGNORECASE,
    )
    m = _RE_DIM.search(descripcion)
    if m:
        medida = m.group(1).strip()
        medida = re.sub(r'\s*[xX]\s*', 'x', medida)                         # normaliza 'x'
        medida = re.sub(r'\s+(?=mm|cm|m\b)', '', medida, flags=re.IGNORECASE)  # pega unidad
        return medida
    return ""


# ===========================================================================
# Parser Metálicas Julio García
# ===========================================================================

class MetalicasJulioGarciaParser(BaseParser):
    """
    Parser para presupuestos y albaranes del proveedor Metálicas Julio García.

    Arquitectura interna (5 fases):
    ──────────────────────────────
    1. _extraer_texto()         → obtiene texto del PDF con pdfplumber.
    2. _reconstruir_bloques()   → agrupa líneas del PDF en bloques de artículo
                                  (maneja multilinea 2, 3 y más líneas).
    3. _parsear_bloque()        → por cada bloque:
         a. _separar_codigo_descripcion()  → divide código / descripción+números
         b. _extraer_numeros_finales()     → extrae los 3 o 4 números del final
         c. _limpiar_descripcion()         → corrige palabras fusionadas (CamelCase)
         d. _es_linea_excluida()           → descarta portes, plazos, avisos
    4. _construir_fila()        → devuelve dict con las 12 columnas objetivo.

    Nota técnica sobre mayúsculas en regex:
      Los patrones de código NO usan re.IGNORECASE porque los códigos de MJG
      son siempre MAYÚSCULAS (ej: 1000AD10, PERSO-ADH, SA-1000-A4AL).
      Esto evita que palabras de descripción en minúsculas ("Riesgo", "eléctrico")
      sean interpretadas erróneamente como inicio de un nuevo artículo.
    """

    PROVEEDOR = "Metálicas Julio García"

    # -----------------------------------------------------------------------
    # Marcadores de sección
    # -----------------------------------------------------------------------

    # Cabecera de tabla: acepta variantes con/sin tildes, columnas extra
    _RE_INICIO_TABLA = re.compile(
        r'C[OÓ]DIGO.{0,60}(?:CANT\.?|CANTIDAD).{0,40}PRECIO',
        re.IGNORECASE,
    )

    # Fin de tabla: totales, resúmenes, condiciones de pago.
    # TODOS los patrones usan \b para evitar falsos positivos dentro de
    # descripciones (p.ej. "Adhes[iva 1]0x10cm" NO debe disparar IVA\s+\d).
    _RE_FIN_TABLA = re.compile(
        r'\bTOTAL\s*(?:BRUTO|IMPORTE|FACTURA|PEDIDO)\b'
        r'|\bBASE\s*IMPONIBLE\b'
        r'|\bFORMA\s*(?:DE\s*)?PAGO\b'
        r'|\bSUBTOTAL\b'
        r'|\bI\.?V\.?A\.?\b\s+\d'   # "IVA 21%", "I.V.A. 10%"
        r'|\bVENCIMIENTO\b',
        re.IGNORECASE,
    )

    # Inicio de artículo: línea que empieza con código MAYÚSCULAS (≥3 chars)
    # Ejemplos: "1000AD10", "PERSO-ADH", "SA-1000-A4AL"
    # NO coincide con: "Riesgo", "tintas UVI", "12,00 50,00"
    _RE_INICIO_ARTICULO = re.compile(
        r'^([A-Z0-9][A-Z0-9\-/]{2,})'
        # Sin IGNORECASE: asegura que sea código real y no texto en minúsculas
    )

    # Patrón que detecta números decimales al inicio (línea solo de números)
    _RE_SOLO_NUMEROS = re.compile(
        r'^\d+[,\.]\d+'
    )

    # -----------------------------------------------------------------------
    # Sistema de exclusión de líneas no-producto
    # -----------------------------------------------------------------------

    _CODIGOS_EXCLUIDOS: frozenset = frozenset({
        'PETT', 'PETT1', 'PETT2',
        'PLAZO', 'PLAZO6', 'PLAZO7', 'PLAZO10',
        'CERRADO', 'FESTIVO',
        'AVISO', 'NOTA', 'INFO',
        'GLS', 'CTT', 'SEUR', 'MRW', 'DHL', 'UPS', 'TNT',
        'PORTES', 'TRANSPORTE',
        # Códigos de referencia interna que aparecen solos en el PDF (artefactos)
        'SA-1000',
    })

    _RE_DESC_EXCLUIDA = re.compile(
        r'portes?\s+mercan'
        r'|plazo\s+de\s+entrega'
        r'|cerrado\s+por'
        r'|festiv'
        r'|agencia\s+de\s+(?:tptes?|transportes?)'
        r'|d[ií]as?\s+h[áa]bil'
        r'|agencias?\s+(?:CTT|GLS|SEUR|MRW|DHL|UPS)',
        re.IGNORECASE,
    )

    # -----------------------------------------------------------------------
    # Interfaz pública (contrato de BaseParser)
    # -----------------------------------------------------------------------

    def parse(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Extrae las líneas de artículos del PDF de Metálicas Julio García.

        Args:
            pdf_bytes: Bytes del PDF (de st.file_uploader).

        Returns:
            Lista de dicts con las 12 columnas objetivo. Lista vacía si error.
        """
        self.errores = []
        self.advertencias = []

        if not pdf_bytes:
            self._registrar_error("MetalicasJulioGarciaParser: bytes vacíos recibidos.")
            return []

        pdf_text = self._extraer_texto(pdf_bytes)

        if not pdf_text or not pdf_text.strip():
            self._registrar_error(
                "MetalicasJulioGarciaParser: no se pudo extraer texto del PDF. "
                "El archivo puede estar protegido o ser imagen escaneada."
            )
            return []

        try:
            return self._parse_texto(pdf_text)
        except Exception as e:
            self._registrar_error(f"MetalicasJulioGarciaParser: error inesperado: {e}")
            return []

    # -----------------------------------------------------------------------
    # Fase 1 — Extracción de texto
    # -----------------------------------------------------------------------

    def _extraer_texto(self, pdf_bytes: bytes) -> str:
        """Extrae texto de todas las páginas del PDF con pdfplumber."""
        partes: List[str] = []
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for num_pag, page in enumerate(pdf.pages, start=1):
                    texto = page.extract_text()
                    if texto:
                        partes.append(texto)
                    else:
                        self._registrar_advertencia(
                            f"MetalicasJulioGarciaParser: "
                            f"página {num_pag} sin texto extraíble (¿imagen?)."
                        )
        except Exception as e:
            self._registrar_error(
                f"MetalicasJulioGarciaParser: error al leer PDF: {e}"
            )
        return "\n".join(partes)

    # -----------------------------------------------------------------------
    # Fase 2 — Reconstrucción de bloques multilinea
    # -----------------------------------------------------------------------

    def _parse_texto(self, pdf_text: str) -> List[Dict[str, Any]]:
        """
        Orquesta las fases de parsing:
          1. Localiza el bloque de artículos entre cabecera y totales.
          2. Reconstruye artículos multilinea acumulando líneas por bloque.
          3. Parsea cada bloque acumulado.
        """
        filas: List[Dict[str, Any]] = []
        en_seccion = False
        buffer: str = ""

        for linea in pdf_text.splitlines():
            linea_strip = linea.strip()

            # Ignorar líneas vacías
            if not linea_strip:
                continue

            # ── Detección de inicio/repetición de cabecera de tabla ────────
            if self._RE_INICIO_TABLA.search(linea_strip):
                en_seccion = True
                continue   # Saltar siempre la línea de cabecera (incl. pág. 2+)

            if not en_seccion:
                continue

            # ── Detección de fin de tabla ──────────────────────────────────
            if self._RE_FIN_TABLA.search(linea_strip):
                break

            # ── Líneas a ignorar completamente (artefactos del PDF) ────────
            # Incluye: códigos solitarios ("SA-1000"), separadores de sección
            # ("*** SEÑALES TROQUELADAS...") y otras líneas de ruido.
            # Estas líneas NO vuelcan el buffer ni se añaden a él.
            if self._es_linea_a_ignorar(linea_strip):
                continue

            # ── ¿La línea empieza con un nuevo código de artículo? ─────────
            if self._es_inicio_articulo(linea_strip):
                # Volcar buffer anterior como bloque completo
                if buffer:
                    fila = self._parsear_bloque(buffer)
                    if fila:
                        filas.append(fila)
                buffer = linea_strip

            else:
                # Línea de continuación: texto o números que completan el bloque.
                if buffer and len(buffer) < 600:
                    if self._RE_SOLO_NUMEROS.match(linea_strip):
                        # Línea de solo números (ej: "12,00") → siempre al final
                        buffer = buffer + " " + linea_strip
                    else:
                        # Texto de descripción (ej: "tintas UVI").
                        # PROBLEMA REAL DEL PDF: pdfplumber puede colocar una
                        # línea de descripción desbordada DESPUÉS de los números,
                        # porque el importe ocupa una línea y la descripción otra.
                        # Secuencia habitual:
                        #   "...de 150x100cm con 2,00 12,00 50,00"  ← línea 1
                        #   "12,00"                                  ← importe
                        #   "tintas UVI"                             ← desc overflow
                        # Si el buffer ya termina con números decimales, insertar
                        # el texto ANTES de esos números para que _extraer_numeros
                        # los siga encontrando al final.
                        trail = re.search(
                            r'((?:\s+\d+[,\.]\d+){2,})\s*$', buffer
                        )
                        if trail:
                            # Texto overflow: va antes de los números finales
                            buffer = (buffer[:trail.start()]
                                      + " " + linea_strip
                                      + buffer[trail.start():])
                        else:
                            buffer = buffer + " " + linea_strip
                # Si no hay buffer activo, esta línea es ruido pre-tabla → ignorar

        # Volcar último bloque pendiente
        if buffer:
            fila = self._parsear_bloque(buffer)
            if fila:
                filas.append(fila)

        # ── Advertencias de resultado ──────────────────────────────────────
        if not en_seccion:
            self._registrar_advertencia(
                "MetalicasJulioGarciaParser: no se encontró la cabecera de tabla "
                "('CÓDIGO ... CANT. ... PRECIO'). "
                "Verifica que el PDF pertenece a Metálicas Julio García "
                "y que el texto es seleccionable."
            )
        elif not filas:
            self._registrar_advertencia(
                "MetalicasJulioGarciaParser: tabla detectada pero sin artículos extraídos. "
                "Puede que el formato de las líneas haya cambiado."
            )

        return filas

    # -----------------------------------------------------------------------
    # Clasificación de líneas
    # -----------------------------------------------------------------------

    def _es_linea_a_ignorar(self, linea: str) -> bool:
        """
        Devuelve True para líneas que deben saltarse completamente:
        NO vuelcan el buffer ni se añaden a él.

        Casos:
          1. Separadores de sección: "*** SEÑALES TROQUELADAS, FORMA DE TRIANGULO"
             (líneas que empiezan con uno o más '*')
          2. Códigos solitarios: una línea que es SOLO un código sin descripción
             ni números detrás, como "SA-1000" que aparece como etiqueta de
             referencia en las celdas multilínea del PDF de MJG.

        Estos son artefactos del PDF que no forman parte de ningún artículo.
        """
        # Caso 1: separador de sección (empieza con *)
        if linea.startswith('*'):
            return True

        # Caso 2: código CONOCIDO como artefacto, solo en la línea (ej: "SA-1000")
        # Solo se ignoran códigos de la lista _CODIGOS_EXCLUIDOS cuando aparecen
        # solos. Un código real como "PERSO-150X100" en solitario NO se ignora:
        # su descripción puede venir en la línea siguiente.
        m = self._RE_INICIO_ARTICULO.match(linea)
        if m and self._es_codigo_valido(m.group(1)):
            resto = linea[m.end():].strip()
            if not resto:
                codigo = m.group(1).upper().strip()
                if codigo in self._CODIGOS_EXCLUIDOS:
                    return True   # Artefacto conocido (SA-1000, PETT, etc.)

        return False

    def _es_inicio_articulo(self, linea: str) -> bool:
        """
        Devuelve True si la línea empieza con lo que parece un código MJG
        seguido de contenido (descripción o números).

        Criterios:
          · Comienza con secuencia [A-Z0-9][A-Z0-9\\-/]{2,}  (≥3 chars de código)
          · El código extraído pasa _es_codigo_valido()
          · La línea no es solo números (ej: "12,00 50,00 12,00" = continuación)
          · Hay algo después del código (no es línea de código solitario, ya
            filtrada antes por _es_linea_a_ignorar)

        Ejemplos que devuelven True:
          "1000AD10 Señal Adhesiva..."    → True
          "PERSO-ADH Adhesivo..."         → True
          "SA-1000-40X30ALSeñal ALUM..."  → True  (código pegado a descripción)

        Ejemplos que devuelven False:
          "tintas UVI"                    → False  (minúsculas)
          "Riesgo eléctrico"              → False  (minúsculas tras R)
          "12,00 50,00 12,00"             → False  (solo números)
          "con 2,00 tintas"               → False  (minúsculas)
        """
        if self._RE_SOLO_NUMEROS.match(linea):
            return False  # Línea que empieza con decimal → continuación numérica
        m = self._RE_INICIO_ARTICULO.match(linea)
        if not m:
            return False
        codigo = m.group(1)
        # Excepción: códigos de la lista de exclusión SIN dígito/guión (PETT, CERRADO…)
        # Deben tratarse como inicio de bloque para que el buffer anterior se vuelque
        # correctamente. El bloque se descartará después en _parsear_bloque.
        if codigo.upper().strip() in self._CODIGOS_EXCLUIDOS:
            return True
        return self._es_codigo_valido(codigo)

    # -----------------------------------------------------------------------
    # Fase 3a — Separación código / resto del bloque
    # -----------------------------------------------------------------------

    @staticmethod
    def _separar_codigo_descripcion(bloque: str) -> Tuple[Optional[str], str]:
        """
        Extrae el código del principio del bloque y devuelve (código, resto).

        Maneja el caso de código y descripción pegados sin espacio:
          "SA-1000-40X30ALSeñal ALUM 30x40cm 1,00 5,98 50,00 5,98"
           → código="SA-1000-40X30AL",  resto="Señal ALUM 30x40cm 1,00 ..."

        Algoritmo:
          1. El regex consume todos los chars [A-Z0-9\\-/] del principio.
          2. Si lo que sigue (resto) empieza con minúscula (o letra acentuada
             sin espacio previo), el último carácter del código es en realidad
             el inicio de la primera palabra de la descripción: se devuelve al resto.
          3. Se repite hasta que el resto empiece con mayúscula, dígito o espacio.

        Returns:
            (codigo, resto_sin_codigo)  — resto incluye descripción Y números.
            (None, bloque)              — si no se detecta código válido.
        """
        m = re.match(r'^([A-Z0-9][A-Z0-9\-/]*)(.*)', bloque)
        if not m:
            return None, bloque

        codigo = m.group(1)
        resto = m.group(2)

        # ── Caso especial A: palabra larga tras dígito (sin espacio entre cols) ──
        # "PERSO-150X100ALUMINIO 0,8mm..." → código="PERSO-150X100",
        #                                     resto="ALUMINIO 0,8mm..."
        # Ocurre cuando pdfplumber no añade espacio entre columnas y la
        # descripción empieza con una palabra larga en mayúsculas (≥5 letras)
        # que va pegada inmediatamente detrás de un dígito del código.
        word_post_digit = re.search(r'(?<=\d)([A-Z]{5,})$', codigo)
        if word_post_digit:
            word = word_post_digit.group(1)
            split_pos = len(codigo) - len(word)
            resto = word + ' ' + resto.lstrip()
            codigo = codigo[:split_pos]
            resto = resto.strip()
            if not codigo:
                return None, bloque
            # Continuar (puede ser necesario el check de duplicación también)

        # ── Caso especial B: palabra duplicada (PERSO-ALUMINIOALUMINIO) ────────
        # Ocurre cuando pdfplumber pega sin espacio y la descripción empieza
        # con la misma palabra que termina el código.
        # Ejemplo: "PERSO-ALUMINIO" + "ALUMINIO 0,8mm..." extraído como
        #          "PERSO-ALUMINIOALUMINIO 0,8mm..."
        # Detección: el código termina con una secuencia de ≥3 mayúsculas
        # repetida dos veces seguidas (ej: ALUMINIOALUMINIO).
        dup_m = re.search(r'([A-Z]{3,})\1$', codigo)
        if dup_m:
            word = dup_m.group(1)
            split_pos = len(codigo) - len(word)
            # La segunda ocurrencia pasa a ser el inicio de la descripción
            resto = word + ' ' + resto.lstrip()
            codigo = codigo[:split_pos]
            resto = resto.strip()
            if not codigo:
                return None, bloque
            return codigo, resto

        # ── Caso especial C: guión + prefijo corto + palabra de descripción ──────
        # "PERSO-150X100-CALUMINIO 0,8mm..." → código="PERSO-150X100-C",
        #                                       resto="ALUMINIO 0,8mm..."
        # Ocurre cuando el código termina en un segmento como "-C" y pdfplumber
        # lo pega sin espacio con la primera palabra de la descripción "ALUMINIO",
        # formando "-CALUMINIO".
        #
        # Condición de activación:
        #   · El código termina en -[1-3 chars][4+ letras mayúsculas]
        #   · El texto a continuación empieza con no-mayúscula (dígito, minúscula)
        #     → indica que la palabra larga era la descripción, no el código
        #
        # NO activa si la descripción empieza con mayúscula (ej: "ALUMINIO..."),
        # ya que en ese caso la separación ya es correcta (o la maneja Fix B).
        resto_strip_c = resto.lstrip()
        if resto_strip_c and not resto_strip_c[0].isupper():
            long_seg = re.search(r'-([A-Z0-9]{1,3}?)([A-Z]{4,})$', codigo)
            if long_seg:
                word = long_seg.group(2)
                split_pos = len(codigo) - len(word)
                resto = word + ' ' + resto_strip_c
                codigo = codigo[:split_pos]
                resto = resto.strip()
                if not codigo:
                    return None, bloque
                return codigo, resto

        # Si hay espacio al principio del resto → separación limpia
        if resto.startswith(' '):
            return codigo, resto.lstrip()

        # Sin espacio: código y descripción están pegados.
        # Retroceder desde el final del código hasta que el resto empiece
        # con un carácter "de inicio de palabra real" (mayúscula + minúscula).
        # Señal → 'S' (upper) + 'e' (lower)  → es inicio de palabra
        # Adhesiva → 'A' + 'd' → inicio de palabra
        # Riesgo → 'R' + 'i' → inicio de palabra
        while len(codigo) > 1 and resto:
            # ¿El resto empieza con mayúscula seguida de minúscula?
            if (len(resto) >= 2
                    and resto[0].isupper()
                    and (not resto[1].isupper() and not resto[1].isdigit())):
                break   # Hemos encontrado la frontera palabra / código
            # ¿El resto empieza con minúscula o acento (letra fusionada)?
            if resto[0].islower() or (not resto[0].isupper() and not resto[0].isdigit()):
                # Devolver el último char del código al resto
                resto = codigo[-1] + resto
                codigo = codigo[:-1]
            else:
                break

        if not codigo:
            return None, bloque

        return codigo, resto

    # -----------------------------------------------------------------------
    # Fase 3b — Extracción de números finales
    # -----------------------------------------------------------------------

    @staticmethod
    def _extraer_numeros_finales(
        texto: str,
    ) -> Optional[Tuple[str, List[str]]]:
        """
        Extrae los 3 o 4 números decimales (con coma o punto) que cierran el texto.

        Prueba primero 4 números (con descuento), luego 3 (sin descuento).

        Returns:
            (texto_antes_de_numeros, [n1, n2, n3, n4])   — con dto
            (texto_antes_de_numeros, [n1, n2, n3])        — sin dto
            None                                           — si no hay números
        """
        # Intentar 4 números al final
        m4 = re.match(
            r'^(.*?)\s+'
            r'(\d+[,\.]\d+)\s+(\d+[,\.]\d+)\s+(\d+[,\.]\d+)\s+(\d+[,\.]\d+)\s*$',
            texto,
            re.DOTALL,
        )
        if m4:
            return m4.group(1).strip(), [m4.group(2), m4.group(3), m4.group(4), m4.group(5)]

        # Intentar 3 números al final
        m3 = re.match(
            r'^(.*?)\s+'
            r'(\d+[,\.]\d+)\s+(\d+[,\.]\d+)\s+(\d+[,\.]\d+)\s*$',
            texto,
            re.DOTALL,
        )
        if m3:
            return m3.group(1).strip(), [m3.group(2), m3.group(3), m3.group(4)]

        return None

    # -----------------------------------------------------------------------
    # Fase 3c — Limpieza de descripción
    # -----------------------------------------------------------------------

    @staticmethod
    def _limpiar_descripcion(desc: str) -> str:
        """
        Limpia y normaliza la descripción extraída del bloque.

        Operaciones:
          1. Inserta espacio en fronteras CamelCase (palabras fusionadas):
               "SeñalAdhesiva"  → "Señal Adhesiva"
               "RiesgoElectrico"→ "Riesgo Electrico"
          2. Normaliza espacios múltiples a uno solo.
          3. Elimina guiones sueltos al inicio o al final.
          4. Elimina espacios sobrantes al inicio/final.

        Ejemplos:
            "SeñalAdhesiva 10x10cm"       → "Señal Adhesiva 10x10cm"
            " - Señal personalizada - "    → "Señal personalizada"
            "Adhesivo   TROQUELADO"        → "Adhesivo TROQUELADO"
        """
        if not desc:
            return desc

        # 1. Insertar espacio en frontera lowercase→uppercase (CamelCase)
        #    Cubre letras con tildes/eñe: á é í ó ú ü ñ Á É Í Ó Ú Ü Ñ
        desc = re.sub(r'(?<=[a-záéíóúüñ])(?=[A-ZÁÉÍÓÚÜÑ])', ' ', desc)

        # 2. Normalizar espacios
        desc = re.sub(r'\s+', ' ', desc).strip()

        # 3. Eliminar guión solitario al principio o al final
        desc = re.sub(r'^[\s\-]+|[\s\-]+$', '', desc).strip()

        return desc

    # -----------------------------------------------------------------------
    # Fase 3 — Parseo de un bloque completo
    # -----------------------------------------------------------------------

    def _parsear_bloque(self, bloque: str) -> Optional[Dict[str, Any]]:
        """
        Parsea un bloque de texto que representa un artículo completo.

        El bloque puede ser una sola línea o la unión de varias líneas del PDF.
        Ejemplo de bloque multilínea reconstruido:
          "PERSO-150X100-CALUMINIO 0,8mm - Señal personalizada de 150x100cm con 2,00 tintas UVI 12,00 50,00 12,00"

        Flujo:
          1. _separar_codigo_descripcion  → (codigo, texto_sin_codigo)
          2. _extraer_numeros_finales     → (desc_raw, [nums])
          3. _limpiar_descripcion         → desc limpia
          4. Validaciones (código + exclusiones)
          5. _construir_fila
        """
        # — Paso 1: separar código —
        codigo, resto = self._separar_codigo_descripcion(bloque)
        if not codigo or not resto:
            return None
        if not self._es_codigo_valido(codigo):
            return None

        # — Paso 2: extraer números del final —
        resultado = self._extraer_numeros_finales(resto)
        if resultado is None:
            return None

        desc_raw, nums = resultado

        if len(nums) == 4:
            cant, precio, dto, importe = nums
        elif len(nums) == 3:
            cant, precio, importe = nums
            dto = ""
        else:
            return None

        # — Paso 3: limpiar descripción —
        desc = self._limpiar_descripcion(desc_raw)
        if not desc:
            return None

        # — Paso 4: validaciones de exclusión —
        if self._es_linea_excluida(codigo, desc):
            return None

        # — Paso 5: construir fila —
        return self._construir_fila(
            codigo=codigo,
            descripcion=desc,
            cantidad=cant,
            precio=precio,
            dto=dto,
            importe=importe,
        )

    # -----------------------------------------------------------------------
    # Validaciones
    # -----------------------------------------------------------------------

    @staticmethod
    def _es_codigo_valido(codigo: str) -> bool:
        """
        Verifica que el código es un código de producto real de MJG,
        no un fragmento de texto de descripción.

        Regla: después de quitar dígitos, guiones y barras, las letras
        restantes deben ser todas MAYÚSCULAS (o no quedar ninguna letra).

        Acepta:   "1000AD10"    → tiene dígito + letras=AD  → isupper ✓
                  "PERSO-ADH"  → tiene guión  + letras=PERSOADH → isupper ✓
                  "SA-1000-A4AL"→ tiene guión y dígito → isupper ✓
        Rechaza:  "Riesgo"     → letras=Riesgo → NOT isupper ✗
                  "eléctrico"  → letras=eltrico → NOT isupper ✗
                  "ALUMINIO"   → solo letras, sin dígito ni guión ✗
                  "SEÑAL"      → solo letras, sin dígito ni guión ✗

        Nota: los códigos MJG son identificadores estructurados (siempre
        contienen al menos un dígito o guión). Las palabras puramente
        alfabéticas como ALUMINIO o SEÑAL son descripciones, no códigos.
        """
        if len(codigo) < 3:
            return False
        letras = re.sub(r'[\d\-/]', '', codigo)
        if letras and not letras.isupper():
            return False
        # Los códigos MJG siempre tienen al menos un dígito o guión/barra.
        # Palabras solo con letras (ALUMINIO, SEÑAL...) son descripciones.
        if not re.search(r'[\d\-/]', codigo):
            return False
        return True

    def _es_linea_excluida(self, codigo: str, desc: str) -> bool:
        """
        Devuelve True si la línea no es un artículo vendible
        (portes, plazo de entrega, aviso de cierre, etc.).
        """
        if codigo.upper().strip() in self._CODIGOS_EXCLUIDOS:
            return True
        if self._RE_DESC_EXCLUIDA.search(desc):
            return True
        return False

    # -----------------------------------------------------------------------
    # Construcción del dict de salida
    # -----------------------------------------------------------------------

    def _construir_fila(
        self,
        codigo: str,
        descripcion: str,
        cantidad: str,
        precio: str,
        dto: str,
        importe: str,
    ) -> Dict[str, Any]:
        """
        Construye el dict con las 12 columnas objetivo.

        Mapeo PDF → columnas Excel:
          CÓDIGO      → Modelo
          DESCRIPCIÓN → Descripción
          CANT        → Cantidad
          PRECIO      → Coste vigente  +  Precio venta excl. IVA
          DTO%        → % Descuento línea  (vacío si no existe)
          IMPORTE     → Importe  +  Importe línea excl. IVA
          (fijo)      → Marca = "METÁLICAS JULIO GARCÍA"
          (auto)      → Medidas ← extract_medidas(descripción)

        Nota: "Cód. concepto" y "Nº" los calcula excel_exporter.py.
        """
        return {
            "Descripción":             descripcion,
            "Marca":                   "METÁLICAS JULIO GARCÍA",
            "Modelo":                  codigo.strip(),
            "Medidas":                 extract_medidas(descripcion),
            "Cantidad":                _a_float(cantidad),
            "Coste vigente":           _a_float(precio),
            "Coste unitario (DL)":     "",
            "Precio venta excl. IVA":  _a_float(precio),
            "% Descuento línea":       _a_float(dto) if dto else "",
            "Margen":                  "",
            "Importe":                 _a_float(importe),
            "Importe línea excl. IVA": _a_float(importe),
        }


# ===========================================================================
# Helpers de módulo
# ===========================================================================

def _a_float(valor: str) -> Union[float, str]:
    """
    Convierte cadena numérica (coma o punto decimal) a float.
    Devuelve "" si el valor está vacío o no es convertible.

        "1,00"  → 1.0
        "50,00" → 50.0
        "5,98"  → 5.98
        ""      → ""
    """
    if not valor or not valor.strip():
        return ""
    try:
        return float(valor.strip().replace(",", "."))
    except ValueError:
        return ""
