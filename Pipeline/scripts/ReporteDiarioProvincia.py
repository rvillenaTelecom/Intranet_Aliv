"""
ReporteDiarioProvincia.py
==========================
Genera el reporte diario de Provincia de Aliv Telecom en PDF.
Consulta SQL Server directamente (tabla winforce_provincia).
Excluye Lima y Callao. Sin filtro de Tipo de domicilio.

Uso:
    python ReporteDiarioProvincia.py

El PDF se guarda como: Reporte_Diario_Provincia_YYYY-MM-DD.pdf
"""

import sys
import os
from datetime import datetime, timedelta
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
# CONFIGURACIÓN — actualizar cada mes
# ──────────────────────────────────────────────

# Cuota total Provincia por mes
CUOTA_POR_MES = {
    1: 700,
    2: 800,
    3: 750,
    4: 900,
    5: 1054,
    6: 1054,
    7: 1054,
    8: 1054,
    9: 1054,
    10: 1054,
    11: 1054,
    12: 1054,
}

# Cuota por departamento — actualizar cada mes {mes: {departamento: cuota}}
CUOTA_DEPARTAMENTO = {
    5: {
        "PIURA":        540,
        "LA LIBERTAD":  365,
        "LAMBAYEQUE":    72,
        "ANCASH":        27,
        "JUNIN":        20,
        "AREQUIPA":     15,
        "CUSCO":        15,
    },
}

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
    cuota        = CUOTA_POR_MES.get(mes_num, 1054)
    dias_totales = 30
    primer_dia   = ayer.replace(day=1)
    dias_trans   = (ayer - primer_dia).days + 1
    dias_rest    = dias_totales - dias_trans
    cuota_dept   = CUOTA_DEPARTAMENTO.get(mes_num, {})

    engine = get_engine()

    with engine.connect() as conn:
        # KPIs totales MTD + ayer (sin Lima/Callao)
        row = conn.execute(sa.text("""
            SELECT
                SUM(CASE WHEN CAST([Fecha de registro] AS DATE) >= :primer_dia AND CAST([Fecha de registro] AS DATE) <= :ayer THEN 1 ELSE 0 END) AS total_mtd,
                SUM(CASE WHEN [Estado orden] = 'Ejecutada' AND TRY_CONVERT(DATE, LEFT([Fecha programación], 10), 105) >= :primer_dia AND TRY_CONVERT(DATE, LEFT([Fecha programación], 10), 105) <= :ayer THEN 1 ELSE 0 END) AS altas_mtd,
                SUM(CASE WHEN CAST([Fecha de registro] AS DATE) = :ayer THEN 1 ELSE 0 END) AS total_ayer,
                SUM(CASE WHEN [Estado orden] = 'Ejecutada' AND TRY_CONVERT(DATE, LEFT([Fecha programación], 10), 105) = :ayer THEN 1 ELSE 0 END) AS altas_ayer
            FROM winforce_provincia
            WHERE (
                (CAST([Fecha de registro] AS DATE) >= :primer_dia AND CAST([Fecha de registro] AS DATE) <= :ayer)
                OR
                ([Estado orden] = 'Ejecutada' AND TRY_CONVERT(DATE, LEFT([Fecha programación], 10), 105) >= :primer_dia AND TRY_CONVERT(DATE, LEFT([Fecha programación], 10), 105) <= :ayer)
            )
            AND [Departamento] NOT IN ('LIMA', 'CALLAO')
        """), {"ayer": ayer, "primer_dia": primer_dia}).fetchone()

        total_mtd  = int(row[0] or 0)   # preventas MTD
        altas_mtd  = int(row[1] or 0)   # ejecutadas MTD
        total_ayer = int(row[2] or 0)   # preventas ayer
        altas_ayer = int(row[3] or 0)   # ejecutadas ayer

        # Desglose por departamento MTD
        rows_dept = conn.execute(sa.text("""
            SELECT
                [Departamento],
                SUM(CASE WHEN CAST([Fecha de registro] AS DATE) >= :primer_dia AND CAST([Fecha de registro] AS DATE) <= :ayer THEN 1 ELSE 0 END) AS preventas,
                SUM(CASE WHEN [Estado orden] = 'Ejecutada' AND TRY_CONVERT(DATE, LEFT([Fecha programación], 10), 105) >= :primer_dia AND TRY_CONVERT(DATE, LEFT([Fecha programación], 10), 105) <= :ayer THEN 1 ELSE 0 END) AS altas
            FROM winforce_provincia
            WHERE (
                (CAST([Fecha de registro] AS DATE) >= :primer_dia AND CAST([Fecha de registro] AS DATE) <= :ayer)
                OR
                ([Estado orden] = 'Ejecutada' AND TRY_CONVERT(DATE, LEFT([Fecha programación], 10), 105) >= :primer_dia AND TRY_CONVERT(DATE, LEFT([Fecha programación], 10), 105) <= :ayer)
            )
            AND [Departamento] NOT IN ('LIMA', 'CALLAO')
            GROUP BY [Departamento]
            ORDER BY altas DESC
        """), {"ayer": ayer, "primer_dia": primer_dia}).fetchall()

        por_departamento = []
        for r in rows_dept:
            dept      = r[0]
            prev      = int(r[1] or 0)
            altas     = int(r[2] or 0)
            cuota_d   = cuota_dept.get(dept, 0)
            proyec    = round(altas / dias_trans * dias_totales) if dias_trans > 0 else 0
            pct_proy  = proyec / cuota_d * 100 if cuota_d else None
            pct_alc   = altas / cuota_d * 100 if cuota_d else None
            conv      = altas / prev * 100 if prev else 0
            # Estado departamento
            if cuota_d:
                ratio = (altas / cuota_d) / (dias_trans / dias_totales)
                if ratio >= 0.95:
                    estado_d = "En ritmo"
                elif ratio >= 0.75:
                    estado_d = "Riesgo"
                else:
                    estado_d = "Bajo"
            else:
                estado_d = "—"
            por_departamento.append({
                "dept":     dept,
                "prev":     prev,
                "altas":    altas,
                "proyec":   proyec,
                "pct_proy": pct_proy,
                "cuota_d":  cuota_d,
                "pct_alc":  pct_alc,
                "conv":     conv,
                "estado_d": estado_d,
            })

        # Top vendedores ayer
        rows_v = conn.execute(sa.text("""
            SELECT TOP 10 [Vendedor real], COUNT(*) AS altas
            FROM winforce_provincia
            WHERE [Estado orden] = 'Ejecutada'
            AND TRY_CONVERT(DATE, LEFT([Fecha programación], 10), 105) = :ayer
            AND [Departamento] NOT IN ('LIMA', 'CALLAO')
            GROUP BY [Vendedor real]
            ORDER BY altas DESC
        """), {"ayer": ayer}).fetchall()
        top_v = [{"Vendedor real": r[0], "altas": r[1]} for r in rows_v]

        # Top vendedores MTD
        rows_v_mtd = conn.execute(sa.text("""
            SELECT TOP 10 [Vendedor real], COUNT(*) AS altas
            FROM winforce_provincia
            WHERE [Estado orden] = 'Ejecutada'
            AND TRY_CONVERT(DATE, LEFT([Fecha programación], 10), 105) >= :primer_dia
            AND TRY_CONVERT(DATE, LEFT([Fecha programación], 10), 105) <= :ayer
            AND [Departamento] NOT IN ('LIMA', 'CALLAO')
            GROUP BY [Vendedor real]
            ORDER BY altas DESC
        """), {"ayer": ayer, "primer_dia": primer_dia}).fetchall()
        top_v_mtd = {r[0]: r[1] for r in rows_v_mtd}

        # Por plan ayer
        rows_p = conn.execute(sa.text("""
            SELECT TOP 8 [Plan], COUNT(*) AS altas
            FROM winforce_provincia
            WHERE [Estado orden] = 'Ejecutada'
            AND TRY_CONVERT(DATE, LEFT([Fecha programación], 10), 105) = :ayer
            AND [Departamento] NOT IN ('LIMA', 'CALLAO')
            GROUP BY [Plan]
            ORDER BY altas DESC
        """), {"ayer": ayer}).fetchall()
        por_plan = [{"Plan": r[0], "altas": r[1]} for r in rows_p]

        # Por plan MTD
        rows_p_mtd = conn.execute(sa.text("""
            SELECT TOP 8 [Plan], COUNT(*) AS altas
            FROM winforce_provincia
            WHERE [Estado orden] = 'Ejecutada'
            AND TRY_CONVERT(DATE, LEFT([Fecha programación], 10), 105) >= :primer_dia
            AND TRY_CONVERT(DATE, LEFT([Fecha programación], 10), 105) <= :ayer
            AND [Departamento] NOT IN ('LIMA', 'CALLAO')
            GROUP BY [Plan]
            ORDER BY altas DESC
        """), {"ayer": ayer, "primer_dia": primer_dia}).fetchall()
        por_plan_mtd = {r[0]: r[1] for r in rows_p_mtd}

    # Métricas totales
    ritmo      = round(altas_mtd / dias_trans, 1) if dias_trans > 0 else 0
    proyeccion = round(altas_mtd / dias_trans * dias_totales) if dias_trans > 0 else 0
    pct_cuota    = altas_mtd / cuota if cuota else 0
    pct_esperado = dias_trans / dias_totales
    ratio        = pct_cuota / pct_esperado if pct_esperado > 0 else 0
    faltantes    = max(cuota - altas_mtd, 0)
    req_ritmo    = round(cuota / dias_totales, 1)
    req_restante = round(faltantes / dias_rest, 1) if dias_rest > 0 else faltantes
    vs_promedio  = round(altas_ayer - ritmo, 1)

    if ratio >= 0.95:
        estado, color_sem = "EN RITMO",         C_VERDE
    elif ratio >= 0.75:
        estado, color_sem = "LIGERAMENTE BAJO", C_AMARILLO
    else:
        estado, color_sem = "BAJO RITMO",       C_ROJO

    return {
        "ayer":              ayer,
        "mes_num":           mes_num,
        "cuota":             cuota,
        "dias_trans":        dias_trans,
        "dias_totales":      dias_totales,
        "dias_rest":         dias_rest,
        "total_mtd":         total_mtd,
        "altas_mtd":         altas_mtd,
        "total_ayer":        total_ayer,
        "altas_ayer":        altas_ayer,
        "ritmo":             ritmo,
        "proyeccion":        proyeccion,
        "pct_cuota":         pct_cuota,
        "pct_esperado":      pct_esperado,
        "estado":            estado,
        "color_sem":         color_sem,
        "faltantes":         faltantes,
        "req_ritmo":         req_ritmo,
        "req_restante":      req_restante,
        "vs_promedio":       vs_promedio,
        "por_departamento":  por_departamento,
        "top_vendedores":    top_v,
        "top_vendedores_mtd": top_v_mtd,
        "por_plan":          por_plan,
        "por_plan_mtd":      por_plan_mtd,
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


def color_estado(estado_str):
    return {"En ritmo": C_VERDE, "Riesgo": C_AMARILLO, "Bajo": C_ROJO}.get(estado_str, C_GRIS_CLARO)


def generar_pdf(d: dict) -> str:
    ayer   = d["ayer"]
    nombre = f"Reporte_Diario_Provincia_{ayer.strftime('%Y-%m-%d')}.pdf"

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

    ESTADO_COLOR = {"EN RITMO": C_VERDE, "LIGERAMENTE BAJO": C_AMARILLO,
                    "BAJO RITMO": C_ROJO, "OK": C_VERDE, "RIESGO": C_ROJO}

    doc = SimpleDocTemplate(nombre, pagesize=A4,
                            rightMargin=1.8*cm, leftMargin=1.8*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    story = []

    mes_nombre = ayer.strftime("%B %Y").capitalize()

    # ── ENCABEZADO ───────────────────────────────
    story.append(Paragraph("ALIV TELECOM — WIN DISTRIBUIDORA PROVINCIA", S["titulo"]))
    story.append(Paragraph(
        f"Reporte Diario Provincia · {ayer.strftime('%d/%m/%Y')} · {mes_nombre} · "
        f"Dia {d['dias_trans']} de {d['dias_totales']}",
        S["sub"]
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=C_NARANJA))
    story.append(Spacer(1, 10))

    # ── 1. SEGUIMIENTO CUOTA ─────────────────────
    story.append(Paragraph("1. Cuota del Mes — Provincia", S["seccion"]))
    story.append(Paragraph(
        f"<b>{d['altas_mtd']:,}</b> altas de <b>{d['cuota']:,}</b> meta  ·  "
        f"Ritmo actual: <b>{d['ritmo']}/dia</b>  ·  "
        f"Proyeccion cierre: <b>{d['proyeccion']:,}</b>",
        S["cuerpo"]
    ))
    story.append(Paragraph(
        f"Altas ayer: {d['altas_ayer']}  ·  Preventas MTD: {d['total_mtd']:,}  ·  "
        f"Conversion MTD: {d['altas_mtd']/d['total_mtd']*100:.1f}%" if d['total_mtd'] else
        f"Altas ayer: {d['altas_ayer']}  ·  Preventas MTD: {d['total_mtd']:,}",
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
        ["Altas Provincia MTD",        f"{d['altas_mtd']:,}",        f"Meta: {d['cuota']:,}",              d["estado"]],
        ["Altas ayer",                 f"{d['altas_ayer']}",          f"Promedio: {d['ritmo']}/dia",        "OK" if d["altas_ayer"] >= d["ritmo"] else "RIESGO"],
        ["% Alcance cuota",            f"{d['pct_cuota']*100:.1f}%",  f"Esperado: {d['pct_esperado']*100:.1f}%", d["estado"]],
        ["Proyeccion fin de mes",      f"{d['proyeccion']:,}",        f"Meta: {d['cuota']:,}",              "OK" if d["proyeccion"] >= d["cuota"] else "RIESGO"],
        ["Ritmo actual / dia",         f"{d['ritmo']}",               f"Requerido: {d['req_ritmo']}/dia",   d["estado"]],
        ["Ritmo necesario (restante)", f"{d['req_restante']}/dia",    f"{d['dias_rest']} dias restantes",   "OK" if d["req_restante"] <= d["ritmo"]*1.1 else "RIESGO"],
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
        urgente = d["req_restante"] > d["ritmo"] * 1.2
        story.append(Paragraph(
            f"Faltan <b>{d['faltantes']:,}</b> altas. "
            f"Con {d['dias_rest']} dias restantes se requieren "
            f"<b>{d['req_restante']}/dia</b> (ritmo actual: {d['ritmo']}/dia).",
            S["alerta"] if urgente else S["cuerpo"]
        ))
    else:
        story.append(Paragraph(
            f"Meta mensual superada: {d['altas_mtd']:,} altas vs {d['cuota']:,} de cuota.",
            S["ok"]
        ))
    if d["altas_ayer"] < d["ritmo"] * 0.8 and d["altas_ayer"] > 0:
        story.append(Paragraph(
            f"Ayer se registraron solo {d['altas_ayer']} altas "
            f"(bajo el ritmo de {d['ritmo']}/dia). Revisar actividad de vendedores.",
            S["alerta"]
        ))
    story.append(Spacer(1, 6))

    # ── 3. ALTAS AYER ────────────────────────────
    story.append(Paragraph("3. Altas del Dia de Ayer", S["seccion"]))
    vs     = d["vs_promedio"]
    vs_str = f"+{vs}" if vs > 0 else str(vs)

    cards_l = [Paragraph(lbl, S["kpi_lbl"]) for lbl in
               ["PROV. AYER", "PROV. MTD", "PROMEDIO/DIA", "DIAS RESTANTES"]]
    cards_v = [Paragraph(val, S["kpi_val"]) for val in [
        str(d["altas_ayer"]),
        str(d["altas_mtd"]),
        str(d["ritmo"]),
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
        f"Ayer vs promedio diario Provincia: <b>{vs_str} altas</b>  ·  "
        f"Acumulado Provincia MTD: <b>{d['altas_mtd']:,}</b> en {d['dias_trans']} dias.",
        S["cuerpo"]
    ))
    story.append(Spacer(1, 8))

    # ── 4. POR DEPARTAMENTO ──────────────────────
    if d["por_departamento"]:
        story.append(Paragraph("4. Por Departamento — MTD", S["seccion"]))

        # Totales para la fila de cierre
        tot_prev  = sum(r["prev"]  for r in d["por_departamento"])
        tot_altas = sum(r["altas"] for r in d["por_departamento"])
        tot_proy  = round(tot_altas / d["dias_trans"] * d["dias_totales"]) if d["dias_trans"] else 0
        tot_conv  = tot_altas / tot_prev * 100 if tot_prev else 0

        hdrs = ["Departamento", "Preventas", "Altas", "Proy. Cierre",
                "% Proy.", "Cuota Mes", "% Alcance", "Conversion", "Estado"]
        col_w = [3.5*cm, 1.6*cm, 1.3*cm, 2*cm, 1.5*cm, 1.8*cm, 1.8*cm, 1.8*cm, 1.7*cm]

        data = [hdrs]
        for r in d["por_departamento"]:
            proy_str = str(r["proyec"])
            pproy    = f"{r['pct_proy']:.1f}%" if r["pct_proy"] is not None else "—"
            cuota_s  = str(r["cuota_d"]) if r["cuota_d"] else "—"
            palc     = f"{r['pct_alc']:.1f}%" if r["pct_alc"] is not None else "—"
            conv_s   = f"{r['conv']:.1f}%"
            data.append([
                r["dept"].title(),
                str(r["prev"]),
                str(r["altas"]),
                proy_str,
                pproy,
                cuota_s,
                palc,
                conv_s,
                r["estado_d"],
            ])

        # Fila total
        tot_pct_proy = f"{tot_proy / d['cuota'] * 100:.1f}%" if d["cuota"] else "—"
        data.append([
            "TOTAL",
            str(tot_prev),
            str(tot_altas),
            str(tot_proy),
            tot_pct_proy,
            str(d["cuota"]),
            f"{d['pct_cuota']*100:.1f}%",
            f"{tot_conv:.1f}%",
            d["estado"],
        ])

        t_dept = Table(data, colWidths=col_w)
        est_dept = tabla_base()

        # Colorear columna Estado y fila total
        for i, row in enumerate(data[1:], 1):
            c = color_estado(str(row[8]))
            est_dept.add("TEXTCOLOR", (8, i), (8, i), c)
            if i == len(data) - 1:  # fila total
                est_dept.add("FONTNAME",   (0, i), (-1, i), "Helvetica-Bold")
                est_dept.add("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F0F0F0"))

        t_dept.setStyle(est_dept)
        story.append(t_dept)
        story.append(Spacer(1, 10))

    # ── 5. TOP VENDEDORES ────────────────────────
    if d["top_vendedores"]:
        story.append(Paragraph("5. Top Vendedores — Ayer vs MTD", S["seccion"]))
        data = [["Vendedor", "Altas Ayer", "Altas MTD"]]
        for v in d["top_vendedores"]:
            nombre = v.get("Vendedor real", "—")
            altas_ayer = str(v.get("altas", "0"))
            altas_mtd  = str(d["top_vendedores_mtd"].get(nombre, "—"))
            data.append([nombre, altas_ayer, altas_mtd])
        t = Table(data, colWidths=[8.5*cm, 3*cm, 3.5*cm])
        t.setStyle(tabla_base())
        story.append(t)
        story.append(Spacer(1, 10))

    # ── 6. POR PLAN ──────────────────────────────
    if d["por_plan"]:
        story.append(Paragraph("6. Altas por Plan — Ayer vs MTD", S["seccion"]))
        data = [["Plan", "Altas Ayer", "Altas MTD"]]
        for p in d["por_plan"]:
            plan = p.get("Plan", "—")
            altas_ayer = str(p.get("altas", "0"))
            altas_mtd  = str(d["por_plan_mtd"].get(plan, "—"))
            data.append([plan, altas_ayer, altas_mtd])
        t = Table(data, colWidths=[8.5*cm, 3*cm, 3.5*cm])
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
    print(f"Generando reporte diario Provincia para: {ayer.strftime('%d/%m/%Y')}")

    try:
        datos = extraer_datos(ayer)
        print(f"   Datos: {datos['altas_mtd']} altas MTD · {datos['altas_ayer']} ayer · "
              f"{datos['total_mtd']} preventas MTD · "
              f"{len(datos['por_departamento'])} departamentos")
    except Exception as e:
        print(f"Error extrayendo datos de SQL: {e}")
        sys.exit(1)

    generar_pdf(datos)
