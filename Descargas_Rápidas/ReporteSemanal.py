"""
reporte_mensual_aliv.py
========================
Genera el reporte mensual de seguimiento de cuota de Aliv Telecom en PDF.
Lee data.json generado por extraer_datos_pbi.py (datos MTD desde Power BI).

Uso:
    python ReporteSemanal.py

Requisitos:
    pip install reportlab
    Ejecutar primero: python ExtraerDatos.py

El PDF se guarda en la misma carpeta del script como:
    Reporte_Mensual_Aliv_YYYY-MM-DD.pdf
"""

import subprocess
import json
import sys
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# ──────────────────────────────────────────────
# CONFIGURACIÓN
# ──────────────────────────────────────────────
MCP_EXE = r"C:\Users\Usuario\.vscode\extensions\analysis-services.powerbi-modeling-mcp-0.5.4-win32-x64\server\powerbi-modeling-mcp.exe"
CUOTA_ABRIL = 310  # Actualiza este valor cada mes

# Colores Aliv
C_NARANJA   = colors.HexColor("#F47920")
C_OSCURO    = colors.HexColor("#1C1C1E")
C_GRIS      = colors.HexColor("#252528")
C_VERDE     = colors.HexColor("#1D9E75")
C_ROJO      = colors.HexColor("#E24B4A")
C_AMARILLO  = colors.HexColor("#EF9F27")
C_AZUL      = colors.HexColor("#00B0F0")
C_BLANCO    = colors.white
C_TEXTO     = colors.HexColor("#E0E0E0")
C_GRIS_CLARO = colors.HexColor("#AAAAAA")

# ──────────────────────────────────────────────
# CONEXIÓN MCP → POWER BI
# ──────────────────────────────────────────────

def mcp_call(operation, params=None):
    """Llama al MCP de Power BI y retorna el resultado como dict."""
    payload = {"operation": operation}
    if params:
        payload.update(params)
    cmd = [MCP_EXE, "--start"]
    proc = subprocess.run(
        cmd,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30
    )
    if proc.returncode != 0:
        raise RuntimeError(f"MCP error: {proc.stderr}")
    return json.loads(proc.stdout)


def dax(query):
    """Ejecuta una consulta DAX y retorna filas como lista de dicts."""
    payload = {
        "operation": "Execute",
        "query": query,
        "maxRows": 500
    }
    cmd = [MCP_EXE, "--start"]
    proc = subprocess.run(
        cmd,
        input=json.dumps({"dax_query": payload}),
        capture_output=True,
        text=True,
        timeout=30
    )
    # Parsear output CSV-like del MCP
    lines = proc.stdout.strip().split("\n")
    if len(lines) < 2:
        return []
    headers = [h.strip("[]").split("]")[0].split("[")[-1] for h in lines[0].split(",")]
    rows = []
    for line in lines[1:]:
        vals = line.split(",")
        rows.append(dict(zip(headers, [v.strip() for v in vals])))
    return rows


# ──────────────────────────────────────────────
# EXTRACCIÓN DE DATOS (sin MCP directo — via archivo)
# ──────────────────────────────────────────────
# NOTA: Como el MCP requiere la app abierta y conexión previa,
# este script usa un archivo JSON intermedio que tú generas
# corriendo el bloque de extracción en Power BI / Python con
# el conector. Ver instrucciones abajo.
#
# Para generar data.json, corre en tu entorno:
#   python extraer_datos_pbi.py
# ──────────────────────────────────────────────

