"""
graficos.py
===========
Funciones que DIBUJAN los resultados con Matplotlib.

Regla de oro: cada función RECIBE datos y DEVUELVE una figura (`Figure`).
No muestra nada por sí misma. Así la misma figura sirve para:
    - mostrarla en Streamlit:   st.pyplot(fig)
    - guardarla como imagen:     figura_a_png(fig)
    - meterla en un PDF:         exportar.generar_pdf(...)
"""

import io
import os
import tempfile

import matplotlib
matplotlib.use("Agg")  # "Agg" = dibujar sin ventana (necesario en servidores web)
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np

from .calculos import ResultadosAnalisis, generar_espectro
from .parametros import ParametrosSismicos

# Paleta de colores por modo (se repite si hay más de 6 modos)
COLORES_MODOS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
MARCADORES = ["o", "s", "^", "D", "v", "P"]


def _estilo_ejes(ax, titulo, xlabel, ylabel=None, pisos=None):
    ax.set_title(titulo, fontsize=11, fontweight="bold")
    ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    if pisos is not None:
        ax.set_yticks(pisos)
    ax.grid(True, linestyle="--", alpha=0.6)


# ---------------------------------------------------------------------------
# 1. Espectro de diseño
# ---------------------------------------------------------------------------
def grafico_espectro(params: ParametrosSismicos, periodos_modos=None, Sa_modos=None,
                     T_max: float = 5.0):
    """Espectro de pseudo-aceleraciones con Tp, Tl y (opcional) los modos marcados."""
    esp = generar_espectro(params, T_max=T_max)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(esp["T (s)"], esp["Sa (m/s²)"], color="red", linewidth=2, label="Espectro de diseño $S_a$")
    ax.axvline(params.Tp, color="gray", linestyle=":", label=f"Tp = {params.Tp} s")
    ax.axvline(params.Tl, color="gray", linestyle="--", label=f"Tl = {params.Tl} s")

    if periodos_modos is not None and Sa_modos is not None:
        for j, (T, Sa) in enumerate(zip(periodos_modos, Sa_modos)):
            ax.plot(T, Sa, MARCADORES[j % 6], color=COLORES_MODOS[j % 6], markersize=9,
                    label=f"Modo {j + 1}: T={T:.3f} s, Sa={Sa:.3f}")

    _estilo_ejes(ax, "Espectro de Pseudo-aceleraciones ($S_a$)", "Periodo T (s)",
                 "Aceleración $S_a$ (m/s²)")
    ax.legend(fontsize=9)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 2. Formas modales
# ---------------------------------------------------------------------------
def grafico_formas_modales(res: ResultadosAnalisis):
    """Una gráfica por modo: deformada (con la base fija en 0)."""
    n = res.n_modos
    fig, axs = plt.subplots(1, n, figsize=(3.6 * n, 5.5), sharey=True)
    axs = np.atleast_1d(axs)
    niveles = np.concatenate([[0], res.pisos])
    limite = 1.15 * np.max(np.abs(res.phi))

    for j, ax in enumerate(axs):
        forma = np.concatenate([[0.0], res.phi[:, j]])
        color = COLORES_MODOS[j % 6]
        ax.plot(np.zeros_like(niveles), niveles, color="lightgray", linewidth=1.5)  # edificio sin deformar
        ax.plot(forma, niveles, "o-", color=color, linewidth=2.5, markersize=7)
        ax.fill_betweenx(niveles, 0, forma, color=color, alpha=0.12)
        ax.set_xlim(-limite, limite)
        _estilo_ejes(ax, f"Modo {j + 1}  (T = {res.periodos[j]:.3f} s)", "Amplitud φ")
        ax.set_yticks(niveles)
        ax.set_yticklabels(["Base"] + [f"Piso {p}" for p in res.pisos])
    fig.tight_layout()
    return fig


def animacion_modo_gif(res: ResultadosAnalisis, modo: int, n_cuadros: int = 40) -> bytes:
    """
    Crea un GIF animado del modo `modo` (0 = primer modo) y lo devuelve en bytes.

    Nota: en el notebook original los GIF salían "planos" porque solo se
    guardaba el primer cuadro (sin(0) = 0). Aquí la amplitud varía con sin(t)
    a lo largo de un ciclo completo, y se dibuja también la posición inicial.
    """
    niveles = np.concatenate([[0], res.pisos])
    forma = np.concatenate([[0.0], res.phi[:, modo]])
    limite = 1.15 * np.max(np.abs(res.phi))
    t = np.linspace(0, 2 * np.pi, n_cuadros, endpoint=False)

    fig, ax = plt.subplots(figsize=(4, 6))
    ax.plot(np.zeros_like(niveles), niveles, color="lightgray", linewidth=1.5)
    ax.plot(forma, niveles, ":", color="gray", linewidth=1)  # envolvente
    ax.plot(-forma, niveles, ":", color="gray", linewidth=1)
    linea, = ax.plot(forma, niveles, "o-", color=COLORES_MODOS[modo % 6], linewidth=2.5, markersize=8)
    ax.set_xlim(-limite, limite)
    ax.set_yticks(niveles)
    ax.set_yticklabels(["Base"] + [f"Piso {p}" for p in res.pisos])
    _estilo_ejes(ax, f"Modo {modo + 1} (T = {res.periodos[modo]:.3f} s)", "Deformada / Amplitud")
    fig.tight_layout()

    def actualizar(k):
        linea.set_xdata(forma * np.sin(t[k] + np.pi / 2))  # empieza en la amplitud máxima
        return (linea,)

    anim = animation.FuncAnimation(fig, actualizar, frames=n_cuadros, blit=True)
    # El escritor "pillow" necesita un archivo; usamos uno temporal y luego lo leemos.
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = os.path.join(carpeta, "modo.gif")
        anim.save(ruta, writer="pillow", fps=20)
        with open(ruta, "rb") as f:
            datos = f.read()
    plt.close(fig)
    return datos


