"""
app.py — Página web (Streamlit) para el Análisis Sísmico Modal Espectral E.030
==============================================================================

Cómo ejecutar en tu computadora:
    pip install -r requirements.txt
    streamlit run app.py

¿Cómo funciona Streamlit? (lo más importante para un principiante)
------------------------------------------------------------------
1. Streamlit ejecuta ESTE archivo de arriba hacia abajo cada vez que el usuario
   toca un widget (botón, casilla, tabla...). A eso se le llama "rerun".
2. Por eso las variables normales se "olvidan" entre reruns. Lo que queremos
   recordar (datos cargados, resultados) se guarda en `st.session_state`,
   que funciona como un diccionario que sobrevive a los reruns.
3. Este archivo SOLO se encarga de la interfaz. Todos los cálculos viven en la
   carpeta `sismica/` y se importan como una librería cualquiera.
"""

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

# --- Nuestra propia librería (carpeta sismica/) ------------------------------
from sismica import (
    COEF_REDUCCION_R0, DESCRIPCION_SUELO, FACTOR_USO, FACTOR_ZONA,
    ParametrosSismicos, a_arreglos, datos_ejemplo, ejecutar_analisis,
    leer_archivo, parametros_desde_norma, plantilla_csv, plantilla_excel,
    sincronizar_periodos, validar_datos,
)
from sismica import exportar, graficos

# =============================================================================
# 0. CONFIGURACIÓN DE LA PÁGINA
# =============================================================================
st.set_page_config(
    page_title="Análisis Sísmico E.030",
    page_icon="🏢",
    layout="wide",
)


# =============================================================================
# 1. ESTADO DE LA SESIÓN (memoria entre reruns)
# =============================================================================
def inicializar_estado():
    """Carga los datos de ejemplo la primera vez que se abre la página."""
    if "df_estructura" not in st.session_state:
        df_est, df_T = datos_ejemplo()
        st.session_state.df_estructura = df_est
        st.session_state.df_periodos = df_T
        st.session_state.version_editor = 0      # cambia para "reiniciar" las tablas editables
        st.session_state.archivo_cargado = None  # id del último archivo leído
        st.session_state.params_archivo = None   # parámetros que venían en el Excel
        st.session_state.resultados = None
        st.session_state.huella_resultados = None
        st.session_state.archivos_export = {}


def reemplazar_datos(df_est: pd.DataFrame, df_T: pd.DataFrame):
    """Pone nuevas tablas de entrada y reinicia los editores."""
    st.session_state.df_estructura = df_est.reset_index(drop=True)
    st.session_state.df_periodos = sincronizar_periodos(df_est, df_T)
    st.session_state.version_editor += 1


inicializar_estado()

# =============================================================================
# 2. ENCABEZADO
# =============================================================================
st.title("🏢 Análisis Sísmico Dinámico Modal Espectral")
st.caption("Norma Técnica Peruana E.030 · Combinación 0.25·Σ|V| + 0.75·√ΣV² · "
           "Herramienta educativa — verifique siempre los resultados.")

