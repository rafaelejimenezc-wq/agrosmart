"""
=============================================================================
 AgroSmart - Asistente inteligente
=============================================================================
 Dos modos:
   1) REGLAS (siempre disponible, gratis): guia paso a paso, responde dudas
      frecuentes y detecta datos erroneos.
   2) LLM (opcional): si configuras AGROSMART_LLM_URL, AGROSMART_LLM_KEY y
      AGROSMART_LLM_MODEL, el asistente usa un modelo de lenguaje real.
      Funciona con cualquier API compatible con OpenAI (OpenAI, Groq,
      OpenRouter, etc.).
=============================================================================
"""

import os
import requests

# ---------------------------------------------------------------------------
# Configuracion del LLM (opcional)
# ---------------------------------------------------------------------------
def _cfg(nombre: str, default: str = "") -> str:
    """Lee de variable de entorno o de .streamlit/secrets.toml."""
    v = os.environ.get(nombre, "").strip()
    if v:
        return v
    try:
        import streamlit as st
        return str(st.secrets.get(nombre, default)).strip()
    except Exception:
        return default


LLM_URL = _cfg("AGROSMART_LLM_URL")
LLM_KEY = _cfg("AGROSMART_LLM_KEY")
LLM_MODEL = _cfg("AGROSMART_LLM_MODEL", "gpt-4o-mini") or "gpt-4o-mini"

PASOS = [
    ("Registra tu análisis de suelo", "Ve a 🧪 Análisis de suelo y digita los resultados del laboratorio."),
    ("Dibuja y guarda tu terreno", "Ve a 🗺️ Terreno y hectáreas, dibuja el lote y guarda el área."),
    ("Calcula tus cultivos", "Ve a 🌱 Recomendación de cultivos y pulsa Calcular."),
    ("Configura el riego", "Ve a 💧 Riego IoT y ajusta los umbrales (o conecta el ESP32)."),
    ("Revisa plagas", "Ve a 🐛 Plagas para una orientación preliminar."),
    ("Genera tu reporte", "Ve a 📄 Reportes y descarga el PDF."),
]

SYSTEM_PROMPT = """Eres el asistente de AgroSmart, una app de apoyo a la decision
agricola para un proyecto universitario de Ingenieria Ambiental en Colombia.
Responde en espanol, claro y breve (maximo 6 frases). Guia al usuario paso a paso.
Reglas:
- El dato quimico del suelo SIEMPRE viene del laboratorio; una foto no lo reemplaza.
- No inventes valores ni porcentajes de compatibilidad.
- Si falta un dato, dilo y explica como obtenerlo.
- Recomienda consultar a un profesional agricola para decisiones criticas.
- Usa el contexto del usuario que se te entrega."""


def llm_configurado() -> bool:
    return bool(LLM_URL and LLM_KEY)


