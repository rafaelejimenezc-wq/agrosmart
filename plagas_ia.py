"""
=============================================================================
 AgroSmart - Clasificacion de plagas/enfermedades por imagen (Fase 3)
=============================================================================
 Usa un modelo preentrenado de Hugging Face (MobileNetV2 entrenado con
 PlantVillage) si `torch` y `transformers` estan instalados.

 Si no estan instalados, la app sigue funcionando con el sistema experto
 por sintomas. Para habilitar la IA ejecuta:  instalar_ia.bat

 Modelo configurable con la variable de entorno AGROSMART_MODELO_PLAGAS.
=============================================================================
"""

import io
import os

MODELO_ID = os.environ.get(
    "AGROSMART_MODELO_PLAGAS",
    "linkanjarad/mobilenet_v2_1.0_224-plant-disease-identification",
)

_modelo = None
_error = None


def estado():
    """Devuelve (disponible, mensaje)."""
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True, f"Motor de IA listo (modelo: {MODELO_ID})"
    except Exception as e:  # pragma: no cover
        return False, f"IA no instalada: {e}"


def cargar_modelo():
    """Carga el pipeline de clasificacion de imagenes (una sola vez)."""
    global _modelo, _error
    if _modelo is not None:
        return _modelo
    try:
        from transformers import pipeline

        # El modelo de PlantVillage no declara `image_processor_type`, asi que
        # Transformers 5 no lo autodetecta. Lo creamos explicitamente.
        try:
            from transformers import MobileNetV2ImageProcessor

            procesador = MobileNetV2ImageProcessor()
        except Exception:
            from transformers import ViTImageProcessor

            procesador = ViTImageProcessor(
                size={"height": 224, "width": 224},
                image_mean=[0.485, 0.456, 0.406],
                image_std=[0.229, 0.224, 0.225],
            )

        _modelo = pipeline(
            "image-classification",
            model=MODELO_ID,
            image_processor=procesador,
        )
        return _modelo
    except Exception as e:  # pragma: no cover
        _error = str(e)
        return None


def ultimo_error():
    return _error


# Traduccion de las etiquetas del modelo PlantVillage al espanol.
_TRADUCCIONES = {
    "Apple Scab": "Manzana: sarna (Venturia)",
    "Apple with Black Rot": "Manzana: podredumbre negra",
    "Cedar Apple Rust": "Manzana: roya del cedro",
    "Healthy Apple": "Manzana: sana",
    "Healthy Blueberry Plant": "Arandano: sano",
    "Cherry with Powdery Mildew": "Cereza: oidio",
    "Healthy Cherry Plant": "Cereza: sana",
    "Corn (Maize) with Cercospora and Gray Leaf Spot": "Maiz: mancha gris (Cercospora)",
    "Corn (Maize) with Common Rust": "Maiz: roya comun",
    "Corn (Maize) with Northern Leaf Blight": "Maiz: tizon norteno",
    "Healthy Corn (Maize) Plant": "Maiz: sano",
    "Grape with Black Rot": "Uva: podredumbre negra",
    "Grape with Esca (Black Measles)": "Uva: yesca (sarampion negro)",
    "Grape with Isariopsis Leaf Spot": "Uva: mancha foliar (Isariopsis)",
    "Healthy Grape Plant": "Uva: sana",
    "Orange with Citrus Greening": "Naranja: HLB (greening)",
    "Peach with Bacterial Spot": "Durazno: mancha bacteriana",
    "Healthy Peach Plant": "Durazno: sano",
    "Bell Pepper with Bacterial Spot": "Pimiento: mancha bacteriana",
    "Healthy Bell Pepper Plant": "Pimiento: sano",
    "Potato with Early Blight": "Papa: tizon temprano",
    "Potato with Late Blight": "Papa: tizon tardio",
    "Healthy Potato Plant": "Papa: sana",
    "Healthy Raspberry Plant": "Frambuesa: sana",
    "Healthy Soybean Plant": "Soja: sana",
    "Squash with Powdery Mildew": "Calabaza: oidio",
    "Strawberry with Leaf Scorch": "Fresa: quemadura de hoja",
    "Healthy Strawberry Plant": "Fresa: sana",
    "Tomato with Bacterial Spot": "Tomate: mancha bacteriana",
    "Tomato with Early Blight": "Tomate: tizon temprano",
    "Tomato with Late Blight": "Tomate: tizon tardio",
    "Tomato with Leaf Mold": "Tomate: moho de la hoja",
    "Tomato with Septoria Leaf Spot": "Tomate: mancha de Septoria",
    "Tomato with Spider Mites or Two-spotted Spider Mite": "Tomate: arana roja",
    "Tomato with Target Spot": "Tomate: mancha diana",
    "Tomato Yellow Leaf Curl Virus": "Tomate: virus del rizado amarillo",
    "Tomato Mosaic Virus": "Tomate: virus del mosaico",
    "Healthy Tomato Plant": "Tomate: sano",
}


def traducir(etiqueta: str) -> str:
    if etiqueta in _TRADUCCIONES:
        return _TRADUCCIONES[etiqueta]
    # Etiquetas tipo "Cultivo___Problema"
    partes = etiqueta.replace("___", ": ").replace("_", " ").split(":")
    if len(partes) == 2:
        cultivo = partes[0].strip().capitalize()
        problema = partes[1].strip().replace("  ", " ")
        return f"{cultivo}: {problema}"
    return etiqueta


def clasificar(modelo, imagen_bytes: bytes, top: int = 5):
    """Devuelve [(etiqueta_es, probabilidad), ...] ordenado de mayor a menor."""
    from PIL import Image

    imagen = Image.open(io.BytesIO(imagen_bytes)).convert("RGB")
    predicciones = modelo(imagen, top_k=top)
    return [(traducir(p["label"]), round(float(p["score"]), 4)) for p in predicciones]
