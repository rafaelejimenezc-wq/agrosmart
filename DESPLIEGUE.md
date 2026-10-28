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

### Repositorio ya creado

- **Repo:** https://github.com/rafaelejimenezc-wq/agrosmart (público)
- **App en línea:** https://agrosmart-h6mj2vpjj6acmwwjrrthjf.streamlit.app/
- **Rama:** `main`
- **Archivo principal:** `app.py`

### Pasos

1. Entra a https://share.streamlit.io e inicia sesión con GitHub
   (`rafaelejimenezc-wq`).
2. Autoriza a Streamlit para acceder al repositorio privado `agrosmart`.
3. Pulsa **New app** y elige:
   - Repository: `rafaelejimenezc-wq/agrosmart`
   - Branch: `main`
   - Main file path: `app.py`
4. En **Advanced settings → Secrets**, pega el contenido de tu archivo local
   `.streamlit/secrets.toml` (contiene `DATABASE_URL` y `AGROSMART_SECRET`).
   No lo compartas ni lo subas a GitHub.
5. Pulsa **Deploy**. En 2–3 minutos tendrás tu enlace público.

> **Importante:** en la nube la base de datos es **Neon**, así que las cuentas
> y los datos persisten. No se usa el SQLite local.
>
> Si Streamlit no puede acceder al repo privado, puedes hacerlo público
> **solo después de cambiar la contraseña del administrador** y quitar las
> credenciales de la documentación.

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
