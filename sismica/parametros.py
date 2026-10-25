"""
parametros.py
=============
Parámetros sísmicos de la Norma Técnica E.030 "Diseño Sismorresistente" (Perú).

Aquí guardamos las TABLAS de la norma como diccionarios de Python.
Así la página web puede ofrecer listas desplegables (zona, suelo, categoría,
sistema estructural) y llenar automáticamente Z, U, S, Tp, Tl y R.

👉 Idea clave para el estudiante:
   Un diccionario es como una tabla de "búsqueda":  clave -> valor.
   Ejemplo:  FACTOR_ZONA["Zona 4"]  devuelve  0.45

⚠️ Los valores corresponden a la E.030 (versión 2018). Verifíquelos siempre
   contra la versión vigente de la norma antes de usarlos en un proyecto real.
"""

from dataclasses import dataclass, asdict

# ---------------------------------------------------------------------------
# Tabla N° 1 - Factor de zona "Z"
# ---------------------------------------------------------------------------
FACTOR_ZONA = {
    "Zona 4": 0.45,
    "Zona 3": 0.35,
    "Zona 2": 0.25,
    "Zona 1": 0.10,
}

# ---------------------------------------------------------------------------
# Tabla N° 3 - Factor de suelo "S"  (depende de la zona Y del tipo de suelo)
# ---------------------------------------------------------------------------
FACTOR_SUELO = {
    "Zona 4": {"S0": 0.80, "S1": 1.00, "S2": 1.05, "S3": 1.10},
    "Zona 3": {"S0": 0.80, "S1": 1.00, "S2": 1.15, "S3": 1.20},
    "Zona 2": {"S0": 0.80, "S1": 1.00, "S2": 1.20, "S3": 1.40},
    "Zona 1": {"S0": 0.80, "S1": 1.00, "S2": 1.60, "S3": 2.00},
}

DESCRIPCION_SUELO = {
    "S0": "S0 - Roca dura",
    "S1": "S1 - Roca o suelos muy rígidos",
    "S2": "S2 - Suelos intermedios",
    "S3": "S3 - Suelos blandos",
}

# ---------------------------------------------------------------------------
# Tabla N° 4 - Periodos "Tp" y "Tl" (dependen del tipo de suelo)
# ---------------------------------------------------------------------------
PERIODOS_SUELO = {
    "S0": {"Tp": 0.3, "Tl": 3.0},
    "S1": {"Tp": 0.4, "Tl": 2.5},
    "S2": {"Tp": 0.6, "Tl": 2.0},
    "S3": {"Tp": 1.0, "Tl": 1.6},
}

# ---------------------------------------------------------------------------
# Tabla N° 5 - Factor de uso "U"
# ---------------------------------------------------------------------------
FACTOR_USO = {
    "A1 - Esencial (sin aislamiento)": 1.5,
    "A2 - Esencial": 1.5,
    "B - Importante": 1.3,
    "C - Común": 1.0,
}

# ---------------------------------------------------------------------------
# Tabla N° 7 - Coeficiente básico de reducción "R0"
# ---------------------------------------------------------------------------
COEF_REDUCCION_R0 = {
    "Concreto armado - Pórticos": 8.0,
    "Concreto armado - Dual": 7.0,
    "Concreto armado - Muros estructurales": 6.0,
    "Concreto armado - Muros de ductilidad limitada": 4.0,
    "Acero - Pórticos especiales (SMF)": 8.0,
    "Acero - Pórticos intermedios (IMF)": 5.0,
    "Acero - Pórticos ordinarios (OMF)": 4.0,
    "Acero - Arriostres concéntricos especiales (SCBF)": 7.0,
    "Acero - Arriostres concéntricos ordinarios (OCBF)": 4.0,
    "Acero - Arriostres excéntricos (EBF)": 8.0,
    "Albañilería armada o confinada": 3.0,
    "Madera": 7.0,
}


@dataclass
class ParametrosSismicos:
    """
    Agrupa todos los parámetros que necesita el análisis.

    Un 'dataclass' es una clase "contenedor": sólo guarda datos con nombre.
    Se usa así:   p = ParametrosSismicos(Z=0.45, U=1.0, ...)
                  p.Z   -> 0.45
    """
    Z: float = 0.45     # Factor de zona
    U: float = 1.0      # Factor de uso
    S: float = 1.0      # Factor de suelo
    R: float = 8.0      # Coeficiente de reducción (R = R0 * Ia * Ip)
    Tp: float = 0.4     # Periodo de plataforma (s)
    Tl: float = 2.5     # Periodo de inicio de desplazamiento constante (s)
    g: float = 9.81     # Gravedad (m/s²)

    def como_diccionario(self) -> dict:
        """Devuelve los parámetros como diccionario {nombre: valor}."""
        return asdict(self)

    def validar(self) -> list:
        """
        Revisa que los valores tengan sentido físico.
        Devuelve una lista de mensajes de error (vacía si todo está bien).
        """
        errores = []
        for nombre in ("Z", "U", "S", "R", "Tp", "Tl", "g"):
            if getattr(self, nombre) <= 0:
                errores.append(f"El parámetro {nombre} debe ser mayor que cero.")
        if self.Tl <= self.Tp:
            errores.append("Tl debe ser mayor que Tp.")
        return errores


def parametros_desde_norma(zona: str, suelo: str, categoria: str,
                           sistema: str, Ia: float = 1.0, Ip: float = 1.0,
                           g: float = 9.81) -> ParametrosSismicos:
    """
    Construye los parámetros sísmicos leyendo las tablas de la E.030.

    Parámetros
    ----------
    zona      : "Zona 1" ... "Zona 4"
    suelo     : "S0", "S1", "S2" o "S3"
    categoria : clave de FACTOR_USO (ej. "C - Común")
    sistema   : clave de COEF_REDUCCION_R0
    Ia, Ip    : factores de irregularidad en altura y en planta (1.0 = regular)

    Ejemplo
    -------
    >>> p = parametros_desde_norma("Zona 4", "S1", "C - Común", "Concreto armado - Pórticos")
    >>> p.Z, p.S, p.R
    (0.45, 1.0, 8.0)
    """
    return ParametrosSismicos(
        Z=FACTOR_ZONA[zona],
        U=FACTOR_USO[categoria],
        S=FACTOR_SUELO[zona][suelo],
        R=COEF_REDUCCION_R0[sistema] * Ia * Ip,
        Tp=PERIODOS_SUELO[suelo]["Tp"],
        Tl=PERIODOS_SUELO[suelo]["Tl"],
        g=g,
    )
