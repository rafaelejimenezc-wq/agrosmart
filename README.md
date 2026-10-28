# 🌱 AgroSmart

> 🌐 **App en línea:** https://agrosmart-h6mj2vpjj6acmwwjrrthjf.streamlit.app/

**Sistema inteligente de apoyo a la decisión agrícola** — proyecto académico de
Ingeniería Ambiental.

Integra análisis de suelo de laboratorio, superficie del terreno, recomendación
de cultivos, riego IoT, apoyo en plagas (con IA) e información satelital
(Google Earth Engine), con generación de reportes y exportación a QGIS.

> ⚠️ Los datos de ejemplo (rangos de cultivos, umbrales, catálogo de plagas)
> deben reemplazarse y citarse con fuentes confiables (FAO EcoCrop, ICA,
> Agrosavia) antes de la entrega final.

---

## 1. Requisitos (una sola vez)

- Windows.
- Python 3.12 (si no lo tienes):

  ```powershell
  winget install --id Python.Python.3.12 -e --scope user
  ```

## 2. Instalar la aplicación (una sola vez)

Doble clic en **`instalar.bat`**. Crea un entorno virtual en
`C:\Users\<tu-usuario>\agrosmart-venv` e instala las librerías base.

## 3. Ejecutar (cada vez)

Doble clic en **`iniciar.bat`** → se abre en `http://localhost:8501`.

### Modo demo sin internet

Doble clic en **`iniciar_demo.bat`**. Usa SQLite local con datos de ejemplo
(no requiere internet) y las cuentas:

- Las credenciales están en `CREDENCIALES.txt` (no se sube a GitHub).

La guía completa para la presentación está en **`PRESENTACION.md`**.

### Usar desde celular, tablet o PC

La aplicación es **web y adaptable**: la misma URL sirve para los tres.

- **Misma red Wi-Fi:** abre en el celular la **Network URL** que muestra
  `iniciar.bat` (ej. `http://192.168.0.10:8501`).
- **Desde cualquier lugar:** publica la app gratis con Streamlit Community
  Cloud. Instrucciones paso a paso en **`DESPLIEGUE.md`**.
- **Como ícono en el celular:** en Chrome/Safari elige
  "Añadir a pantalla de inicio".

### Cuentas de usuario

- Cada persona crea su cuenta con **nombre, correo y contraseña**.
- Los análisis, terrenos y reportes quedan **separados por usuario**.
- La sesión se mantiene 30 días en el mismo navegador.
- Puedes **cambiar la contraseña** desde la barra lateral.

### Asistente inteligente

- **Bot flotante** que te dice el siguiente paso y avisa si un dato está fuera
  de rango (se puede ocultar desde la barra lateral).
- Página **🤖 Asistente** con chat y botones rápidos.
- Funciona **gratis en modo guía** (reglas). Para IA generativa, copia
  `.streamlit/secrets.toml.example` a `.streamlit/secrets.toml` y pon una clave
  gratuita de **Google Gemini** o **Groq**.

### Base de datos: Neon Postgres

La app usa **Neon Postgres** si existe `DATABASE_URL`; si no, SQLite local.
`db.py` carga `.env.local` automáticamente.

Servicios provisionados con `neon deploy`:

- PostgreSQL (rama `production`)
- Neon Auth (JWKS)
- Functions (`hello`)
- Realtime
- AI Gateway: **requiere plan pago** (se omitió)

Comandos:

```bash
npm run build   # valida neon.ts con `neon config plan`
neon deploy     # aplica los servicios y escribe .env.local
```

No subas `.env.local` ni `.neon` a GitHub.

---

## 4. Módulos

| Módulo | Qué hace |
|---|---|
| 🏠 **Inicio** | Ruta guiada paso a paso y datos de demostración. |
| 🤖 **Asistente** | Chat que guía, valida datos y responde dudas (reglas + IA opcional). |
| 🧪 **Análisis de suelo** | Resultados de laboratorio (pH, MO, N-P-K, CE, textura...). |
| 🗺️ **Terreno y hectáreas** | Dibuja el lote en mapa satélite y calcula área total/apta. |
| 🌱 **Recomendación de cultivos** | 38 cultivos, puntaje con pesos explícitos y desglose. |
| 📚 **Catálogo de cultivos** | Fichas con pH, temperatura, agua, ciclo, nutrientes y plagas asociadas. |
| 💧 **Riego IoT** | Pestaña **En vivo** (ESP32 real) y **Simulador**. |
| 🐛 **Plagas (apoyo)** | **IA por imagen** (PlantVillage) + sistema por síntomas. |
| 🛰️ **Satélite (GEE)** | Elevación, NDVI, cobertura y lluvia; exporta a QGIS. |
| 📊 **Mi historial** | Todo lo registrado por el usuario, con gráficas y exportación. |
| 📄 **Reportes** | PDF con suelo + terreno + recomendaciones y CSV. |

---

## 5. Fase 2 — Riego IoT (ESP32)

### 5.1 Arrancar el servidor

Doble clic en **`iniciar_iot.bat`** (deja la ventana abierta).
Documentación de la API: `http://localhost:8000/docs`.

### 5.2 Cargar el firmware

Abre `firmware/esp32_riego.ino` en Arduino IDE y cambia:

- `SSID` y `PASSWORD` de tu Wi-Fi.
- `SERVIDOR`: la **IP local de tu computador** (no `localhost`), por ejemplo
  `http://192.168.1.100:8000/api/lectura`.
- `SECO` y `MOJADO`: calibración del sensor (mira el monitor serial).

Hardware: ESP32, sensor capacitivo de humedad (GPIO 34), relé (GPIO 26), bomba o
electroválvula con fuente independiente.