def cargar_datos():
    """
    Carga los datos desde data.json generado por extraer_datos_pbi.py
    Si no existe, usa datos de ejemplo para prueba.
    """
    try:
        with open("data.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print("No se encontró data.json — usando datos de ejemplo")
        return datos_ejemplo()


def datos_ejemplo():
    """Datos de ejemplo basados en un mes de referencia (Abril 2026 — cuota 310)."""
    return {
        "fecha_reporte":      "30/04/2026",
        "mes":                "Abril 2026",
        "dias_transcurridos": 30,
        "dias_totales_mes":   30,
        "cuota_mes":          310,
        "kpis": {
            "total_altas":        298,
            "altas_ceh":          287,
            "total_preventas":    390,
            "total_anulaciones":  32,
            "score_promedio":     601,
            "ventas_en_riesgo":   45,
            "sin_score":          60,
            "no_venta":           22,
            "ritmo_diario":       9.9,
            "ritmo_ceh":          9.6,
            "proyeccion_fin_mes": 298,
            "proyeccion_ceh":     287,
        },
        "semanas_mes": [
            {"label": "01/04 – 06/04", "altas": 55, "altas_ceh": 53, "preventas": 72,  "en_curso": False},
            {"label": "07/04 – 13/04", "altas": 78, "altas_ceh": 75, "preventas": 101, "en_curso": False},
            {"label": "14/04 – 20/04", "altas": 82, "altas_ceh": 79, "preventas": 107, "en_curso": False},
            {"label": "21/04 – 27/04", "altas": 61, "altas_ceh": 59, "preventas": 79,  "en_curso": False},
            {"label": "28/04 – 30/04", "altas": 22, "altas_ceh": 21, "preventas": 31,  "en_curso": False},
        ],
        "planes": [
            {"plan": "850 Nov25",            "altas": 120, "preventas": 158},
            {"plan": "Plan 1000 Mbps JUN25", "altas": 78,  "preventas": 99},
            {"plan": "750 Mbps Mar26",        "altas": 55,  "preventas": 72},
            {"plan": "1000 Nov25",            "altas": 30,  "preventas": 41},
            {"plan": "500 Mbps HB Mar26",     "altas": 15,  "preventas": 20},
        ],
        "zonas": [
            {"zona": "Sin modificación (201)", "altas": 170, "preventas": 222, "en_riesgo": 2,  "sin_score": 30},
            {"zona": "Zona P2 (401)",           "altas": 112, "preventas": 145, "en_riesgo": 43, "sin_score": 30},
            {"zona": "No Venta",                "altas": 16,  "preventas": 23,  "en_riesgo": 0,  "sin_score": 0},
        ],
        "tramos": [
            {"tramo": "Mismo día", "altas": 60},
            {"tramo": "1 día",     "altas": 140},
            {"tramo": "2 días",    "altas": 55},
            {"tramo": "3 días",    "altas": 25},
            {"tramo": "4+ días",   "altas": 18},
        ],
        "top_vendedores": [
            {"vendedor": "Mariantonieta Passalacqua", "altas": 42, "en_riesgo": 4},
            {"vendedor": "Carlos Roberto Segura",     "altas": 38, "en_riesgo": 5},
            {"vendedor": "Segundo Eladio Maluquiz",   "altas": 35, "en_riesgo": 6},
            {"vendedor": "Jesus Mendez Piña",         "altas": 32, "en_riesgo": 4},
            {"vendedor": "Any Sotelo",                "altas": 28, "en_riesgo": 3},
        ],
    }


# ──────────────────────────────────────────────
# ESTILOS
# ──────────────────────────────────────────────

def build_styles():
    styles = getSampleStyleSheet()
    custom = {}

    custom["titulo_doc"] = ParagraphStyle(
        "titulo_doc",
        fontName="Helvetica-Bold",
        fontSize=20,
        textColor=C_NARANJA,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    custom["subtitulo_doc"] = ParagraphStyle(
        "subtitulo_doc",
        fontName="Helvetica",
        fontSize=10,
        textColor=C_GRIS_CLARO,
        alignment=TA_CENTER,
        spaceAfter=16,
    )
    custom["seccion"] = ParagraphStyle(
        "seccion",
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=C_NARANJA,
        spaceBefore=14,
        spaceAfter=6,
    )
    custom["cuerpo"] = ParagraphStyle(
        "cuerpo",
        fontName="Helvetica",
        fontSize=9,
        textColor=colors.HexColor("#333333"),
        spaceAfter=4,
        leading=14,
    )
    custom["alerta"] = ParagraphStyle(
        "alerta",
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=C_ROJO,
        spaceAfter=3,
    )
    custom["ok"] = ParagraphStyle(
        "ok",
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=C_VERDE,
        spaceAfter=3,
    )
    custom["nota"] = ParagraphStyle(
        "nota",
        fontName="Helvetica-Oblique",
        fontSize=8,
        textColor=C_GRIS_CLARO,
        spaceAfter=4,
    )
    return custom


# ──────────────────────────────────────────────
# HELPERS TABLAS
# ──────────────────────────────────────────────

def pct(num, den):
    if den == 0:
        return "—"
    return f"{num/den*100:.1f}%"


def tabla_estilo_base(header_color=None):
    color = header_color or C_OSCURO
    return TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  color),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  C_BLANCO),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  8),
        ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.HexColor("#F9F9F9"), colors.white]),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 8),
        ("ALIGN",         (1, 1), (-1, -1), "CENTER"),
        ("ALIGN",         (0, 1), (0, -1),  "LEFT"),
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#DDDDDD")),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
    ])


