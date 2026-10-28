# 🎓 AgroSmart — Guía para la presentación

> 🌐 **App en línea:** https://agrosmart-h6mj2vpjj6acmwwjrrthjf.streamlit.app/

## 1. Antes de salir de casa

- Lleva el **computador cargado** y el cargador.
- Prueba **`iniciar_demo.bat`** (funciona **sin internet**).
- Lleva también **`AgroSmart_listo.zip`** y unas **capturas** por si falla el proyector.
- Opcional: activa un **hotspot** desde el celular para usar la versión Neon.

## 2. Cómo entrar

**Opción recomendada para el aula (sin internet):**

1. Doble clic en **`iniciar_demo.bat`**.
2. Abre **http://localhost:8501** en el navegador.
3. Inicia sesión con:

| Rol | Correo | Contraseña |
|---|---|---|
| **Administrador** | `admin@agrosmart.local` | (ver `CREDENCIALES.txt`) |
| **Usuario demo** | `maria@demo.local` | (ver `CREDENCIALES.txt`) |

**Opción con Neon (requiere internet):** `iniciar.bat`.

> Cambia la contraseña del administrador antes de la entrega:
> barra lateral → **🔑 Cambiar contraseña**.

## 3. Guion de demo (6–8 minutos)

1. **Entra como administrador** y muestra el **🛡️ Panel admin**:
   - usuarios registrados, activos, análisis, terrenos, recomendaciones y cultivos;
   - tabla con los datos de cada usuario;
   - **📂 Abrir expediente** de *María Productora*: suelo, terrenos, recomendaciones, cultivos y alertas;
   - **🧾 Auditoría**: queda registro de que el admin consultó el expediente.
2. **Cierra sesión** y entra como **María**.
3. **🏠 Inicio**: ruta paso a paso y **bot flotante** que dice el siguiente paso.
4. **🧪 Análisis de suelo**: muestra pH, materia orgánica, N-P-K, textura.
5. **🗺️ Terreno y hectáreas**: dibuja un polígono en el mapa y muestra el área.
6. **🌱 Recomendación de cultivos**: calcula y explica el **desglose por criterio** (no es una caja negra).
7. **🌾 Mis cultivos**: agrega un cultivo y actualiza su estado (seguimiento).
8. **📚 Catálogo**: abre la ficha de un cultivo y sus **plagas asociadas**.
9. **🐛 Plagas**: sube una foto (IA PlantVillage) o usa el modo por síntomas.
10. **💧 Riego IoT**: muestra el simulador (y menciona el ESP32 real).
11. **📄 Reportes**: genera el **PDF**.
12. Vuelve al **admin** y muestra la **auditoría**.

## 4. Qué decir sobre seguridad y privacidad

- **Cada usuario solo ve sus propios datos**: todas las consultas filtran por `usuario_id`.
- El **panel admin** solo aparece para cuentas con rol `admin`; un usuario normal no lo ve.
- El admin **no puede ver las contraseñas**: se guardan con **scrypt + salt**.
- La sesión usa un **token firmado**; cambiar el ID en la URL no da acceso a otro usuario.
- Cada consulta del admin a un expediente queda en la **auditoría**.
- **Limitación**: el token de sesión viaja en la URL; no compartas el enlace de tu sesión.

## 5. Arquitectura (para explicar)

```
Streamlit (Python)  ──>  Neon Postgres (datos y usuarios)
        │
        ├── IA de plagas (MobileNetV2 / PlantVillage)
        ├── Google Earth Engine (NDVI, elevación, lluvia)
        ├── Riego IoT (ESP32 + sensor de humedad)
        └── Reportes PDF / exportación a QGIS
```

- `db.py` usa **Neon** si existe `DATABASE_URL`; si no, **SQLite local**.
- Servicios Neon activos: **Postgres, Auth (JWKS), Functions y Realtime**.
- **AI Gateway** requiere plan pago (se omitió).

## 6. Si falla el internet o el proyector

- Usa **`iniciar_demo.bat`** (SQLite local, no depende de internet).
- Si falla el proyector, muestra las **capturas** y el **PDF** de ejemplo.
- El **ZIP** contiene todo el código y los datos de ejemplo.

## 7. Después de la presentación: GitHub + publicación

1. Crea un repositorio nuevo en GitHub.
2. Sube el proyecto **sin** estas carpetas/archivos:
   - `.env.local`, `.neon`, `node_modules/`, `datos/agrosmart.db`, `datos/iot.db`, `.streamlit/secrets.toml`.
   - El `.gitignore` ya los excluye.
3. En **Streamlit Community Cloud** (https://share.streamlit.io):
   - **New app** → elige el repositorio → archivo `app.py` → **Deploy**.
4. En **Secrets** agrega:
   ```toml
   DATABASE_URL = "postgresql://...de Neon..."
   ```
5. Listo: tendrás un enlace público para celular, tablet y PC.

> Para la base de datos persistente, usa el `DATABASE_URL` de Neon.
> No subas contraseñas ni `.env.local` al repositorio.

## 8. Preguntas que te pueden hacer

| Pregunta | Respuesta corta |
|---|---|
| ¿La foto analiza el suelo? | No. El dato químico viene del laboratorio; la foto es apoyo para plagas. |
| ¿Cómo se calcula la compatibilidad? | Pesos explícitos: pH 30 %, textura 15 %, temperatura 15 %, agua 15 %, N 10 %, P 5 %, K 10 %. |
| ¿De dónde salen los rangos? | Son de ejemplo; deben citarse con FAO EcoCrop, ICA o Agrosavia. |
| ¿Es gratis? | Sí: Streamlit, Neon Free, GEE e IA local. |
| ¿Aguanta más usuarios? | Sí: Postgres, roles y auditoría; el siguiente paso es el despliegue. |
| ¿Por qué hay un administrador? | Para seguimiento académico y verificación de datos; no puede ver contraseñas. |
