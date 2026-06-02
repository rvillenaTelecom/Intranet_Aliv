"""
ReporteDiario.py
========================
Genera el reporte diario de Aliv Telecom en PDF.
Consulta SQL Server directamente (tabla winforce_lima).

Uso:
    python ReporteDiario.py

Requisitos:
    pip install reportlab sqlalchemy pyodbc

El PDF se guarda como: Reporte_Diario_Aliv_YYYY-MM-DD.pdf
"""

import sys
import os
from datetime import datetime, timedelta
import calendar
import sqlalchemy as sa
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER

sys.path.insert(0, os.path.dirname(__file__))
from db_config import get_engine

# ──────────────────────────────────────────────
# CONFIGURACIÓN
# ──────────────────────────────────────────────

# Cuota C/E Habilitado por mes — actualizar cada mes
CUOTA_POR_MES = {
    1: 230,
    2: 265,
    3: 231,
    4: 310,
    5: 320,
    6: 320,
    7: 320,
    8: 320,
    9: 320,
    10: 320,
    11: 320,
    12: 320,
}

TIPO_DOMICILIO = "Condominio/Edificio"

# Colores Aliv
C_NARANJA    = colors.HexColor("#F47920")
C_OSCURO     = colors.HexColor("#1C1C1E")
C_VERDE      = colors.HexColor("#1D9E75")
C_ROJO       = colors.HexColor("#E24B4A")
C_AMARILLO   = colors.HexColor("#EF9F27")
C_BLANCO     = colors.white
C_GRIS_CLARO = colors.HexColor("#AAAAAA")


# ──────────────────────────────────────────────
# EXTRACCIÓN DE DATOS (SQL Server)
# ──────────────────────────────────────────────

