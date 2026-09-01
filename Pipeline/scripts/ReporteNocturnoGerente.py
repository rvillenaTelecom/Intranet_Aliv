"""
ReporteNocturnoGerente.py
=========================
Reporte nocturno gerencial — MTD hasta HOY con foco en el día actual.
Misma estructura que el reporte de mañana pero "Altas hoy" en vez de "Altas ayer".

Uso:
    python ReporteNocturnoGerente.py

PDF: Reporte_Nocturno_Aliv_YYYY-MM-DD.pdf
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
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER

sys.path.insert(0, os.path.dirname(__file__))
from db_config import get_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from cuotas_config import cuota_lima

VERTICAL_TIPOS = {'Condominio/Edificio'}

_AGENCIAS = ['ALIV', 'DEZANET', 'GYA', 'LOTTUS', 'SIPION', 'SUB-AGENCIAS']

def _norm_agencia(raw):
    ag = str(raw).upper().strip() if raw else 'ALIV'
    if 'ALIV'    in ag: return 'ALIV'
    if 'DEZANET' in ag: return 'DEZANET'
    if 'GYA'     in ag: return 'GYA'
    if 'SIPION'  in ag or 'SIPIÓN' in ag: return 'SIPION'
    if 'LOTTUS'  in ag or 'LOTUS'  in ag: return 'LOTTUS'
    return 'SUB-AGENCIAS'


C_OSCURO     = colors.HexColor("#1C1C1E")
C_VERDE      = colors.HexColor("#1D9E75")
C_ROJO       = colors.HexColor("#E24B4A")
C_AMARILLO   = colors.HexColor("#EF9F27")
C_BLANCO     = colors.white
C_GRIS_CLARO = colors.HexColor("#AAAAAA")
C_AZUL       = colors.HexColor("#2E86AB")
C_NARANJA    = colors.HexColor("#F47920")
C_VIOLETA    = colors.HexColor("#7B2D8B")


# ──────────────────────────────────────────────
# HELPERS DE ESTILO
# ──────────────────────────────────────────────

def calcular_estado(ratio):
    if ratio >= 0.95:
        return "EN RITMO", C_VERDE
    elif ratio >= 0.75:
        return "LIGERAMENTE BAJO", C_AMARILLO
    return "BAJO RITMO", C_ROJO


def tabla_base():
    return TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0),  C_OSCURO),
        ("TEXTCOLOR",      (0, 0), (-1, 0),  C_BLANCO),
        ("FONTNAME",       (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, 0),  7.5),
        ("ALIGN",          (0, 0), (-1, 0),  "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F9F9F9"), colors.white]),
        ("FONTNAME",       (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",       (0, 1), (-1, -1), 7.5),
        ("ALIGN",          (1, 1), (-1, -1), "CENTER"),
        ("ALIGN",          (0, 1), (0, -1),  "LEFT"),
        ("GRID",           (0, 0), (-1, -1), 0.3, colors.HexColor("#DDDDDD")),
        ("TOPPADDING",     (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 3),
        ("LEFTPADDING",    (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 5),
    ])

def _total_row_style(st, last):
    st.add("BACKGROUND", (0, last), (-1, last), C_OSCURO)
    st.add("TEXTCOLOR",  (0, last), (-1, last), C_BLANCO)
    st.add("FONTNAME",   (0, last), (-1, last), "Helvetica-Bold")
    return st

def tabla_ventas():
    s = tabla_base()
    s.add("BACKGROUND", (0, 0), (-1, 0), C_AZUL)
    return s

def tabla_altas():
    s = tabla_base()
    s.add("BACKGROUND", (0, 0), (-1, 0), C_VERDE)
    return s

def cabecera_seccion(texto, color_fondo):
    st = ParagraphStyle("hs", fontName="Helvetica-Bold", fontSize=12,
                        textColor=C_BLANCO, alignment=TA_CENTER)
    t = Table([[Paragraph(texto, st)]], colWidths=[17 * cm], rowHeights=[0.85 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), color_fondo),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


# ──────────────────────────────────────────────
# EXTRACCIÓN DE DATOS — MTD hasta hoy
# ──────────────────────────────────────────────

def extraer_datos(hoy):
    mes_num    = hoy.month
    primer_dia = hoy.replace(day=1)
    dias_trans = (hoy - primer_dia).days + 1
    dias_totales = 25
    dias_rest    = max(dias_totales - dias_trans, 0)

    engine = get_engine()

    with engine.connect() as conn:
        # Altas MTD (desde el 1ro del mes hasta hoy)
        rows_raw = conn.execute(sa.text("""
            SELECT wl.[Fecha programación], wl.[Tipo de domicilio], wl.[Plan],
                   wl.[Zona_KML], wl.[Distrito],
                   ISNULL(da.agencia, wl.[Agencia]) AS agencia_raw
            FROM winforce_lima wl
            LEFT JOIN dim_usuarios_Aliv da ON da.vendedor = wl.[Vendedor real]
            WHERE wl.[Estado orden] = 'Ejecutada'
              AND TRY_CONVERT(DATE, LEFT(wl.[Fecha programación], 10), 105) >= :primer_dia
              AND TRY_CONVERT(DATE, LEFT(wl.[Fecha programación], 10), 105) <= :hoy
              AND wl.[Departamento] IN ('LIMA', 'CALLAO')
              AND LOWER(wl.[Distrito]) NOT IN ('barranca', 'chancay', 'huacho', 'hualmay', 'huaral')
        """), {"primer_dia": primer_dia, "hoy": hoy}).fetchall()

        # Ventas MTD
        ventas_raw = conn.execute(sa.text("""
            SELECT CAST(wl.[Fecha de registro] AS DATE),
                   wl.[Tipo de domicilio], wl.[Plan],
                   ISNULL(da.agencia, wl.[Agencia]) AS agencia_raw
            FROM winforce_lima wl
            LEFT JOIN dim_usuarios_Aliv da ON da.vendedor = wl.[Vendedor real]
            WHERE MONTH(wl.[Fecha de registro]) = :mes
              AND YEAR(wl.[Fecha de registro]) = :anio
              AND CAST(wl.[Fecha de registro] AS DATE) <= :hoy
              AND wl.[Plan] IS NOT NULL AND wl.[Plan] <> ''
              AND wl.[Departamento] IN ('LIMA', 'CALLAO')
              AND LOWER(wl.[Distrito]) NOT IN ('barranca', 'chancay', 'huacho', 'hualmay', 'huaral')
        """), {"mes": mes_num, "anio": hoy.year, "hoy": hoy}).fetchall()

    altas = []
    for row in rows_raw:
        fp_str, dom_tipo, plan, zona, distrito, agencia_raw = row
        if not fp_str:
            continue
        try:
            fp_date = datetime.strptime(fp_str[:10].replace('/', '-'), "%d-%m-%Y").date()
        except Exception:
            continue
        altas.append({
            "date":     fp_date,
            "plan":     plan or "—",
            "zona":     zona or "—",
            "distrito": distrito or "—",
            "agencia":  _norm_agencia(agencia_raw),
            "vertical": (dom_tipo or "") in VERTICAL_TIPOS,
        })

    ventas = []
    for vrow in ventas_raw:
        vfecha, vdom, vplan, vagencia = vrow
        if not vfecha:
            continue
        try:
            vd = vfecha if hasattr(vfecha, 'year') else datetime.strptime(str(vfecha)[:10], "%Y-%m-%d").date()
        except Exception:
            continue
        ventas.append({
            "date":     vd,
            "plan":     vplan or "—",
            "agencia":  _norm_agencia(vagencia),
            "vertical": (vdom or "") in VERTICAL_TIPOS,
        })

    def top_n(filas, campo, n=8):
        counts = {}
        for r in filas:
            counts[r[campo]] = counts.get(r[campo], 0) + 1
        return sorted(counts.items(), key=lambda x: x[1], reverse=True)[:n]

    def ag_agg(filas):
        res = {ag: {"mtd": 0, "hoy": 0} for ag in _AGENCIAS}
        for r in filas:
            ag = r["agencia"] if r["agencia"] in res else "SUB-AGENCIAS"
            res[ag]["mtd"] += 1
            if r["date"] == hoy:
                res[ag]["hoy"] += 1
        return res

    def plan_ag(filas, n=7):
        pivot = {}
        for r in filas:
            plan = r["plan"]
            ag   = r["agencia"] if r["agencia"] in _AGENCIAS else "SUB-AGENCIAS"
            if plan not in pivot:
                pivot[plan] = {a: 0 for a in _AGENCIAS}
            pivot[plan][ag] += 1
        items = sorted(pivot.items(), key=lambda x: sum(x[1].values()), reverse=True)[:n]
        return [(pl, v, sum(v.values())) for pl, v in items]

    def metricas(filas, cuota, ventas_filas=None):
        mtd   = len(filas)
        hoy_c = sum(1 for r in filas if r["date"] == hoy)
        ritmo = round(mtd / dias_trans, 1) if dias_trans else 0
        proy  = round(mtd / dias_trans * dias_totales) if dias_trans else 0
        pct_esp = dias_trans / dias_totales

        if cuota:
            pct_cuota = mtd / cuota
            ratio     = pct_cuota / pct_esp if pct_esp else 0
            faltantes = max(cuota - mtd, 0)
            req_dia   = round(faltantes / dias_rest, 1) if dias_rest else faltantes
            estado, color_sem = calcular_estado(ratio)
        else:
            pct_cuota = 0
            ratio     = 0
            faltantes = 0
            req_dia   = 0
            estado, color_sem = "SIN CUOTA", C_GRIS_CLARO

        filas_hoy   = [r for r in filas if r["date"] == hoy]
        v_filas_hoy = [r for r in (ventas_filas or []) if r["date"] == hoy]

        return {
            "mtd": mtd, "hoy_c": hoy_c, "cuota": cuota,
            "ritmo": ritmo, "proy": proy,
            "pct_cuota": pct_cuota, "pct_esp": pct_esp,
            "req_dia": req_dia, "faltantes": faltantes,
            "estado": estado, "color_sem": color_sem,
            "ventas_hoy": len(v_filas_hoy),
            "ventas_mtd": len(ventas_filas or []),
            "por_plan_hoy":         top_n(filas_hoy, "plan"),
            "por_plan_mtd":         top_n(filas, "plan"),
            "por_plan_ventas_hoy":  top_n(v_filas_hoy, "plan"),
            "por_plan_ventas_mtd":  top_n(ventas_filas or [], "plan"),
            "ag_altas":             ag_agg(filas),
            "ag_ventas":            ag_agg(ventas_filas or []),
            "plan_ag_a":            plan_ag(filas),
            "plan_ag_v":            plan_ag(ventas_filas or []),
        }

    altas_v  = [r for r in altas  if r["vertical"]]
    altas_h  = [r for r in altas  if not r["vertical"]]
    ventas_v = [r for r in ventas if r["vertical"]]
    ventas_h = [r for r in ventas if not r["vertical"]]

    return {
        "hoy":          hoy,
        "mes_num":      mes_num,
        "dias_trans":   dias_trans,
        "dias_totales": dias_totales,
        "dias_rest":    dias_rest,
        "total_mtd":    len(altas),
        "total_hoy":    sum(1 for r in altas if r["date"] == hoy),
        "vertical":     metricas(altas_v, cuota_lima(mes_num, 'Vertical'), ventas_v),
        "horizontal":   metricas(altas_h, cuota_lima(mes_num, 'Horizontal'), ventas_h),
    }


# ──────────────────────────────────────────────
# SECCIÓN DEL PDF (Vertical u Horizontal)
# ──────────────────────────────────────────────

def seccion_area(story, label, m, datos, S, color_acento):
    dias_trans   = datos["dias_trans"]
    dias_rest    = datos["dias_rest"]

    ESTADO_COLOR = {
        "EN RITMO": C_VERDE, "LIGERAMENTE BAJO": C_AMARILLO,
        "BAJO RITMO": C_ROJO, "OK": C_VERDE, "RIESGO": C_ROJO,
        "SIN CUOTA": C_GRIS_CLARO,
    }

    story.append(cabecera_seccion(f"  {label.upper()}", color_acento))
    story.append(Spacer(1, 8))

    # ── Tabla de indicadores ─────────────────────
    ind = [["Indicador", "Valor MTD", "Referencia", "Estado"]]
    ind.append(["Altas instaladas MTD", str(m["mtd"]),
                f"Meta: {m['cuota']}" if m["cuota"] else "sin cuota asignada",
                m["estado"]])
    ind.append(["Altas hoy", str(m["hoy_c"]),
                f"Ritmo: {m['ritmo']}/día",
                "OK" if m["hoy_c"] >= m["ritmo"] else "RIESGO"])
    if m["cuota"]:
        ind.append(["% Avance cuota", f"{m['pct_cuota']*100:.1f}%",
                    f"Ideal día {dias_trans}: {m['pct_esp']*100:.0f}%",
                    m["estado"]])
        ind.append(["Proyección cierre", str(m["proy"]),
                    f"Meta: {m['cuota']}",
                    "OK" if m["proy"] >= m["cuota"] else "RIESGO"])
        ind.append(["Ritmo actual/día", str(m["ritmo"]),
                    f"Necesario: {m['req_dia']}/día ({dias_rest} días restantes)",
                    "OK" if m["ritmo"] >= m["req_dia"] else "RIESGO"])
    else:
        ind.append(["Proyección cierre", str(m["proy"]), "a fin de mes", "—"])
        ind.append(["Ritmo actual/día", str(m["ritmo"]), "—", "—"])

    t_ind = Table(ind, colWidths=[6*cm, 2.8*cm, 4.7*cm, 3.5*cm])
    est = tabla_base()
    for i, row in enumerate(ind[1:], 1):
        est.add("TEXTCOLOR", (3, i), (3, i), ESTADO_COLOR.get(str(row[3]), C_GRIS_CLARO))
        if i == 1:
            est.add("FONTNAME", (1, i), (1, i), "Helvetica-Bold")
    t_ind.setStyle(est)
    story.append(t_ind)
    story.append(Spacer(1, 8))

    # ── Planes hoy ───────────────────────────────
    pv_hoy = dict(m["por_plan_ventas_hoy"])
    total_v_hoy = m["ventas_hoy"] or 1
    total_a_hoy = m["hoy_c"] or 1

    if m["por_plan_hoy"] or m["por_plan_ventas_hoy"]:
        story.append(Paragraph("Planes instalados — Hoy", S["sub_sec"]))
        p_data = [["Plan", "Ventas", "%V", "Altas", "%A"]]
        planes_vistos = set()
        for plan, cnt in m["por_plan_hoy"]:
            v_cnt = pv_hoy.get(plan, 0)
            p_data.append([str(plan)[:40],
                           str(v_cnt), f"{v_cnt/total_v_hoy*100:.1f}%",
                           str(cnt),   f"{cnt/total_a_hoy*100:.1f}%"])
            planes_vistos.add(plan)
        for plan, v_cnt in m["por_plan_ventas_hoy"]:
            if plan not in planes_vistos:
                p_data.append([str(plan)[:40],
                               str(v_cnt), f"{v_cnt/total_v_hoy*100:.1f}%",
                               "0", "0.0%"])
        p_data.append(["TOTAL", str(m["ventas_hoy"]), "—", str(m["hoy_c"]), "—"])
        t = Table(p_data, colWidths=[7*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm])
        st_p = tabla_base()
        st_p.add("BACKGROUND", (1, 0), (2, 0), C_AZUL)
        st_p.add("BACKGROUND", (3, 0), (4, 0), C_VERDE)
        _total_row_style(st_p, len(p_data) - 1)
        t.setStyle(st_p)
        story.append(t)
        story.append(Spacer(1, 6))

    # ── Planes MTD ───────────────────────────────
    pv_mtd = dict(m["por_plan_ventas_mtd"])
    total_v_mtd = m["ventas_mtd"] or 1
    total_a_mtd = m["mtd"] or 1

    if m["por_plan_mtd"]:
        story.append(Paragraph("Planes instalados — Mes actual", S["sub_sec"]))
        p_data = [["Plan", "Ventas", "%V", "Altas", "%A"]]
        for plan, cnt in m["por_plan_mtd"]:
            v_cnt = pv_mtd.get(plan, 0)
            p_data.append([str(plan)[:40],
                           str(v_cnt), f"{v_cnt/total_v_mtd*100:.1f}%",
                           str(cnt),   f"{cnt/total_a_mtd*100:.1f}%"])
        p_data.append(["TOTAL", str(m["ventas_mtd"]), "—", str(m["mtd"]), "—"])
        t = Table(p_data, colWidths=[7*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm])
        st_m = tabla_base()
        st_m.add("BACKGROUND", (1, 0), (2, 0), C_AZUL)
        st_m.add("BACKGROUND", (3, 0), (4, 0), C_VERDE)
        _total_row_style(st_m, len(p_data) - 1)
        t.setStyle(st_m)
        story.append(t)
        story.append(Spacer(1, 6))

    # ── Agencias ─────────────────────────────────
    ag_v = m["ag_ventas"]
    ag_a = m["ag_altas"]
    _ag_hdr = [""] + _AGENCIAS + ["Total"]

    story.append(Paragraph("Ventas por agencia — Mes actual", S["sub_v"]))
    ag_vdata = [
        _ag_hdr,
        ["Ventas MTD"]  + [str(ag_v[ag]["mtd"])  for ag in _AGENCIAS]
                        + [str(sum(ag_v[ag]["mtd"]  for ag in _AGENCIAS))],
        ["Ventas hoy"]  + [str(ag_v[ag]["hoy"])  for ag in _AGENCIAS]
                        + [str(sum(ag_v[ag]["hoy"]  for ag in _AGENCIAS))],
    ]
    t_agv = Table(ag_vdata, colWidths=[3*cm] + [1.9*cm]*6 + [2.6*cm])
    t_agv.setStyle(tabla_ventas())
    story.append(t_agv)
    story.append(Spacer(1, 4))

    story.append(Paragraph("Altas por agencia — Mes actual", S["sub_a"]))
    ag_adata = [
        _ag_hdr,
        ["Altas MTD"]  + [str(ag_a[ag]["mtd"])  for ag in _AGENCIAS]
                       + [str(sum(ag_a[ag]["mtd"]  for ag in _AGENCIAS))],
        ["Altas hoy"]  + [str(ag_a[ag]["hoy"])  for ag in _AGENCIAS]
                       + [str(sum(ag_a[ag]["hoy"]  for ag in _AGENCIAS))],
    ]
    t_aga = Table(ag_adata, colWidths=[3*cm] + [1.9*cm]*6 + [2.6*cm])
    t_aga.setStyle(tabla_altas())
    story.append(t_aga)
    story.append(Spacer(1, 8))

    # ── Pivot Ventas Plan × Agencia ──────────────
    piv_hdr = ["Plan"] + _AGENCIAS + ["Total"]
    if m["plan_ag_v"]:
        story.append(Paragraph("Ventas por plan y agencia — Mes actual", S["sub_v"]))
        piv_v = [piv_hdr]
        for plan, ag_cnts, total in m["plan_ag_v"]:
            piv_v.append([str(plan)[:28]] + [str(ag_cnts[ag]) for ag in _AGENCIAS] + [str(total)])
        piv_v.append(["TOTAL"]
                     + [str(ag_v[ag]["mtd"]) for ag in _AGENCIAS]
                     + [str(sum(ag_v[ag]["mtd"] for ag in _AGENCIAS))])
        t_pv = Table(piv_v, colWidths=[4*cm] + [1.8*cm]*6 + [2.2*cm])
        st_pv = tabla_ventas()
        _total_row_style(st_pv, len(piv_v) - 1)
        t_pv.setStyle(st_pv)
        story.append(t_pv)
        story.append(Spacer(1, 4))

    # ── Pivot Altas Plan × Agencia ───────────────
    if m["plan_ag_a"]:
        story.append(Paragraph("Altas por plan y agencia — Mes actual", S["sub_a"]))
        piv_a = [piv_hdr]
        for plan, ag_cnts, total in m["plan_ag_a"]:
            piv_a.append([str(plan)[:28]] + [str(ag_cnts[ag]) for ag in _AGENCIAS] + [str(total)])
        piv_a.append(["TOTAL"]
                     + [str(ag_a[ag]["mtd"]) for ag in _AGENCIAS]
                     + [str(sum(ag_a[ag]["mtd"] for ag in _AGENCIAS))])
        t_pa = Table(piv_a, colWidths=[4*cm] + [1.8*cm]*6 + [2.2*cm])
        st_pa = tabla_altas()
        _total_row_style(st_pa, len(piv_a) - 1)
        t_pa.setStyle(st_pa)
        story.append(t_pa)
        story.append(Spacer(1, 6))


# ──────────────────────────────────────────────
# PDF PRINCIPAL
# ──────────────────────────────────────────────

def generar_pdf(datos):
    hoy    = datos["hoy"]
    nombre = f"Reporte_Nocturno_Aliv_{hoy.strftime('%Y-%m-%d')}.pdf"

    S = {}
    S["titulo"]    = ParagraphStyle("t",  fontName="Helvetica-Bold", fontSize=17,
                                    textColor=C_VIOLETA, alignment=TA_CENTER, spaceAfter=3)
    S["sub"]       = ParagraphStyle("s",  fontName="Helvetica", fontSize=9,
                                    textColor=C_GRIS_CLARO, alignment=TA_CENTER, spaceAfter=8)
    S["nota"]      = ParagraphStyle("n",  fontName="Helvetica-Oblique", fontSize=7,
                                    textColor=C_GRIS_CLARO, spaceAfter=4)
    S["sub_sec"]   = ParagraphStyle("ss", fontName="Helvetica-Bold", fontSize=8.5,
                                    textColor=C_OSCURO, spaceBefore=4, spaceAfter=2)
    S["sub_v"]     = ParagraphStyle("sv", fontName="Helvetica-Bold", fontSize=8.5,
                                    textColor=C_AZUL,  spaceBefore=6, spaceAfter=2)
    S["sub_a"]     = ParagraphStyle("sa", fontName="Helvetica-Bold", fontSize=8.5,
                                    textColor=C_VERDE, spaceBefore=6, spaceAfter=2)

    doc = SimpleDocTemplate(nombre, pagesize=A4,
                            rightMargin=1.8*cm, leftMargin=1.8*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    story = []

    mv = datos["vertical"]
    mh = datos["horizontal"]
    dias_trans   = datos["dias_trans"]
    dias_totales = datos["dias_totales"]
    mes_nombre   = hoy.strftime("%B %Y").capitalize()

    def encabezado_pagina():
        story.append(Paragraph("ALIV TELECOM — REPORTE NOCTURNO", S["titulo"]))
        story.append(Paragraph(
            f"Cierre del día {hoy.strftime('%d/%m/%Y')} · {mes_nombre} · "
            f"Día {dias_trans} de {dias_totales} (base 25)",
            S["sub"]
        ))
        story.append(HRFlowable(width="100%", thickness=1.5, color=C_VIOLETA))
        story.append(Spacer(1, 8))

    # ── PÁGINA 1 — Resumen + Vertical ────────────
    encabezado_pagina()

    # Tabla resumen Lima Total
    _ec = {"EN RITMO": C_VERDE, "LIGERAMENTE BAJO": C_AMARILLO,
           "BAJO RITMO": C_ROJO, "SIN CUOTA": C_GRIS_CLARO}

    res_data = [
        ["Métrica",              "Lima Total",             "Vertical",                                          "Horizontal"],
        ["Altas instaladas MTD", str(datos["total_mtd"]),  str(mv["mtd"]),                                      str(mh["mtd"])],
        ["Altas hoy",            str(datos["total_hoy"]),  str(mv["hoy_c"]),                                    str(mh["hoy_c"])],
        ["Cuota del mes",        "—",                      str(mv["cuota"]) if mv["cuota"] else "—",            str(mh["cuota"]) if mh["cuota"] else "—"],
        ["% Avance cuota",       "—",
         f"{mv['pct_cuota']*100:.1f}%" if mv["cuota"] else "—",
         f"{mh['pct_cuota']*100:.1f}%" if mh["cuota"] else "—"],
        ["Proyección cierre",    "—",
         str(mv["proy"]),
         str(mh["proy"]) if mh["cuota"] else "—"],
        ["% Proyección / cuota", "—",
         f"{mv['proy']/mv['cuota']*100:.1f}%" if mv["cuota"] else "—",
         f"{mh['proy']/mh['cuota']*100:.1f}%" if mh["cuota"] else "—"],
        ["Ritmo actual/día",     "—",                      str(mv["ritmo"]),                                    str(mh["ritmo"])],
        ["Estado",               "—",                      mv["estado"],                                        mh["estado"]],
    ]
    t_res = Table(res_data, colWidths=[5.5*cm, 3.5*cm, 4*cm, 4*cm])
    est_res = tabla_base()
    for i in [1, 2]:
        est_res.add("FONTNAME", (1, i), (3, i), "Helvetica-Bold")
    est_res.add("TEXTCOLOR", (2, 0), (2, 0), C_NARANJA)
    est_res.add("TEXTCOLOR", (3, 0), (3, 0), C_AZUL)
    est_res.add("TEXTCOLOR", (2, len(res_data)-1), (2, len(res_data)-1), _ec.get(mv["estado"], C_GRIS_CLARO))
    est_res.add("TEXTCOLOR", (3, len(res_data)-1), (3, len(res_data)-1), _ec.get(mh["estado"], C_GRIS_CLARO))
    t_res.setStyle(est_res)
    story.append(t_res)
    story.append(Spacer(1, 12))

    seccion_area(story, "Vertical", mv, datos, S, C_NARANJA)

    # ── PÁGINA 2 — Horizontal ────────────────────
    story.append(PageBreak())
    encabezado_pagina()

    seccion_area(story, "Horizontal", mh, datos, S, C_AZUL)

    # ── PIE ──────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_GRIS_CLARO))
    story.append(Spacer(1, 3))
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
    hoy = datetime.now().date()
    print(f"Generando reporte nocturno para: {hoy.strftime('%d/%m/%Y')}")

    try:
        datos = extraer_datos(hoy)
        v = datos["vertical"]
        h = datos["horizontal"]
        print(f"  Lima Total — MTD: {datos['total_mtd']}  |  Hoy: {datos['total_hoy']}")
        print(f"  Vertical   — MTD: {v['mtd']}  |  Hoy: {v['hoy_c']}  |  Ritmo: {v['ritmo']}/día  |  Proy: {v['proy']}  |  Estado: {v['estado']}")
        print(f"  Horizontal — MTD: {h['mtd']}  |  Hoy: {h['hoy_c']}  |  Ritmo: {h['ritmo']}/día  |  Proy: {h['proy']}  |  Estado: {h['estado']}")
    except Exception as e:
        print(f"Error extrayendo datos: {e}")
        sys.exit(1)

    generar_pdf(datos)
