"""
calculos.py
===========
Motor de cálculo del Análisis Dinámico Modal Espectral (NTE E.030).

Cada paso del procedimiento es UNA función pequeña. Así es fácil:
  1) entender qué hace cada fórmula,
  2) probarla por separado,
  3) reutilizarla desde Streamlit con un simple `import`.

Convención de datos (¡importante!)
----------------------------------
- Los pisos se ordenan de ABAJO hacia ARRIBA:  índice 0 = Piso 1.
- phi es una matriz (n_pisos x n_modos):  filas = pisos, columnas = modos.
- Las masas están en  t·s²/m  y Sa en  m/s²  ->  las fuerzas salen en  t (tonf).

Flujo completo (ver función `ejecutar_analisis`):
    T  ->  ω = 2π/T
    T  ->  C(T)  ->  Sa = Z·U·C·S/R · g
    φ, m  ->  Γ = φᵀ·m / (φᵀ·M·φ)
    Ü = Sa · Γ · φ          (aceleración por piso, cada modo)
    F = M · Ü               (fuerza por piso, cada modo)
    V = Σ F (desde arriba)  (cortante por piso, cada modo)
    Combinación:  Vrnc_h = 0.25·Σ|V| + 0.75·√(ΣV²)
    Vreal = Vrnc_h · 0.75 · R
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .parametros import ParametrosSismicos


# ===========================================================================
# PASO 1 - Frecuencia angular
# ===========================================================================
def calcular_frecuencias(periodos) -> np.ndarray:
    """ω = 2π / T   (rad/s). Acepta un número o un arreglo de periodos."""
    periodos = np.asarray(periodos, dtype=float)
    return 2 * np.pi / periodos


# ===========================================================================
# PASO 2 - Factor de amplificación sísmica C y espectro Sa
# ===========================================================================
def calcular_factor_c(T: float, Tp: float = 0.4, Tl: float = 2.5) -> float:
    """
    Factor de amplificación sísmica C (Art. 14, E.030).

        T <  Tp          ->  C = 2.5
        Tp <= T <= Tl    ->  C = 2.5 · (Tp / T)
        T >  Tl          ->  C = 2.5 · (Tp · Tl / T²)
    """
    if T < Tp:
        return 2.5
    elif T <= Tl:
        return 2.5 * (Tp / T)
    else:
        return 2.5 * (Tp * Tl) / (T ** 2)


def calcular_pseudoaceleracion(periodos, params: ParametrosSismicos):
    """
    Pseudo-aceleración espectral:   Sa = (Z·U·C·S / R) · g

    Devuelve (C, Sa) como arreglos de NumPy, uno por cada periodo.
    """
    periodos = np.atleast_1d(np.asarray(periodos, dtype=float))
    C = np.array([calcular_factor_c(T, params.Tp, params.Tl) for T in periodos])
    Sa = (params.Z * params.U * C * params.S / params.R) * params.g
    return C, Sa


def generar_espectro(params: ParametrosSismicos, T_max: float = 5.0,
                     n_puntos: int = 500) -> pd.DataFrame:
    """Curva completa del espectro de diseño (para graficar)."""
    T = np.linspace(0.01, T_max, n_puntos)
    C, Sa = calcular_pseudoaceleracion(T, params)
    return pd.DataFrame({"T (s)": T, "C": C, "Sa (m/s²)": Sa})


# ===========================================================================
# PASO 3 - Factor de participación modal Γ
# ===========================================================================
def calcular_factor_participacion(phi, masas, normalizados: bool = True):
    """
    Γ = (φᵀ · m) / (φᵀ · M · φ)

    Si los modos están normalizados respecto a M, el denominador vale 1
    y la fórmula se reduce a  Γ = φᵀ · m   (que es lo que usa el notebook).

    Devuelve (gamma, masa_generalizada) — esta última es el denominador,
    útil para comprobar que realmente vale ≈ 1.
    """
    phi = np.asarray(phi, dtype=float)
    masas = np.asarray(masas, dtype=float)
    M = np.diag(masas)

    numerador = phi.T @ masas                         # φᵀ·m   (un valor por modo)
    masa_generalizada = np.diag(phi.T @ M @ phi)      # φᵀ·M·φ (un valor por modo)

    if normalizados:
        gamma = numerador
    else:
        gamma = numerador / masa_generalizada
    return gamma, masa_generalizada


def calcular_masa_participativa(phi, masas):
    """
    Porcentaje de masa participativa (masa efectiva) de cada modo:
        %Mj = (φjᵀ·m)² / (φjᵀ·M·φj) / Σm  · 100
    La E.030 pide que la suma de los modos considerados sea ≥ 90 %.
    """
    phi = np.asarray(phi, dtype=float)
    masas = np.asarray(masas, dtype=float)
    numerador = phi.T @ masas
    masa_generalizada = np.diag(phi.T @ np.diag(masas) @ phi)
    return numerador ** 2 / masa_generalizada / np.sum(masas) * 100


# ===========================================================================
# PASO 4 y 5 - Aceleraciones, fuerzas y cortantes por modo
# ===========================================================================
def calcular_aceleraciones(phi, Sa, gamma) -> np.ndarray:
    """Ü(i, j) = Sa_j · Γ_j · φ(i, j)     (m/s²)"""
    phi = np.asarray(phi, dtype=float)
    # Gracias al "broadcasting" de NumPy, (n x m) * (m,) multiplica cada columna.
    return phi * (np.asarray(Sa) * np.asarray(gamma))


def calcular_fuerzas(masas, U_ddot) -> np.ndarray:
    """F = M · Ü     (fuerza sísmica en cada piso y cada modo, en t)"""
    return np.diag(np.asarray(masas, dtype=float)) @ U_ddot


def calcular_cortantes(F) -> np.ndarray:
    """
    Cortante de entrepiso: suma acumulada de fuerzas desde el TECHO hacia abajo.
        V_i = Σ_{k=i}^{n} F_k
    Truco: voltear, sumar acumulado, volver a voltear.
    """
    F = np.asarray(F, dtype=float)
    return np.flip(np.cumsum(np.flip(F, axis=0), axis=0), axis=0)


# ===========================================================================
# PASO 6 - Combinación modal y cortante real
# ===========================================================================
def combinar_modos(V, peso_abs: float = 0.25, peso_rcsc: float = 0.75):
    """
    Combinación de respuestas modales (Art. 29.4 E.030):
        Vsum_abs = Σ|V_j|
        Vrcsc    = √(Σ V_j²)
        Vrnc_h   = 0.25·Vsum_abs + 0.75·Vrcsc
    """
    V = np.asarray(V, dtype=float)
    Vsum_abs = np.sum(np.abs(V), axis=1)
    Vrcsc = np.sqrt(np.sum(V ** 2, axis=1))
    Vrnc_h = peso_abs * Vsum_abs + peso_rcsc * Vrcsc
    return Vsum_abs, Vrcsc, Vrnc_h


def calcular_cortante_real(Vrnc_h, R: float, factor: float = 0.75):
    """Vreal = Vrnc_h · factor · R    (factor = 0.75 según el ejercicio)."""
    return np.asarray(Vrnc_h) * factor * R


# ===========================================================================
# CONTENEDOR DE RESULTADOS
# ===========================================================================
@dataclass
class ResultadosAnalisis:
    """Guarda TODOS los resultados para mostrarlos, graficarlos o exportarlos."""
    params: ParametrosSismicos
    pisos: np.ndarray
    masas: np.ndarray
    periodos: np.ndarray
    phi: np.ndarray
    w: np.ndarray
    C: np.ndarray
    Sa: np.ndarray
    gamma: np.ndarray
    masa_generalizada: np.ndarray
    masa_participativa: np.ndarray
    U_ddot: np.ndarray
    F: np.ndarray
    V: np.ndarray
    Vsum_abs: np.ndarray
    Vrcsc: np.ndarray
    Vrnc_h: np.ndarray
    Vreal: np.ndarray
    opciones: dict = field(default_factory=dict)

    # ---- Propiedades de ayuda -------------------------------------------
    @property
    def n_modos(self) -> int:
        return self.phi.shape[1]

    @property
    def nombres_modos(self) -> list:
        return [f"Modo {j + 1}" for j in range(self.n_modos)]

    # ---- Tablas listas para mostrar (pandas DataFrame) -------------------
    def tabla_modal(self) -> pd.DataFrame:
        return pd.DataFrame({
            "Modo": self.nombres_modos,
            "T (s)": self.periodos,
            "ω (rad/s)": self.w,
            "C": self.C,
            "Sa (m/s²)": self.Sa,
            "φᵀMφ": self.masa_generalizada,
            "Γ": self.gamma,
            "% Masa part.": self.masa_participativa,
        })

    def _tabla_por_piso(self, matriz) -> pd.DataFrame:
        df = pd.DataFrame(matriz, columns=self.nombres_modos)
        df.insert(0, "Piso", self.pisos)
        # Mostramos del piso más alto al más bajo (como se ve el edificio).
        return df.iloc[::-1].reset_index(drop=True)

    def tabla_aceleraciones(self) -> pd.DataFrame:
        return self._tabla_por_piso(self.U_ddot)

    def tabla_fuerzas(self) -> pd.DataFrame:
        return self._tabla_por_piso(self.F)

    def tabla_cortantes_modales(self) -> pd.DataFrame:
        return self._tabla_por_piso(self.V)

    def tabla_combinacion(self) -> pd.DataFrame:
        df = pd.DataFrame({
            "Piso": self.pisos,
            "Masa (t·s²/m)": self.masas,
            **{f"V {n} (t)": self.V[:, j] for j, n in enumerate(self.nombres_modos)},
            "Vsum_abs (t)": self.Vsum_abs,
            "Vrcsc (t)": self.Vrcsc,
            "Vrnc_h (t)": self.Vrnc_h,
            "Vreal (t)": self.Vreal,
        })
        return df.iloc[::-1].reset_index(drop=True)

    def tabla_parametros(self) -> pd.DataFrame:
        descripcion = {
            "Z": "Factor de zona", "U": "Factor de uso", "S": "Factor de suelo",
            "R": "Coeficiente de reducción", "Tp": "Periodo de plataforma (s)",
            "Tl": "Periodo desplaz. constante (s)", "g": "Gravedad (m/s²)",
        }
        return pd.DataFrame(
            [(k, v, descripcion[k]) for k, v in self.params.como_diccionario().items()],
            columns=["Parámetro", "Valor", "Descripción"],
        )

    def resumen(self) -> dict:
        """Números clave para las tarjetas (métricas) de la página."""
        return {
            "Cortante basal Vrnc_h (t)": float(self.Vrnc_h[0]),
            "Cortante basal real (t)": float(self.Vreal[0]),
            "Periodo fundamental (s)": float(self.periodos[0]),
            "Masa participativa acumulada (%)": float(np.sum(self.masa_participativa)),
        }


# ===========================================================================
# FUNCIÓN PRINCIPAL - ejecuta todo el análisis de una sola vez
# ===========================================================================
def ejecutar_analisis(pisos, masas, periodos, phi, params: ParametrosSismicos,
                      normalizados: bool = True, peso_abs: float = 0.25,
                      peso_rcsc: float = 0.75,
                      factor_vreal: float = 0.75) -> ResultadosAnalisis:
    """
    Ejecuta el análisis modal espectral completo.

    Parámetros
    ----------
    pisos    : números de piso, de abajo hacia arriba  (n,)
    masas    : masa de cada piso  (n,)                 [t·s²/m]
    periodos : periodo de cada modo  (m,)              [s]
    phi      : formas modales  (n x m)
    params   : ParametrosSismicos
    normalizados : True si φ ya está normalizado respecto a M
    peso_abs, peso_rcsc : pesos de la combinación modal (0.25 / 0.75)
    factor_vreal        : factor de la cortante real (0.75)
    """
    pisos = np.asarray(pisos)
    masas = np.asarray(masas, dtype=float)
    periodos = np.asarray(periodos, dtype=float)
    phi = np.asarray(phi, dtype=float)

    w = calcular_frecuencias(periodos)
    C, Sa = calcular_pseudoaceleracion(periodos, params)
    gamma, masa_gen = calcular_factor_participacion(phi, masas, normalizados)
    masa_part = calcular_masa_participativa(phi, masas)
    U_ddot = calcular_aceleraciones(phi, Sa, gamma)
    F = calcular_fuerzas(masas, U_ddot)
    V = calcular_cortantes(F)
    Vsum_abs, Vrcsc, Vrnc_h = combinar_modos(V, peso_abs, peso_rcsc)
    Vreal = calcular_cortante_real(Vrnc_h, params.R, factor_vreal)

    return ResultadosAnalisis(
        params=params, pisos=pisos, masas=masas, periodos=periodos, phi=phi,
        w=w, C=C, Sa=Sa, gamma=gamma, masa_generalizada=masa_gen,
        masa_participativa=masa_part, U_ddot=U_ddot, F=F, V=V,
        Vsum_abs=Vsum_abs, Vrcsc=Vrcsc, Vrnc_h=Vrnc_h, Vreal=Vreal,
        opciones={"normalizados": normalizados, "peso_abs": peso_abs,
                  "peso_rcsc": peso_rcsc, "factor_vreal": factor_vreal},
    )