def _llamar_llm(pregunta: str, contexto: str, historial=None) -> str:
    mensajes = [{"role": "system", "content": SYSTEM_PROMPT}]
    if historial:
        for m in historial[-6:]:
            mensajes.append({"role": m["role"], "content": m["content"]})
    mensajes.append({
        "role": "user",
        "content": f"Contexto del usuario:\n{contexto}\n\nPregunta: {pregunta}",
    })
    r = requests.post(
        LLM_URL,
        headers={"Authorization": f"Bearer {LLM_KEY}", "Content-Type": "application/json"},
        json={
            "model": LLM_MODEL,
            "messages": mensajes,
            "temperature": 0.4,
            "max_tokens": 700,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


# ---------------------------------------------------------------------------
# Validacion de datos
# ---------------------------------------------------------------------------
def validar_suelo(d: dict):
    """Devuelve una lista de {'nivel': 'error'|'aviso', 'mensaje': str}."""
    avisos = []

    ph = d.get("ph")
    if ph is not None:
        if ph < 4.5:
            avisos.append({"nivel": "aviso", "mensaje": f"pH {ph}: muy ácido. Verifica el laboratorio y considera encalar."})
        elif ph > 8.5:
            avisos.append({"nivel": "aviso", "mensaje": f"pH {ph}: muy alcalino. Verifica el dato y considera yeso/azufre."})

    mo = d.get("materia_organica")
    if mo is not None and mo > 10:
        avisos.append({"nivel": "aviso", "mensaje": f"Materia orgánica {mo} %: valor alto; confirma las unidades con el laboratorio."})

    ce = d.get("conductividad")
    if ce is not None and ce > 4:
        avisos.append({"nivel": "aviso", "mensaje": f"Conductividad {ce} dS/m: posible salinidad; revisa el riego y el drenaje."})

    for nombre, clave in (("Nitrógeno", "nitrogeno"), ("Fósforo", "fosforo"), ("Potasio", "potasio")):
        v = d.get(clave)
        if v is not None and v <= 0:
            avisos.append({"nivel": "aviso", "mensaje": f"{nombre} en 0: ¿falta el dato del laboratorio o es un valor real?"})

    t = d.get("temperatura")
    if t is not None and (t < 0 or t > 40):
        avisos.append({"nivel": "aviso", "mensaje": f"Temperatura {t} °C fuera de lo común; revisa el dato."})

    return avisos


def validar_terreno(area_total, area_apta):
    avisos = []
    if area_total is None or area_total <= 0:
        avisos.append({"nivel": "error", "mensaje": "El área total debe ser mayor que 0. Vuelve a dibujar el polígono."})
    elif area_total > 10000:
        avisos.append({"nivel": "aviso", "mensaje": f"Área de {area_total:,.0f} ha: es muy grande; verifica las coordenadas."})
    if area_apta is not None and area_total is not None and area_apta > area_total:
        avisos.append({"nivel": "error", "mensaje": "El área apta no puede ser mayor que el área total."})
    return avisos


# ---------------------------------------------------------------------------
# Guia paso a paso
# ---------------------------------------------------------------------------
def paso_siguiente(estado: dict):
    """estado = {'suelos': int, 'terrenos': int, 'recomendaciones': int}."""
    if estado.get("suelos", 0) == 0:
        return 0
    if estado.get("terrenos", 0) == 0:
        return 1
    if estado.get("recomendaciones", 0) == 0:
        return 2
    return 5


def texto_paso(indice: int) -> str:
    if 0 <= indice < len(PASOS):
        titulo, detalle = PASOS[indice]
        return f"{titulo}: {detalle}"
    return "¡Todo listo! Genera tu reporte y compártelo."


# ---------------------------------------------------------------------------
# Respuestas por reglas
# ---------------------------------------------------------------------------
def _reglas(pregunta: str, contexto: dict) -> str:
    q = (pregunta or "").lower()
    nombre = contexto.get("nombre", "")
    estado = contexto.get("estado", {})
    avisos = contexto.get("avisos", [])
    paso = paso_siguiente(estado)

    def tiene(*palabras):
        return any(p in q for p in palabras)

    if tiene("hola", "buenas", "buenos días", "buenas tardes"):
        return (
            f"¡Hola, {nombre}! Soy tu asistente de AgroSmart. "
            f"Tu siguiente paso es: {texto_paso(paso)} "
            "Pregúntame lo que quieras o escribe 'revisa mis datos'."
        )

    if tiene("revisa", "revisar", "error", "erróneo", "erroneo", "validar", "datos"):
        if avisos:
            lista = " ".join(f"- {a['mensaje']}" for a in avisos[:4])
            return f"Encontré esto en tus datos:\n{lista}\nCorrige lo marcado antes de continuar."
        return "Revisé tus datos y no veo valores fuera de rango. ¡Vas bien!"

    if tiene("paso", "primero", "empezar", "comenzar", "guía", "guia", "siguiente"):
        return f"Tu siguiente paso es: {texto_paso(paso)}"

    if tiene("suelo", "laboratorio", "análisis", "analisis", "ph", "nutriente"):
        return (
            "El análisis de suelo se hace en laboratorio: pH, materia orgánica, "
            "N-P-K, conductividad y textura. La foto NO reemplaza ese análisis. "
            "Digita los resultados en 🧪 Análisis de suelo."
        )

    if tiene("terreno", "hectárea", "hectarea", "área", "area", "mapa", "lote", "polígono", "poligono"):
        return (
            "En 🗺️ Terreno y hectáreas dibuja el lote con la herramienta de polígono. "
            "La app calcula el área y tú indicas qué porcentaje no es cultivable "
            "(agua, pendiente, infraestructura)."
        )

    if tiene("cultivo", "recomienda", "recomendación", "recomendacion", "sembrar", "qué siembro", "que siembro"):
        return (
            "Ve a 🌱 Recomendación de cultivos: compara pH, textura, temperatura, "
            "agua y nutrientes con 38 cultivos. El porcentaje sale de pesos "
            "explícitos, no de una caja negra."
        )

    if tiene("riego", "bomba", "esp32", "sensor", "humedad"):
        return (
            "En 💧 Riego IoT puedes simular la histéresis o conectar un ESP32 real. "
            "Configura el umbral mínimo (enciende) y el de apagado (corta). "
            "El firmware está en firmware/esp32_riego.ino."
        )

    if tiene("plaga", "enfermedad", "hongo", "insecto", "foto", "hoja"):
        return (
            "En 🐛 Plagas puedes subir una foto (IA PlantVillage) o elegir síntomas. "
            "Es una orientación preliminar: confirma con inspección de campo."
        )

    if tiene("satélite", "satelite", "gee", "ndvi", "earth", "imagen"):
        return (
            "En 🛰️ Satélite (GEE) calculas NDVI, elevación, cobertura y lluvia. "
            "Necesitas autenticarte una vez con `earthengine authenticate`."
        )

    if tiene("reporte", "pdf", "documento", "descargar"):
        return (
            "En 📄 Reportes generas el PDF con suelo, terreno y recomendaciones, "
            "y puedes exportar CSV/GeoJSON para QGIS."
        )

    if tiene("cuenta", "usuario", "contraseña", "contrasena", "sesión", "sesion"):
        return (
            "Tu cuenta guarda tus análisis y terrenos por separado. "
            "Puedes cerrar sesión desde la barra lateral; tus datos quedan guardados."
        )

    if tiene("gracias", "listo", "ok"):
        return "¡Con gusto! Sigue con el paso que te indiqué y avísame si algo falla."

    return (
        f"Soy tu asistente de AgroSmart. Puedo explicarte el análisis de suelo, "
        f"el mapa, los cultivos, el riego, las plagas o los reportes. "
        f"Ahora mismo, tu siguiente paso es: {texto_paso(paso)}"
    )


# ---------------------------------------------------------------------------
# Funcion principal
# ---------------------------------------------------------------------------
def responder(pregunta: str, contexto: dict, historial=None) -> str:
    if llm_configurado():
        texto_ctx = (
            f"Nombre: {contexto.get('nombre')}. "
            f"Análisis de suelo: {contexto.get('estado', {}).get('suelos', 0)}. "
            f"Terrenos: {contexto.get('estado', {}).get('terrenos', 0)}. "
            f"Recomendaciones: {contexto.get('estado', {}).get('recomendaciones', 0)}. "
            f"Paso actual: {texto_paso(paso_siguiente(contexto.get('estado', {})))}. "
            f"Avisos: {'; '.join(a['mensaje'] for a in contexto.get('avisos', [])) or 'ninguno'}."
        )
        try:
            return _llamar_llm(pregunta, texto_ctx, historial)
        except Exception as e:
            base = _reglas(pregunta, contexto)
            return f"{base}\n\n_(No pude conectar con el modelo de lenguaje: {e})_"
    return _reglas(pregunta, contexto)
