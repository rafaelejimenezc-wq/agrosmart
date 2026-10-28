"""
=============================================================================
 AgroSmart - Servidor IoT (Fase 2)
=============================================================================
 Recibe las lecturas del ESP32, guarda el historial y decide si la bomba
 debe encenderse (con histeresis). Tambien expone la configuracion y el
 estado para que la app de Streamlit lo consulte.

 Ejecutar:
     "%USERPROFILE%\\agrosmart-venv\\Scripts\\uvicorn.exe" iot_server:app --host 0.0.0.0 --port 8000

 Documentacion interactiva:  http://localhost:8000/docs
=============================================================================
"""

import os
import sqlite3
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "datos")
DB_PATH = os.path.join(DATA_DIR, "iot.db")
os.makedirs(DATA_DIR, exist_ok=True)

app = FastAPI(
    title="AgroSmart IoT",
    description="API de riego: lecturas del ESP32 y control de la bomba.",
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS config (
                device_id TEXT PRIMARY KEY,
                umbral_min REAL DEFAULT 35,
                umbral_max REAL DEFAULT 45,
                modo TEXT DEFAULT 'auto',
                manual_riego INTEGER DEFAULT 0
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS lecturas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                ts TEXT,
                humedad REAL,
                temperatura REAL,
                riego INTEGER
            )"""
        )
        conn.commit()


init_db()


def obtener_config(device_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM config WHERE device_id=?", (device_id,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO config (device_id) VALUES (?)", (device_id,)
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM config WHERE device_id=?", (device_id,)
            ).fetchone()
        return dict(row)


def ultima_lectura(device_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM lecturas WHERE device_id=? ORDER BY id DESC LIMIT 1",
            (device_id,),
        ).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------
class LecturaIn(BaseModel):
    device_id: str = Field(default="esp32-01")
    humedad: float = Field(ge=0, le=100, description="Humedad del suelo en %")
    temperatura: Optional[float] = Field(default=None, description="Temperatura en C")


class ConfigIn(BaseModel):
    umbral_min: float = Field(ge=0, le=100)
    umbral_max: float = Field(ge=0, le=100)


class RiegoIn(BaseModel):
    encender: bool


# ---------------------------------------------------------------------------
# Logica de riego con histeresis
# ---------------------------------------------------------------------------
def decidir_riego(humedad: float, cfg: dict, estado_previo: Optional[int]) -> bool:
    if cfg["modo"] == "manual":
        return bool(cfg["manual_riego"])

    if estado_previo is None:
        return humedad < cfg["umbral_min"]
    if estado_previo == 1:
        # Sigue regando hasta alcanzar el umbral de apagado
        return humedad < cfg["umbral_max"]
    # Estaba apagado: solo enciende por debajo del minimo
    return humedad < cfg["umbral_min"]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/")
def raiz():
    return {"servicio": "AgroSmart IoT", "estado": "ok", "hora": datetime.now().isoformat()}


@app.post("/api/lectura")
def recibir_lectura(lectura: LecturaIn):
    """El ESP32 envia aqui su lectura y recibe la orden de riego."""
    cfg = obtener_config(lectura.device_id)
    prev = ultima_lectura(lectura.device_id)
    estado_previo = prev["riego"] if prev else None
    riego = decidir_riego(lectura.humedad, cfg, estado_previo)

    with get_conn() as conn:
        conn.execute(
            """INSERT INTO lecturas (device_id, ts, humedad, temperatura, riego)
               VALUES (?,?,?,?,?)""",
            (
                lectura.device_id,
                datetime.now().isoformat(timespec="seconds"),
                lectura.humedad,
                lectura.temperatura,
                1 if riego else 0,
            ),
        )
        conn.commit()

    return {
        "riego": riego,
        "umbral_min": cfg["umbral_min"],
        "umbral_max": cfg["umbral_max"],
        "modo": cfg["modo"],
        "recibido": datetime.now().isoformat(timespec="seconds"),
    }


@app.get("/api/estado/{device_id}")
def estado(device_id: str):
    cfg = obtener_config(device_id)
    prev = ultima_lectura(device_id)
    return {
        "device_id": device_id,
        "config": cfg,
        "ultima": prev,
        "riego_actual": bool(prev["riego"]) if prev else False,
    }


@app.get("/api/lecturas/{device_id}")
def lecturas(device_id: str, limite: int = 100):
    limite = max(1, min(limite, 2000))
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM lecturas WHERE device_id=? ORDER BY id DESC LIMIT ?",
            (device_id, limite),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


@app.get("/api/config/{device_id}")
def leer_config(device_id: str):
    return obtener_config(device_id)


@app.post("/api/config/{device_id}")
def guardar_config(device_id: str, cfg: ConfigIn):
    if cfg.umbral_max <= cfg.umbral_min:
        raise HTTPException(status_code=400, detail="umbral_max debe ser mayor que umbral_min")
    obtener_config(device_id)
    with get_conn() as conn:
        conn.execute(
            "UPDATE config SET umbral_min=?, umbral_max=? WHERE device_id=?",
            (cfg.umbral_min, cfg.umbral_max, device_id),
        )
        conn.commit()
    return obtener_config(device_id)


@app.post("/api/riego/{device_id}")
def control_manual(device_id: str, orden: RiegoIn):
    """Fuerza manualmente la bomba (modo manual)."""
    obtener_config(device_id)
    with get_conn() as conn:
        conn.execute(
            "UPDATE config SET modo='manual', manual_riego=? WHERE device_id=?",
            (1 if orden.encender else 0, device_id),
        )
        conn.commit()
    return obtener_config(device_id)


@app.post("/api/auto/{device_id}")
def volver_auto(device_id: str):
    """Devuelve el control a modo automatico (histeresis)."""
    obtener_config(device_id)
    with get_conn() as conn:
        conn.execute(
            "UPDATE config SET modo='auto', manual_riego=0 WHERE device_id=?",
            (device_id,),
        )
        conn.commit()
    return obtener_config(device_id)
