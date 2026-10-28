"""
=============================================================================
 AgroSmart - Crear una cuenta de administrador
=============================================================================
 Uso interactivo:
     crear_admin.bat
 o:
     python crear_admin.py

 Uso directo:
     python crear_admin.py --nombre "Ana" --email ana@correo.com --password "Clave123"
=============================================================================
"""

import argparse
import getpass

import auth


def main():
    parser = argparse.ArgumentParser(description="Crea una cuenta de administrador de AgroSmart.")
    parser.add_argument("--nombre")
    parser.add_argument("--email")
    parser.add_argument("--password")
    args = parser.parse_args()

    auth.init_auth_db()

    nombre = args.nombre or input("Nombre del administrador: ").strip()
    email = args.email or input("Correo del administrador: ").strip()
    password = args.password or getpass.getpass("Contraseña (mínimo 6): ")

    if not password:
        password = getpass.getpass("Repite la contraseña: ")

    try:
        uid = auth.crear_admin(nombre, email, password)
        print(f"\n✅ Administrador creado correctamente (id {uid}).")
        print(f"   Correo: {email.lower()}")
        print("   Cambia la contraseña al entrar, desde la barra lateral.")
    except ValueError as e:
        print(f"\n❌ {e}")


if __name__ == "__main__":
    main()
