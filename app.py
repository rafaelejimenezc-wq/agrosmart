"""
=============================================================================
 AgroSmart - Sistema inteligente de apoyo a la decision agricola
 Fase 1 (MVP): suelo, terreno, recomendacion de cultivos, riego (simulador),
 plagas (apoyo) y reportes.
=============================================================================
 Ejecutar con:   streamlit run app.py
=============================================================================
 Recordatorio academico:
   - Los rangos de los cultivos en datos/cultivos.json son ILUSTRATIVOS.
     Reemplazalos con FAO EcoCrop / ICA / Agrosavia y citalos.
   - La foto NO analiza quimicamente el suelo: el dato quimico viene del
     laboratorio. La foto se usa para apoyo en plagas (modulo aparte).
=============================================================================
"""

import os
import io
import json
import math
import html
from datetime import date, datetime

import numpy as np
import pandas as pd
import requests
import streamlit as st
import folium
from folium.plugins import Draw, MeasureControl, LocateControl
from streamlit_folium import st_folium

from reportes import generar_pdf_reporte
import plagas_ia
import gee_utils
import auth
import asistente
import db

# ---------------------------------------------------------------------------
# Rutas y constantes
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "datos")
DB_PATH = os.path.join(DATA_DIR, "agrosmart.db")
CULTIVOS_PATH = os.path.join(DATA_DIR, "cultivos.json")
PLAGAS_PATH = os.path.join(DATA_DIR, "plagas.json")

os.makedirs(DATA_DIR, exist_ok=True)

CENTRO_DEFECTO = [4.8133, -75.6961]  # Pereira, Risaralda (ajusta a tu zona)

NIVEL = {"bajo": 1, "medio": 2, "alto": 3}
NIVEL_INV = {1: "bajo", 2: "medio", 3: "alto"}
AGUA = {"baja": 1, "media": 2, "alta": 3}

# Pesos transparentes del motor de recomendacion (suman 1.0)
PESOS = {
    "ph": 0.30,
    "textura": 0.15,
    "temperatura": 0.15,
    "agua": 0.15,
    "nitrogeno": 0.10,
    "fosforo": 0.05,
    "potasio": 0.10,
}

ETIQUETAS_CRITERIO = {
    "ph": "pH", "textura": "textura", "temperatura": "temperatura",
    "agua": "agua", "nitrogeno": "nitrógeno", "fosforo": "fósforo",
    "potasio": "potasio",
}

# Umbrales DE EJEMPLO (mg/kg) para clasificar nutrientes. Citalos antes de la entrega.
UMBRALES_N = (20, 40)
UMBRALES_P = (10, 20)
UMBRALES_K = (100, 200)
UMBRALES_MO = (2, 4)          # Materia organica (%)
UMBRALES_CE = (1, 2)          # Conductividad electrica (dS/m)

TEXTURAS = ["arenosa", "franco-arenosa", "franca", "franco-arcillosa", "arcillosa"]


# ---------------------------------------------------------------------------
# Acceso a datos (PostgreSQL/Neon o SQLite local)
# ---------------------------------------------------------------------------
def get_conn():
    return db.get_conn()


def init_db():
    with get_conn() as conn:
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS analisis_suelo (
                id {db.PK},
                fecha TEXT, lote TEXT,
                ph REAL, materia_organica REAL,
                nitrogeno REAL, fosforo REAL, potasio REAL,
                calcio REAL, magnesio REAL,
                conductividad REAL, humedad REAL,
                textura TEXT, agua TEXT, temperatura REAL,
                lat REAL, lon REAL, notas TEXT
            )"""
        )
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS terrenos (
                id {db.PK},
                fecha TEXT, nombre TEXT, geojson TEXT,
                area_total_ha REAL, area_apta_ha REAL, notas TEXT
            )"""
        )
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS recomendaciones (
                id {db.PK},
                usuario_id INTEGER,
                fecha TEXT,
                condiciones TEXT,
                resultados TEXT
            )"""
        )
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS seguimiento_cultivos (
                id {db.PK},
                usuario_id INTEGER,
                cultivo TEXT,
                lote TEXT,
                fecha_siembra TEXT,
                estado TEXT,
                notas TEXT,
                creado TEXT,
                actualizado TEXT
            )"""
        )
        # Migracion: versiones anteriores no tenian usuario_id.
        for tabla in ("analisis_suelo", "terrenos"):
            cols = db.columnas(conn, tabla)
            if "usuario_id" not in cols:
                conn.execute(f"ALTER TABLE {tabla} ADD COLUMN usuario_id INTEGER")
        conn.commit()
    auth.init_auth_db()


def insert_suelo(d):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO analisis_suelo
               (usuario_id,fecha,lote,ph,materia_organica,nitrogeno,fosforo,potasio,
                calcio,magnesio,conductividad,humedad,textura,agua,temperatura,lat,lon,notas)
               VALUES (:usuario_id,:fecha,:lote,:ph,:materia_organica,:nitrogeno,:fosforo,
                :potasio,:calcio,:magnesio,:conductividad,:humedad,:textura,:agua,
                :temperatura,:lat,:lon,:notas)""",
            d,
        )
        conn.commit()


def insert_terreno(nombre, geojson, area_total, area_apta, notas, usuario_id):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO terrenos
               (usuario_id,fecha,nombre,geojson,area_total_ha,area_apta_ha,notas)
               VALUES (?,?,?,?,?,?,?)""",
            (usuario_id, date.today().isoformat(), nombre, json.dumps(geojson),
             area_total, area_apta, notas),
        )
        conn.commit()


def _filas_a_df(rows):
    return pd.DataFrame([dict(r) for r in rows])


def list_suelo(usuario_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM analisis_suelo WHERE usuario_id=? ORDER BY id DESC",
            (usuario_id,),
        ).fetchall()
    return _filas_a_df(rows)


def list_terrenos(usuario_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM terrenos WHERE usuario_id=? ORDER BY id DESC",
            (usuario_id,),
        ).fetchall()
    return _filas_a_df(rows)


def delete_suelo(id_, usuario_id):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM analisis_suelo WHERE id=? AND usuario_id=?",
            (id_, usuario_id),
        )
        conn.commit()


def delete_terreno(id_, usuario_id):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM terrenos WHERE id=? AND usuario_id=?",
            (id_, usuario_id),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Recomendaciones guardadas y seguimiento de cultivos
# ---------------------------------------------------------------------------
def save_recomendacion(usuario_id, condiciones, resultados):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO recomendaciones (usuario_id, fecha, condiciones, resultados)
               VALUES (?,?,?,?)""",
            (
                usuario_id,
                datetime.now().isoformat(timespec="seconds"),
                json.dumps(condiciones, ensure_ascii=False, default=str),
                json.dumps(resultados, ensure_ascii=False, default=str),
            ),
        )
        conn.commit()


def list_recomendaciones(usuario_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM recomendaciones WHERE usuario_id=? ORDER BY id DESC",
            (usuario_id,),
        ).fetchall()
    return _filas_a_df(rows)


def add_cultivo(usuario_id, cultivo, lote, fecha_siembra, estado, notas):
    ahora = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO seguimiento_cultivos
               (usuario_id, cultivo, lote, fecha_siembra, estado, notas, creado, actualizado)
               VALUES (?,?,?,?,?,?,?,?)""",
            (usuario_id, cultivo, lote, fecha_siembra, estado, notas, ahora, ahora),
        )
        conn.commit()


def list_cultivos(usuario_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM seguimiento_cultivos WHERE usuario_id=? ORDER BY id DESC",
            (usuario_id,),
        ).fetchall()
    return _filas_a_df(rows)


def update_cultivo(id_, usuario_id, estado, notas):
    with get_conn() as conn:
        conn.execute(
            """UPDATE seguimiento_cultivos
               SET estado=?, notas=?, actualizado=?
               WHERE id=? AND usuario_id=?""",
            (estado, notas, datetime.now().isoformat(timespec="seconds"), id_, usuario_id),
        )
        conn.commit()


def delete_cultivo(id_, usuario_id):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM seguimiento_cultivos WHERE id=? AND usuario_id=?",
            (id_, usuario_id),
        )
        conn.commit()


def contar_usuario(usuario_id):
    tablas = {
        "suelos": "analisis_suelo",
        "terrenos": "terrenos",
        "recomendaciones": "recomendaciones",
        "cultivos": "seguimiento_cultivos",
    }
    with get_conn() as conn:
        return {
            clave: conn.execute(
                f"SELECT COUNT(*) AS n FROM {tabla} WHERE usuario_id=?", (usuario_id,)
            ).fetchone()["n"]
            for clave, tabla in tablas.items()
        }


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
@st.cache_data
def _cargar_json(path, mtime):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def cargar_json(path):
    # La fecha de modificación entra en la caché: si editas el JSON,
    # la app lo recarga sin reiniciar.
    return _cargar_json(path, os.path.getmtime(path))


@st.cache_resource(show_spinner=False)
def _cargar_modelo_ia():
    return plagas_ia.cargar_modelo()


@st.cache_data(ttl=60, show_spinner=False)
def _estado_servicios_neon():
    import neon_services as ns
    return {
        "PostgreSQL": ns.estado_postgres(),
        "Functions": ns.estado_functions(),
        "Auth (JWKS)": ns.estado_auth(),
        "Realtime": ns.estado_realtime(),
        "AI Gateway": ns.estado_ai_gateway(),
    }


def area_geodesica_ha(coords_latlon):
    """Area de un poligono en hectareas. coords = [(lat, lon), ...]."""
    if not coords_latlon or len(coords_latlon) < 3:
        return 0.0
    R = 6378137.0  # radio terrestre (m)
    total = 0.0
    n = len(coords_latlon)
    for i in range(n):
        lat1, lon1 = coords_latlon[i]
        lat2, lon2 = coords_latlon[(i + 1) % n]
        total += math.radians(lon2 - lon1) * (
            2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2))
        )
    area_m2 = abs(total * R * R / 2.0)
    return area_m2 / 10000.0


