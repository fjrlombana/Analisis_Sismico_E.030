"""
datos.py
========
Todo lo relacionado con los DATOS DE ENTRADA:
  - datos de ejemplo (edificio de 5 pisos del ejercicio),
  - lectura de archivos Excel (.xlsx) o CSV,
  - validación (que no falten columnas, que no haya celdas vacías...),
  - conversión de tablas (DataFrame) a arreglos de NumPy para el cálculo,
  - generación de plantillas descargables.

Formato de las tablas
---------------------
Tabla "Estructura" (una fila por piso):
    | Piso | Masa | Modo 1 | Modo 2 | Modo 3 | ...

Tabla "Periodos" (una fila por modo):
    | Modo   | T (s) |
    | Modo 1 | 0.556 |

Formato de archivo Excel:  hojas "Estructura", "Periodos" y (opcional) "Parametros".
Formato de archivo CSV:    la tabla Estructura + una fila final con Piso = "T"
                           que contiene los periodos de cada modo (igual que la
                           tabla del enunciado).
"""

import io

import numpy as np
import pandas as pd

from .parametros import ParametrosSismicos

COL_PISO = "Piso"
COL_MASA = "Masa"
COL_T = "T (s)"
HOJA_ESTRUCTURA = "Estructura"
HOJA_PERIODOS = "Periodos"
HOJA_PARAMETROS = "Parametros"


# ===========================================================================
# DATOS DE EJEMPLO
# ===========================================================================
def datos_ejemplo():
    """
    Devuelve (df_estructura, df_periodos) del edificio de 5 pisos del ejercicio.
    Los pisos van de abajo (1) hacia arriba (5).
    """
    df_estructura = pd.DataFrame({
        COL_PISO: [1, 2, 3, 4, 5],
        COL_MASA: [31.80, 31.80, 31.80, 31.80, 27.50],
        "Modo 1": [0.03112, 0.05959, 0.08302, 0.09940, 0.10834],
        "Modo 2": [-0.08102, -0.10193, -0.05484, 0.03358, 0.10609],
        "Modo 3": [0.10415, 0.03021, -0.09525, -0.05769, 0.09176],
    })
    df_periodos = pd.DataFrame({
        "Modo": ["Modo 1", "Modo 2", "Modo 3"],
        COL_T: [0.556, 0.193, 0.126],
    })
    return df_estructura, df_periodos


def columnas_modos(df_estructura: pd.DataFrame) -> list:
    """Nombres de las columnas que contienen formas modales (todo excepto Piso y Masa)."""
    return [c for c in df_estructura.columns if c not in (COL_PISO, COL_MASA)]


def sincronizar_periodos(df_estructura: pd.DataFrame, df_periodos: pd.DataFrame) -> pd.DataFrame:
    """
    Asegura que la tabla de periodos tenga una fila por cada modo de la tabla
    Estructura (si el usuario agrega 'Modo 4', aparece aquí con T vacío).
    """
    modos = columnas_modos(df_estructura)
    actuales = dict(zip(df_periodos["Modo"].astype(str), df_periodos[COL_T]))
    return pd.DataFrame({"Modo": modos, COL_T: [actuales.get(m, np.nan) for m in modos]})


# ===========================================================================
# LECTURA DE ARCHIVOS
# ===========================================================================
def _normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Quita espacios extra en los nombres y reconoce variantes como 'PISOS' o 'MASA (t.s2/m)'."""
    nuevas = {}
    for c in df.columns:
        texto = str(c).strip()
        bajo = texto.lower()
        if bajo.startswith("piso"):
            nuevas[c] = COL_PISO
        elif bajo.startswith("masa"):
            nuevas[c] = COL_MASA
        elif bajo.startswith("t") and ("(s)" in bajo or bajo in ("t", "periodo", "periodo (s)")):
            nuevas[c] = COL_T
        elif bajo.startswith("periodo"):
            nuevas[c] = COL_T
        else:
            nuevas[c] = texto
    return df.rename(columns=nuevas)


def _leer_parametros(df: pd.DataFrame):
    """Convierte la hoja 'Parametros' (Parámetro | Valor) en ParametrosSismicos."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    nombre_col, valor_col = df.columns[0], df.columns[1]
    valores = {}
    for _, fila in df.iterrows():
        clave = str(fila[nombre_col]).strip()
        # Acepta "Z", "Z (factor de zona)", etc.: nos quedamos con la primera palabra.
        clave = clave.split()[0] if clave else clave
        if clave in ParametrosSismicos.__dataclass_fields__:
            valores[clave] = float(fila[valor_col])
    return ParametrosSismicos(**valores) if valores else None


def leer_excel(archivo) -> dict:
    """
    Lee un Excel con las hojas 'Estructura', 'Periodos' y opcionalmente 'Parametros'.
    `archivo` puede ser una ruta o el objeto que entrega st.file_uploader.
    """
    hojas = pd.read_excel(archivo, sheet_name=None)  # None = leer TODAS las hojas
    nombres = {n.strip().lower(): n for n in hojas}

    if HOJA_ESTRUCTURA.lower() not in nombres:
        raise ValueError(f"El Excel debe tener una hoja llamada '{HOJA_ESTRUCTURA}'.")
    if HOJA_PERIODOS.lower() not in nombres:
        raise ValueError(f"El Excel debe tener una hoja llamada '{HOJA_PERIODOS}'.")

    df_estructura = _normalizar_columnas(hojas[nombres[HOJA_ESTRUCTURA.lower()]])
    df_periodos = _normalizar_columnas(hojas[nombres[HOJA_PERIODOS.lower()]])
    df_periodos = df_periodos.rename(columns={df_periodos.columns[0]: "Modo"})

    parametros = None
    if HOJA_PARAMETROS.lower() in nombres:
        parametros = _leer_parametros(hojas[nombres[HOJA_PARAMETROS.lower()]])

    return {"estructura": df_estructura, "periodos": df_periodos, "parametros": parametros}


