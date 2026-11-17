"""
Invernadero IoT - App de análisis
Proyecto Final · Computación Física e Internet de las Cosas

Carga el CSV exportado desde Grafana (uno con las dos variables, o uno por panel)
y analiza la temperatura del aire y la humedad del suelo del invernadero.
"""
import re
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ---------- Configuración de página ----------
st.set_page_config(
    page_title="Invernadero IoT · Dashboard",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- Estilos CSS Personalizados ----------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }

    /* Fondo general y espaciado */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
        max-width: 1250px;
    }

    /* Hero Header */
    .hero-banner {
        background: linear-gradient(135deg, #143627 0%, #1e563b 60%, #2a7551 100%);
        padding: 1.75rem 2rem;
        border-radius: 16px;
        color: white;
        margin-bottom: 1.5rem;
        box-shadow: 0 10px 25px -5px rgba(20, 54, 39, 0.25);
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 1rem;
    }
    .hero-title {
        font-size: 1.75rem;
        font-weight: 700;
        margin: 0 0 0.35rem 0;
        letter-spacing: -0.02em;
    }
    .hero-subtitle {
        font-size: 0.92rem;
        color: #d1e7dd;
        margin: 0;
        max-width: 650px;
    }
    .hero-meta {
        background: rgba(255, 255, 255, 0.12);
        backdrop-filter: blur(8px);
        padding: 0.65rem 1rem;
        border-radius: 12px;
        font-size: 0.85rem;
        border: 1px solid rgba(255, 255, 255, 0.18);
        text-align: right;
    }

    /* Tarjetas KPI */
    .kpi-card {
        background-color: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.18);
        border-radius: 14px;
        padding: 1.25rem 1.4rem;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
        height: 100%;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(0, 0, 0, 0.06);
    }
    .kpi-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.5rem;
    }
    .kpi-title {
        font-size: 0.92rem;
        font-weight: 600;
        opacity: 0.8;
    }
    .kpi-value {
        font-size: 2.15rem;
        font-weight: 700;
        line-height: 1.1;
        margin: 0.25rem 0 0.6rem 0;
        letter-spacing: -0.03em;
    }
    .kpi-footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.82rem;
        padding-top: 0.65rem;
        border-top: 1px solid rgba(128, 128, 128, 0.15);
    }

    /* Badges de estado */
    .badge-ok {
        background-color: rgba(46, 125, 50, 0.14);
        color: #2e7d32;
        padding: 0.25rem 0.65rem;
        border-radius: 999px;
        font-weight: 600;
        font-size: 0.78rem;
    }
    .badge-warn {
        background-color: rgba(211, 47, 47, 0.14);
        color: #d32f2f;
        padding: 0.25rem 0.65rem;
        border-radius: 999px;
        font-weight: 600;
        font-size: 0.78rem;
    }

    /* Tarjeta de Recomendaciones */
    .rec-box {
        background-color: var(--secondary-background-color);
        border-left: 4px solid #2e7d32;
        border-radius: 10px;
        padding: 1rem 1.25rem;
        margin-bottom: 0.75rem;
        font-size: 0.94rem;
    }
    .rec-box.alert {
        border-left-color: #e65100;
    }

    /* Estilizado de pestañas */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        margin-bottom: 1rem;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 10px;
        padding: 0.5rem 1.1rem;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Definición del sistema ----------
VARIABLES = {
    "temperatura": {
        "nombre": "Temperatura del aire",
        "icono": "🌡️",
        "unidad": "°C",
        "min": 18.0,
        "max": 30.0,
        "limites": (0.0, 50.0),
        "claves": ["temp"],
        "color": "#e53935",
        "fill_color": "rgba(229, 57, 53, 0.08)",
        "alerta_alta": "Calor excesivo: enciende el ventilador.",
        "alerta_baja": "Frío: mantén el ventilador apagado y cierra el invernadero.",
    },
    "humedad_suelo": {
        "nombre": "Humedad del suelo",
        "icono": "💧",
        "unidad": "%",
        "min": 40.0,
        "max": 80.0,
        "limites": (0.0, 100.0),
        "claves": ["hum", "suelo"],
        "color": "#0288d1",
        "fill_color": "rgba(2, 136, 209, 0.08)",
        "alerta_alta": "Suelo encharcado: suspende el riego.",
        "alerta_baja": "Suelo seco: hace falta regar.",
    },
}
CSV_EJEMPLO = Path(__file__).parent / "datos_grafana.csv"


