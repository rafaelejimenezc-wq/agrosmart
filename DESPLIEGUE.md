# 📱 Cómo usar AgroSmart en celular, tablet y PC

La aplicación es **web y adaptable**: la misma URL funciona en los tres
dispositivos. No hay que crear una app distinta para cada uno.

---

## Opción A — En tu casa / misma red Wi-Fi (gratis, sin cuentas)

Ideal para la exposición o para probar con el celular.

1. En el PC, doble clic en **`iniciar.bat`**.
2. La ventana negra mostrará algo como:

   ```
   Local URL:   http://localhost:8501
   Network URL: http://192.168.0.10:8501
   ```

3. En el celular o tablet, conéctate a **la misma red Wi-Fi** y abre en el
   navegador la **Network URL** (ej. `http://192.168.0.10:8501`).
4. Si no carga, permite a Python/Streamlit en el **Firewall de Windows**
   (red privada). Para ver tu IP: abre PowerShell y escribe `ipconfig`.

> El PC debe quedar encendido y con `iniciar.bat` abierto mientras usas el
> celular.

---

## Opción B — Publicarla en internet con Streamlit Community Cloud (gratis)

Así tendrás un enlace tipo `https://agrosmart.streamlit.app` que abre desde
cualquier lugar, sin tener el PC encendido.

### Lo que necesitas (cuentas gratuitas)

1. Una cuenta de **GitHub**: https://github.com/signup
2. Una cuenta de **Streamlit Community Cloud**: https://share.streamlit.io
   (se entra con la cuenta de GitHub)

### Pasos

1. Crea un repositorio nuevo en GitHub (puede ser privado).
2. Sube **todo el contenido de esta carpeta** (excepto `.venv`, que no existe
   aquí). Puedes usar GitHub Desktop si no manejas Git.
3. Entra a https://share.streamlit.io → **New app**.
4. Elige el repositorio, la rama `main` y el archivo principal **`app.py`**.
5. Pulsa **Deploy**. En 2–3 minutos tendrás tu enlace público.

> **Importante:** en la nube, la base de datos SQLite (`datos/agrosmart.db`)
> es **temporal**: si la app se reinicia, se pierden las cuentas y los registros.
> Para una demo o exposición es suficiente. Si necesitas persistencia real,
> habría que usar una base de datos externa gratuita (por ejemplo **Supabase**
> o **Neon**) y yo adapto el código para conectarla. Dime y lo hacemos.

---

## Cuentas y datos

La app pide **crear una cuenta** (nombre, correo y contraseña). Cada usuario ve
solo sus análisis, terrenos y reportes.

- **En tu PC:** los datos quedan en `datos/agrosmart.db` y persisten.
- **Con Neon (recomendado):** la app usa `DATABASE_URL` y los datos persisten
  en PostgreSQL. `db.py` lee `.env.local` automáticamente.
- **En la nube gratuita sin Neon:** el disco es temporal; las cuentas se
  reinician.
- **Contraseña:** se guarda con hash scrypt; nunca en texto plano. Se puede
  cambiar desde la barra lateral.

> Neon Auth está provisionado (JWKS), pero el inicio de sesión de la app sigue
> siendo propio (Python/Streamlit), para no reescribir el manejo de sesiones.
> Functions y Realtime están activos y se pueden probar con el CLI; AI Gateway
> requiere plan pago.

---

## Clave de IA (opcional)

El asistente funciona **gratis en modo guía**. Para respuestas generativas:

1. Copia `.streamlit/secrets.toml.example` a `.streamlit/secrets.toml`.
2. Crea una clave gratuita en **Google AI Studio** (Gemini) o **Groq**.
3. Pega la clave en `AGROSMART_LLM_KEY` y reinicia la app.

> Nunca subas `secrets.toml` a GitHub (ya está en `.gitignore`).

> Los módulos **IoT** y **Google Earth Engine** siguen funcionando, pero el
> servidor IoT (`localhost:8000`) debe correr aparte; en la nube solo queda la
> app principal.

---

## Opción C — Render / Railway con Docker

El proyecto ya incluye `Dockerfile` y `render.yaml`.

1. Sube el repositorio a GitHub.
2. En https://render.com → **New → Web Service** → conecta el repo.
3. Render detecta el `Dockerfile` automáticamente. Plan **Free**.
4. Deploy. Te dará una URL pública.

---

## "Instalar" la app en el celular (sin tienda de apps)

Cuando la tengas abierta en el navegador:

- **Android (Chrome):** menú ⋮ → **Añadir a pantalla de inicio**.
- **iPhone/iPad (Safari):** botón Compartir → **Añadir a pantalla de inicio**.

Quedará como un ícono más, en pantalla completa.

> Una app nativa (APK/IPA) requeriría otro desarrollo (Flutter o React Native)
> y no es necesaria para este proyecto: la web adaptable cubre móvil, tablet y PC.

---

## ¿Qué necesito de ti para publicarla?

Solo una de estas dos cosas:

- **Opción A:** nada; ya funciona en tu red.
- **Opción B/C:** créate la cuenta de GitHub (y de Streamlit Cloud o Render) y
  dime cuando la tengas. Yo te guío paso a paso para subir el proyecto y
  dejarlo en línea. No necesito tus contraseñas.
