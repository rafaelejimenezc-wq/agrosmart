"""
=============================================================================
 AgroSmart - Generacion del PDF de reporte
=============================================================================
 Se separo de app.py para poder probarlo y mantenerlo.
=============================================================================
"""

from datetime import datetime

from fpdf import FPDF


def limpiar_pdf(texto):
    """fpdf2 con fuentes base solo admite latin-1."""
    return str(texto).encode("latin-1", "replace").decode("latin-1")


def generar_pdf_reporte(analisis, terreno, recomendaciones):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, limpiar_pdf("AgroSmart - Reporte del predio"), ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(90)
    pdf.cell(0, 6, limpiar_pdf(f"Generado el {datetime.now().strftime('%Y-%m-%d %H:%M')}"), ln=True)
    pdf.set_text_color(0)
    pdf.ln(3)

    def titulo(t):
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_fill_color(230, 245, 230)
        pdf.cell(0, 8, limpiar_pdf(t), ln=True, fill=True)
        pdf.set_font("Helvetica", "", 11)

    # Suelo
    titulo("1. Analisis de suelo")
    if analisis:
        filas = [
            ("Lote", analisis.get("lote")),
            ("Fecha", analisis.get("fecha")),
            ("pH", analisis.get("ph")),
            ("Materia organica (%)", analisis.get("materia_organica")),
            ("Nitrogeno (mg/kg)", analisis.get("nitrogeno")),
            ("Fosforo (mg/kg)", analisis.get("fosforo")),
            ("Potasio (mg/kg)", analisis.get("potasio")),
            ("Conductividad (dS/m)", analisis.get("conductividad")),
            ("Textura", analisis.get("textura")),
            ("Disponibilidad de agua", analisis.get("agua")),
            ("Temperatura (C)", analisis.get("temperatura")),
        ]
        for k, v in filas:
            pdf.cell(70, 7, limpiar_pdf(k), border=0)
            pdf.cell(0, 7, limpiar_pdf("-" if v is None else v), ln=True)
    else:
        pdf.multi_cell(0, 7, limpiar_pdf("Sin analisis de suelo registrado."))
    pdf.ln(3)

    # Terreno
    titulo("2. Terreno y superficie")
    if terreno:
        pdf.cell(0, 7, limpiar_pdf(f"Nombre: {terreno['nombre']}"), ln=True)
        pdf.cell(0, 7, limpiar_pdf(f"Area total: {terreno['area_total_ha']:.2f} ha"), ln=True)
        pdf.cell(0, 7, limpiar_pdf(f"Area apta: {terreno['area_apta_ha']:.2f} ha"), ln=True)
    else:
        pdf.multi_cell(0, 7, limpiar_pdf("Sin terreno registrado."))
    pdf.ln(3)

    # Recomendaciones
    titulo("3. Cultivos recomendados")
    if recomendaciones:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(60, 7, "Cultivo", border=1)
        pdf.cell(35, 7, "Compatibilidad", border=1, ln=True)
        pdf.set_font("Helvetica", "", 11)
        for r in recomendaciones:
            pdf.cell(60, 7, limpiar_pdf(r["cultivo"]["nombre"]), border=1)
            pdf.cell(35, 7, limpiar_pdf(f"{r['puntaje']} %"), border=1, ln=True)
    else:
        pdf.multi_cell(0, 7, limpiar_pdf("Sin recomendaciones calculadas."))
    pdf.ln(3)

    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(120)
    pdf.multi_cell(
        0, 5,
        limpiar_pdf(
            "Nota: los rangos de cultivos son ilustrativos y deben citarse con "
            "fuentes confiables. Este reporte es apoyo a la decision y no "
            "reemplaza la asesoria de un profesional agricola."
        ),
    )
    salida = pdf.output(dest="S")
    if isinstance(salida, str):
        return salida.encode("latin-1")
    return bytes(salida)
