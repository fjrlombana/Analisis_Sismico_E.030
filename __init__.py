"""
sismica — mini-librería para Análisis Sísmico Modal Espectral (NTE E.030).

Módulos:
    parametros  -> tablas de la norma y la clase ParametrosSismicos
    datos       -> datos de ejemplo, lectura de Excel/CSV, validación, plantillas
    calculos    -> el motor de cálculo (ω, C, Sa, Γ, Ü, F, V, combinación)
    graficos    -> figuras de Matplotlib
    exportar    -> reportes Excel, PDF y ZIP de imágenes

Uso típico (igual que cualquier librería):

    from sismica import ParametrosSismicos, ejecutar_analisis, datos_ejemplo, a_arreglos

    df_est, df_T = datos_ejemplo()
    pisos, masas, periodos, phi = a_arreglos(df_est, df_T)
    res = ejecutar_analisis(pisos, masas, periodos, phi, ParametrosSismicos())
    print(res.tabla_combinacion())
"""

from .parametros import (ParametrosSismicos, parametros_desde_norma, FACTOR_ZONA,
                         FACTOR_SUELO, FACTOR_USO, COEF_REDUCCION_R0, PERIODOS_SUELO,
                         DESCRIPCION_SUELO)
from .calculos import ejecutar_analisis, ResultadosAnalisis, calcular_factor_c, generar_espectro
from .datos import (datos_ejemplo, leer_archivo, validar_datos, a_arreglos,
                    sincronizar_periodos, plantilla_excel, plantilla_csv)
from . import graficos, exportar

__version__ = "1.0.0"
