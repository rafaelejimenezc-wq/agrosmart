"""
=============================================================================
 AgroSmart - Autenticacion de usuarios
=============================================================================
 Registro e inicio de sesion con correo y contrasena.
 - Contrasenas con hash scrypt + salt (nunca se guardan en texto plano).
 - Sesion persistente con token firmado (itsdangerous) en la URL.
 - Los datos de cada usuario se separan por `usuario_id`.
=============================================================================
"""

import os
import re
import hmac
import hashlib
import secrets
from datetime import date

from itsdangerous import URLSafeTimedSerializer

import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "datos")
SECRET_PATH = os.path.join(DATA_DIR, ".secret")

os.makedirs(DATA_DIR, exist_ok=True)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DIAS_SESION = 30


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------
def _get_secret():
    # 1) Variable de entorno (Render, Docker, etc.)
    env = os.environ.get("AGROSMART_SECRET", "").strip()
    if env:
        return env
    # 2) Secrets de Streamlit (Streamlit Community Cloud)
    try:
        import streamlit as st
        v = str(st.secrets.get("AGROSMART_SECRET", "")).strip()
        if v:
            return v
    except Exception:
        pass
    # 3) Archivo local
    if os.path.exists(SECRET_PATH):
        with open(SECRET_PATH, "r", encoding="utf-8") as f:
            s = f.read().strip()
            if s:
                return s
    s = secrets.token_urlsafe(48)
    with open(SECRET_PATH, "w", encoding="utf-8") as f:
        f.write(s)
    return s


_SECRET = _get_secret()
_serializer = URLSafeTimedSerializer(_SECRET, salt="agrosmart-sesion")


def get_conn():
    return db.get_conn()


def _hash(password: str, salt: bytes) -> str:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32
    ).hex()


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------
def init_auth_db():
    with get_conn() as conn:
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS usuarios (
                id {db.PK},
                nombre TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                creado TEXT NOT NULL
            )"""
        )
        # Migraciones para versiones anteriores.
        cols = db.columnas(conn, "usuarios")
        migraciones = {
            "rol": "TEXT NOT NULL DEFAULT 'usuario'",
            "activo": "INTEGER NOT NULL DEFAULT 1",
            "ultimo_acceso": "TEXT",
        }
        for col, ddl in migraciones.items():
            if col not in cols:
                conn.execute(f"ALTER TABLE usuarios ADD COLUMN {col} {ddl}")

        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS auditoria_admin (
                id {db.PK},
                admin_id INTEGER,
                usuario_id INTEGER,
                accion TEXT,
                detalle TEXT,
                fecha TEXT
            )"""
        )
        conn.commit()


def crear_usuario(nombre: str, email: str, password: str, rol: str = "usuario"):
    nombre = (nombre or "").strip()
    email = (email or "").strip().lower()

    if len(nombre) < 2:
        raise ValueError("Escribe tu nombre (mínimo 2 caracteres).")
    if not _EMAIL_RE.match(email):
        raise ValueError("El correo no tiene un formato válido.")
    if len(password) < 6:
        raise ValueError("La contraseña debe tener al menos 6 caracteres.")

    salt = secrets.token_bytes(16)
    with get_conn() as conn:
        try:
            cur = conn.execute(
                """INSERT INTO usuarios
                   (nombre, email, password_hash, salt, creado, rol, activo)
                   VALUES (?,?,?,?,?,?,1)""",
                (nombre, email, _hash(password, salt), salt.hex(),
                 date.today().isoformat(), rol),
            )
            conn.commit()
            return cur.lastrowid
        except db.IntegrityError:
            raise ValueError("Ese correo ya está registrado. Inicia sesión.")


def crear_admin(nombre: str, email: str, password: str):
    return crear_usuario(nombre, email, password, rol="admin")


def existe_admin() -> bool:
    with get_conn() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM usuarios WHERE rol='admin'"
        ).fetchone()["n"]
    return n > 0


def autenticar(email: str, password: str):
    email = (email or "").strip().lower()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM usuarios WHERE email=?", (email,)
        ).fetchone()
    if not row:
        return None
    esperado = row["password_hash"]
    calculado = _hash(password, bytes.fromhex(row["salt"]))
    if not hmac.compare_digest(esperado, calculado):
        return None
    if not row["activo"]:
        return None
    return {
        "id": row["id"],
        "nombre": row["nombre"],
        "email": row["email"],
        "creado": row["creado"],
        "rol": row["rol"],
        "activo": row["activo"],
        "ultimo_acceso": row["ultimo_acceso"],
    }


def obtener_usuario(uid: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "nombre": row["nombre"],
        "email": row["email"],
        "creado": row["creado"],
        "rol": row["rol"],
        "activo": row["activo"],
        "ultimo_acceso": row["ultimo_acceso"],
    }


def actualizar_ultimo_acceso(uid: int):
    from datetime import datetime
    with get_conn() as conn:
        conn.execute(
            "UPDATE usuarios SET ultimo_acceso=? WHERE id=?",
            (datetime.now().isoformat(timespec="seconds"), uid),
        )
        conn.commit()


def listar_usuarios():
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, nombre, email, rol, activo, creado, ultimo_acceso
               FROM usuarios ORDER BY id"""
        ).fetchall()
    return [dict(r) for r in rows]


def cambiar_activo(uid: int, activo: bool):
    with get_conn() as conn:
        conn.execute(
            "UPDATE usuarios SET activo=? WHERE id=?",
            (1 if activo else 0, uid),
        )
        conn.commit()


def registrar_auditoria(admin_id: int, usuario_id: int, accion: str, detalle: str = ""):
    from datetime import datetime
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO auditoria_admin (admin_id, usuario_id, accion, detalle, fecha)
               VALUES (?,?,?,?,?)""",
            (admin_id, usuario_id, accion, detalle,
             datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()


def listar_auditoria(limite: int = 200):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT a.*, u.nombre AS usuario_nombre, adm.nombre AS admin_nombre
               FROM auditoria_admin a
               LEFT JOIN usuarios u ON u.id = a.usuario_id
               LEFT JOIN usuarios adm ON adm.id = a.admin_id
               ORDER BY a.id DESC LIMIT ?""",
            (limite,),
        ).fetchall()
    return [dict(r) for r in rows]


def cambiar_password(uid: int, actual: str, nueva: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone()
    if not row:
        raise ValueError("Usuario no encontrado.")
    calculado = _hash(actual, bytes.fromhex(row["salt"]))
    if not hmac.compare_digest(row["password_hash"], calculado):
        raise ValueError("La contraseña actual no es correcta.")
    if len(nueva) < 6:
        raise ValueError("La nueva contraseña debe tener al menos 6 caracteres.")
    salt = secrets.token_bytes(16)
    with get_conn() as conn:
        conn.execute(
            "UPDATE usuarios SET password_hash=?, salt=? WHERE id=?",
            (_hash(nueva, salt), salt.hex(), uid),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Sesion persistente
# ---------------------------------------------------------------------------
def crear_token(uid: int) -> str:
    return _serializer.dumps({"uid": uid})


def verificar_token(token: str):
    try:
        data = _serializer.loads(token, max_age=_DIAS_SESION * 24 * 3600)
        return int(data.get("uid"))
    except Exception:
        return None