# ---------------------------------------------------------------------------
# 3. Fuerzas y cortantes por modo (lienzo 1x2)
# ---------------------------------------------------------------------------
def grafico_fuerzas_cortantes(res: ResultadosAnalisis):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    for j, nombre in enumerate(res.nombres_modos):
        estilo = dict(color=COLORES_MODOS[j % 6], marker=MARCADORES[j % 6], linewidth=2, label=nombre)
        ax1.plot(res.F[:, j], res.pisos, **estilo)
        ax2.plot(res.V[:, j], res.pisos, **estilo)
    for ax in (ax1, ax2):
        ax.axvline(0, color="black", linewidth=0.8)
        ax.legend()
    _estilo_ejes(ax1, "Fuerzas Sísmicas por Piso (F)", "Fuerza sísmica (t)", "Piso", res.pisos)
    _estilo_ejes(ax2, "Cortante Sísmica por Piso (V)", "Cortante sísmica (t)", pisos=res.pisos)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 4. Combinaciones modales y cortante real (lienzo 2x2)
# ---------------------------------------------------------------------------
def grafico_combinaciones(res: ResultadosAnalisis):
    fig, axs = plt.subplots(2, 2, figsize=(12, 10), sharey=True)
    series = [
        (axs[0, 0], res.Vsum_abs, "o-", "#d62728", "Suma de Valores Absolutos (Vsum_abs)"),
        (axs[0, 1], res.Vrcsc, "s-", "#9467bd", "Raíz Cuadrada de Suma de Cuadrados (Vrcsc)"),
        (axs[1, 0], res.Vrnc_h, "^-", "#8c564b", "Respuesta Máxima (Vrnc_h)"),
        (axs[1, 1], res.Vreal, "d-", "#17becf", "Cortante Real (Vreal)"),
    ]
    for ax, valores, fmt, color, titulo in series:
        ax.plot(valores, res.pisos, fmt, color=color, linewidth=2.5)
        for x, y in zip(valores, res.pisos):          # etiqueta con el valor
            ax.annotate(f"{x:.1f}", (x, y), textcoords="offset points", xytext=(6, 4), fontsize=8)
        _estilo_ejes(ax, titulo, "Cortante (t)", pisos=res.pisos)
    axs[0, 0].set_ylabel("Piso")
    axs[1, 0].set_ylabel("Piso")
    fig.tight_layout()
    return fig


def grafico_comparacion_cortantes(res: ResultadosAnalisis):
    """Las tres combinaciones (sin escalar) en un mismo gráfico, en escalones."""
    fig, ax = plt.subplots(figsize=(7, 5))
    for valores, color, nombre in [(res.Vsum_abs, "#d62728", "Vsum_abs"),
                                   (res.Vrcsc, "#9467bd", "Vrcsc"),
                                   (res.Vrnc_h, "#8c564b", "Vrnc_h")]:
        # Cada entrepiso i va del nivel (i-1) al nivel i con cortante constante V_i
        xs, ys = [], []
        for i, v in enumerate(valores):
            xs += [v, v]
            ys += [i, i + 1]
        ax.plot(xs, ys, color=color, linewidth=2, label=nombre)
    _estilo_ejes(ax, "Comparación de combinaciones (cortante de entrepiso)", "Cortante (t)", "Nivel")
    ax.legend()
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Utilidad: figura -> PNG (bytes)
# ---------------------------------------------------------------------------
def figura_a_png(fig, dpi: int = 200) -> bytes:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=dpi, bbox_inches="tight")
    return buffer.getvalue()


def generar_todas_las_figuras(res: ResultadosAnalisis) -> dict:
    """Devuelve {nombre_archivo: figura} con todos los gráficos del análisis."""
    return {
        "01_espectro.png": grafico_espectro(res.params, res.periodos, res.Sa),
        "02_formas_modales.png": grafico_formas_modales(res),
        "03_fuerzas_cortantes_por_modo.png": grafico_fuerzas_cortantes(res),
        "04_combinaciones_modales.png": grafico_combinaciones(res),
        "05_comparacion_cortantes.png": grafico_comparacion_cortantes(res),
    }