# =============================================================================
# 3. BARRA LATERAL: PARÁMETROS SÍSMICOS Y OPCIONES
# =============================================================================
with st.sidebar:
    st.header("⚙️ Parámetros sísmicos")

    opciones_fuente = ["Tablas de la E.030", "Ingreso manual"]
    if st.session_state.params_archivo is not None:
        opciones_fuente.append("Desde archivo cargado")
    fuente = st.radio("¿Cómo definir los parámetros?", opciones_fuente,
                      help="Con 'Tablas de la E.030' eliges zona, suelo, uso y sistema; "
                           "los valores se buscan automáticamente.")

    if fuente == "Tablas de la E.030":
        zona = st.selectbox("Zona sísmica", list(FACTOR_ZONA), index=0)
        suelo = st.selectbox("Tipo de suelo", list(DESCRIPCION_SUELO), index=1,
                             format_func=lambda s: DESCRIPCION_SUELO[s])
        categoria = st.selectbox("Categoría de la edificación", list(FACTOR_USO), index=3)
        sistema = st.selectbox("Sistema estructural (R0)", list(COEF_REDUCCION_R0), index=0)
        c1, c2 = st.columns(2)
        Ia = c1.number_input("Ia (irreg. altura)", 0.1, 1.0, 1.0, 0.05)
        Ip = c2.number_input("Ip (irreg. planta)", 0.1, 1.0, 1.0, 0.05)
        params = parametros_desde_norma(zona, suelo, categoria, sistema, Ia, Ip)
        st.dataframe(pd.DataFrame([params.como_diccionario()]), hide_index=True)

    elif fuente == "Ingreso manual":
        c1, c2 = st.columns(2)
        params = ParametrosSismicos(
            Z=c1.number_input("Z", 0.01, 1.0, 0.45, 0.05, format="%.2f"),
            U=c2.number_input("U", 0.5, 2.0, 1.00, 0.1, format="%.2f"),
            S=c1.number_input("S", 0.5, 3.0, 1.00, 0.05, format="%.2f"),
            R=c2.number_input("R", 1.0, 12.0, 8.00, 0.5, format="%.2f"),
            Tp=c1.number_input("Tp (s)", 0.05, 3.0, 0.40, 0.05, format="%.2f"),
            Tl=c2.number_input("Tl (s)", 0.1, 6.0, 2.50, 0.1, format="%.2f"),
            g=st.number_input("g (m/s²)", 1.0, 20.0, 9.81, 0.01, format="%.2f"),
        )
    else:
        # 'or' = si no hay parámetros del archivo (p. ej. se restauró el ejemplo), usa los por defecto
        params = st.session_state.params_archivo or ParametrosSismicos()
        st.dataframe(pd.DataFrame([params.como_diccionario()]), hide_index=True)

    with st.expander("🔧 Opciones de cálculo"):
        normalizados = st.checkbox(
            "Modos normalizados respecto a M (Γ = φᵀ·m)", value=True,
            help="Si se desmarca, se usa la fórmula completa Γ = φᵀ·m / (φᵀ·M·φ).")
        peso_abs = st.slider("Peso de Σ|V| en la combinación", 0.0, 1.0, 0.25, 0.05)
        peso_rcsc = 1.0 - peso_abs
        st.caption(f"Peso de √ΣV²: **{peso_rcsc:.2f}**")
        factor_vreal = st.number_input("Factor para Vreal = Vrnc_h · factor · R", 0.0, 2.0, 0.75, 0.05)
        T_max = st.slider("Periodo máximo del espectro (s)", 1.0, 10.0, 5.0, 0.5)

    ejecutar = st.button("▶️ Ejecutar análisis", type="primary")

# =============================================================================
# 4. PESTAÑAS PRINCIPALES
# =============================================================================
tab_datos, tab_espectro, tab_modos, tab_fuerzas, tab_comb, tab_export, tab_teoria = st.tabs([
    "📥 Datos de entrada", "📈 Espectro", "🌀 Modos de vibración",
    "⚖️ Fuerzas y cortantes", "📊 Combinación modal", "💾 Exportar", "📘 Teoría",
])

