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

# ---------- Definición del sistema ----------
VARIABLES = {
    "temperatura": {
        "nombre": "🌡️ Temperatura del aire",
        "unidad": "°C",
        "min": 18.0,
        "max": 30.0,
        "limites": (0.0, 50.0),
        "claves": ["temp"],
        "color": "#e53935",
        "alerta_alta": "🔥 Calor excesivo: enciende el ventilador.",
        "alerta_baja": "❄️ Frío: mantén el ventilador apagado y cierra el invernadero.",
    },
    "humedad_suelo": {
        "nombre": "💧 Humedad del suelo",
        "unidad": "%",
        "min": 40.0,
        "max": 80.0,
        "limites": (0.0, 100.0),
        "claves": ["hum", "suelo"],
        "color": "#0288d1",
        "alerta_alta": "🌊 Suelo encharcado: suspende el riego.",
        "alerta_baja": "🏜️ Suelo seco: hace falta regar.",
    },
}
CSV_EJEMPLO = Path(__file__).parent / "datos_grafana.csv"

st.set_page_config(page_title="Invernadero IoT 🌱", page_icon="🌱", layout="wide")

# ---------- Estilos visuales (Fondo verde y azul clarito) ----------
st.markdown(
    """
    <style>
        /* Fondo principal con degradado verde menta y azul cielo clarito */
        .stApp {
            background: linear-gradient(135deg, #e8f5e9 0%, #e1f5fe 100%);
        }

        /* Fondo del panel lateral (sidebar) */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #dff2e3 0%, #d8effc 100%);
            border-right: 1px solid rgba(255, 255, 255, 0.6);
        }

        /* Barra superior transparente */
        header[data-testid="stHeader"] {
            background-color: transparent;
        }

        .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
        }

        /* Tarjetas de métricas blancas y translúcidas */
        div[data-testid="stMetric"] {
            background-color: rgba(255, 255, 255, 0.78);
            backdrop-filter: blur(6px);
            border: 1px solid rgba(255, 255, 255, 0.9);
            padding: 15px 20px;
            border-radius: 14px;
            box-shadow: 0 4px 12px rgba(0, 77, 64, 0.05);
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------- Lectura del CSV de Grafana ----------
def _a_numero(serie: pd.Series) -> pd.Series:
    """Convierte '25.3 °C' o '55,2%' en números (Grafana puede exportar con unidades)."""
    if pd.api.types.is_numeric_dtype(serie):
        return serie.astype(float)
    texto = serie.astype(str).str.replace(",", ".", regex=False)
    return pd.to_numeric(texto.str.extract(r"(-?\d+(?:\.\d+)?)")[0], errors="coerce")


def _a_tiempo(serie: pd.Series) -> pd.Series:
    """Acepta fechas en texto o marcas de tiempo en milisegundos."""
    if pd.api.types.is_numeric_dtype(serie):
        return pd.to_datetime(serie, unit="ms", errors="coerce")
    tiempo = pd.to_datetime(serie, errors="coerce")
    if tiempo.notna().sum() == 0:
        tiempo = pd.to_datetime(pd.to_numeric(serie, errors="coerce"), unit="ms", errors="coerce")
    if getattr(tiempo.dt, "tz", None) is not None:   # horas en UTC (InfluxDB) -> hora de Colombia
        tiempo = tiempo.dt.tz_convert("America/Bogota").dt.tz_localize(None)
    return tiempo


def leer_csv(archivo) -> pd.DataFrame:
    """Devuelve un DataFrame con 'tiempo' y las variables que encuentre en el archivo."""
    crudo = pd.read_csv(archivo, sep=None, engine="python", comment="#")
    crudo.columns = [str(c).strip() for c in crudo.columns]
    crudo = crudo.loc[:, [c for c in crudo.columns if c and not c.startswith("Unnamed")]]

    if {"_field", "_value"}.issubset(crudo.columns):
        col_t = "_time" if "_time" in crudo.columns else "time"
        crudo = (crudo.pivot_table(index=col_t, columns="_field", values="_value", aggfunc="last")
                 .reset_index().rename(columns={col_t: "time"}))
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
    """Une los CSV (por ejemplo, uno por panel de Grafana) en una sola tabla por tiempo."""
    datos = None
    for tabla in tablas:
        tabla = tabla.sort_values("tiempo")
        if datos is None:
            datos = tabla
            continue
        nuevas = [c for c in tabla.columns if c != "tiempo" and c not in datos.columns]
        if nuevas:
            datos = pd.merge_asof(
                datos, tabla[["tiempo"] + nuevas], on="tiempo",
                direction="nearest", tolerance=pd.Timedelta(seconds=10),
            )
    return datos.sort_values("tiempo").reset_index(drop=True)


def episodios(datos: pd.DataFrame, clave: str) -> pd.DataFrame:
    """Agrupa las lecturas consecutivas fuera de rango en episodios de alerta."""
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
        filas.append({
            "Variable": var["nombre"],
            "Tipo": "📈 Por encima del rango" if tipo == "alta" else "📉 Por debajo del rango",
            "Inicio": bloque["tiempo"].iloc[0],
            "Fin": bloque["tiempo"].iloc[-1],
            "Duración (min)": round((bloque["tiempo"].iloc[-1] - bloque["tiempo"].iloc[0]).total_seconds() / 60, 1),
            "Valor extremo": f'{(bloque[clave].max() if tipo == "alta" else bloque[clave].min()):.1f} {var["unidad"]}',
            "Lecturas": len(bloque),
        })
    return pd.DataFrame(filas)


# ---------- Interfaz ----------
st.title("🌱 Invernadero IoT — Análisis de Operación 🌿")
st.caption(
    "📊 Telemetría del ESP32 (temperatura del aire y humedad del suelo) guardada en InfluxDB "
    "y exportada desde Grafana."
)
st.divider()

with st.sidebar:
    st.header("📂 Panel de Datos")
    archivos = st.file_uploader(
        "📥 CSV exportado de Grafana", type="csv", accept_multiple_files=True,
        help="Puedes subir un CSV con las dos variables o uno por cada panel.",
    )
    st.divider()
    st.header("⚙️ Rangos de Cultivo")
    for clave, var in VARIABLES.items():
        var["min"], var["max"] = st.slider(
            f'{var["nombre"]} ({var["unidad"]})',
            min_value=var["limites"][0], max_value=var["limites"][1],
            value=(var["min"], var["max"]), step=0.5,
        )
    st.caption("🍅 Los valores por defecto corresponden a un cultivo de hortalizas (tomate).")

if archivos:
    datos = unir([leer_csv(a) for a in archivos])
elif CSV_EJEMPLO.exists():
    datos = unir([leer_csv(CSV_EJEMPLO)])
    st.info("💡 Mostrando el CSV incluido en el repositorio. Sube otro CSV de Grafana en el panel lateral para analizarlo.")
else:
    st.warning("⚠️ Sube el CSV exportado desde Grafana en el panel lateral para comenzar.")
    st.stop()

presentes = [c for c in VARIABLES if c in datos.columns and datos[c].notna().any()]
if datos.empty or not presentes:
    st.error(
        "❌ No encontré las variables en el archivo. El CSV debe tener una columna de tiempo y "
        "columnas llamadas `temperatura` y `humedad_suelo`."
    )
    st.stop()

inicio, fin = datos["tiempo"].min(), datos["tiempo"].max()
st.info(
    f"⏱️ **Periodo analizado:** {inicio:%Y-%m-%d %H:%M} a {fin:%Y-%m-%d %H:%M} &nbsp;&nbsp;|&nbsp;&nbsp; "
    f"📈 **Total registros:** {len(datos):,} lecturas"
)

# --- Estado actual ---
st.subheader("📌 Última Lectura en Tiempo Real")
columnas = st.columns(len(presentes))
for col, clave in zip(columnas, presentes):
    var = VARIABLES[clave]
    serie = datos[clave].dropna()
    ultimo = serie.iloc[-1]
    with col:
        st.metric(var["nombre"], f'{ultimo:.1f} {var["unidad"]}',
                  delta=f'{ultimo - serie.mean():+.1f} vs. promedio', delta_color="off")
        if ultimo > var["max"]:
            st.error(f'⚠️ {var["alerta_alta"]}')
        elif ultimo < var["min"]:
            st.error(f'⚠️ {var["alerta_baja"]}')
        else:
            st.success(f'🌱 Dentro del rango óptimo ({var["min"]:g}–{var["max"]:g} {var["unidad"]})')

st.divider()

# --- Series de tiempo ---
st.subheader("📈 Evolución Histórica en el Invernadero")
for clave in presentes:
    var = VARIABLES[clave]
    d = datos[["tiempo", clave]].dropna()
    fuera = d[(d[clave] > var["max"]) | (d[clave] < var["min"])]
    fig = go.Figure()
    fig.add_hrect(y0=var["min"], y1=var["max"], fillcolor="#2e7d32", opacity=0.10, line_width=0,
                  annotation_text="🌿 Rango óptimo de operación", annotation_position="top left")
    fig.add_trace(go.Scatter(x=d["tiempo"], y=d[clave], mode="lines", name=var["nombre"],
                             line=dict(color=var["color"], width=2, shape="spline")))
    if not fuera.empty:
        fig.add_trace(go.Scatter(x=fuera["tiempo"], y=fuera[clave], mode="markers", name="Fuera de rango",
                                 marker=dict(color="#111111", size=6, symbol="x")))
    fig.update_layout(
        height=320,
        margin=dict(l=15, r=15, t=40, b=15),
        title=f'{var["nombre"]} ({var["unidad"]})',
        yaxis_title=var["unidad"],
        legend=dict(orientation="h", y=-0.2),
        hovermode="x unified",
        paper_bgcolor="rgba(255, 255, 255, 0.78)",
        plot_bgcolor="rgba(255, 255, 255, 0.5)",
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- Estadísticas ---
st.subheader("📋 Resumen Estadístico del Cultivo")
filas = []
for clave in presentes:
    var = VARIABLES[clave]
    s = datos[clave].dropna()
    en_rango = ((s >= var["min"]) & (s <= var["max"])).mean() * 100
    filas.append({
        "Variable": f'{var["nombre"]} ({var["unidad"]})',
        "Mínimo": round(s.min(), 1), "Promedio": round(s.mean(), 1), "Máximo": round(s.max(), 1),
        "Desv. estándar": round(s.std(), 2),
        "Rango permitido": f'{var["min"]:g} – {var["max"]:g}',
        "% del tiempo en rango": round(en_rango, 1),
    })
st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)

st.divider()

# --- Alertas ---
st.subheader("🚨 Alertas y Monitoreo de Umbrales")
tablas = [episodios(datos, c) for c in presentes]
alertas = pd.concat([t for t in tablas if not t.empty]) if any(not t.empty for t in tablas) else pd.DataFrame()
if alertas.empty:
    st.success("🎉 ¡Excelente cultivo! No hubo lecturas fuera de rango en todo el periodo analizado.")
else:
    st.write(f"⚠️ Se detectaron **{len(alertas)} episodios** fuera de los rangos ideales:")
    st.dataframe(alertas.sort_values("Inicio"), hide_index=True, use_container_width=True)

# --- Correlación ---
if len(presentes) == 2:
    st.divider()
    st.subheader("🔬 Correlación Climática (Temperatura vs. Humedad)")
    par = datos[presentes].dropna()
    if len(par) >= 3 and par.nunique().min() > 1:
        r = par["temperatura"].corr(par["humedad_suelo"])
        izq, der = st.columns([2, 1])
        with izq:
            fig = go.Figure(go.Scatter(
                x=par["temperatura"], y=par["humedad_suelo"], mode="markers",
                marker=dict(color="#2e7d32", size=7, opacity=0.6)))
            fig.update_layout(
                height=340,
                margin=dict(l=15, r=15, t=15, b=15),
                xaxis_title="Temperatura del aire (°C)",
                yaxis_title="Humedad del suelo (%)",
                paper_bgcolor="rgba(255, 255, 255, 0.78)",
                plot_bgcolor="rgba(255, 255, 255, 0.5)",
            )
            st.plotly_chart(fig, use_container_width=True)
        with der:
            st.metric("📊 Correlación de Pearson", f"{r:.2f}")
            fuerza = "fuerte" if abs(r) >= 0.7 else "moderada" if abs(r) >= 0.4 else "débil"
            if abs(r) < 0.2:
                st.write("🌿 Las dos variables casi no se relacionan en este periodo.")
            elif r < 0:
                st.write(f"☀️ Relación inversa {fuerza}: cuando sube la temperatura, el suelo tiende a secarse. "
                         "Conviene programar el riego automático para las horas más calientes.")
            else:
                st.write(f"🌱 Relación directa {fuerza}: temperatura y humedad del suelo suben juntas en este periodo.")
    else:
        st.info("ℹ️ Se necesitan más lecturas (y que varíen) para calcular la correlación.")

st.divider()

# --- Recomendaciones ---
st.subheader("💡 Recomendaciones para la Operación del Invernadero")
recomendaciones = []
if "temperatura" in presentes:
    s = datos["temperatura"].dropna()
    calor = (s > VARIABLES["temperatura"]["max"]).mean() * 100
    if calor > 0:
        recomendaciones.append(f"🌡️ La temperatura superó el máximo el **{calor:.0f} %** del tiempo: "
                               "el sistema de ventilación debió estar encendido en esos periodos.")
if "humedad_suelo" in presentes:
    s = datos["humedad_suelo"].dropna()
    seco = (s < VARIABLES["humedad_suelo"]["min"]).mean() * 100
    if seco > 0:
        recomendaciones.append(f"💧 El suelo estuvo seco el **{seco:.0f} %** del tiempo: revisa la frecuencia de riego del sistema.")
if not recomendaciones:
    recomendaciones.append("🌱 El invernadero operó perfectamente dentro de los rangos definidos. ¡Buen trabajo de cultivo!")
for texto in recomendaciones:
    st.markdown(f"- {texto}")

with st.expander("📂 Ver datos crudos cargados"):
    st.dataframe(datos, hide_index=True, use_container_width=True)
