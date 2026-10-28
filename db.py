"""
=============================================================================
 AgroSmart - Capa de base de datos
=============================================================================
 Usa PostgreSQL (Neon) si existe DATABASE_URL; si no, SQLite local.
 Esto permite desarrollar sin internet y desplegar con Neon.
=============================================================================
"""

import os
import re
import sqlite3
from pathlib import Path
from urllib.parse import quote, urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env.local")
load_dotenv(BASE_DIR / ".env")


def _cfg(nombre, default=""):
    v = os.environ.get(nombre, "").strip()
    if v:
        return v
    try:
        import streamlit as st
        return str(st.secrets.get(nombre, default)).strip()
    except Exception:
        return default


def _url_valida(u: str) -> bool:
    try:
        p = urlparse(u)
        h = p.hostname or ""
        if not h or ".." in h or h.startswith(".") or h.endswith("."):
            return False
        return all(0 < len(part) <= 63 for part in h.split("."))
    except Exception:
        return False


def _url_desde_pg():
    host = _cfg("PGHOST")
    dbname = _cfg("PGDATABASE")
    user = _cfg("PGUSER")
    password = _cfg("PGPASSWORD")
    sslmode = _cfg("PGSSLMODE", "require") or "require"
    if host and dbname and user and password:
        return (
            f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}"
            f"@{host}/{quote(dbname, safe='')}?sslmode={quote(sslmode, safe='')}"
        )
    return ""


DATABASE_URL = _cfg("DATABASE_URL")
# Limpiar saltos de línea, espacios y comillas que se cuelan al pegar el secreto.
DATABASE_URL = DATABASE_URL.strip().strip('"').strip("'")
DATABASE_URL = "".join(DATABASE_URL.split())

# Si la URL no es válida, reconstruirla con las variables PG* (más robusto).
if not DATABASE_URL or not _url_valida(DATABASE_URL):
    _pg = _url_desde_pg()
    if _pg:
        DATABASE_URL = _pg

FORCE_SQLITE = os.environ.get("AGROSMART_DB", "").strip().lower() == "sqlite"
USE_POSTGRES = (not FORCE_SQLITE) and DATABASE_URL.startswith(("postgres://", "postgresql://"))

DB_PATH = str(BASE_DIR / "datos" / "agrosmart.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

if USE_POSTGRES:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.errors import UniqueViolation
else:
    psycopg = None

# Clave primaria segun el motor
PK = "SERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"


class IntegrityError(Exception):
    """Error de unicidad comun a SQLite y PostgreSQL."""


class Result:
    def __init__(self, cur, lastrowid=None):
        self._cur = cur
        self._lastrowid = lastrowid

    @property
    def lastrowid(self):
        return self._lastrowid

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def __iter__(self):
        return iter(self._cur)


class Conn:
    """Envoltorio minimo para usar la misma API con SQLite y PostgreSQL."""

    def __init__(self):
        self.is_pg = USE_POSTGRES
        if self.is_pg:
            self.raw = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        else:
            self.raw = sqlite3.connect(DB_PATH, check_same_thread=False)
            self.raw.row_factory = sqlite3.Row

    def execute(self, sql, params=()):
        if self.is_pg:
            # Escapar % literales antes de introducir placeholders %s.
            sql = sql.replace("%", "%%")
            if isinstance(params, dict):
                sql = re.sub(r":([a-zA-Z_][a-zA-Z0-9_]*)", r"%(\1)s", sql)
                ph_params = params
            else:
                sql = sql.replace("?", "%s")
                ph_params = params

            es_insert = sql.lstrip().upper().startswith("INSERT")
            if es_insert and "RETURNING" not in sql.upper():
                sql = sql.rstrip().rstrip(";") + " RETURNING id"

            try:
                cur = self.raw.cursor()
                cur.execute(sql, ph_params)
            except UniqueViolation as e:
                self.raw.rollback()
                raise IntegrityError(str(e))

            lastrowid = None
            if es_insert:
                row = cur.fetchone()
                if row:
                    lastrowid = row["id"] if isinstance(row, dict) else row[0]
            return Result(cur, lastrowid)

        try:
            cur = self.raw.execute(sql, params)
        except sqlite3.IntegrityError as e:
            raise IntegrityError(str(e))
        return Result(cur, cur.lastrowid)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.raw.commit()
        else:
            self.raw.rollback()
        self.raw.close()
        return False


def get_conn():
    return Conn()


def columnas(conn, tabla):
    """Nombres de columnas de una tabla (SQLite o PostgreSQL)."""
    if USE_POSTGRES:
        rows = conn.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_name=? AND table_schema='public'""",
            (tabla,),
        ).fetchall()
        return [r["column_name"] for r in rows]
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({tabla})")]