def extraer_datos(ayer: datetime.date) -> dict:
    mes_num      = ayer.month
    cuota        = CUOTA_POR_MES.get(mes_num, 320)
    dias_totales = 30
    primer_dia   = ayer.replace(day=1)
    dias_trans   = (ayer - primer_dia).days + 1
    dias_rest      = dias_totales - dias_trans
    dias_reales    = calendar.monthrange(ayer.year, mes_num)[1]
    dias_rest_real = dias_totales - dias_trans
    tipo           = TIPO_DOMICILIO

    # Compute dynamic calendar weeks starting on Monday
    cal = calendar.Calendar(firstweekday=0)
    month_days = cal.monthdayscalendar(ayer.year, mes_num)
    semanas_def = []
    for week in month_days:
        days = [d for d in week if d != 0]
        if days:
            semanas_def.append((days[0], days[-1]))

    engine = get_engine()

    with engine.connect() as conn:
        # Single query to fetch MTD Ejecutada rows
        rows = conn.execute(sa.text("""
            SELECT [Fecha programación], [Tipo de domicilio], [Plan], [Zona_KML]
            FROM winforce_lima
            WHERE [Estado orden] = 'Ejecutada'
            AND TRY_CONVERT(DATE, LEFT([Fecha programación], 10), 105) >= :primer_dia
            AND TRY_CONVERT(DATE, LEFT([Fecha programación], 10), 105) <= :ayer
        """), {"primer_dia": primer_dia, "ayer": ayer}).fetchall()

    # Parse rows in Python
    parsed_rows = []
    for row in rows:
        fp_str, dom_tipo, plan, zona = row
        if not fp_str:
            continue
        try:
            fp_date = datetime.strptime(fp_str[:10].replace('/', '-'), "%d-%m-%Y").date()
        except Exception:
            continue
        parsed_rows.append({
            "date": fp_date,
            "tipo": dom_tipo,
            "plan": plan or "—",
            "zona": zona or "—"
        })

    # Aggregations in Python
    ceh_mtd = sum(1 for r in parsed_rows if r["tipo"] == tipo)
    ceh_ayer = sum(1 for r in parsed_rows if r["tipo"] == tipo and r["date"] == ayer)
    total_ayer_lima = sum(1 for r in parsed_rows if r["date"] == ayer)
    total_mtd_lima = len(parsed_rows)

    # Por plan ayer C/E Hab
    plan_ayer_counts = {}
    for r in parsed_rows:
        if r["tipo"] == tipo and r["date"] == ayer:
            plan_ayer_counts[r["plan"]] = plan_ayer_counts.get(r["plan"], 0) + 1
    por_plan = [{"Plan": p, "altas": c} for p, c in sorted(plan_ayer_counts.items(), key=lambda x: x[1], reverse=True)[:8]]

    # Por zona ayer C/E Hab
    zona_ayer_counts = {}
    for r in parsed_rows:
        if r["tipo"] == tipo and r["date"] == ayer:
            zona_ayer_counts[r["zona"]] = zona_ayer_counts.get(r["zona"], 0) + 1
    por_zona = [{"Zona_KML": z, "altas": c} for z, c in sorted(zona_ayer_counts.items(), key=lambda x: x[1], reverse=True)]

    # Por plan MTD C/E Hab
    plan_mtd_counts = {}
    for r in parsed_rows:
        if r["tipo"] == tipo:
            plan_mtd_counts[r["plan"]] = plan_mtd_counts.get(r["plan"], 0) + 1
    por_plan_mtd = [{"Plan": p, "altas": c} for p, c in sorted(plan_mtd_counts.items(), key=lambda x: x[1], reverse=True)[:8]]

    # Por zona MTD C/E Hab
    zona_mtd_counts = {}
    for r in parsed_rows:
        if r["tipo"] == tipo:
            zona_mtd_counts[r["zona"]] = zona_mtd_counts.get(r["zona"], 0) + 1
    por_zona_mtd = [{"Zona_KML": z, "altas": c} for z, c in sorted(zona_mtd_counts.items(), key=lambda x: x[1], reverse=True)]

    # Altas C/E reales por semana
    semanas_altas = []
    for s_ini, s_fin in semanas_def:
        f_i = primer_dia.replace(day=s_ini)
        f_f = min(primer_dia.replace(day=s_fin), ayer)
        if f_i > ayer:
            semanas_altas.append(None)
            continue
        count_sem = sum(1 for r in parsed_rows if r["tipo"] == tipo and f_i <= r["date"] <= f_f)
        semanas_altas.append(count_sem)

    # Métricas
    ritmo_ceh  = round(ceh_mtd / dias_trans, 1) if dias_trans > 0 else 0
    proyeccion = round(ceh_mtd / dias_trans * dias_totales) if dias_trans > 0 else 0
    pct_cuota    = ceh_mtd / cuota if cuota else 0
    pct_esperado = dias_trans / dias_totales
    ratio        = pct_cuota / pct_esperado if pct_esperado > 0 else 0
    faltantes    = max(cuota - ceh_mtd, 0)
    req_ritmo    = round(cuota / dias_totales, 1)
    req_restante = round(faltantes / dias_rest, 1) if dias_rest > 0 else faltantes
    promedio_dia         = ritmo_ceh
    vs_promedio          = round(ceh_ayer - ritmo_ceh, 1)
    pct_mes_real         = dias_trans / dias_totales
    ritmo_necesario_real = round(faltantes / dias_rest_real, 1) if dias_rest_real > 0 else faltantes
    ritmo_ideal_hoy      = round(cuota * dias_trans / dias_totales)

    if ratio >= 0.95:
        estado, color_sem = "EN RITMO",         C_VERDE
    elif ratio >= 0.75:
        estado, color_sem = "LIGERAMENTE BAJO", C_AMARILLO
    else:
        estado, color_sem = "BAJO RITMO",       C_ROJO

    return {
        "ayer":            ayer,
        "mes_num":         mes_num,
        "cuota":           cuota,
        "tipo":            tipo,
        "dias_trans":      dias_trans,
        "dias_totales":    dias_totales,
        "dias_rest":       dias_rest,
        "ceh_mtd":         ceh_mtd,
        "ceh_ayer":        ceh_ayer,
        "total_ayer_lima": total_ayer_lima,
        "total_mtd_lima":  total_mtd_lima,
        "ritmo_ceh":       ritmo_ceh,
        "proyeccion":      proyeccion,
        "pct_cuota":       pct_cuota,
        "pct_esperado":    pct_esperado,
        "estado":          estado,
        "color_sem":       color_sem,
        "faltantes":       faltantes,
        "req_ritmo":       req_ritmo,
        "req_restante":    req_restante,
        "promedio_dia":          promedio_dia,
        "vs_promedio":           vs_promedio,
        "dias_reales":           dias_totales,
        "dias_rest_real":        dias_rest_real,
        "pct_mes_real":          pct_mes_real,
        "ritmo_necesario_real":  ritmo_necesario_real,
        "ritmo_ideal_hoy":       ritmo_ideal_hoy,
        "semanas_def":           semanas_def,
        "semanas_altas":         semanas_altas,
        "por_plan":        por_plan,
        "por_zona":        por_zona,
        "por_plan_mtd":    por_plan_mtd,
        "por_zona_mtd":    por_zona_mtd,
    }