### 5.3 Cómo funciona

1. El ESP32 envía `POST /api/lectura` con la humedad.
2. El servidor decide con **histéresis** (enciende bajo el mínimo, apaga al
   alcanzar el máximo) y guarda el historial.
3. El ESP32 recibe `{"riego": true/false}` y activa el relé.
4. La app muestra el estado y el historial en **💧 Riego IoT → En vivo**.

También puedes forzar la bomba o volver a automático desde la app.

> Si el ESP32 no conecta: revisa que estén en la misma red, que el Firewall de
> Windows permita el puerto 8000 y que la IP sea la correcta.

---

## 6. Fase 3 — IA para plagas

### 6.1 Instalar (una sola vez)

Doble clic en **`instalar_ia.bat`** (descarga PyTorch CPU + Transformers, ~150 MB).

### 6.2 Usar

En **🐛 Plagas → Analizar imagen (IA)**, sube una foto de una hoja y pulsa
**Analizar con IA**. La primera vez descarga el modelo (~15 MB).

- Modelo: `linkanjarad/mobilenet_v2_1.0_224-plant-disease-identification`
  (MobileNetV2, PlantVillage, ~95 % de precisión en laboratorio).
- Devuelve las 5 clases más probables, traducidas al español.
- **Limitación**: fue entrenado con fotos de laboratorio; en campo puede fallar.
  Úsalo como apoyo, no como diagnóstico definitivo.
- Puedes cambiar el modelo con la variable de entorno
  `AGROSMART_MODELO_PLAGAS`.

Si no instalas la IA, la app sigue funcionando con el sistema por síntomas.

---

## 7. Google Earth Engine

### 7.1 Instalar y autenticar (una sola vez)

1. Doble clic en **`instalar_gee.bat`**.
2. Regístrate con tu correo institucional:
   https://code.earthengine.google.com/register
3. Crea un proyecto en Google Cloud y habilita Earth Engine API.
4. Copia el **ID del proyecto**.

### 7.2 Usar

En **🛰️ Satélite (GEE)**:

1. Elige un terreno guardado.
2. Pega el ID del proyecto.
3. Elige el rango de fechas.
4. Pulsa **Analizar con GEE**.

Obtendrás área, elevación media (SRTM), NDVI (Sentinel-2), cobertura del suelo
(ESA WorldCover) y precipitación acumulada (CHIRPS), además del mapa NDVI.

### 7.3 Exportar a QGIS

En el mismo módulo puedes descargar:

- El polígono en **GeoJSON** (arrástralo a QGIS).
- Los análisis de suelo en **CSV**.

> GEE **no** analiza químicamente el suelo. El dato químico viene del
> laboratorio; GEE aporta información espacial y ambiental.

---

## 8. Estructura del proyecto

```
Proyecto predeterminado/
├── app.py                  # Aplicación Streamlit (interfaz)
├── auth.py                 # Registro, login y sesiones
├── asistente.py            # Asistente: guía, validación y LLM opcional
├── iot_server.py           # API FastAPI del riego (Fase 2)
├── plagas_ia.py            # Clasificador de plagas (Fase 3)
├── gee_utils.py            # Integración con Earth Engine
├── reportes.py             # Generación del PDF
├── requirements.txt        # Dependencias base
├── requirements-ia.txt     # Dependencias de IA (opcionales)
├── iniciar.bat             # Ejecutar la app
├── instalar.bat            # Instalar dependencias base
├── iniciar_iot.bat         # Ejecutar el servidor IoT
├── instalar_ia.bat         # Instalar IA
├── instalar_gee.bat        # Instalar/autenticar GEE
├── firmware/
│   └── esp32_riego.ino     # Sketch del ESP32
├── datos/
│   ├── cultivos.json       # 38 cultivos (editable)
│   ├── plagas.json         # 45 plagas/enfermedades (editable)
│   ├── agrosmart.db        # Base de datos (usuarios + datos)
│   └── iot.db              # Historial de sensores
├── Dockerfile              # Imagen para publicar
├── render.yaml             # Configuración para Render
├── DESPLIEGUE.md           # Guía celular/tablet/nube
└── .streamlit/
    ├── config.toml         # Tema
    └── secrets.toml.example# Plantilla para la clave de IA
```

---

## 9. Cómo editar

- **Cultivos**: `datos/cultivos.json` (38 fichas).
- **Plagas y síntomas**: `datos/plagas.json` (45 fichas y 49 síntomas).
- Los cambios en los JSON se recargan solos, sin reiniciar la app.
- **Pesos del motor**: en `app.py`, diccionario `PESOS`.
- **Umbrales de nutrientes**: en `app.py`, `UMBRALES_N/P/K`.
- **Umbrales de riego iniciales**: en `iot_server.py` (tabla `config`).

---

## 10. Solución de problemas

| Problema | Solución |
|---|---|
| `streamlit no se reconoce` | Ejecuta `instalar.bat` y usa `iniciar.bat`. |
| La app no abre | Revisa que el puerto 8501 esté libre. |
| El ESP32 no conecta | Misma red Wi-Fi, IP correcta y puerto 8000 permitido. |
| La IA no carga | Ejecuta `instalar_ia.bat` y verifica internet. |
| GEE falla | Ejecuta `earthengine authenticate` y revisa el ID del proyecto. |
| QGIS no abre el GeoJSON | Usa "Capa → Añadir capa → Añadir capa vectorial". |

---

*Nota académica: este sistema es una herramienta de **apoyo** a la decisión.
No sustituye el análisis de laboratorio ni la asesoría de un profesional agrícola.*