# ──────────────────────────────────────────────
# GENERACIÓN DEL PDF
# ──────────────────────────────────────────────

def generar_pdf(datos):
    fecha_str = datetime.now().strftime("%Y-%m-%d")
    nombre_archivo = f"Reporte_Mensual_Aliv_{fecha_str}.pdf"

    doc = SimpleDocTemplate(
        nombre_archivo,
        pagesize=A4,
        rightMargin=1.8*cm, leftMargin=1.8*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm,
    )

    styles = build_styles()
    story = []

    k       = datos["kpis"]
    planes  = datos["planes"]
    zonas   = datos["zonas"]
    tramos  = datos["tramos"]
    top_v   = datos["top_vendedores"]
    semanas = datos.get("semanas_mes", [])
    cuota   = datos.get("cuota_mes", CUOTA_ABRIL)
    dias_t  = datos.get("dias_transcurridos", 1)
    dias_m  = datos.get("dias_totales_mes", 30)

    altas_ceh    = k.get("altas_ceh", k["total_altas"])  # C/E Habilitado = métrica de cuota
    pct_cuota    = altas_ceh / cuota if cuota else 0
    pct_esperado = dias_t / dias_m if dias_m else 0
    ratio_vs_esp = pct_cuota / pct_esperado if pct_esperado > 0 else 0
    conv_gral    = k["total_altas"] / k["total_preventas"] if k["total_preventas"] else 0
    pct_riesgo   = k["ventas_en_riesgo"] / k["total_preventas"] if k["total_preventas"] else 0
    pct_anul     = k["total_anulaciones"] / k["total_preventas"] if k["total_preventas"] else 0
    faltantes    = cuota - altas_ceh
    dias_rest    = dias_m - dias_t

    # Semáforo basado en ritmo actual vs ritmo esperado
    if ratio_vs_esp >= 0.95:
        color_semaforo = C_VERDE
        estado_ritmo   = "EN RITMO"
    elif ratio_vs_esp >= 0.75:
        color_semaforo = C_AMARILLO
        estado_ritmo   = "LIGERAMENTE BAJO"
    else:
        color_semaforo = C_ROJO
        estado_ritmo   = "BAJO RITMO"

    estado_colores = {
        "EN RITMO": C_VERDE, "LIGERAMENTE BAJO": C_AMARILLO, "BAJO RITMO": C_ROJO,
        "OK": C_VERDE, "REV": C_ROJO, "ALTO": C_ROJO, "RIESGO": C_ROJO,
    }

    # ── ENCABEZADO ─────────────────────────────────
    story.append(Paragraph("ALIV TELECOM — WIN DISTRIBUIDORA", styles["titulo_doc"]))
    story.append(Paragraph(
        f"Seguimiento Mensual · {datos['mes']} · "
        f"Al {datos['fecha_reporte']} — Día {dias_t} de {dias_m}",
        styles["subtitulo_doc"]
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=C_NARANJA))
    story.append(Spacer(1, 10))

    # ── 1. SEGUIMIENTO DE CUOTA ─────────────────────
    story.append(Paragraph("1. Seguimiento de Cuota del Mes — C/E Habilitado", styles["seccion"]))
    story.append(Paragraph(
        f"<b>{altas_ceh:,}</b> altas C/E Habilitado de <b>{cuota:,}</b> meta mensual  ·  "
        f"Ritmo: <b>{k.get('ritmo_ceh', k['ritmo_diario'])}/día</b>  ·  "
        f"Proyección al cierre: <b>{k.get('proyeccion_ceh', k['proyeccion_fin_mes']):,} altas</b>",
        styles["cuerpo"]
    ))
    story.append(Paragraph(
        f"Total altas (todos los tipos): {k['total_altas']:,}  ·  "
        f"Total preventas: {k['total_preventas']:,}",
        ParagraphStyle("sub_ceh", fontName="Helvetica", fontSize=8,
                       textColor=C_GRIS_CLARO, spaceAfter=4)
    ))
    story.append(Spacer(1, 4))

    # Barra de progreso visual
    bar_w    = 13 * cm
    filled_w = bar_w * min(pct_cuota, 1.0)
    empty_w  = bar_w - filled_w
    if empty_w < 0.05 * cm:
        bar = Table([[""]], colWidths=[bar_w], rowHeights=[14])
        bar.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, 0), color_semaforo),
            ("GRID",          (0, 0), (-1, -1), 0, colors.white),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
    else:
        bar = Table([["", ""]], colWidths=[filled_w, empty_w], rowHeights=[14])
        bar.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, 0), color_semaforo),
            ("BACKGROUND",    (1, 0), (1, 0), colors.HexColor("#2A2A2E")),
            ("GRID",          (0, 0), (-1, -1), 0, colors.white),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
    story.append(bar)
    story.append(Paragraph(
        f"{pct_cuota*100:.1f}% de la cuota  ·  "
        f"Ritmo esperado al día {dias_t}: {pct_esperado*100:.1f}%  ·  Estado: {estado_ritmo}",
        ParagraphStyle("bar_label", fontName="Helvetica", fontSize=7,
                       textColor=C_GRIS_CLARO, spaceAfter=6)
    ))
    story.append(Spacer(1, 4))

    req_ritmo = cuota / dias_m if dias_m else 0
    proy_ceh  = k.get("proyeccion_ceh", k["proyeccion_fin_mes"])
    ritmo_ceh = k.get("ritmo_ceh", k["ritmo_diario"])
    kpis_data = [
        ["Indicador", "Valor MTD", "Referencia", "Estado"],
        ["Altas C/E Habilitado",    f"{altas_ceh:,}",           f"Meta: {cuota:,}",               estado_ritmo],
        ["Total altas (todos)",     f"{k['total_altas']:,}",    "—",                              "—"],
        ["Total preventas",         f"{k['total_preventas']:,}","—",                              "—"],
        ["Conversión general",      f"{conv_gral*100:.1f}%",    "Ref. >77%",                      "OK" if conv_gral >= 0.77 else "REV"],
        ["Anulaciones",             f"{k['total_anulaciones']:,}", f"{pct_anul*100:.1f}% del pipe","OK" if pct_anul <= 0.07 else "ALTO"],
        ["Proyección C/E Hab.",     f"{proy_ceh:,}",            f"Meta: {cuota:,}",               "OK" if proy_ceh >= cuota else "RIESGO"],
        ["Ritmo C/E Hab./día",      f"{ritmo_ceh}",             f"Requerido: {req_ritmo:.1f}/día", estado_ritmo],
    ]

    t_kpis = Table(kpis_data, colWidths=[5.5*cm, 2.5*cm, 4*cm, 3*cm])
    est_kpis = tabla_estilo_base()
    for i, row in enumerate(kpis_data[1:], 1):
        c = estado_colores.get(str(row[3]), C_GRIS_CLARO)
        est_kpis.add("TEXTCOLOR", (3, i), (3, i), c)
    t_kpis.setStyle(est_kpis)
    story.append(t_kpis)
    story.append(Spacer(1, 10))

    # ── 2. FOCOS DE ATENCIÓN ────────────────────────
    story.append(Paragraph("2. Focos de Atención", styles["seccion"]))

    if faltantes > 0:
        req_diario_rest = faltantes / dias_rest if dias_rest > 0 else faltantes
        urgente = req_diario_rest > ritmo_ceh * 1.2
        story.append(Paragraph(
            f"Faltan <b>{faltantes:,}</b> altas C/E Habilitado para la meta. "
            f"Con {dias_rest} días restantes se necesitan "
            f"<b>{req_diario_rest:.1f}</b>/día (ritmo actual: {ritmo_ceh}/día).",
            styles["alerta"] if urgente else styles["cuerpo"]
        ))
    else:
        story.append(Paragraph(
            f"Meta mensual superada: {altas_ceh:,} altas C/E Habilitado vs {cuota:,}.",
            styles["ok"]
        ))

    if pct_riesgo > 0.08:
        story.append(Paragraph(
            f"{k['ventas_en_riesgo']:,} ventas ({pct_riesgo*100:.1f}%) en riesgo por score "
            f"insuficiente en Zona P2. Requiere acción de supervisores.",
            styles["alerta"]
        ))
    if k["sin_score"] > 500:
        story.append(Paragraph(
            f"{k['sin_score']:,} clientes sin score — priorizar obtención para evitar rechazos.",
            styles["alerta"]
        ))
    if k["no_venta"] > 300:
        story.append(Paragraph(
            f"{k['no_venta']:,} preventas en zonas No Venta "
            f"({pct(k['no_venta'], k['total_preventas'])}) — reforzar capacitación.",
            styles["alerta"]
        ))
    story.append(Spacer(1, 6))

    # ── 3. EVOLUCIÓN SEMANAL ────────────────────────
    if semanas:
        story.append(Paragraph("3. Evolución Semanal del Mes", styles["seccion"]))
        sem_data = [["Semana", "C/E Hab.", "Total altas", "Preventas", "Estado"]]
        for s in semanas:
            sem_data.append([
                s["label"],
                f"{s.get('altas_ceh', 0):,}",
                f"{s['altas']:,}",
                f"{s['preventas']:,}",
                "EN CURSO" if s.get("en_curso") else "Cerrada",
            ])
        tot_ceh = sum(s.get("altas_ceh", 0) for s in semanas)
        tot_a   = sum(s["altas"] for s in semanas)
        tot_p   = sum(s["preventas"] for s in semanas)
        sem_data.append(["TOTAL MTD", f"{tot_ceh:,}", f"{tot_a:,}", f"{tot_p:,}", "—"])

        t_sem = Table(sem_data, colWidths=[4.5*cm, 2*cm, 2.5*cm, 2.5*cm, 2*cm])
        est_sem = tabla_estilo_base()
        for i, s in enumerate(semanas, 1):
            if s.get("en_curso"):
                est_sem.add("BACKGROUND", (0, i), (-1, i), colors.HexColor("#162216"))
                est_sem.add("TEXTCOLOR",  (0, i), (-1, i), C_VERDE)
        total_row = len(sem_data) - 1
        est_sem.add("BACKGROUND", (0, total_row), (-1, total_row), C_GRIS)
        est_sem.add("TEXTCOLOR",  (0, total_row), (-1, total_row), C_BLANCO)
        est_sem.add("FONTNAME",   (0, total_row), (-1, total_row), "Helvetica-Bold")
        t_sem.setStyle(est_sem)
        story.append(t_sem)
        story.append(Spacer(1, 10))

    # ── 4. PLANES ──────────────────────────────────
    story.append(Paragraph("4. Análisis por Plan — Acumulado del Mes", styles["seccion"]))

    total_altas_planes = sum(p["altas"] for p in planes)
    plan_data = [["Plan", "Altas", "Preventas", "Conv.", "% Participación"]]
    for p in planes:
        conv_p = p["altas"] / p["preventas"] if p["preventas"] else 0
        part   = p["altas"] / total_altas_planes if total_altas_planes else 0
        plan_data.append([
            p["plan"],
            f"{p['altas']:,}",
            f"{p['preventas']:,}",
            f"{conv_p*100:.1f}%",
            f"{part*100:.1f}%",
        ])

    t_planes = Table(plan_data, colWidths=[5.5*cm, 1.8*cm, 2*cm, 1.8*cm, 3*cm])
    t_planes.setStyle(tabla_estilo_base())
    story.append(t_planes)

    top_plan  = max(planes, key=lambda x: x["altas"])
    low_conv  = min(planes, key=lambda x: x["altas"] / x["preventas"] if x["preventas"] else 1)
    best_conv = max(planes, key=lambda x: x["altas"] / x["preventas"] if x["preventas"] else 0)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"Mayor volumen: <b>{top_plan['plan']}</b> ({top_plan['altas']:,} altas, "
        f"{pct(top_plan['altas'], top_plan['preventas'])} conv.)",
        styles["cuerpo"]
    ))
    story.append(Paragraph(
        f"Menor conversión: <b>{low_conv['plan']}</b> "
        f"({pct(low_conv['altas'], low_conv['preventas'])} conv.) — revisar proceso de cierre.",
        styles["cuerpo"]
    ))

    # ── 5. ZONAS ─────────────────────────────────────
    story.append(Paragraph("5. Análisis por Zona Score P2", styles["seccion"]))

    zona_data = [["Zona", "Altas", "Preventas", "Conv.", "En Riesgo", "Sin Score"]]
    for z in zonas:
        zona_data.append([
            z["zona"],
            f"{z['altas']:,}",
            f"{z['preventas']:,}",
            pct(z["altas"], z["preventas"]),
            f"{z['en_riesgo']:,}" if z["en_riesgo"] else "—",
            f"{z['sin_score']:,}" if z["sin_score"] else "—",
        ])

    t_zonas = Table(zona_data, colWidths=[4.5*cm, 1.8*cm, 2*cm, 1.8*cm, 2.2*cm, 2.2*cm])
    est_zonas = tabla_estilo_base()
    for i, z in enumerate(zonas, start=1):
        if z["zona"] == "No Venta":
            est_zonas.add("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FFF0F0"))
    t_zonas.setStyle(est_zonas)
    story.append(t_zonas)

    # ── 6. VELOCIDAD DE INSTALACIÓN ─────────────────
    story.append(Paragraph("6. Velocidad de Instalación", styles["seccion"]))

    tramo_data = [["Tramo", "Altas", "% del Total"]]
    total_tramos = sum(t["altas"] for t in tramos)
    for t_item in tramos:
        tramo_data.append([
            t_item["tramo"],
            f"{t_item['altas']:,}",
            pct(t_item["altas"], total_tramos),
        ])

    t_tramos = Table(tramo_data, colWidths=[4*cm, 3*cm, 3*cm])
    t_tramos.setStyle(tabla_estilo_base())
    story.append(t_tramos)

    mismo_dia = next((t for t in tramos if t["tramo"] == "Mismo día"), None)
    un_dia    = next((t for t in tramos if t["tramo"] == "1 día"), None)
    rapidos   = (mismo_dia["altas"] if mismo_dia else 0) + (un_dia["altas"] if un_dia else 0)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"{pct(rapidos, total_tramos)} de instalaciones realizadas en 0-1 días — buen ritmo operativo.",
        styles["cuerpo"]
    ))

    # ── 7. TOP VENDEDORES ───────────────────────────
    story.append(Paragraph("7. Top 5 Vendedores del Mes", styles["seccion"]))

    vend_data = [["Vendedor", "Altas", "En Riesgo", "% Riesgo"]]
    for v in top_v:
        vend_data.append([
            v["vendedor"],
            f"{v['altas']:,}",
            f"{v['en_riesgo']:,}",
            pct(v["en_riesgo"], v["altas"]),
        ])

    t_vend = Table(vend_data, colWidths=[7*cm, 2.5*cm, 2.5*cm, 2.5*cm])
    est_vend = tabla_estilo_base()
    for i, v in enumerate(top_v, start=1):
        if v["altas"] and v["en_riesgo"] / v["altas"] > 0.12:
            est_vend.add("TEXTCOLOR", (3, i), (3, i), C_ROJO)
    t_vend.setStyle(est_vend)
    story.append(t_vend)

    # ── 8. RECOMENDACIONES ──────────────────────────
    story.append(Paragraph("8. Recomendaciones para el resto del mes", styles["seccion"]))

    recomendaciones = []

    if faltantes > 0 and dias_rest > 0:
        req_dia = faltantes / dias_rest
        if req_dia > ritmo_ceh * 1.1:
            recomendaciones.append(
                f"<b>Cuota en riesgo:</b> Se necesitan {req_dia:.1f} altas C/E Hab./día ({faltantes:,} faltantes "
                f"en {dias_rest} días, ritmo actual: {ritmo_ceh}/día). Priorizar cierres y reducir preventas sin seguimiento."
            )
        else:
            recomendaciones.append(
                f"<b>Cuota alcanzable:</b> Mantener ritmo de {ritmo_ceh}/día — "
                f"faltan {faltantes:,} altas C/E Hab. en {dias_rest} días ({req_dia:.1f}/día requerido)."
            )
    elif faltantes <= 0:
        recomendaciones.append(
            f"<b>Meta superada:</b> {altas_ceh:,} altas C/E Habilitado vs {cuota:,}. "
            f"Mantener ritmo hacia el próximo mes."
        )

    if pct_riesgo > 0.05:
        recomendaciones.append(
            f"<b>Score P2:</b> Revisar {k['ventas_en_riesgo']:,} ventas con score insuficiente — "
            f"supervisores deben validar antes de agendar instalación."
        )

    if k["sin_score"] > 500:
        recomendaciones.append(
            f"<b>Sin score:</b> Gestionar score para {k['sin_score']:,} clientes. "
            f"Sin score = riesgo de rechazo en instalación."
        )

    recomendaciones.append(
        f"<b>Plan foco:</b> Impulsar <b>{best_conv['plan']}</b> — mayor conversión del portafolio "
        f"({pct(best_conv['altas'], best_conv['preventas'])} conv.)."
    )

    if k["no_venta"] > 300:
        recomendaciones.append(
            f"<b>Zonas No Venta:</b> {k['no_venta']:,} preventas en zonas bloqueadas — "
            f"reforzar briefing de zonas en reunión de inicio de semana."
        )

    for r in recomendaciones:
        story.append(Paragraph(f"→  {r}", styles["cuerpo"]))

    # ── PIE ─────────────────────────────────────────
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_GRIS_CLARO))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Generado el {datos['fecha_reporte']} · Fuente: WinForce / Power BI · Aliv Telecom · Confidencial",
        styles["nota"]
    ))

    doc.build(story)
    print(f"PDF generado: {nombre_archivo}")
    return nombre_archivo


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("Generando reporte semanal Aliv Telecom...")
    datos = cargar_datos()
    archivo = generar_pdf(datos)
    print(f"Listo: {archivo}")