# -----------------------------------------------------------------------------
# 4.1 DATOS DE ENTRADA (manual o por archivo)
# -----------------------------------------------------------------------------
with tab_datos:
    st.subheader("Datos de la estructura")

    origen = st.radio("Origen de los datos", ["✍️ Ingreso manual", "📂 Cargar archivo"],
                      horizontal=True)

    if origen == "📂 Cargar archivo":
        col_a, col_b = st.columns([2, 1])
        with col_a:
            archivo = st.file_uploader(
                "Sube un Excel (.xlsx) con hojas 'Estructura', 'Periodos' y opcional "
                "'Parametros', o un CSV con una fila final 'T' de periodos.",
                type=["xlsx", "csv", "txt"])
        with col_b:
            st.markdown("**¿No tienes un archivo? Descarga una plantilla:**")
            st.download_button("⬇️ Plantilla Excel", plantilla_excel(),
                               "plantilla_edificio.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.download_button("⬇️ Plantilla CSV", plantilla_csv(),
                               "plantilla_edificio.csv", "text/csv")

        # Leemos el archivo una sola vez (no en cada rerun)
        if archivo is not None:
            id_archivo = (archivo.name, archivo.size)
            if st.session_state.archivo_cargado != id_archivo:
                # try/except: si el archivo está mal, mostramos el error en vez de "romper" la página
                try:
                    datos = leer_archivo(archivo, archivo.name)
                    errores = validar_datos(datos["estructura"], datos["periodos"])
                except Exception as exc:
                    datos, errores = None, [f"No se pudo leer el archivo: {exc}"]

                if errores:
                    for e in errores:
                        st.error(e)
                else:
                    reemplazar_datos(datos["estructura"], datos["periodos"])
                    st.session_state.params_archivo = datos["parametros"]
                    st.session_state.archivo_cargado = id_archivo
                    st.session_state.resultados = None   # fuerza a recalcular con los datos nuevos
                    st.rerun()  # vuelve a dibujar la página (y la barra lateral) con los datos nuevos
            else:
                n = len(st.session_state.df_estructura)
                st.success(f"✅ Usando datos de **{archivo.name}** ({n} pisos). "
                           "Puedes seguir editándolos abajo.")
                if st.session_state.params_archivo is not None:
                    st.caption("El archivo trae parámetros sísmicos: elige "
                               "'Desde archivo cargado' en la barra lateral para usarlos.")

    # --- Botones para modificar la estructura de la tabla ---------------------
    b1, b2, b3, _ = st.columns([1, 1, 1, 3])
    if b1.button("➕ Agregar modo"):
        df = st.session_state.df_estructura.copy()
        df[f"Modo {len(df.columns) - 1}"] = 0.0
        reemplazar_datos(df, st.session_state.df_periodos)
        st.rerun()
    if b2.button("➖ Quitar último modo"):
        df = st.session_state.df_estructura
        if len(df.columns) > 3:
            reemplazar_datos(df.iloc[:, :-1], st.session_state.df_periodos)
            st.rerun()
    if b3.button("↩️ Restaurar ejemplo"):
        reemplazar_datos(*datos_ejemplo())
        st.session_state.archivo_cargado = None
        st.session_state.params_archivo = None
        st.rerun()

    # --- Tablas editables -----------------------------------------------------
    col_est, col_T = st.columns([3, 1])
    with col_est:
        st.markdown("**Masas y formas modales φ** (una fila por piso, Piso 1 = el más bajo). "
                    "Usa ➕ al final de la tabla para agregar pisos.")
        formato = {c: st.column_config.NumberColumn(c, format="%.5f")
                   for c in st.session_state.df_estructura.columns if c.startswith("Modo")}
        formato["Masa"] = st.column_config.NumberColumn("Masa (t·s²/m)", format="%.2f", min_value=0.0)
        formato["Piso"] = st.column_config.NumberColumn("Piso", format="%d", step=1)
        df_estructura = st.data_editor(
            st.session_state.df_estructura, num_rows="dynamic", hide_index=True,
            column_config=formato, key=f"editor_est_{st.session_state.version_editor}")
    with col_T:
        st.markdown("**Periodos por modo**")
        df_periodos = st.data_editor(
            sincronizar_periodos(df_estructura, st.session_state.df_periodos),
            hide_index=True, disabled=["Modo"],
            column_config={"T (s)": st.column_config.NumberColumn("T (s)", format="%.3f", min_value=0.0)},
            key=f"editor_T_{st.session_state.version_editor}")

    errores_datos = validar_datos(df_estructura, df_periodos)
    for e in errores_datos:
        st.warning(e)

# -----------------------------------------------------------------------------
# 5. EJECUCIÓN DEL ANÁLISIS
# -----------------------------------------------------------------------------
# "Huella" = resumen de todas las entradas. Si cambia, los resultados quedan desactualizados.
huella = (df_estructura.to_json(), df_periodos.to_json(), str(params.como_diccionario()),
          normalizados, peso_abs, factor_vreal)

errores_param = params.validar()
primera_vez = st.session_state.resultados is None

if (ejecutar or primera_vez) and not errores_datos and not errores_param:
    pisos, masas, periodos, phi = a_arreglos(df_estructura, df_periodos)
    st.session_state.resultados = ejecutar_analisis(
        pisos, masas, periodos, phi, params, normalizados=normalizados,
        peso_abs=peso_abs, peso_rcsc=peso_rcsc, factor_vreal=factor_vreal)
    st.session_state.huella_resultados = huella
    st.session_state.archivos_export = {}   # los reportes viejos ya no sirven
    if ejecutar:
        st.toast("Análisis ejecutado ✅")

for e in errores_param:
    st.sidebar.error(e)

res = st.session_state.resultados
if res is not None and st.session_state.huella_resultados != huella:
    st.warning("⚠️ Cambiaste datos o parámetros. Pulsa **▶️ Ejecutar análisis** "
               "en la barra lateral para actualizar los resultados.")

# Tarjetas con los resultados clave (arriba de las pestañas de resultados)
if res is not None:
    with tab_datos:
        st.divider()
        st.markdown("#### Resultados clave")
        cols = st.columns(4)
        for col, (nombre, valor) in zip(cols, res.resumen().items()):
            col.metric(nombre, f"{valor:,.3f}" if "Periodo" in nombre else f"{valor:,.2f}")


