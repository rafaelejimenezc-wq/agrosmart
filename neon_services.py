"""
=============================================================================
 AgroSmart - Estado de los servicios de Neon
=============================================================================
 Comprueba en vivo Postgres, Functions, Auth (JWKS), Realtime y AI Gateway
 usando las variables que `neon deploy` escribe en .env.local.
=============================================================================
"""

import os

import requests

import db  # carga .env.local / .env

BASE = os.path.dirname(os.path.abspath(__file__))


def estado_postgres():
    try:
        with db.get_conn() as conn:
            row = conn.execute("SELECT version() AS v").fetchone()
        version = row["v"] if row else "?"
        return True, version.split(",")[0]
    except Exception as e:
        return False, str(e)


def estado_functions():
    url = os.environ.get("NEON_FUNCTION_HELLO_BASE_URL", "").strip()
    if not url:
        return False, "sin NEON_FUNCTION_HELLO_BASE_URL"
    try:
        r = requests.get(url, timeout=10)
        return r.ok, f"HTTP {r.status_code}: {r.text[:80]}"
    except Exception as e:
        return False, str(e)


def estado_auth():
    url = os.environ.get("NEON_AUTH_JWKS_URL", "").strip()
    if not url:
        return False, "sin NEON_AUTH_JWKS_URL"
    try:
        r = requests.get(url, timeout=10)
        claves = r.json().get("keys", [])
        return r.ok and bool(claves), f"HTTP {r.status_code}, {len(claves)} clave(s) JWKS"
    except Exception as e:
        return False, str(e)


def estado_realtime():
    url = os.environ.get("NEON_REALTIME_URL", "").strip()
    if not url:
        return False, "sin NEON_REALTIME_URL"
    return True, f"configurado: {url} (probado con `neon realtime subscribe`)"


def estado_ai_gateway():
    url = os.environ.get("NEON_AI_GATEWAY_BASE_URL", "").strip()
    if not url:
        return False, "no disponible en el plan Free"
    return True, url