def clasificar(valor, umbrales):
    """Devuelve 'bajo'/'medio'/'alto' segun los umbrales (min, max)."""
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return None
    b, a = umbrales
    if valor < b:
        return "bajo"
    if valor <= a:
        return "medio"
    return "alto"


def latlon_de_geojson(geojson):
    """Extrae el anillo exterior de un poligono GeoJSON como [(lat, lon), ...]."""
    try:
        geom = geojson["geometry"] if geojson.get("type") == "Feature" else geojson
        if geom["type"] == "Polygon":
            anillo = geom["coordinates"][0]
        elif geom["type"] == "MultiPolygon":
            anillo = geom["coordinates"][0][0]
        else:
            return []
        return [(pt[1], pt[0]) for pt in anillo]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Motor de recomendacion de cultivos
# ---------------------------------------------------------------------------
def _sat_rango(valor, vmin, vmax):
    """Satisfaccion 1.0 dentro del rango; decae fuera de el."""
    if valor is None:
        return 0.0
    if vmin <= valor <= vmax:
        return 1.0
    dist = (vmin - valor) if valor < vmin else (valor - vmax)
    margen = max(vmax - vmin, 1e-6)
    return max(0.0, 1.0 - dist / margen)


def _sat_nutriente(cat_usuario, cat_requerido):
    if cat_usuario is None or cat_requerido is None:
        return 0.0
    dif = NIVEL[cat_usuario] - NIVEL[cat_requerido]
    if dif >= 0:
        return 1.0
    if dif == -1:
        return 0.5
    return 0.0


def _sat_textura(textura_usuario, texturas_ok):
    if not textura_usuario:
        return 0.0
    if textura_usuario in texturas_ok:
        return 1.0
    # vecindad: comparte parte del nombre (franco-*)
    if any(textura_usuario.split("-")[0] == t.split("-")[0] for t in texturas_ok):
        return 0.5
    return 0.15


def _sat_agua(agua_usuario, agua_requerida):
    if not agua_usuario or not agua_requerida:
        return 0.0
    dif = AGUA[agua_usuario] - AGUA[agua_requerida]
    if dif >= 0:
        return 1.0
    if dif == -1:
        return 0.5
    return 0.15


def evaluar_cultivo(cultivo, cond):
    detalle = {}
    detalle["ph"] = _sat_rango(cond.get("ph"), cultivo["ph_min"], cultivo["ph_max"])
    detalle["textura"] = _sat_textura(cond.get("textura"), cultivo["texturas"])
    detalle["temperatura"] = _sat_rango(
        cond.get("temperatura"), cultivo["temp_min"], cultivo["temp_max"]
    )
    detalle["agua"] = _sat_agua(cond.get("agua"), cultivo["agua"])
    detalle["nitrogeno"] = _sat_nutriente(cond.get("nitrogeno_cat"), cultivo["n"])
    detalle["fosforo"] = _sat_nutriente(cond.get("fosforo_cat"), cultivo["p"])
    detalle["potasio"] = _sat_nutriente(cond.get("potasio_cat"), cultivo["k"])

    puntaje = sum(PESOS[k] * detalle[k] for k in PESOS) * 100.0
    return {"puntaje": round(puntaje, 1), "detalle": detalle}


def recomendar(cond, top=5, categoria=None):
    cultivos = cargar_json(CULTIVOS_PATH)["cultivos"]
    if categoria and categoria != "Todas":
        cultivos = [c for c in cultivos if c.get("categoria") == categoria]
    resultados = []
    for c in cultivos:
        ev = evaluar_cultivo(c, cond)
        resultados.append({"cultivo": c, **ev})
    resultados.sort(key=lambda x: x["puntaje"], reverse=True)
    return resultados[:top]


def clasificar_puntaje(p):
    if p >= 80:
        return "Alta", "#2e7d32"
    if p >= 60:
        return "Media", "#f9a825"
    return "Baja", "#c62828"


# ---------------------------------------------------------------------------
# Interfaz
# ---------------------------------------------------------------------------
st.set_page_config(page_title="AgroSmart", page_icon="🌱", layout="wide")
try:
    init_db()