def leer_csv(archivo) -> dict:
    """
    Lee un CSV con la tabla Estructura y una fila final 'T' con los periodos.
    Detecta automáticamente si el separador es ',' o ';'.
    """
    df = pd.read_csv(archivo, sep=None, engine="python")
    df = _normalizar_columnas(df)
    if COL_PISO not in df.columns:
        raise ValueError("El CSV debe tener una columna 'Piso'.")

    es_fila_T = df[COL_PISO].astype(str).str.strip().str.upper().isin(["T", "PERIODO", "PERIODO (S)", "T (S)"])
    if not es_fila_T.any():
        raise ValueError("El CSV debe tener una fila con Piso = 'T' que contenga los periodos.")

    fila_T = df[es_fila_T].iloc[0]
    df_estructura = df[~es_fila_T].copy()
    df_estructura[COL_PISO] = pd.to_numeric(df_estructura[COL_PISO])
    modos = columnas_modos(df_estructura)
    df_periodos = pd.DataFrame({"Modo": modos, COL_T: [float(fila_T[m]) for m in modos]})
    return {"estructura": df_estructura.reset_index(drop=True), "periodos": df_periodos,
            "parametros": None}


def leer_archivo(archivo, nombre: str = None) -> dict:
    """Elige el lector según la extensión del archivo (.xlsx o .csv/.txt)."""
    nombre = (nombre or getattr(archivo, "name", "") or str(archivo)).lower()
    if nombre.endswith((".xlsx", ".xls")):
        return leer_excel(archivo)
    if nombre.endswith((".csv", ".txt")):
        return leer_csv(archivo)
    raise ValueError("Formato no soportado. Use .xlsx o .csv")


# ===========================================================================
# VALIDACIÓN Y CONVERSIÓN
# ===========================================================================
def validar_datos(df_estructura: pd.DataFrame, df_periodos: pd.DataFrame) -> list:
    """Devuelve una lista de errores. Lista vacía = datos correctos."""
    errores = []
    for col in (COL_PISO, COL_MASA):
        if col not in df_estructura.columns:
            errores.append(f"Falta la columna '{col}' en la tabla Estructura.")
    if errores:
        return errores

    modos = columnas_modos(df_estructura)
    if not modos:
        errores.append("Debe haber al menos una columna de modo (ej. 'Modo 1').")
    if len(df_estructura) < 1:
        errores.append("La tabla Estructura no tiene pisos.")

    numericas = df_estructura[[COL_PISO, COL_MASA] + modos].apply(pd.to_numeric, errors="coerce")
    if numericas.isna().any().any():
        errores.append("Hay celdas vacías o no numéricas en la tabla Estructura.")
    elif (numericas[COL_MASA] <= 0).any():
        errores.append("Todas las masas deben ser mayores que cero.")
    if df_estructura[COL_PISO].duplicated().any():
        errores.append("Hay números de piso repetidos.")

    T = pd.to_numeric(df_periodos.get(COL_T, pd.Series(dtype=float)), errors="coerce")
    if len(T) != len(modos):
        errores.append(f"Hay {len(modos)} modos pero {len(T)} periodos.")
    elif T.isna().any() or (T <= 0).any():
        errores.append("Todos los periodos deben ser números mayores que cero.")
    return errores


def a_arreglos(df_estructura: pd.DataFrame, df_periodos: pd.DataFrame):
    """
    Convierte las tablas en arreglos de NumPy listos para `ejecutar_analisis`.
    Ordena los pisos de abajo hacia arriba (por si el usuario los escribió al revés).
    """
    df = df_estructura.copy()
    df[COL_PISO] = pd.to_numeric(df[COL_PISO])
    df = df.sort_values(COL_PISO).reset_index(drop=True)
    modos = columnas_modos(df)

    pisos = df[COL_PISO].to_numpy(dtype=int)
    masas = df[COL_MASA].to_numpy(dtype=float)
    phi = df[modos].to_numpy(dtype=float)
    periodos = pd.to_numeric(df_periodos[COL_T]).to_numpy(dtype=float)
    return pisos, masas, periodos, phi


# ===========================================================================
# PLANTILLAS DESCARGABLES
# ===========================================================================
def plantilla_excel(params: ParametrosSismicos = None) -> bytes:
    """Crea un Excel de ejemplo (en memoria) que el usuario puede descargar y llenar."""
    df_estructura, df_periodos = datos_ejemplo()
    params = params or ParametrosSismicos()
    df_param = pd.DataFrame(list(params.como_diccionario().items()), columns=["Parametro", "Valor"])

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_estructura.to_excel(writer, sheet_name=HOJA_ESTRUCTURA, index=False)
        df_periodos.to_excel(writer, sheet_name=HOJA_PERIODOS, index=False)
        df_param.to_excel(writer, sheet_name=HOJA_PARAMETROS, index=False)
    return buffer.getvalue()


def plantilla_csv() -> bytes:
    """Crea un CSV de ejemplo: tabla Estructura + fila 'T' con los periodos."""
    df_estructura, df_periodos = datos_ejemplo()
    fila_T = {COL_PISO: "T", COL_MASA: ""}
    fila_T.update(dict(zip(df_periodos["Modo"], df_periodos[COL_T])))
    df = pd.concat([df_estructura.astype(object), pd.DataFrame([fila_T])], ignore_index=True)
    return df.to_csv(index=False).encode("utf-8")