def mostrar_figura(fig, nombre_archivo: str, clave: str):
    """Muestra una figura y un botón para descargarla como PNG."""
    st.pyplot(fig)
    st.download_button("🖼️ Descargar PNG", graficos.figura_a_png(fig), nombre_archivo,
                       "image/png", key=clave)
    plt.close(fig)  # libera memoria


def sin_resultados():
    st.info("Aún no hay resultados. Revisa los datos y pulsa **▶️ Ejecutar análisis**.")


# -----------------------------------------------------------------------------
# 4.2 ESPECTRO
# -----------------------------------------------------------------------------
with tab_espectro:
    if res is None:
        sin_resultados()
    else:
        st.subheader("Espectro de pseudo-aceleraciones")
        mostrar_figura(graficos.grafico_espectro(res.params, res.periodos, res.Sa, T_max),
                       "espectro.png", "png_espectro")
        st.markdown("**Propiedades modales y espectrales**")
        st.dataframe(res.tabla_modal().style.format(precision=4), hide_index=True)

        masa_total = res.masa_participativa.sum()
        if masa_total >= 90:
            st.success(f"Masa participativa acumulada = {masa_total:.1f} % ≥ 90 % ✔️")
        else:
            st.error(f"Masa participativa acumulada = {masa_total:.1f} % < 90 %. "
                     "La E.030 exige considerar más modos.")

        with st.expander("📐 Ver fórmulas utilizadas"):
            st.latex(r"\omega = \frac{2\pi}{T}")
            st.latex(r"C = \begin{cases} 2.5 & T < T_P \\ 2.5\,\frac{T_P}{T} & T_P \le T \le T_L "
                     r"\\ 2.5\,\frac{T_P\,T_L}{T^2} & T > T_L \end{cases}")
            st.latex(r"S_a = \frac{Z\,U\,C\,S}{R}\,g")
            st.latex(r"\Gamma = \frac{\phi^T m}{\phi^T M \phi}")
        with st.expander("📋 Ver tabla completa del espectro"):
            from sismica import generar_espectro
            st.dataframe(generar_espectro(res.params, T_max, 200).style.format(precision=4),
                         hide_index=True, height=300)

# -----------------------------------------------------------------------------
# 4.3 MODOS DE VIBRACIÓN
# -----------------------------------------------------------------------------
with tab_modos:
    if res is None:
        sin_resultados()
    else:
        st.subheader("Formas modales")
        mostrar_figura(graficos.grafico_formas_modales(res), "formas_modales.png", "png_modos")

        st.markdown("#### 🎬 Animación de un modo")
        c1, c2 = st.columns([1, 2])
        modo_sel = c1.selectbox("Modo a animar", range(res.n_modos),
                                format_func=lambda j: f"Modo {j + 1}")
        if c1.button("Generar animación GIF"):
            with st.spinner("Generando animación..."):
                st.session_state.gif = (modo_sel, graficos.animacion_modo_gif(res, modo_sel))
        if "gif" in st.session_state and st.session_state.gif[0] < res.n_modos:
            j, gif = st.session_state.gif
            c2.image(gif, caption=f"Modo {j + 1}")
            c1.download_button("⬇️ Descargar GIF", gif, f"modo_{j + 1}.gif", "image/gif")

        with st.expander("📋 Tabla de formas modales φ"):
            st.dataframe(res._tabla_por_piso(res.phi).style.format(precision=5), hide_index=True)

# -----------------------------------------------------------------------------
# 4.4 FUERZAS Y CORTANTES POR MODO
# -----------------------------------------------------------------------------
with tab_fuerzas:
    if res is None:
        sin_resultados()
    else:
        st.subheader("Fuerzas y cortantes por modo")
        mostrar_figura(graficos.grafico_fuerzas_cortantes(res), "fuerzas_cortantes.png", "png_fv")

        with st.expander("📋 Aceleraciones por piso Ü = Sa·Γ·φ  (m/s²)"):
            st.dataframe(res.tabla_aceleraciones().style.format(precision=4), hide_index=True)
        with st.expander("📋 Fuerzas sísmicas F = M·Ü  (t)", expanded=True):
            st.dataframe(res.tabla_fuerzas().style.format(precision=3), hide_index=True)
        with st.expander("📋 Cortantes por piso V = ΣF (desde el techo)  (t)", expanded=True):
            st.dataframe(res.tabla_cortantes_modales().style.format(precision=3), hide_index=True)