# ──────────────────────────────────────────────
# PDF
# ──────────────────────────────────────────────

def tabla_base():
    return TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0),  C_OSCURO),
        ("TEXTCOLOR",      (0, 0), (-1, 0),  C_BLANCO),
        ("FONTNAME",       (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, 0),  8),
        ("ALIGN",          (0, 0), (-1, 0),  "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F9F9F9"), colors.white]),
        ("FONTNAME",       (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",       (0, 1), (-1, -1), 8),
        ("ALIGN",          (1, 1), (-1, -1), "CENTER"),
        ("ALIGN",          (0, 1), (0, -1),  "LEFT"),
        ("GRID",           (0, 0), (-1, -1), 0.3, colors.HexColor("#DDDDDD")),
        ("TOPPADDING",     (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
        ("LEFTPADDING",    (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 6),
    ])


def barra_progreso(pct, color_sem, bar_w=13*cm):
    filled = bar_w * min(pct, 1.0)
    empty  = bar_w - filled
    if empty < 0.05*cm:
        t = Table([[""]], colWidths=[bar_w], rowHeights=[12])
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(0,0),color_sem),
                                ("GRID",(0,0),(-1,-1),0,colors.white),
                                ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]))
    else:
        t = Table([["",""]], colWidths=[filled, empty], rowHeights=[12])
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(0,0),color_sem),
                                ("BACKGROUND",(1,0),(1,0),colors.HexColor("#2A2A2E")),
                                ("GRID",(0,0),(-1,-1),0,colors.white),
                                ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]))
    return t