# ---------- Lectura del CSV de Grafana (Sin cambios funcionales) ----------
def _a_numero(serie: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(serie):
        return serie.astype(float)
    texto = serie.astype(str).str.replace(",", ".", regex=False)
    return pd.to_numeric(texto.str.extract(r"(-?\d+(?:\.\d+)?)")[0], errors="coerce")


def _a_tiempo(serie: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(serie):
        return pd.to_datetime(serie, unit="ms", errors="coerce")
    tiempo = pd.to_datetime(serie, errors="coerce")
    if tiempo.notna().sum() == 0:
        tiempo = pd.to_datetime(pd.to_numeric(serie, errors="coerce"), unit="ms", errors="coerce")
    if getattr(tiempo.dt, "tz", None) is not None:
        tiempo = tiempo.dt.tz_convert("America/Bogota").dt.tz_localize(None)
    return tiempo


def leer_csv(archivo) -> pd.DataFrame:
    crudo = pd.read_csv(archivo, sep=None, engine="python", comment="#")
    crudo.columns = [str(c).strip() for c in crudo.columns]
    crudo = crudo.loc[:, [c for c in crudo.columns if c and not c.startswith("Unnamed")]]

    if {"_field", "_value"}.issubset(crudo.columns):
        col_t = "_time" if "_time" in crudo.columns else "time"
        crudo = (
            crudo.pivot_table(index=col_t, columns="_field", values="_value", aggfunc="last")
            .reset_index()
            .rename(columns={col_t: "time"})
        )
        crudo.columns = [str(c) for c in crudo.columns]

    col_tiempo = next(
        (c for c in crudo.columns if re.search(r"time|tiempo|fecha", c, re.I)), crudo.columns[0]
    )
    salida = pd.DataFrame({"tiempo": _a_tiempo(crudo[col_tiempo])})

    for clave, var in VARIABLES.items():
        for col in crudo.columns:
            if col == col_tiempo:
                continue
            if any(k in col.lower() for k in var["claves"]):
                salida[clave] = _a_numero(crudo[col])
                break
    return salida.dropna(subset=["tiempo"])


def unir(tablas: list) -> pd.DataFrame:
    datos = None
    for tabla in tablas:
        tabla = tabla.sort_values("tiempo")
        if datos is None:
            datos = tabla
            continue
        nuevas = [c for c in tabla.columns if c != "tiempo" and c not in datos.columns]
        if nuevas:
            datos = pd.merge_asof(
                datos,
                tabla[["tiempo"] + nuevas],
                on="tiempo",
                direction="nearest",
                tolerance=pd.Timedelta(seconds=10),
            )
    return datos.sort_values("tiempo").reset_index(drop=True)


def episodios(datos: pd.DataFrame, clave: str) -> pd.DataFrame:
    var = VARIABLES[clave]
    d = datos[["tiempo", clave]].dropna()
    estado = pd.Series("ok", index=d.index)
    estado[d[clave] > var["max"]] = "alta"
    estado[d[clave] < var["min"]] = "baja"
    grupo = (estado != estado.shift()).cumsum()
    filas = []
    for _, bloque in d.groupby(grupo):
        tipo = estado.loc[bloque.index[0]]
        if tipo == "ok":
            continue
        filas.append(
            {
                "Variable": f'{var["icono"]} {var["nombre"]}',
                "Tipo": "⬆️ Por encima del rango" if tipo == "alta" else "⬇️ Por debajo del rango",
                "Inicio": bloque["tiempo"].iloc[0],
                "Fin": bloque["tiempo"].iloc[-1],
                "Duración (min)": round(
                    (bloque["tiempo"].iloc[-1] - bloque["tiempo"].iloc[0]).total_seconds() / 60, 1
                ),
                "Valor extremo": f'{(bloque[clave].max() if tipo == "alta" else bloque[clave].min()):.1f} {var["unidad"]}',
                "Lecturas": len(bloque),
            }
        )
    return pd.DataFrame(filas)


# ---------- Sidebar ----------
with st.sidebar:
    st.markdown("### 📂 Fuente de datos")
    archivos = st.file_uploader(
        "CSV exportado de Grafana",
        type="csv",
        accept_multiple_files=True,
        help="Puedes subir un CSV con las dos variables o uno por cada panel.",
    )
    st.divider()
    st.markdown("### 🎛️ Umbrales de operación")
    for clave, var in VARIABLES.items():
        var["min"], var["max"] = st.slider(
            f'{var["icono"]} {var["nombre"]} ({var["unidad"]})',
            min_value=var["limites"][0],
            max_value=var["limites"][1],
            value=(var["min"], var["max"]),
            step=0.5,
        )
    st.caption("ℹ️ Valores por defecto calibrados para cultivo de hortalizas (tomate).")

# ---------- Carga de datos ----------
usando_ejemplo = False
if archivos:
    datos = unir([leer_csv(a) for a in archivos])
elif CSV_EJEMPLO.exists():
    datos = unir([leer_csv(CSV_EJEMPLO)])
    usando_ejemplo = True
else:
    st.warning("👈 Sube el CSV exportado desde Grafana en el panel lateral para comenzar.")
    st.stop()

presentes = [c for c in VARIABLES if c in datos.columns and datos[c].notna().any()]
if datos.empty or not presentes:
    st.error(
        "No encontré las variables en el archivo. El CSV debe tener una columna de tiempo y "
        "columnas llamadas `temperatura` y `humedad_suelo`."
    )
    st.stop()

inicio, fin = datos["tiempo"].min(), datos["tiempo"].max()

# ---------- Hero Header ----------
st.markdown(
    f"""
    <div class="hero-banner">
        <div>
            <div class="hero-title">🌱 Invernadero IoT · Monitor de Operación</div>
            <p class="hero-subtitle">
                Telemetría ESP32 → InfluxDB → Grafana · Análisis térmico e hídrico del cultivo
            </p>
        </div>
        <div class="hero-meta">
            <div><strong>📅 Periodo:</strong> {inicio:%d/%m/%Y %H:%M} → {fin:%d/%m/%Y %H:%M}</div>
            <div style="margin-top:4px;"><strong>📊 Muestras:</strong> {len(datos):,} lecturas</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if usando_ejemplo:
    st.info(
        "📌 **Modo demostración:** Visualizando el archivo `datos_grafana.csv` del repositorio. "
        "Carga tus propios archivos desde la barra lateral."
    )

# ---------- KPIs Principales (Tarjetas) ----------
columnas = st.columns(len(presentes))
for col, clave in zip(columnas, presentes):
    var = VARIABLES[clave]
    serie = datos[clave].dropna()
    ultimo = serie.iloc[-1]
    promedio = serie.mean()
    delta = ultimo - promedio

    if ultimo > var["max"]:
        badge = '<span class="badge-warn">⚠️ Sobre el límite</span>'
        mensaje_estado = var["alerta_alta"]
        color_valor = "#d32f2f"
    elif ultimo < var["min"]:
        badge = '<span class="badge-warn">⚠️ Bajo el límite</span>'
        mensaje_estado = var["alerta_baja"]
        color_valor = "#d32f2f"
    else:
        badge = '<span class="badge-ok">✓ Rango óptimo</span>'
        mensaje_estado = f'Operación estable ({var["min"]:g}–{var["max"]:g} {var["unidad"]})'
        color_valor = var["color"]

    with col:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-header">
                    <span class="kpi-title">{var["icono"]} {var["nombre"].upper()}</span>
                    {badge}
                </div>
                <div class="kpi-value" style="color: {color_valor};">
                    {ultimo:.1f}<span style="font-size:1.1rem; font-weight:500; opacity:0.7;"> {var["unidad"]}</span>
                </div>
                <div style="font-size:0.86rem; margin-bottom:0.85rem; opacity:0.9;">
                    {mensaje_estado}
                </div>
                <div class="kpi-footer">
                    <span>Media: <strong>{promedio:.1f} {var["unidad"]}</strong></span>
                    <span>Desv. vs media: <strong>{delta:+.1f} {var["unidad"]}</strong></span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.markdown("<div style='height: 1.25rem;'></div>", unsafe_allow_html=True)

# ---------- Navegación por Pestañas ----------
tab_graficas, tab_alertas, tab_datos = st.tabs(
    ["📈 Series de Tiempo y Correlación", "🚨 Alertas y Diagnóstico", "🗂️ Tabla de Datos"]
)

# === PESTAÑA 1: GRÁFICAS ===
with tab_graficas:
    for clave in presentes:
        var = VARIABLES[clave]
        d = datos[["tiempo", clave]].dropna()
        fuera = d[(d[clave] > var["max"]) | (d[clave] < var["min"])]

        fig = go.Figure()
        # Banda de rango óptimo
        fig.add_hrect(
            y0=var["min"],
            y1=var["max"],
            fillcolor="rgba(46, 125, 50, 0.09)",
            line_width=0,
            annotation_text=f'Zona óptima ({var["min"]:g}–{var["max"]:g} {var["unidad"]})',
            annotation_position="top left",
            annotation_font=dict(size=11, color="#2e7d32"),
        )
        # Líneas límite punteadas
        fig.add_hline(y=var["max"], line_dash="dot", line_color="rgba(46,125,50,0.4)", line_width=1)
        fig.add_hline(y=var["min"], line_dash="dot", line_color="rgba(46,125,50,0.4)", line_width=1)

        # Serie principal con área suave
        fig.add_trace(
            go.Scatter(
                x=d["tiempo"],
                y=d[clave],
                mode="lines",
                name=var["nombre"],
                line=dict(color=var["color"], width=2.5, shape="spline", smoothing=0.4),
                fill="tozeroy",
                fillcolor=var["fill_color"],
            )
        )

        # Puntos fuera de rango
        if not fuera.empty:
            fig.add_trace(
                go.Scatter(
                    x=fuera["tiempo"],
                    y=fuera[clave],
                    mode="markers",
                    name="Fuera de rango",
                    marker=dict(color="#111111", size=6, symbol="circle-open", line=dict(width=2)),
                )
            )

        fig.update_layout(
            height=330,
            margin=dict(l=15, r=15, t=45, b=15),
            title=dict(text=f'{var["icono"]} {var["nombre"]}', font=dict(size=16)),
            yaxis_title=var["unidad"],
            hovermode="x unified",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.12)"),
            yaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.12)"),
            legend=dict(orientation="h", y=1.12, x=1, xanchor="right"),
        )
        st.plotly_chart(fig, use_container_width=True)

    # Correlación
    if len(presentes) == 2:
        st.divider()
        st.markdown("#### 🔗 Relación Temperatura vs. Humedad del Suelo")
        par = datos[presentes].dropna()
        if len(par) >= 3 and par.nunique().min() > 1:
            r = par["temperatura"].corr(par["humedad_suelo"])
            izq, der = st.columns([2.2, 1])
            with izq:
                fig = go.Figure(
                    go.Scatter(
                        x=par["temperatura"],
                        y=par["humedad_suelo"],
                        mode="markers",
                        marker=dict(
                            color=par["temperatura"],
                            colorscale="Tealrose",
                            size=8,
                            opacity=0.