# -----------------------------------------------------------------------------
# 4.5 COMBINACIÓN MODAL
# -----------------------------------------------------------------------------
with tab_comb:
    if res is None:
        sin_resultados()
    else:
        st.subheader("Combinación modal y cortante real")
        st.dataframe(res.tabla_combinacion().style.format(precision=3), hide_index=True)

        vista = st.radio("Tipo de gráfico", ["Lienzo 2×2 (como el informe)", "Comparación en escalones"],
                         horizontal=True)
        if vista.startswith("Lienzo"):
            mostrar_figura(graficos.grafico_combinaciones(res), "combinaciones.png", "png_comb")
        else:
            mostrar_figura(graficos.grafico_comparacion_cortantes(res), "comparacion.png", "png_comp")

        with st.expander("📐 Ver fórmulas de combinación"):
            st.latex(r"V_{sum\_abs} = \sum_j |V_j| \qquad V_{rcsc} = \sqrt{\sum_j V_j^2}")
            st.latex(rf"V_{{rnc\_h}} = {res.opciones['peso_abs']:.2f}\,V_{{sum\_abs}} + "
                     rf"{res.opciones['peso_rcsc']:.2f}\,V_{{rcsc}}")
            st.latex(rf"V_{{real}} = V_{{rnc\_h}} \cdot {res.opciones['factor_vreal']:.2f} \cdot R"
                     rf" = V_{{rnc\_h}} \cdot {res.opciones['factor_vreal'] * res.params.R:.2f}")

# -----------------------------------------------------------------------------
# 4.6 EXPORTAR
# -----------------------------------------------------------------------------
with tab_export:
    if res is None:
        sin_resultados()
    else:
        st.subheader("Exportar resultados")
        st.write("Los reportes se generan con los **últimos resultados calculados**.")

        if st.button("🛠️ Preparar archivos de descarga"):
            with st.spinner("Generando reportes (Excel, PDF e imágenes)..."):
                figuras = graficos.generar_todas_las_figuras(res)
                st.session_state.archivos_export = {
                    "excel": exportar.generar_excel(res, figuras),
                    "pdf": exportar.generar_pdf(res, figuras),
                    "zip": exportar.generar_zip_imagenes(res, figuras),
                }
                for f in figuras.values():
                    plt.close(f)

        archivos = st.session_state.archivos_export
        if archivos:
            c1, c2, c3 = st.columns(3)
            c1.download_button("📗 Reporte Excel (.xlsx)", archivos["excel"],
                               "Reporte_Analisis_Sismico_E030.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            c2.download_button("📕 Reporte PDF (.pdf)", archivos["pdf"],
                               "Reporte_Analisis_Sismico_E030.pdf", "application/pdf")
            c3.download_button("🖼️ Gráficos PNG (.zip)", archivos["zip"],
                               "Graficos_Analisis_Sismico_E030.zip", "application/zip")
            st.download_button("📄 Tabla de cortantes (.csv)",
                               res.tabla_combinacion().to_csv(index=False).encode("utf-8"),
                               "cortantes_por_piso.csv", "text/csv")

# -----------------------------------------------------------------------------
# 4.7 TEORÍA
# -----------------------------------------------------------------------------
with tab_teoria:
    st.subheader("Procedimiento del análisis modal espectral")
    pasos = [
        ("1. Frecuencia angular", r"\omega = \frac{2\pi}{T}",
         "Cada modo vibra con su propio periodo T."),
        ("2. Espectro de diseño", r"S_a = \frac{Z\,U\,C\,S}{R}\,g",
         "C depende de T, Tp y Tl (meseta, rama descendente y zona de desplazamiento constante)."),
        ("3. Factor de participación", r"\Gamma = \frac{\phi^T m}{\phi^T M \phi}",
         "Si φ está normalizado respecto a M, el denominador vale 1 y Γ = φᵀ·m."),
        ("4. Aceleración por piso", r"\ddot{U} = S_a\,\Gamma\,\phi", "Una columna por modo."),
        ("5. Fuerza sísmica", r"F = M\,\ddot{U}", "M es la matriz diagonal de masas."),
        ("6. Cortante de entrepiso", r"V_i = \sum_{k=i}^{n} F_k", "Se acumula desde el techo hacia abajo."),
        ("7. Combinación modal", r"V_{rnc\_h} = 0.25\sum|V_j| + 0.75\sqrt{\sum V_j^2}",
         "Art. 29.4 de la E.030."),
        ("8. Cortante real", r"V_{real} = V_{rnc\_h}\cdot 0.75 \cdot R", "Según el enunciado del ejercicio."),
    ]
    for titulo, formula, nota in pasos:
        with st.expander(titulo):
            st.latex(formula)
            st.caption(nota)
