"""
=============================================================================
 AgroSmart - Integracion con Google Earth Engine (GEE)
=============================================================================
 Calcula, para el poligono del terreno:
   - Area (ha)
   - Elevacion media (SRTM)
   - NDVI medio/min/max (Sentinel-2)
   - Cobertura del suelo (ESA WorldCover)
   - Precipitacion acumulada (CHIRPS)

 Requiere:
   1) pip install earthengine-api   (lo hace instalar_gee.bat)
   2) Autenticarse una vez:  earthengine authenticate
   3) Un proyecto de Google Cloud con Earth Engine habilitado.

 Nota: GEE NO analiza quimicamente el suelo. Aporta informacion espacial y
 ambiental; el dato quimico viene del laboratorio.
=============================================================================
"""

# `ee` se importa dentro de las funciones para que la app funcione
# aunque earthengine-api todavia no este instalado.

# Codigos de cobertura de ESA WorldCover
COBERTURA = {
    10: "Cobertura arborea",
    20: "Matorral",
    30: "Pastizal",
    40: "Cultivos",
    50: "Zona urbana/construida",
    60: "Suelo desnudo",
    70: "Nieve/hielo",
    80: "Cuerpo de agua",
    90: "Humedal",
    95: "Manglar",
    100: "Musgo/liquen",
}


def estado():
    try:
        import ee  # noqa: F401
        return True, "earthengine-api instalado"
    except Exception as e:  # pragma: no cover
        return False, f"No instalado: {e}"


def inicializar(proyecto: str | None = None):
    import ee

    if proyecto:
        ee.Initialize(project=proyecto)
    else:
        ee.Initialize()


def _geometria(coords_latlon):
    """coords = [(lat, lon), ...] -> ee.Geometry.Polygon"""
    import ee

    anillo = [[lon, lat] for lat, lon in coords_latlon]
    return ee.Geometry.Polygon([anillo])


def analizar(coords_latlon, proyecto, fecha_inicio, fecha_fin):
    """Devuelve un diccionario con los indicadores del terreno."""
    import ee

    inicializar(proyecto)
    geom = _geometria(coords_latlon)
    resultado = {}

    resultado["area_ha"] = float(geom.area(1).divide(10000).getInfo())

    # --- Elevacion (SRTM) ---
    try:
        elev = ee.Image("USGS/SRTMGL1_003")
        valor = elev.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=geom, scale=30, maxPixels=1e9
        ).get("elevation")
        resultado["elevacion_m"] = valor.getInfo()
    except Exception as e:
        resultado["elevacion_error"] = str(e)

    # --- NDVI (Sentinel-2) ---
    try:
        s2 = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(geom)
            .filterDate(fecha_inicio, fecha_fin)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
        )
        if s2.size().getInfo() > 0:
            img = s2.median()
            ndvi = img.normalizedDifference(["B8", "B4"]).rename("NDVI")
            stats = ndvi.reduceRegion(
                reducer=ee.Reducer.mean().combine(
                    ee.Reducer.minMax(), sharedInputs=True
                ),
                geometry=geom,
                scale=10,
                maxPixels=1e9,
            ).getInfo()
            resultado["ndvi_medio"] = stats.get("NDVI_mean")
            resultado["ndvi_min"] = stats.get("NDVI_min")
            resultado["ndvi_max"] = stats.get("NDVI_max")
            resultado["imagenes_s2"] = s2.size().getInfo()
            mapid = ndvi.getMapId(
                {"min": -0.2, "max": 0.9, "palette": ["brown", "yellow", "green", "darkgreen"]}
            )
            resultado["ndvi_tile"] = mapid["tile_fetcher"].url_format
        else:
            resultado["ndvi_medio"] = None
            resultado["imagenes_s2"] = 0
    except Exception as e:
        resultado["ndvi_error"] = str(e)

    # --- Cobertura del suelo (ESA WorldCover) ---
    try:
        lc = ee.ImageCollection("ESA/WorldCover/v200").first()
        histograma = lc.reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=geom,
            scale=10,
            maxPixels=1e9,
        ).getInfo()
        clases = histograma.get("Map", {}) or {}
        total = sum(clases.values()) or 1
        resultado["cobertura"] = {
            COBERTURA.get(int(k), f"Clase {k}"): round(v / total * 100, 1)
            for k, v in sorted(clases.items(), key=lambda x: -x[1])
        }
    except Exception as e:
        resultado["cobertura_error"] = str(e)

    # --- Precipitacion (CHIRPS) ---
    try:
        ch = (
            ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
            .filterBounds(geom)
            .filterDate(fecha_inicio, fecha_fin)
        )
        if ch.size().getInfo() > 0:
            precip = ch.sum()
            valor = precip.reduceRegion(
                reducer=ee.Reducer.mean(), geometry=geom, scale=5000, maxPixels=1e9
            ).get("precipitation")
            resultado["precipitacion_mm"] = valor.getInfo()
        else:
            resultado["precipitacion_mm"] = None
    except Exception as e:
        resultado["precipitacion_error"] = str(e)

    return resultado