except Exception as e:
    st.error(
        "No se pudo conectar a la base de datos. Revisa los Secrets "
        "(PGHOST, PGDATABASE, PGUSER, PGPASSWORD, PGSSLMODE)."
    )
    st.code(str(e))
    st.stop()

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.5rem;}
      .agro-card {background:#f1f8e9;border-left:6px solid #558b2f;
                  padding:14px 18px;border-radius:8px;margin-bottom:8px;}
      .agro-muted {color:#5f6b5f;font-size:0.9rem;}
      h1, h2, h3 {color:#33691e;}

      /* ---------- Asistente flotante ---------- */
      .agro-bot {position:fixed;right:18px;bottom:18px;z-index:99999;
        display:flex;align-items:center;gap:10px;text-decoration:none !important;
        color:inherit !important;animation:botFloat 3.2s ease-in-out infinite;}
      .agro-bot-emoji {width:58px;height:58px;border-radius:50%;
        background:linear-gradient(135deg,#7cb342,#33691e);
        display:flex;align-items:center;justify-content:center;font-size:30px;
        box-shadow:0 8px 24px rgba(51,105,30,.35);border:3px solid #fff;}
      .agro-bot-bubble {max-width:270px;background:#fff;color:#1b1b1b;
        padding:10px 14px;border-radius:14px;font-size:13px;line-height:1.35;
        box-shadow:0 8px 24px rgba(0,0,0,.18);border-left:4px solid #558b2f;
        animation:botPeek 7s ease-in-out infinite;}
      .agro-bot.alerta .agro-bot-emoji {
        background:linear-gradient(135deg,#ffb74d,#e65100);}
      .agro-bot.oculto .agro-bot-bubble {display:none;}
      .agro-bot.oculto {right:-34px;opacity:.7;}
      .agro-bot.oculto:hover {right:18px;opacity:1;}
      @keyframes botFloat {
        0%,100% {transform:translateY(0);} 50% {transform:translateY(-8px);}
      }
      @keyframes botPeek {
        0%,90%,100% {opacity:1;} 94% {opacity:.25;}
      }

      /* ---------- Movil y tablet ---------- */
      @media (max-width: 768px) {
        .block-container {padding: 1rem 0.75rem 2.5rem 0.75rem;}
        h1 {font-size: 1.6rem; line-height: 1.2;}
        h2 {font-size: 1.3rem;}
        h3 {font-size: 1.1rem;}
        .stButton > button, .stDownloadButton > button {
          width: 100%; min-height: 2.9rem; font-size: 1rem;
        }
        [data-testid="stMetricValue"] {font-size: 1.5rem;}
        [data-testid="stMetricLabel"] {font-size: 0.85rem;}
        .stTabs [data-baseweb="tab"] {font-size: 0.9rem; padding: 0.5rem 0.6rem;}
        .agro-card {padding: 12px 14px;}
        .agro-bot {right: 10px; bottom: 10px;}
        .agro-bot-emoji {width: 50px; height: 50px; font-size: 26px;}
        .agro-bot-bubble {max-width: 190px; font-size: 12px;}
        /* Apilar columnas en pantallas pequenas */
        [data-testid="stHorizontalBlock"] {flex-wrap: wrap; gap: 0.6rem;}
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
          flex: 1 1 100% !important;
          width: 100% !important;
          min-width: 100% !important;
        }
      }
      @media (max-width: 480px) {
        h1 {font-size: 1.4rem;}
        h2 {font-size: 1.15rem;}
        .block-container {padding-left: 0.5rem; padding-right: 0.5rem;}
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Autenticacion (registro / inicio de sesion)
# ---------------------------------------------------------------------------
def _usuario_actual():
    if st.session_state.get("usuario"):
        return st.session_state["usuario"]
    token = st.query_params.get("s")
    if token:
        uid = auth.verificar_token(token)
        if uid:
            u = auth.obtener_usuario(uid)
            if u:
                st.session_state["usuario"] = u
                st.session_state["token"] = token
                return u
    return None


def render_login():
    st.markdown(
        """
        <div style="text-align:center;padding:1rem 0 0.3rem 0;">
          <div style="font-size:3.2rem;line-height:1">🌱</div>
          <h1 style="margin:0.2rem 0 0 0">AgroSmart</h1>
          <p style="color:#5f6b5f;margin-top:0.3rem">
            Decide qué cultivar con datos de suelo, mapa, clima y riego.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns([1, 1.7, 1])
    with c2:
        tab_login, tab_reg = st.tabs(["Iniciar sesión", "Crear cuenta"])

        with tab_login:
            with st.form("form_login"):
                email = st.text_input("Correo electrónico", placeholder="tu@correo.com")
                password = st.text_input("Contraseña", type="password")
                entrar = st.form_submit_button(
                    "Entrar", use_container_width=True, type="primary"
                )
            if entrar:
                u = auth.autenticar(email, password)
                if u:
                    auth.actualizar_ultimo_acceso(u["id"])
                    token = auth.crear_token(u["id"])
                    st.session_state["usuario"] = u
                    st.session_state["token"] = token
                    st.query_params["s"] = token
                    st.rerun()
                else:
                    st.error("Correo o contraseña incorrectos, o cuenta desactivada.")

        with tab_reg:
            with st.form("form_registro"):
                nombre = st.text_input("Nombre")
                email2 = st.text_input("Correo electrónico")
                pass1 = st.text_input("Contraseña (mínimo 6)", type="password")
                pass2 = st.text_input("Repite la contraseña", type="password")
                crear = st.form_submit_button(
                    "Crear mi cuenta", use_container_width=True, type="primary"
                )
            if crear:
                if pass1 != pass2:
                    st.error("Las contraseñas no coinciden.")
                else:
                    try:
                        uid = auth.crear_usuario(nombre, email2, pass1)
                        auth.actualizar_ultimo_acceso(uid)
                        u = auth.obtener_usuario(uid)
                        token = auth.crear_token(uid)
                        st.session_state["usuario"] = u
                        st.session_state["token"] = token
                        st.query_params["s"] = token
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

        st.caption(
            "Es gratis. Tus análisis quedan guardados en tu cuenta. "
            "Un administrador puede revisar tus registros para seguimiento; "
            "nunca puede ver tu contraseña."
        )


usuario = _usuario_actual()
if usuario is None:
    render_login()
    st.stop()

USUARIO_ID = usuario["id"]
ES_ADMIN = usuario.get("rol") == "admin"

# Estado de sesión
if "terreno_geojson" not in st.session_state:
    st.session_state.terreno_geojson = None
if "ultima_recomendacion" not in st.session_state:
    st.session_state.ultima_recomendacion = None
if "chat" not in st.session_state:
    st.session_state.chat = [{
        "role": "assistant",
        "content": (
            f"¡Hola, {usuario['nombre']}! 👋 Soy tu asistente de AgroSmart. "
            "Puedo guiarte paso a paso y revisar tus datos. "
            "¿Quieres que empecemos?"
        ),
    }]

PAGINAS = [
    "🏠 Inicio",
    "🤖 Asistente",
    "🧪 Análisis de suelo",
    "🗺️ Terreno y hectáreas",
    "🌱 Recomendación de cultivos",
    "🌾 Mis cultivos",
    "📚 Catálogo de cultivos",
    "💧 Riego IoT",
    "🐛 Plagas (apoyo)",
    "🛰️ Satélite (GEE)",
    "📊 Mi historial",
]
if ES_ADMIN:
    PAGINAS.append("🛡️ Panel admin")
PAGINAS.append("📄 Reportes")

# Sidebar
st.sidebar.title("🌱 AgroSmart")
st.sidebar.caption(f"👤 {usuario['nombre']}" + (" · 🛡️ Admin" if ES_ADMIN else ""))
_qp = st.query_params.get("pagina")
_idx = PAGINAS.index("🤖 Asistente") if _qp == "asistente" else 0
pagina = st.sidebar.radio("Módulo", PAGINAS, index=_idx)
st.sidebar.divider()
bot_visible = st.sidebar.toggle("Mostrar asistente flotante", value=True)

with st.sidebar.expander("🔑 Cambiar contraseña"):
    with st.form("form_cambiar_pass"):
        _actual = st.text_input("Contraseña actual", type="password")
        _nueva = st.text_input("Nueva contraseña", type="password")
        _conf = st.text_input("Repite la nueva", type="password")
        if st.form_submit_button("Actualizar contraseña", use_container_width=True):
            if _nueva != _conf:
                st.error("Las contraseñas nuevas no coinciden.")
            else:
                try:
                    auth.cambiar_password(USUARIO_ID, _actual, _nueva)
                    st.success("Contraseña actualizada.")
                except ValueError as e:
                    st.error(str(e))

if st.sidebar.button("Cerrar sesión", use_container_width=True):
    for _k in ("usuario", "token", "chat", "terreno_geojson", "ultima_recomendacion"):
        st.session_state.pop(_k, None)
    try:
        st.query_params.clear()
    except Exception:
        for k in list(st.query_params.keys()):
            del st.query_params[k]
    st.rerun()
st.sidebar.caption("Fase 2 · Cuentas + Asistente")


# ---------------------------------------------------------------------------
# Asistente flotante (CSS)
# ---------------------------------------------------------------------------
def render_bot(tip: str, alerta: bool = False, visible: bool = True):
    token = st.session_state.get("token", "")
    tip = html.escape(tip)
    clase = "agro-bot"
    if alerta:
        clase += " alerta"
    if not visible:
        clase += " oculto"
    st.html(
        f"""
        <a class="{clase}" href="?s={token}&amp;pagina=asistente" target="_self"
           title="Abrir el asistente">
          <span class="agro-bot-bubble">{tip}</span>
          <span class="agro-bot-emoji">🤖</span>
        </a>
        """
    )


def _contexto_asistente():
    dfs = list_suelo(USUARIO_ID)
    dft = list_terrenos(USUARIO_ID)
    recs = st.session_state.get("ultima_recomendacion") or []
    avisos = asistente.validar_suelo(dfs.iloc[0].to_dict()) if not dfs.empty else []
    return {
        "nombre": usuario["nombre"],
        "estado": {
            "suelos": len(dfs),
            "terrenos": len(dft),
            "recomendaciones": len(recs),
        },
        "avisos": avisos,
    }


def _enviar_asistente(texto: str):
    st.session_state.chat.append({"role": "user", "content": texto})
    ctx = _contexto_asistente()
    respuesta = asistente.responder(texto, ctx, st.session_state.chat)
    st.session_state.chat.append({"role": "assistant", "content": respuesta})
    st.rerun()


# --------------------------- INICIO ---------------------------------------
if pagina == "🏠 Inicio":
    st.title("AgroSmart")
    st.subheader("Sistema inteligente de apoyo a la decisión agrícola")
    st.markdown(
        """
        <div class="agro-card">
        <b>Enfoque:</b> integrar el <b>análisis de suelo de laboratorio</b>, la
        ubicación y superficie del terreno, la recomendación de cultivos, el
        monitoreo de riego y el apoyo en plagas, en una sola herramienta.
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Análisis de suelo", len(list_suelo(USUARIO_ID)))
    c2.metric("Terrenos", len(list_terrenos(USUARIO_ID)))
    c3.metric("Cultivos en base", len(cargar_json(CULTIVOS_PATH)["cultivos"]))

    if st.button("🧪 Cargar datos de demostración"):
        with get_conn() as conn:
            existe = conn.execute(
                "SELECT COUNT(*) AS n FROM analisis_suelo WHERE lote='Lote demostración' AND usuario_id=?",
                (USUARIO_ID,),
            ).fetchone()["n"]
        if existe:
            st.info("Los datos de demostración ya están cargados.")
        else:
            insert_suelo({
                "usuario_id": USUARIO_ID,
                "fecha": date.today().isoformat(), "lote": "Lote demostración",
                "ph": 6.2, "materia_organica": 3.5, "nitrogeno": 25.0,
                "fosforo": 15.0, "potasio": 150.0, "calcio": None, "magnesio": None,
                "conductividad": 0.8, "humedad": 32.0, "textura": "franca",
                "agua": "media", "temperatura": 22.0,
                "lat": 4.8133, "lon": -75.6961, "notas": "Datos de ejemplo",
            })
            poly = {
                "type": "Polygon",
                "coordinates": [[
                    [-75.7000, 4.8100], [-75.6985, 4.8100],
                    [-75.6985, 4.8115], [-75.7000, 4.8115],
                    [-75.7000, 4.8100],
                ]],
            }
            coords = latlon_de_geojson(poly)
            area = area_geodesica_ha(coords)
            insert_terreno("Finca demostración", poly, area, area * 0.9,
                           "Datos de ejemplo", USUARIO_ID)
            st.success(
                "Datos de demostración cargados. Ve a **🌱 Recomendación de cultivos** "
                "y luego a **📄 Reportes**."
            )
            st.rerun()

    st.markdown("### Tu ruta en AgroSmart")
    _dfs = list_suelo(USUARIO_ID)
    _dft = list_terrenos(USUARIO_ID)
    _recs = st.session_state.get("ultima_recomendacion") or []
    _estado = {"suelos": len(_dfs), "terrenos": len(_dft), "recomendaciones": len(_recs)}
    _paso = asistente.paso_siguiente(_estado)
    _total = len(asistente.PASOS)
    st.progress(min(_paso / _total, 1.0), text=f"Paso {min(_paso + 1, _total)} de {_total}")
    for _i, (_titulo, _detalle) in enumerate(asistente.PASOS):
        if _i < _paso:
            _icono = "✅"
        elif _i == _paso:
            _icono = "👉"
        else:
            _icono = "⚪"
        st.markdown(f"{_icono} **{_titulo}** — {_detalle}")

    _avisos = asistente.validar_suelo(_dfs.iloc[0].to_dict()) if not _dfs.empty else []
    if _avisos:
        st.warning("🤖 Revisa estos datos antes de seguir:\n" +
                   "\n".join(f"- {a['mensaje']}" for a in _avisos))

    if st.button("🤖 Hablar con el asistente", use_container_width=True):
        st.query_params["pagina"] = "asistente"
        st.rerun()

    st.info(
        "Recuerda: el dato químico del suelo viene del **laboratorio**. "
        "La fotografía no reemplaza el análisis de laboratorio."
    )


# --------------------------- ASISTENTE ------------------------------------
elif pagina == "🤖 Asistente":
    st.title("🤖 Asistente AgroSmart")
    _ctx = _contexto_asistente()
    _est = _ctx["estado"]
    st.caption(
        f"Te guío paso a paso. Llevas {_est['suelos']} análisis de suelo, "
        f"{_est['terrenos']} terreno(s) y {_est['recomendaciones']} recomendación(es)."
    )
    if asistente.llm_configurado():
        st.success("Modo IA generativa activado.")
    else:
        st.info(
            "Modo guía (reglas), siempre disponible y gratis. Para respuestas "
            "generativas, agrega las claves AGROSMART_LLM_URL y AGROSMART_LLM_KEY "
            "en .streamlit/secrets.toml."
        )

    c1, c2, c3 = st.columns(3)
    if c1.button("¿Qué hago primero?", use_container_width=True):
        _enviar_asistente("¿Qué hago primero?")
    if c2.button("Revisa mis datos", use_container_width=True):
        _enviar_asistente("Revisa mis datos")
    if c3.button("¿Qué cultivo me conviene?", use_container_width=True):
        _enviar_asistente("¿Qué cultivo me conviene?")

    for _m in st.session_state.chat:
        with st.chat_message(_m["role"]):
            st.markdown(_m["content"])

    _prompt = st.chat_input("Escribe tu pregunta...")
    if _prompt:
        _enviar_asistente(_prompt)


# --------------------------- SUELO ----------------------------------------
elif pagina == "🧪 Análisis de suelo":
    st.title("🧪 Análisis de suelo (laboratorio)")

    with st.form("form_suelo", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        lote = c1.text_input("Nombre del lote", "Lote 1")
        fecha = c2.date_input("Fecha del análisis", date.today())
        textura = c3.selectbox("Textura", TEXTURAS, index=2)

        st.markdown("**Parámetros químicos**")
        c1, c2, c3, c4 = st.columns(4)
        ph = c1.number_input("pH", 0.0, 14.0, 6.2, 0.1)
        mo = c2.number_input("Materia orgánica (%)", 0.0, 20.0, 3.0, 0.1)
        ce = c3.number_input("Conductividad (dS/m)", 0.0, 20.0, 0.8, 0.1)
        humedad = c4.number_input("Humedad (%)", 0.0, 100.0, 30.0, 0.5)

        c1, c2, c3 = st.columns(3)
        n = c1.number_input("Nitrógeno (mg/kg)", 0.0, 500.0, 25.0, 1.0)
        p = c2.number_input("Fósforo (mg/kg)", 0.0, 500.0, 15.0, 1.0)
        k = c3.number_input("Potasio (mg/kg)", 0.0, 1000.0, 150.0, 1.0)

        c1, c2, c3 = st.columns(3)
        agua = c1.selectbox("Disponibilidad de agua", ["baja", "media", "alta"], index=1)
        temperatura = c2.number_input("Temperatura media (°C)", -5.0, 45.0, 22.0, 0.5)
        notas = c3.text_input("Notas", "")

        st.markdown("**Referencia geográfica (opcional)**")
        c1, c2 = st.columns(2)
        lat = c1.number_input("Latitud", -90.0, 90.0, CENTRO_DEFECTO[0], format="%.6f")
        lon = c2.number_input("Longitud", -180.0, 180.0, CENTRO_DEFECTO[1], format="%.6f")

        enviado = st.form_submit_button("💾 Guardar análisis", use_container_width=True)

    if enviado:
        datos = {
            "usuario_id": USUARIO_ID,
            "fecha": fecha.isoformat(), "lote": lote, "ph": ph, "materia_organica": mo,
            "nitrogeno": n, "fosforo": p, "potasio": k, "calcio": None, "magnesio": None,
            "conductividad": ce, "humedad": humedad, "textura": textura, "agua": agua,
            "temperatura": temperatura, "lat": lat, "lon": lon, "notas": notas,
        }
        insert_suelo(datos)
        st.success(f"Análisis del lote **{lote}** guardado correctamente.")
        for a in asistente.validar_suelo(datos):
            st.warning("🤖 " + a["mensaje"])

    st.divider()
    st.subheader("Análisis registrados")
    df = list_suelo(USUARIO_ID)
    if df.empty:
        st.caption("Aún no hay análisis registrados.")
    else:
        st.dataframe(
            df[["id", "fecha", "lote", "ph", "materia_organica", "nitrogeno",
                "fosforo", "potasio", "textura", "agua", "temperatura"]],
            use_container_width=True, hide_index=True,
        )
        del_id = st.selectbox("Eliminar por ID", ["—"] + df["id"].tolist())
        if del_id != "—" and st.button("Eliminar análisis seleccionado"):
            delete_suelo(int(del_id), USUARIO_ID)
            st.rerun()


# --------------------------- TERRENO --------------------------------------
elif pagina == "🗺️ Terreno y hectáreas":
    st.title("🗺️ Terreno y cálculo de hectáreas")
    st.caption("Usa la herramienta de polígono (arriba a la izquierda del mapa) para dibujar el lote.")

    c1, c2, c3 = st.columns([1, 1, 2])
    lat0 = c1.number_input("Centro (lat)", -90.0, 90.0, CENTRO_DEFECTO[0], format="%.6f")
    lon0 = c2.number_input("Centro (lon)", -180.0, 180.0, CENTRO_DEFECTO[1], format="%.6f")
    nombre = c3.text_input("Nombre del terreno/lote", "Finca Lote 1")

    mapa = folium.Map(location=[lat0, lon0], zoom_start=15, control_scale=True)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery", name="Satélite",
    ).add_to(mapa)
    folium.TileLayer("OpenStreetMap", name="Calles").add_to(mapa)
    folium.LayerControl().add_to(mapa)
    MeasureControl(position="topleft", primary_length_unit="meters").add_to(mapa)
    LocateControl().add_to(mapa)
    Draw(
        export=False,
        draw_options={
            "polygon": True, "rectangle": True, "polyline": False,
            "circle": False, "marker": False, "circlemarker": False,
        },
        edit_options={"edit": True, "remove": True},
    ).add_to(mapa)

    if st.session_state.terreno_geojson:
        folium.GeoJson(st.session_state.terreno_geojson).add_to(mapa)

    salida = st_folium(
        mapa, width=None, height=520,
        returned_objects=["all_drawings", "last_active_drawing"],
        key="mapa_terreno",
    )

    dibujo = None
    if salida:
        if salida.get("last_active_drawing"):
            dibujo = salida["last_active_drawing"]
        elif salida.get("all_drawings"):
            dibujo = salida["all_drawings"][-1]

    if dibujo:
        st.session_state.terreno_geojson = dibujo

    est = st.session_state.terreno_geojson
    if est:
        coords = latlon_de_geojson(est)
        area_total = area_geodesica_ha(coords)
        st.markdown(f"### Área total dibujada: **{area_total:,.3f} ha**")
        c1, c2 = st.columns(2)
        pct_no_apta = c1.slider("Área no cultivable (cuerpos de agua, infraestructura, pendiente)", 0, 100, 10, 1)
        area_apta = area_total * (1 - pct_no_apta / 100.0)
        c2.metric("Área potencialmente cultivable", f"{area_apta:,.3f} ha")
        notas = st.text_input("Notas del terreno", "")
        if st.button("💾 Guardar terreno", use_container_width=True):
            insert_terreno(nombre, est, area_total, area_apta, notas, USUARIO_ID)
            st.success(f"Terreno **{nombre}** guardado ({area_apta:,.2f} ha aptas).")
            for a in asistente.validar_terreno(area_total, area_apta):
                if a["nivel"] == "error":
                    st.error("🤖 " + a["mensaje"])
                else:
                    st.warning("🤖 " + a["mensaje"])
        st.download_button(
            "⬇️ Descargar GeoJSON para QGIS",
            data=json.dumps(est, ensure_ascii=False).encode("utf-8"),
            file_name=f"{nombre.replace(' ', '_')}.geojson",
            mime="application/geo+json",
            use_container_width=True,
        )
    else:
        st.info("Dibuja un polígono en el mapa para calcular el área.")

    st.divider()
    st.subheader("Terrenos registrados")
    dft = list_terrenos(USUARIO_ID)
    if dft.empty:
        st.caption("Aún no hay terrenos registrados.")
    else:
        st.dataframe(
            dft[["id", "fecha", "nombre", "area_total_ha", "area_apta_ha", "notas"]],
            use_container_width=True, hide_index=True,
        )
        del_id = st.selectbox("Eliminar terreno por ID", ["—"] + dft["id"].tolist())
        if del_id != "—" and st.button("Eliminar terreno seleccionado"):
            delete_terreno(int(del_id), USUARIO_ID)
            st.rerun()


# --------------------------- RECOMENDACION --------------------------------
elif pagina == "🌱 Recomendación de cultivos":
    st.title("🌱 Recomendación de cultivos")
    st.caption("El puntaje se calcula con criterios y pesos explícitos (abajo), no es un dato inventado.")

    df = list_suelo(USUARIO_ID)
    usar_db = False
    if not df.empty:
        usar_db = st.toggle("Usar un análisis de suelo guardado", value=True)

    cond = {}
    if usar_db and not df.empty:
        idx = st.selectbox(
            "Selecciona el análisis", df.index,
            format_func=lambda i: f"#{df.loc[i,'id']} · {df.loc[i,'lote']} · {df.loc[i,'fecha']}",
        )
        fila = df.loc[idx]
        cond = {
            "ph": fila["ph"], "textura": fila["textura"], "temperatura": fila["temperatura"],
            "agua": fila["agua"],
            "nitrogeno_cat": clasificar(fila["nitrogeno"], UMBRALES_N),
            "fosforo_cat": clasificar(fila["fosforo"], UMBRALES_P),
            "potasio_cat": clasificar(fila["potasio"], UMBRALES_K),
        }
        st.write(
            f"**pH:** {fila['ph']} · **Textura:** {fila['textura']} · "
            f"**Temp:** {fila['temperatura']} °C · **Agua:** {fila['agua']}"
        )
    else:
        c1, c2, c3, c4 = st.columns(4)
        cond["ph"] = c1.number_input("pH", 0.0, 14.0, 6.2, 0.1)
        cond["textura"] = c2.selectbox("Textura", TEXTURAS, index=2)
        cond["temperatura"] = c3.number_input("Temperatura (°C)", -5.0, 45.0, 22.0, 0.5)
        cond["agua"] = c4.selectbox("Disponibilidad de agua", ["baja", "media", "alta"], index=1)
        c1, c2, c3 = st.columns(3)
        cond["nitrogeno_cat"] = c1.selectbox("Nitrógeno", ["bajo", "medio", "alto"], index=1)
        cond["fosforo_cat"] = c2.selectbox("Fósforo", ["bajo", "medio", "alto"], index=1)
        cond["potasio_cat"] = c3.selectbox("Potasio", ["bajo", "medio", "alto"], index=1)

    cat_todas = ["Todas"] + sorted({c["categoria"] for c in cargar_json(CULTIVOS_PATH)["cultivos"]})
    c1, c2 = st.columns([2, 1])
    categoria = c1.selectbox("Filtrar por categoría", cat_todas)
    top_n = c2.slider("Número de resultados", 3, 15, 8)

    if st.button("🔎 Calcular recomendaciones", type="primary", use_container_width=True):
        res = recomendar(cond, top=top_n, categoria=categoria)
        st.session_state.ultima_recomendacion = res
        save_recomendacion(
            USUARIO_ID,
            {
                "ph": cond.get("ph"), "textura": cond.get("textura"),
                "temperatura": cond.get("temperatura"), "agua": cond.get("agua"),
                "nitrogeno": cond.get("nitrogeno_cat"),
                "fosforo": cond.get("fosforo_cat"),
                "potasio": cond.get("potasio_cat"),
                "categoria": categoria,
            },
            [
                {
                    "nombre": r["cultivo"]["nombre"],
                    "emoji": r["cultivo"].get("emoji", ""),
                    "puntaje": r["puntaje"],
                }
                for r in res
            ],
        )

    resultados = st.session_state.ultima_recomendacion
    if resultados:
        st.subheader("Resultados")
        for r in resultados:
            c = r["cultivo"]
            nivel, color = clasificar_puntaje(r["puntaje"])
            with st.container(border=True):
                col1, col2 = st.columns([1, 4])
                col1.markdown(f"<h2 style='margin:0'>{c['emoji']}</h2>", unsafe_allow_html=True)
                col2.markdown(
                    f"### {c['nombre']} — "
                    f"<span style='color:{color}'><b>{r['puntaje']} %</b> ({nivel})</span>",
                    unsafe_allow_html=True,
                )
                st.caption(
                    f"{c.get('categoria','')} · {c.get('nombre_cientifico','')} · "
                    f"ciclo {c.get('ciclo_dias','—')} días"
                )
                det = r["detalle"]
                dfd = pd.DataFrame({
                    "Criterio": ["pH", "Textura", "Temperatura", "Agua",
                                 "Nitrógeno", "Fósforo", "Potasio"],
                    "Peso": [f"{PESOS[k]*100:.0f} %" for k in
                             ["ph", "textura", "temperatura", "agua",
                              "nitrogeno", "fosforo", "potasio"]],
                    "Cumplimiento": [f"{det[k]*100:.0f} %" for k in
                                     ["ph", "textura", "temperatura", "agua",
                                      "nitrogeno", "fosforo", "potasio"]],
                })
                st.dataframe(dfd, hide_index=True, use_container_width=True)
                a_mejorar = [k for k in det if det[k] < 0.7]
                if a_mejorar:
                    st.caption(
                        "Por mejorar: "
                        + ", ".join(ETIQUETAS_CRITERIO[k] for k in a_mejorar)
                    )
                else:
                    st.caption("Todas las condiciones evaluadas son favorables.")
        st.info(
            "Los **pesos** y los **rangos** son configurables. Antes de la entrega, "
            "justifícalos y cítalos (FAO EcoCrop, ICA, Agrosavia)."
        )
    else:
        st.caption("Configura las condiciones y pulsa **Calcular recomendaciones**.")


# --------------------------- MIS CULTIVOS --------------------------------
elif pagina == "🌾 Mis cultivos":
    st.title("🌾 Mis cultivos")
    st.caption("Registra lo que siembras y actualiza su estado para hacer seguimiento.")

    nombres_cultivos = [c["nombre"] for c in cargar_json(CULTIVOS_PATH)["cultivos"]]
    ESTADOS = ["Planificado", "Sembrado", "En crecimiento", "Con problema", "Cosechado"]

    with st.form("form_cultivo", clear_on_submit=True):
        c1, c2 = st.columns(2)
        cultivo = c1.selectbox("Cultivo", nombres_cultivos)
        lote = c2.text_input("Lote / ubicación", "")
        c1, c2 = st.columns(2)
        fecha_siembra = c1.date_input("Fecha de siembra", date.today())
        estado = c2.selectbox("Estado", ESTADOS)
        notas = st.text_input("Notas", "")
        if st.form_submit_button("➕ Agregar cultivo", use_container_width=True):
            add_cultivo(USUARIO_ID, cultivo, lote, fecha_siembra.isoformat(), estado, notas)
            st.success(f"Cultivo **{cultivo}** agregado al seguimiento.")
            st.rerun()

    dfc = list_cultivos(USUARIO_ID)
    if dfc.empty:
        st.info("Aún no tienes cultivos en seguimiento.")
    else:
        st.subheader("Seguimiento actual")
        st.dataframe(
            dfc[["id", "cultivo", "lote", "fecha_siembra", "estado", "notas", "actualizado"]],
            hide_index=True, use_container_width=True,
        )

        st.subheader("Actualizar un cultivo")
        c1, c2 = st.columns(2)
        sel = c1.selectbox(
            "Cultivo", dfc["id"].tolist(),
            format_func=lambda i: f"#{i} · {dfc.loc[dfc['id'] == i, 'cultivo'].iloc[0]}",
        )
        nuevo_estado = c2.selectbox("Nuevo estado", ESTADOS)
        nuevas_notas = st.text_input("Notas actualizadas", "")
        if st.button("💾 Actualizar seguimiento", use_container_width=True):
            update_cultivo(int(sel), USUARIO_ID, nuevo_estado, nuevas_notas)
            st.success("Seguimiento actualizado.")
            st.rerun()

        del_id = st.selectbox("Eliminar por ID", ["—"] + dfc["id"].tolist())
        if del_id != "—" and st.button("Eliminar cultivo del seguimiento"):
            delete_cultivo(int(del_id), USUARIO_ID)
            st.rerun()


# --------------------------- CATALOGO -------------------------------------
elif pagina == "📚 Catálogo de cultivos":
    st.title("📚 Catálogo de cultivos")
    st.caption("Explora los cultivos, sus requerimientos y sus plagas antes de decidir.")

    cultivos = cargar_json(CULTIVOS_PATH)["cultivos"]
    catalogo_plagas = cargar_json(PLAGAS_PATH)["plagas"]
    sintomas_cat = cargar_json(PLAGAS_PATH)["sintomas_catalogo"]

    c1, c2, c3 = st.columns([2, 1, 1])
    busqueda = c1.text_input("Buscar por nombre", "")
    categorias = ["Todas"] + sorted({c["categoria"] for c in cultivos})
    cat = c2.selectbox("Categoría", categorias)
    agua = c3.selectbox("Agua", ["Todas", "baja", "media", "alta"])

    filtrados = [
        c for c in cultivos
        if (not busqueda or busqueda.lower() in c["nombre"].lower())
        and (cat == "Todas" or c["categoria"] == cat)
        and (agua == "Todas" or c["agua"] == agua)
    ]

    st.caption(f"{len(filtrados)} cultivo(s) encontrados")

    if filtrados:
        df = pd.DataFrame([
            {
                "Cultivo": f"{c['emoji']} {c['nombre']}",
                "Categoría": c["categoria"],
                "pH": f"{c['ph_min']}–{c['ph_max']}",
                "Temp (°C)": f"{c['temp_min']}–{c['temp_max']}",
                "Agua": c["agua"],
                "Ciclo (días)": c["ciclo_dias"],
                "N-P-K": f"{c['n']} / {c['p']} / {c['k']}",
            }
            for c in filtrados
        ])
        st.dataframe(df, hide_index=True, use_container_width=True)

        st.divider()
        st.subheader("Ficha del cultivo")
        sel = st.selectbox("Elige un cultivo", [c["nombre"] for c in filtrados])
        c = next(x for x in filtrados if x["nombre"] == sel)

        col1, col2 = st.columns([1, 4])
        col1.markdown(f"<h1 style='text-align:center'>{c['emoji']}</h1>", unsafe_allow_html=True)
        col2.markdown(f"## {c['nombre']}")
        col2.caption(f"{c['categoria']} · {c['nombre_cientifico']}")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("pH", f"{c['ph_min']}–{c['ph_max']}")
        m2.metric("Temperatura", f"{c['temp_min']}–{c['temp_max']} °C")
        m3.metric("Agua", c["agua"])
        m4.metric("Ciclo", f"{c['ciclo_dias']} días")

        st.write(f"**Texturas:** {', '.join(c['texturas'])}")
        st.write(f"**Nutrientes:** N {c['n']} · P {c['p']} · K {c['k']}")
        st.info(c["observaciones"])

        plagas_cultivo = [p for p in catalogo_plagas if c["nombre"] in p["cultivos"]]
        st.markdown(f"### Plagas y enfermedades frecuentes ({len(plagas_cultivo)})")
        if plagas_cultivo:
            for p in plagas_cultivo:
                with st.expander(f"{p['nombre']} — {p['tipo']}"):
                    st.markdown(f"**Manejo sugerido:** {p['manejo']}")
                    st.caption(
                        "Síntomas: "
                        + ", ".join(sintomas_cat.get(s, s) for s in p["sintomas"])
                    )
        else:
            st.caption("Sin plagas registradas para este cultivo.")

        st.download_button(
            "⬇️ Descargar catálogo filtrado (CSV)",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="catalogo_cultivos.csv",
            mime="text/csv",
            use_container_width=True,
        )
    else:
        st.info("No hay cultivos que coincidan con los filtros.")


# --------------------------- RIEGO IOT ------------------------------------
elif pagina == "💧 Riego IoT":
    st.title("💧 Riego IoT")

    API = os.environ.get("AGROSMART_IOT_API", "http://localhost:8000")
    DEVICE = os.environ.get("AGROSMART_DEVICE_ID", "esp32-01")

    def _get(ruta):
        try:
            r = requests.get(API + ruta, timeout=3)
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    def _post(ruta, payload=None):
        try:
            r = requests.post(API + ruta, json=payload or {}, timeout=5)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            st.error(f"No se pudo enviar la orden: {e}")
            return None

    tab_vivo, tab_sim = st.tabs(["🟢 En vivo (ESP32)", "🧪 Simulador"])

    # ------------------------- EN VIVO ------------------------------------
    with tab_vivo:
        estado_srv = _get("/")
        if not estado_srv:
            st.warning(
                "No hay conexión con el servidor IoT. Inicia `iniciar_iot.bat` "
                "y verifica que el ESP32 esté en la misma red Wi-Fi."
            )
            st.code("iniciar_iot.bat", language="bat")
            st.caption(f"Servidor esperado: {API}")
        else:
            c1, c2 = st.columns([3, 1])
            c1.success(f"Servidor IoT conectado en {API}")
            if c2.button("🔄 Actualizar", use_container_width=True):
                st.rerun()

            est = _get(f"/api/estado/{DEVICE}")
            if est:
                cfg = est["config"]
                ult = est["ultima"]
                riego = est["riego_actual"]

                c1, c2, c3 = st.columns(3)
                c1.metric("Humedad actual", f"{ult['humedad']:.0f} %" if ult else "—")
                c2.metric("Temperatura", f"{ult['temperatura']:.1f} °C"
                          if ult and ult.get("temperatura") is not None else "—")
                c3.metric("Bomba", "ENCENDIDA 💧" if riego else "APAGADA ⛔")
                st.caption(
                    f"Modo: **{cfg['modo']}** · Umbral mínimo: **{cfg['umbral_min']} %** · "
                    f"Apagado: **{cfg['umbral_max']} %**"
                    + (f" · Última lectura: {ult['ts']}" if ult else "")
                )

                lecturas = _get(f"/api/lecturas/{DEVICE}?limite=300") or []
                if lecturas:
                    dfi = pd.DataFrame(lecturas)
                    dfi["ts"] = pd.to_datetime(dfi["ts"])
                    dfi = dfi.set_index("ts")
                    st.line_chart(dfi[["humedad"]])
                    st.caption("Historial recibido del ESP32 (se actualiza al refrescar).")
                else:
                    st.info("Aún no hay lecturas. Enciende el ESP32 y espera el primer envío.")

                st.divider()
                with st.expander("⚙️ Configurar umbrales y control manual", expanded=True):
                    with st.form("cfg_iot"):
                        c1, c2 = st.columns(2)
                        umin = c1.number_input("Umbral mínimo (%)", 0, 100, int(cfg["umbral_min"]))
                        umax = c2.number_input("Umbral de apagado (%)", 0, 100, int(cfg["umbral_max"]))
                        if st.form_submit_button("Guardar umbrales"):
                            if umax <= umin:
                                st.error("El umbral de apagado debe ser mayor que el mínimo.")
                            else:
                                _post(f"/api/config/{DEVICE}",
                                      {"umbral_min": umin, "umbral_max": umax})
                                st.success("Umbrales actualizados.")
                                st.rerun()
                    c1, c2, c3 = st.columns(3)
                    if c1.button("💧 Encender bomba", use_container_width=True):
                        _post(f"/api/riego/{DEVICE}", {"encender": True})
                        st.rerun()
                    if c2.button("⛔ Apagar bomba", use_container_width=True):
                        _post(f"/api/riego/{DEVICE}", {"encender": False})
                        st.rerun()
                    if c3.button("🤖 Volver a automático", use_container_width=True):
                        _post(f"/api/auto/{DEVICE}")
                        st.rerun()

    # ------------------------- SIMULADOR ----------------------------------
    with tab_sim:
        st.markdown(
            """
            <div class="agro-card">
            Prueba la <b>lógica del riego</b> (histéresis) sin hardware.
            </div>
            """,
            unsafe_allow_html=True,
        )
        c1, c2, c3 = st.columns(3)
        hum_min = c1.slider("Umbral mínimo de humedad (%)", 0, 100, 35)
        hum_max = c2.slider("Umbral de apagado (%)", 0, 100, 45)
        hum_actual = c3.slider("Humedad actual del sensor (%)", 0, 100, 27)

        if hum_max <= hum_min:
            st.warning("El umbral de apagado debe ser mayor que el mínimo.")
        else:
            if hum_actual < hum_min:
                estado, color = "ENCENDIDA 💧", "#1565c0"
                msg = "La humedad está por debajo del mínimo: se activa el riego."
            elif hum_actual >= hum_max:
                estado, color = "APAGADA ⛔", "#2e7d32"
                msg = "La humedad alcanzó el objetivo: se apaga el riego."
            else:
                estado, color = "EN ESPERA ⏳", "#f9a825"
                msg = "Dentro de la banda: mantiene el estado anterior (histéresis)."
            st.markdown(
                f"<h3>Bomba: <span style='color:{color}'>{estado}</span></h3>",
                unsafe_allow_html=True,
            )
            st.caption(msg)

        st.divider()
        st.subheader("Historial simulado")
        rng = np.random.default_rng(42)
        horas = pd.date_range(end=datetime.now(), periods=24, freq="h")
        serie = np.clip(np.cumsum(rng.normal(0, 4, 24)) + 35, 0, 100)
        st.line_chart(pd.DataFrame({"Humedad (%)": serie}, index=horas))
        st.caption("Ejemplo ilustrativo. Con el sensor real, los datos llegan por la pestaña 'En vivo'.")

        with st.expander("🔌 Puesta en marcha del hardware"):
            st.markdown(
                """
                1. Abre `firmware/esp32_riego.ino` en Arduino IDE.
                2. Cambia `SSID`, `PASSWORD` y la IP del computador en `SERVIDOR`.
                3. Calibra `SECO` y `MOJADO` con el monitor serial.
                4. Conecta el sensor a GPIO 34 y el relé a GPIO 26.
                5. Carga el sketch al ESP32.

                El servidor debe estar corriendo con `iniciar_iot.bat` y el
                firewall de Windows debe permitir el puerto 8000.
                """
            )


# --------------------------- PLAGAS ---------------------------------------
elif pagina == "🐛 Plagas (apoyo)":
    st.title("🐛 Apoyo en identificación de plagas")
    st.warning(
        "Este módulo es **preliminar**. No reemplaza la inspección de un "
        "profesional agrícola ni un diagnóstico de laboratorio."
    )

    catalogo = cargar_json(PLAGAS_PATH)
    sintomas_cat = catalogo["sintomas_catalogo"]
    cultivos = [c["nombre"] for c in cargar_json(CULTIVOS_PATH)["cultivos"]]

    tab_ia, tab_sint = st.tabs(["📷 Analizar imagen (IA)", "🔎 Por síntomas"])

    # ------------------------- IA POR IMAGEN ------------------------------
    with tab_ia:
        disponible, msj = plagas_ia.estado()
        if disponible:
            st.success(msj)
        else:
            st.info(
                "El motor de IA no está instalado todavía. Ejecuta **instalar_ia.bat** "
                "para habilitarlo. Mientras tanto puedes usar la pestaña **Por síntomas**."
            )
            st.code("instalar_ia.bat", language="bat")

        c1, c2 = st.columns([2, 1])
        with c1:
            foto = st.file_uploader(
                "Sube una foto clara de la hoja afectada",
                type=["jpg", "jpeg", "png"],
                key="foto_ia",
            )
            if foto:
                st.image(foto, caption="Imagen cargada", use_container_width=True)
        with c2:
            st.markdown("**Recomendaciones para la foto**")
            st.caption(
                "- Una sola hoja, bien iluminada.\n"
                "- Fondo neutro.\n"
                "- Enfoca los síntomas (manchas, moho, insectos)."
            )
            analizar = st.button(
                "🔎 Analizar con IA",
                type="primary",
                use_container_width=True,
                disabled=(foto is None or not disponible),
            )

        if analizar and foto is not None:
            with st.spinner("Cargando modelo y analizando la imagen..."):
                modelo = _cargar_modelo_ia()
            if modelo is None:
                st.error(
                    "No se pudo cargar el modelo. Revisa tu conexión a internet "
                    "o ejecuta `instalar_ia.bat`.\n\n"
                    f"Detalle: {plagas_ia.ultimo_error()}"
                )
            else:
                try:
                    preds = plagas_ia.clasificar(modelo, foto.getvalue(), top=5)
                except Exception as e:
                    st.error(f"Error al clasificar la imagen: {e}")
                    preds = []
                if preds:
                    st.subheader("Resultado preliminar")
                    for etiqueta, prob in preds:
                        st.markdown(f"**{etiqueta}** — {prob * 100:.1f} % de confianza")
                        st.progress(min(prob, 1.0))
                    st.caption(
                        "El modelo fue entrenado con imágenes de laboratorio "
                        "(PlantVillage). En campo puede fallar: úsalo como apoyo "
                        "y confirma con inspección directa."
                    )

        st.info(
            "La IA **no analiza el suelo**. El dato químico del suelo viene del "
            "laboratorio; este módulo solo apoya la identificación de plagas."
        )

    # ------------------------- POR SINTOMAS -------------------------------
    with tab_sint:
        cultivo = st.selectbox("Cultivo", cultivos)
        seleccion = st.multiselect(
            "Selecciona los síntomas que observas",
            options=list(sintomas_cat.keys()),
            format_func=lambda k: sintomas_cat[k],
        )

        if seleccion:
            del_cultivo = [p for p in catalogo["plagas"] if cultivo in p["cultivos"]]
            base = del_cultivo if del_cultivo else catalogo["plagas"]
            puntuados = []
            for pl in base:
                s = set(pl["sintomas"]) & set(seleccion)
                if not s:
                    continue
                puntuados.append((len(s), s, pl))
            puntuados.sort(key=lambda x: x[0], reverse=True)

            if not del_cultivo:
                st.caption(
                    "No hay fichas específicas para este cultivo: se muestran "
                    "coincidencias generales."
                )

            if not puntuados:
                st.info("No se encontraron coincidencias en el catálogo.")
            else:
                st.subheader("Coincidencias preliminares")
                for score, s, pl in puntuados[:6]:
                    with st.container(border=True):
                        st.markdown(f"**{pl['nombre']}** — _{pl['tipo']}_")
                        st.caption("Síntomas coincidentes: " + ", ".join(sintomas_cat[x] for x in s))
                        st.markdown(f"**Manejo sugerido:** {pl['manejo']}")
                st.info(
                    "El catálogo actual es de ejemplo: amplíalo con fuentes "
                    "fitosanitarias (ICA, Agrosavia, FAO)."
                )
        else:
            st.caption("Selecciona al menos un síntoma para ver coincidencias.")


# --------------------------- GEE ------------------------------------------
elif pagina == "🛰️ Satélite (GEE)":
    st.title("🛰️ Satélite — Google Earth Engine")
    st.markdown(
        """
        <div class="agro-card">
        GEE aporta <b>información espacial y ambiental</b> (elevación, NDVI,
        cobertura y lluvia). <b>No</b> analiza químicamente el suelo: eso viene
        del laboratorio.
        </div>
        """,
        unsafe_allow_html=True,
    )

    disp, msj = gee_utils.estado()
    if not disp:
        st.warning(msj)
        st.markdown(
            "Instala el paquete y autentícate una sola vez:"
        )
        st.code(
            "instalar_gee.bat\n"
            "earthengine authenticate",
            language="bat",
        )
        st.caption(
            "También necesitas un proyecto de Google Cloud con Earth Engine "
            "habilitado: https://code.earthengine.google.com/register"
        )

    dft = list_terrenos(USUARIO_ID)
    if dft.empty:
        st.info("Primero dibuja y guarda un terreno en el módulo **🗺️ Terreno y hectáreas**.")
    else:
        idx = st.selectbox(
            "Terreno a analizar", dft.index,
            format_func=lambda i: f"#{dft.loc[i,'id']} · {dft.loc[i,'nombre']} · "
                                  f"{dft.loc[i,'area_total_ha']:.2f} ha",
        )
        fila = dft.loc[idx]
        try:
            geojson = json.loads(fila["geojson"])
        except Exception:
            geojson = None
        coords = latlon_de_geojson(geojson) if geojson else []

        if not coords:
            st.error("El terreno guardado no tiene un polígono válido.")
        else:
            centro = [coords[0][0], coords[0][1]]
            st.caption(f"Polígono con {len(coords)} vértices · centro aproximado {centro[0]:.4f}, {centro[1]:.4f}")

            c1, c2, c3 = st.columns(3)
            proyecto = c1.text_input(
                "ID del proyecto Google Cloud",
                value=os.environ.get("AGROSMART_GEE_PROJECT", ""),
                placeholder="mi-proyecto-123456",
            )
            inicio = c2.date_input("Desde", date(date.today().year - 1, 1, 1))
            fin = c3.date_input("Hasta", date.today())

            if st.button("🛰️ Analizar con GEE", type="primary", use_container_width=True):
                with st.spinner("Consultando Earth Engine... (puede tardar unos segundos)"):
                    try:
                        res = gee_utils.analizar(
                            coords, proyecto or None,
                            inicio.isoformat(), fin.isoformat(),
                        )
                        st.session_state["gee_resultado"] = res
                    except Exception as e:
                        st.session_state["gee_resultado"] = None
                        st.error(
                            "No se pudo consultar Earth Engine. Verifica que ejecutaste "
                            "`earthengine authenticate` y que el proyecto es correcto."
                        )
                        st.code(str(e))

            res = st.session_state.get("gee_resultado")
            if res:
                st.subheader("Resultados")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Área", f"{res.get('area_ha', 0):,.2f} ha")
                c2.metric(
                    "Elevación media",
                    f"{res['elevacion_m']:.0f} m" if res.get("elevacion_m") is not None else "—",
                )
                c3.metric(
                    "NDVI medio",
                    f"{res['ndvi_medio']:.3f}" if res.get("ndvi_medio") is not None else "—",
                )
                c4.metric(
                    "Lluvia acumulada",
                    f"{res['precipitacion_mm']:.0f} mm" if res.get("precipitacion_mm") is not None else "—",
                )
                if res.get("ndvi_min") is not None:
                    st.caption(
                        f"NDVI mín: {res['ndvi_min']:.3f} · máx: {res['ndvi_max']:.3f} · "
                        f"imágenes Sentinel-2 usadas: {res.get('imagenes_s2', '—')}"
                    )

                if res.get("ndvi_tile"):
                    st.subheader("Mapa NDVI")
                    m = folium.Map(location=centro, zoom_start=15)
                    folium.TileLayer(
                        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                        attr="Esri World Imagery", name="Satélite",
                    ).add_to(m)
                    folium.TileLayer(
                        tiles=res["ndvi_tile"], attr="Google Earth Engine",
                        name="NDVI", opacity=0.65, overlay=True,
                    ).add_to(m)
                    folium.GeoJson(geojson, name="Terreno").add_to(m)
                    folium.LayerControl().add_to(m)
                    st_folium(m, height=450, width=None, key="mapa_gee")

                if res.get("cobertura"):
                    st.subheader("Cobertura del suelo (ESA WorldCover)")
                    dfc = pd.DataFrame(
                        list(res["cobertura"].items()),
                        columns=["Cobertura", "% del área"],
                    )
                    st.dataframe(dfc, hide_index=True, use_container_width=True)
                    st.bar_chart(dfc.set_index("Cobertura"))

                for k in ("elevacion_error", "ndvi_error", "cobertura_error", "precipitacion_error"):
                    if res.get(k):
                        with st.expander(f"Detalle ({k})"):
                            st.code(res[k])

            st.divider()
            st.subheader("Exportar a QGIS")
            st.caption(
                "Descarga el polígono en GeoJSON y ábrelo en QGIS (Arrastrar y soltar). "
                "También puedes exportar los análisis de suelo a CSV."
            )
            c1, c2 = st.columns(2)
            with c1:
                st.download_button(
                    "⬇️ Polígono (.geojson)",
                    data=json.dumps(geojson, ensure_ascii=False).encode("utf-8"),
                    file_name=f"terreno_{fila['id']}.geojson",
                    mime="application/geo+json",
                    use_container_width=True,
                )
            with c2:
                dfs = list_suelo(USUARIO_ID)
                if not dfs.empty:
                    st.download_button(
                        "⬇️ Análisis de suelo (.csv)",
                        data=dfs.to_csv(index=False).encode("utf-8"),
                        file_name="analisis_suelo.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )

            with st.expander("📘 Ayuda: autenticación y proyecto de GEE"):
                st.markdown(
                    """
                    1. Instala: `instalar_gee.bat`
                    2. Autentica: abre PowerShell y ejecuta `earthengine authenticate`
                       (se abrirá el navegador; inicia sesión con la cuenta de Google).
                    3. Regístrate en Earth Engine con el mismo correo:
                       https://code.earthengine.google.com/register
                    4. Crea un proyecto en Google Cloud y habilita la Earth Engine API.
                    5. Copia el **ID del proyecto** y pégalo arriba.

                    Si ya lo hiciste y sigue fallando, prueba:
                    `earthengine authenticate --force`
                    """
                )


# --------------------------- PANEL ADMIN ---------------------------------
elif pagina == "🛡️ Panel admin":
    if not ES_ADMIN:
        st.error("No tienes permisos de administrador.")
        st.stop()

    st.title("🛡️ Panel de administración")
    st.caption(
        "Solo el administrador ve esta sección. Cada consulta de un expediente "
        "queda registrada en la auditoría."
    )

    usuarios = auth.listar_usuarios()
    totales = {"suelos": 0, "terrenos": 0, "recomendaciones": 0, "cultivos": 0}
    for u in usuarios:
        c = contar_usuario(u["id"])
        for k in totales:
            totales[k] += c[k]

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Usuarios", len(usuarios))
    c2.metric("Activos", sum(1 for u in usuarios if u["activo"]))
    c3.metric("Análisis", totales["suelos"])
    c4.metric("Terrenos", totales["terrenos"])
    c5.metric("Recomendaciones", totales["recomendaciones"])
    c6.metric("Cultivos", totales["cultivos"])

    with st.expander("🛰️ Servicios de Neon"):
        for _nombre, (_ok, _detalle) in _estado_servicios_neon().items():
            st.markdown(("✅ " if _ok else "⚠️ ") + f"**{_nombre}**: {_detalle}")
        st.caption(
            "PostgreSQL, Functions, Auth y Realtime están activos en la rama "
            "production. AI Gateway requiere plan pago."
        )

    st.divider()
    st.subheader("Usuarios registrados")
    filas = []
    for u in usuarios:
        c = contar_usuario(u["id"])
        filas.append({
            "ID": u["id"], "Nombre": u["nombre"], "Correo": u["email"],
            "Rol": u["rol"], "Activo": "Sí" if u["activo"] else "No",
            "Suelo": c["suelos"], "Terrenos": c["terrenos"],
            "Recom.": c["recomendaciones"], "Cultivos": c["cultivos"],
            "Último acceso": u["ultimo_acceso"] or "—",
        })
    df_usuarios = pd.DataFrame(filas)
    st.dataframe(df_usuarios, hide_index=True, use_container_width=True)
    st.download_button(
        "⬇️ Descargar usuarios (CSV)",
        data=df_usuarios.to_csv(index=False).encode("utf-8"),
        file_name="usuarios_agrosmart.csv",
        mime="text/csv",
        use_container_width=True,
    )

    st.divider()
    st.subheader("Expediente de un usuario")
    opciones = {f"#{u['id']} · {u['nombre']} ({u['email']})": u["id"] for u in usuarios}
    if not opciones:
        st.info("Todavía no hay usuarios registrados.")
    else:
        sel_label = st.selectbox("Selecciona un usuario", list(opciones.keys()))
        sel_id = opciones[sel_label]
        u_sel = next(u for u in usuarios if u["id"] == sel_id)

        c1, c2 = st.columns(2)
        if c1.button("📂 Abrir expediente", use_container_width=True, type="primary"):
            auth.registrar_auditoria(USUARIO_ID, sel_id, "ver_expediente", sel_label)
            st.session_state["admin_expediente"] = sel_id
        if c2.button(
            "🚫 Desactivar cuenta" if u_sel["activo"] else "✅ Activar cuenta",
            use_container_width=True,
        ):
            auth.cambiar_activo(sel_id, not u_sel["activo"])
            auth.registrar_auditoria(
                USUARIO_ID, sel_id, "cambiar_activo",
                "activo" if not u_sel["activo"] else "inactivo",
            )
            st.rerun()

        exp_id = st.session_state.get("admin_expediente")
        if exp_id:
            u_exp = auth.obtener_usuario(exp_id)
            if not u_exp:
                st.warning("Ese usuario ya no existe.")
            else:
                st.markdown(f"### {u_exp['nombre']} · {u_exp['email']}")
                st.caption(
                    f"Rol: {u_exp['rol']} · Creado: {u_exp['creado']} · "
                    f"Último acceso: {u_exp['ultimo_acceso'] or '—'} · "
                    f"Estado: {'activo' if u_exp['activo'] else 'inactivo'}"
                )
                tabs = st.tabs([
                    "🧪 Suelo", "🗺️ Terrenos", "🌱 Recomendaciones",
                    "🌾 Cultivos", "⚠️ Alertas",
                ])
                with tabs[0]:
                    dfs = list_suelo(exp_id)
                    if dfs.empty:
                        st.info("Sin análisis de suelo.")
                    else:
                        st.dataframe(dfs, hide_index=True, use_container_width=True)
                        st.download_button(
                            "⬇️ Suelo (CSV)",
                            data=dfs.to_csv(index=False).encode("utf-8"),
                            file_name=f"suelo_usuario_{exp_id}.csv",
                            mime="text/csv",
                        )
                with tabs[1]:
                    dft = list_terrenos(exp_id)
                    if dft.empty:
                        st.info("Sin terrenos registrados.")
                    else:
                        st.dataframe(
                            dft[["id", "fecha", "nombre", "area_total_ha",
                                 "area_apta_ha", "notas"]],
                            hide_index=True, use_container_width=True,
                        )
                with tabs[2]:
                    dfr = list_recomendaciones(exp_id)
                    if dfr.empty:
                        st.info("Sin recomendaciones guardadas.")
                    else:
                        for _, row in dfr.iterrows():
                            st.markdown(f"**{row['fecha']}**")
                            try:
                                res = json.loads(row["resultados"])
                                st.write(
                                    " · ".join(
                                        f"{r.get('emoji','')} {r['nombre']} ({r['puntaje']}%)"
                                        for r in res
                                    )
                                )
                            except Exception:
                                st.write(row["resultados"])
                with tabs[3]:
                    dfc = list_cultivos(exp_id)
                    if dfc.empty:
                        st.info("Sin cultivos en seguimiento.")
                    else:
                        st.dataframe(
                            dfc[["id", "cultivo", "lote", "fecha_siembra",
                                 "estado", "notas", "actualizado"]],
                            hide_index=True, use_container_width=True,
                        )
                with tabs[4]:
                    dfs = list_suelo(exp_id)
                    if dfs.empty:
                        st.info("Sin datos para validar.")
                    else:
                        avisos = asistente.validar_suelo(dfs.iloc[0].to_dict())
                        if avisos:
                            for a in avisos:
                                st.warning("⚠️ " + a["mensaje"])
                        else:
                            st.success("Sin alertas en el último análisis.")

    with st.expander("🧾 Auditoría de accesos del administrador"):
        audit = auth.listar_auditoria(100)
        if audit:
            st.dataframe(pd.DataFrame(audit), hide_index=True, use_container_width=True)
        else:
            st.caption("Sin registros todavía.")


# --------------------------- HISTORIAL ------------------------------------
elif pagina == "📊 Mi historial":
    st.title("📊 Mi historial")
    st.caption("Todo lo que has registrado queda guardado en tu cuenta.")

    dfs = list_suelo(USUARIO_ID)
    dft = list_terrenos(USUARIO_ID)
    dfr = list_recomendaciones(USUARIO_ID)
    dfc = list_cultivos(USUARIO_ID)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Análisis de suelo", len(dfs))
    c2.metric("Terrenos", len(dft))
    c3.metric("Hectáreas registradas",
              f"{dft['area_total_ha'].sum():,.2f}" if not dft.empty else "0")
    c4.metric("Recomendaciones", len(dfr))

    tab_s, tab_t, tab_r, tab_c = st.tabs(
        ["🧪 Suelo", "🗺️ Terrenos", "🌱 Recomendaciones", "🌾 Cultivos"]
    )

    with tab_s:
        if dfs.empty:
            st.info("Aún no has registrado análisis de suelo.")
        else:
            st.dataframe(dfs, use_container_width=True, hide_index=True)
            if "ph" in dfs.columns and dfs["ph"].notna().any():
                st.subheader("Evolución del pH")
                serie = dfs.dropna(subset=["ph"]).sort_values("fecha")
                st.line_chart(serie.set_index("fecha")[["ph"]])
            st.download_button(
                "⬇️ Descargar análisis (CSV)",
                data=dfs.to_csv(index=False).encode("utf-8"),
                file_name="mi_historial_suelo.csv",
                mime="text/csv",
                use_container_width=True,
            )

    with tab_t:
        if dft.empty:
            st.info("Aún no has registrado terrenos.")
        else:
            st.dataframe(
                dft[["id", "fecha", "nombre", "area_total_ha", "area_apta_ha", "notas"]],
                use_container_width=True, hide_index=True,
            )
            st.download_button(
                "⬇️ Descargar terrenos (CSV)",
                data=dft.to_csv(index=False).encode("utf-8"),
                file_name="mi_historial_terrenos.csv",
                mime="text/csv",
                use_container_width=True,
            )

    with tab_r:
        if dfr.empty:
            st.info("Aún no has calculado recomendaciones.")
        else:
            for _, row in dfr.iterrows():
                st.markdown(f"**{row['fecha']}**")
                try:
                    res = json.loads(row["resultados"])
                    st.write(
                        " · ".join(
                            f"{r.get('emoji','')} {r['nombre']} ({r['puntaje']}%)"
                            for r in res
                        )
                    )
                except Exception:
                    st.write(row["resultados"])
            st.caption("Cada cálculo queda guardado en tu historial.")
            st.download_button(
                "⬇️ Descargar recomendaciones (CSV)",
                data=dfr.to_csv(index=False).encode("utf-8"),
                file_name="mi_historial_recomendaciones.csv",
                mime="text/csv",
                use_container_width=True,
            )

    with tab_c:
        if dfc.empty:
            st.info("Aún no tienes cultivos en seguimiento. Ve a 🌾 Mis cultivos.")
        else:
            st.dataframe(
                dfc[["id", "cultivo", "lote", "fecha_siembra", "estado",
                     "notas", "actualizado"]],
                use_container_width=True, hide_index=True,
            )
            st.download_button(
                "⬇️ Descargar cultivos (CSV)",
                data=dfc.to_csv(index=False).encode("utf-8"),
                file_name="mi_historial_cultivos.csv",
                mime="text/csv",
                use_container_width=True,
            )


# --------------------------- REPORTES -------------------------------------
elif pagina == "📄 Reportes":
    st.title("📄 Reportes")

    df = list_suelo(USUARIO_ID)
    dft = list_terrenos(USUARIO_ID)
    if df.empty and dft.empty:
        st.info("Registra al menos un análisis de suelo o un terreno para generar el reporte.")
    else:
        analisis = df.iloc[0].to_dict() if not df.empty else None
        terreno = dft.iloc[0].to_dict() if not dft.empty else None
        recomendaciones = st.session_state.ultima_recomendacion

        st.subheader("Vista previa")
        if analisis:
            st.markdown(f"**Análisis:** lote {analisis['lote']} · {analisis['fecha']}")
        if terreno:
            st.markdown(f"**Terreno:** {terreno['nombre']} · {terreno['area_apta_ha']:.2f} ha aptas")
        if recomendaciones:
            st.markdown("**Recomendaciones incluidas:** " +
                        ", ".join(f"{r['cultivo']['nombre']} ({r['puntaje']}%)" for r in recomendaciones[:3]))
        else:
            st.caption("Consejo: genera las recomendaciones en el módulo de cultivos para incluirlas.")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("📄 Generar PDF", type="primary", use_container_width=True):
                pdf_bytes = generar_pdf_reporte(analisis, terreno, recomendaciones)
                st.download_button(
                    "⬇️ Descargar PDF",
                    data=pdf_bytes,
                    file_name=f"reporte_agrosmart_{date.today().isoformat()}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
        with c2:
            if not df.empty:
                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "⬇️ Descargar análisis (CSV)",
                    data=csv,
                    file_name=f"analisis_suelo_{date.today().isoformat()}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

        st.divider()
        st.subheader("Todos los datos")
        if not df.empty:
            st.markdown("**Análisis de suelo**")
            st.dataframe(df, use_container_width=True, hide_index=True)
        if not dft.empty:
            st.markdown("**Terrenos**")
            st.dataframe(dft[["id", "fecha", "nombre", "area_total_ha", "area_apta_ha", "notas"]],
                         use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Asistente flotante
# ---------------------------------------------------------------------------
if pagina not in ("🤖 Asistente", "🛡️ Panel admin"):
    _ctx_bot = _contexto_asistente()
    _paso_bot = asistente.paso_siguiente(_ctx_bot["estado"])
    if _ctx_bot["avisos"]:
        _tip_bot = "⚠️ " + _ctx_bot["avisos"][0]["mensaje"]
        _alerta_bot = True
    else:
        _tip_bot = asistente.texto_paso(_paso_bot)
        _alerta_bot = False
    render_bot(_tip_bot, alerta=_alerta_bot, visible=bot_visible)