def generar_pdf(d: dict) -> str:
    ayer = d["ayer"]
    nombre = f"Reporte_Diario_CE_Aliv_{ayer.strftime('%Y-%m-%d')}.pdf"

    S = {}
    S["titulo"]   = ParagraphStyle("t",   fontName="Helvetica-Bold", fontSize=20,
                                   textColor=C_NARANJA, alignment=TA_CENTER, spaceAfter=4)
    S["sub"]      = ParagraphStyle("s",   fontName="Helvetica", fontSize=10,
                                   textColor=C_GRIS_CLARO, alignment=TA_CENTER, spaceAfter=14)
    S["seccion"]  = ParagraphStyle("sec", fontName="Helvetica-Bold", fontSize=12,
                                   textColor=C_NARANJA, spaceBefore=14, spaceAfter=6)
    S["cuerpo"]   = ParagraphStyle("c",   fontName="Helvetica", fontSize=9,
                                   textColor=colors.HexColor("#333333"), spaceAfter=4, leading=14)
    S["sub_gray"] = ParagraphStyle("sg",  fontName="Helvetica", fontSize=8,
                                   textColor=C_GRIS_CLARO, spaceAfter=4)
    S["bar_lbl"]  = ParagraphStyle("bl",  fontName="Helvetica", fontSize=7,
                                   textColor=C_GRIS_CLARO, spaceAfter=6)
    S["alerta"]   = ParagraphStyle("al",  fontName="Helvetica-Bold", fontSize=9,
                                   textColor=C_ROJO, spaceAfter=3)
    S["ok"]       = ParagraphStyle("ok",  fontName="Helvetica-Bold", fontSize=9,
                                   textColor=C_VERDE, spaceAfter=3)
    S["nota"]     = ParagraphStyle("n",   fontName="Helvetica-Oblique", fontSize=8,
                                   textColor=C_GRIS_CLARO, spaceAfter=4)
    S["kpi_lbl"]  = ParagraphStyle("kl",  fontName="Helvetica", fontSize=8,
                                   textColor=C_GRIS_CLARO, alignment=TA_CENTER)
    S["kpi_val"]  = ParagraphStyle("kv",  fontName="Helvetica-Bold", fontSize=22,
                                   textColor=C_NARANJA, alignment=TA_CENTER)
    S["kpi_val16"] = ParagraphStyle("kv16", fontName="Helvetica-Bold", fontSize=16,
                                    alignment=TA_CENTER)
    S["kpi_val22"] = ParagraphStyle("kv22", fontName="Helvetica-Bold", fontSize=22,
                                    alignment=TA_CENTER)

    ESTADO_COLOR = {"EN RITMO": C_VERDE, "LIGERAMENTE BAJO": C_AMARILLO,
                    "BAJO RITMO": C_ROJO, "OK": C_VERDE, "RIESGO": C_ROJO}

    doc = SimpleDocTemplate(nombre, pagesize=A4,
                            rightMargin=1.8*cm, leftMargin=1.8*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    story = []

    mes_nombre = ayer.strftime("%B %Y").capitalize()

    # ── ENCABEZADO ───────────────────────────────
    story.append(Paragraph("ALIV TELECOM — WIN DISTRIBUIDORA", S["titulo"]))
    story.append(Paragraph(
        f"Reporte Diario · {ayer.strftime('%d/%m/%Y')} · {mes_nombre} · "
        f"Dia {d['dias_trans']} de {d['dias_totales']}",
        S["sub"]
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=C_NARANJA))
    story.append(Spacer(1, 10))

    # ── SITUACIÓN ACTUAL ─────────────────────────
    dia_str   = str(ayer.day)
    mes_upper = ayer.strftime("%B").upper()
    story.append(Paragraph(f"SITUACION ACTUAL ({dia_str} {mes_upper})", S["seccion"]))

    sa_data = [
        ("Altas instaladas",    f"{d['ceh_mtd']:,}",               f"de {d['cuota']:,} cuota",
         C_ROJO if d["pct_cuota"] < d["pct_mes_real"] else C_VERDE),
        ("Dias transcurridos",  f"{d['dias_trans']}/{d['dias_reales']}",
         f"{d['pct_mes_real']*100:.1f}% del mes",                  C_OSCURO),
        ("Alcance actual",      f"{d['pct_cuota']*100:.2f}%",
         f"vs. {d['pct_mes_real']*100:.1f}% ideal",                d["color_sem"]),
        ("Altas faltantes",     f"{d['faltantes']:,}",
         f"en {d['dias_rest_real']} dias",
         C_ROJO if d["faltantes"] > 0 else C_VERDE),
        ("Ritmo necesario",     f"{d['ritmo_necesario_real']}/dia",
         f"vs. {d['ritmo_ceh']} actual",                           C_NARANJA),
    ]
    cw5 = 3.48 * cm
    row_sa_lbl = [Paragraph(c[0], S["kpi_lbl"]) for c in sa_data]
    row_sa_val = [Paragraph(c[1], S["kpi_val16"]) for c in sa_data]
    row_sa_ref = [Paragraph(c[2], S["kpi_lbl"]) for c in sa_data]

    t_sa = Table([row_sa_lbl, row_sa_val, row_sa_ref],
                 colWidths=[cw5] * 5, rowHeights=[0.65*cm, 1.4*cm, 0.6*cm])
    sa_style = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#F9F9F9")),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])
    for i, (_, _, _, color) in enumerate(sa_data):
        sa_style.add("TEXTCOLOR", (i, 1), (i, 1), color)
    t_sa.setStyle(sa_style)
    story.append(t_sa)
    story.append(Spacer(1, 4))
    story.append(barra_progreso(d["pct_cuota"], d["color_sem"]))
    story.append(Paragraph(
        f"Progreso hacia cuota  ·  {d['ceh_mtd']:,} / {d['cuota']:,}",
        S["bar_lbl"]
    ))
    story.append(Paragraph(
        f"Ritmo ideal hoy: <b>{d['ritmo_ideal_hoy']} altas</b> "
        f"({d['pct_mes_real']*100:.1f}%)",
        S["sub_gray"]
    ))
    story.append(Spacer(1, 12))

    # ── PLAN SEMANA A SEMANA ─────────────────────
    story.append(Paragraph(
        f"PLAN SEMANA A SEMANA (OBJETIVO: {d['cuota']:,})", S["seccion"]
    ))

    mes_corto    = ayer.strftime("%b").lower()
    semanas_def  = d["semanas_def"]
    semanas_altas = d["semanas_altas"]

    virtual_cum  = 0
    sem_headers, sem_values, sem_subs, sem_val_colors = [], [], [], []

    for i, (s_ini, s_fin) in enumerate(semanas_def):
        altas_real   = semanas_altas[i]
        days_in_week = s_fin - s_ini + 1

        if altas_real is not None:
            past = ayer.day > s_fin
            sem_headers.append(f"Sem {i+1} ({'ya paso' if past else 'en curso'})")
            sem_values.append(str(altas_real))
            sem_subs.append("Base real" if past else "Actual")
            sem_val_colors.append(C_GRIS_CLARO if past else C_NARANJA)
            virtual_cum += altas_real
        else:
            remaining    = d["cuota"] - virtual_cum
            future_days  = sum(
                semanas_def[j][1] - semanas_def[j][0] + 1
                for j in range(i, len(semanas_def))
                if semanas_altas[j] is None
            )
            needed = (remaining if i == len(semanas_def) - 1 or future_days == 0
                      else round(remaining * days_in_week / future_days))
            needed = max(needed, 0)
            virtual_cum += needed
            
            if s_ini <= 15 <= s_fin:
                extra = "quincena"
            elif i == len(semanas_def) - 1:
                extra = "cierre"
            else:
                extra = ""
            sub   = f"Meta: {virtual_cum:,} total" + (f" · {extra}" if extra else "")
            sem_headers.append(f"Sem {i+1} · {s_ini}-{s_fin} {mes_corto}")
            sem_values.append(f"+{needed}")
            sem_subs.append(sub)
            sem_val_colors.append(C_NARANJA)

    num_weeks = len(semanas_def)
    cw       = 17.4 / num_weeks * cm
    row_sh  = [Paragraph(h, S["kpi_lbl"]) for h in sem_headers]
    row_sv  = [Paragraph(sem_values[i], S["kpi_val22"]) for i in range(num_weeks)]
    row_ss  = [Paragraph(s, S["kpi_lbl"]) for s in sem_subs]

    t_sem = Table([row_sh, row_sv, row_ss],
                  colWidths=[cw] * num_weeks, rowHeights=[0.7*cm, 2*cm, 0.8*cm])
    sem_style = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.white),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])
    for i, altas_real in enumerate(semanas_altas):
        sem_style.add("TEXTCOLOR", (i, 1), (i, 1), sem_val_colors[i])
        if altas_real is not None:
            if ayer.day > semanas_def[i][1]:
                sem_style.add("BACKGROUND", (i, 0), (i, -1), colors.HexColor("#F0F0F0"))
            else:
                sem_style.add("BOX", (i, 0), (i, -1), 1.5, C_NARANJA)
    t_sem.setStyle(sem_style)
    story.append(t_sem)
    story.append(Spacer(1, 12))

    # ── 1. SEGUIMIENTO CUOTA C/E HABILITADO ──────
    story.append(Paragraph(f"1. Cuota del Mes — {d['tipo']}", S["seccion"]))
    story.append(Paragraph(
        f"<b>{d['ceh_mtd']:,}</b> altas C/E Habilitado de <b>{d['cuota']:,}</b> meta  ·  "
        f"Ritmo actual: <b>{d['ritmo_ceh']}/dia</b>  ·  "
        f"Proyeccion cierre: <b>{d['proyeccion']:,}</b>",
        S["cuerpo"]
    ))
    story.append(Paragraph(
        f"Altas C/E Hab. ayer: {d['ceh_ayer']}  ·  "
        f"Altas totales Lima MTD: {d['total_mtd_lima']:,}",
        S["sub_gray"]
    ))
    story.append(Spacer(1, 4))
    story.append(barra_progreso(d["pct_cuota"], d["color_sem"]))
    story.append(Paragraph(
        f"{d['pct_cuota']*100:.1f}% de la cuota  ·  "
        f"Esperado al dia {d['dias_trans']}: {d['pct_esperado']*100:.1f}%  ·  "
        f"Estado: {d['estado']}",
        S["bar_lbl"]
    ))
    story.append(Spacer(1, 6))

    kpis_data = [
        ["Indicador", "Valor MTD", "Referencia", "Estado"],
        ["Altas C/E Habilitado MTD",    f"{d['ceh_mtd']:,}",       f"Meta: {d['cuota']:,}",            d["estado"]],
        ["Altas C/E Hab. ayer",         f"{d['ceh_ayer']}",         f"Promedio: {d['ritmo_ceh']}/dia",  "OK" if d["ceh_ayer"] >= d["ritmo_ceh"] else "RIESGO"],
        ["% Alcance cuota",             f"{d['pct_cuota']*100:.1f}%", f"Esperado: {d['pct_esperado']*100:.1f}%", d["estado"]],
        ["Proyeccion fin de mes",       f"{d['proyeccion']:,}",     f"Meta: {d['cuota']:,}",            "OK" if d["proyeccion"] >= d["cuota"] else "RIESGO"],
        ["Ritmo actual C/E Hab./dia",   f"{d['ritmo_ceh']}",        f"Requerido: {d['req_ritmo']}/dia", d["estado"]],
        ["Ritmo necesario (restante)",  f"{d['req_restante']}/dia", f"{d['dias_rest']} dias restantes", "OK" if d["req_restante"] <= d["ritmo_ceh"]*1.1 else "RIESGO"],
    ]
    t_kpis = Table(kpis_data, colWidths=[5.5*cm, 2.5*cm, 4*cm, 3*cm])
    est = tabla_base()
    for i, row in enumerate(kpis_data[1:], 1):
        c = ESTADO_COLOR.get(str(row[3]), C_GRIS_CLARO)
        est.add("TEXTCOLOR", (3, i), (3, i), c)
    t_kpis.setStyle(est)
    story.append(t_kpis)
    story.append(Spacer(1, 10))

    # ── 2. FOCOS DE ATENCIÓN ─────────────────────
    story.append(Paragraph("2. Focos de Atencion", S["seccion"]))
    if d["faltantes"] > 0:
        urgente = d["req_restante"] > d["ritmo_ceh"] * 1.2
        story.append(Paragraph(
            f"Faltan <b>{d['faltantes']:,}</b> altas C/E Habilitado. "
            f"Con {d['dias_rest']} dias restantes se requieren "
            f"<b>{d['req_restante']}/dia</b> (ritmo actual: {d['ritmo_ceh']}/dia).",
            S["alerta"] if urgente else S["cuerpo"]
        ))
    else:
        story.append(Paragraph(
            f"Meta mensual superada: {d['ceh_mtd']:,} altas vs {d['cuota']:,} de cuota.",
            S["ok"]
        ))
    if d["ceh_ayer"] < d["ritmo_ceh"] * 0.8 and d["ceh_ayer"] > 0:
        story.append(Paragraph(
            f"Ayer se registraron solo {d['ceh_ayer']} altas C/E Hab. "
            f"(bajo el ritmo de {d['ritmo_ceh']}/dia). Revisar actividad de vendedores.",
            S["alerta"]
        ))
    story.append(Spacer(1, 6))

    # ── 3. ALTAS AYER ────────────────────────────
    story.append(Paragraph("3. Altas del Dia de Ayer", S["seccion"]))
    vs     = d["vs_promedio"]
    vs_str = f"+{vs}" if vs > 0 else str(vs)

    cards_l = [Paragraph(lbl, S["kpi_lbl"]) for lbl in
               ["TOTAL LIMA AYER", "C/E HAB. AYER", "PROMEDIO/DIA MTD", "DIAS RESTANTES"]]
    cards_v = [Paragraph(val, S["kpi_val"]) for val in [
        str(d["total_ayer_lima"]),
        str(d["ceh_ayer"]),
        str(d["promedio_dia"]),
        str(d["dias_rest"]),
    ]]
    t_cards = Table([cards_l, cards_v], colWidths=[3.8*cm]*4, rowHeights=[1*cm, 1.8*cm])
    t_cards.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#F9F9F9")),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t_cards)
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Ayer vs promedio diario del mes: <b>{vs_str} altas</b>  ·  "
        f"Acumulado Lima MTD: <b>{d['total_mtd_lima']:,}</b> en {d['dias_trans']} dias.",
        S["cuerpo"]
    ))
    story.append(Spacer(1, 8))

    # ── 5. POR PLAN ──────────────────────────────
    if d.get("por_plan"):
        story.append(Paragraph("5. Altas C/E Hab. por Plan — Ayer", S["seccion"]))
        data = [["Plan", "Altas C/E Hab."]]
        for p in d["por_plan"]:
            nombre_plan = p.get("Plan", p.get("plan", "—"))
            altas_plan  = p.get("altas", "0")
            data.append([nombre_plan, str(altas_plan)])
        t = Table(data, colWidths=[11*cm, 4*cm])
        t.setStyle(tabla_base())
        story.append(t)
        story.append(Spacer(1, 10))

    # ── 6. ZONAS LIMA ────────────────────────────
    if d.get("por_zona"):
        story.append(Paragraph("6. Altas C/E Hab. por Zona — Ayer", S["seccion"]))
        data = [["Zona KML", "Altas C/E Hab."]]
        for z in d["por_zona"]:
            zona_nombre = z.get("Zona_KML", z.get("zona", "—"))
            altas_zona  = z.get("altas", "0")
            data.append([zona_nombre, str(altas_zona)])
        t = Table(data, colWidths=[11*cm, 4*cm])
        t.setStyle(tabla_base())
        story.append(t)
        story.append(Spacer(1, 10))

    # ── 7. POR PLAN MTD ──────────────────────────
    if d.get("por_plan_mtd"):
        story.append(Paragraph("7. Altas C/E Hab. por Plan — Situacion Actual", S["seccion"]))
        data = [["Plan", "Altas C/E Hab."]]
        for p in d["por_plan_mtd"]:
            nombre_plan = p.get("Plan", p.get("plan", "—"))
            altas_plan  = p.get("altas", "0")
            data.append([nombre_plan, str(altas_plan)])
        t = Table(data, colWidths=[11*cm, 4*cm])
        t.setStyle(tabla_base())
        story.append(t)
        story.append(Spacer(1, 10))

    # ── 8. ZONAS LIMA MTD ────────────────────────
    if d.get("por_zona_mtd"):
        story.append(Paragraph("8. Altas C/E Hab. por Zona — Situacion Actual", S["seccion"]))
        data = [["Zona KML", "Altas C/E Hab."]]
        for z in d["por_zona_mtd"]:
            zona_nombre = z.get("Zona_KML", z.get("zona", "—"))
            altas_zona  = z.get("altas", "0")
            data.append([zona_nombre, str(altas_zona)])
        t = Table(data, colWidths=[11*cm, 4*cm])
        t.setStyle(tabla_base())
        story.append(t)
        story.append(Spacer(1, 10))

    # ── PIE ─────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_GRIS_CLARO))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} · "
        f"Fuente: WinForce / SQL Server · Aliv Telecom · Confidencial",
        S["nota"]
    ))

    doc.build(story)
    print(f"PDF generado: {nombre}")
    return nombre


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

if __name__ == "__main__":
    ayer = datetime.now().date() - timedelta(days=1)
    print(f"Generando reporte diario para: {ayer.strftime('%d/%m/%Y')}")

    try:
        datos = extraer_datos(ayer)
        print(f"   Datos: {datos['ceh_mtd']} altas C/E Hab. MTD · {datos['ceh_ayer']} ayer · {datos['total_mtd_lima']} Lima MTD")
    except Exception as e:
        print(f"Error extrayendo datos de SQL: {e}")
        sys.exit(1)

    generar_pdf(datos)
