"""
ReporteDiarioGerente.py
========================
Reporte diario gerencial en PDF.
Página 1: Lima Total + Vertical (Condominio/Edificio)
Página 2: Horizontal (todo lo que no es Vertical)

Uso:
    python ReporteDiarioGerente.py

PDF: Reporte_Gerente_Aliv_YYYY-MM-DD.pdf
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


C_NARANJA    = colors.HexColor("#F47920")
C_OSCURO     = colors.HexColor("#1C1C1E")
C_VERDE      = colors.HexColor("#1D9E75")
C_ROJO       = colors.HexColor("#E24B4A")
C_AMARILLO   = colors.HexColor("#EF9F27")
C_BLANCO     = colors.white
C_GRIS_CLARO = colors.HexColor("#AAAAAA")
C_AZUL       = colors.HexColor("#2E86AB")


# ──────────────────────────────────────────────
# HELPERS
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


def barra_progreso(pct, color_bar, bar_w=17 * cm):
    filled = bar_w * min(pct, 1.0)
    empty  = bar_w - filled
    if empty < 0.05 * cm:
        t = Table([[""]], colWidths=[bar_w], rowHeights=[10])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, 0), color_bar),
            ("GRID",          (0, 0), (-1, -1), 0, colors.white),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
    else:
        t = Table([["", ""]], colWidths=[filled, empty], rowHeights=[10])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, 0), color_bar),
            ("BACKGROUND",    (1, 0), (1, 0), colors.HexColor("#2A2A2E")),
            ("GRID",          (0, 0), (-1, -1), 0, colors.white),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
    return t


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
# EXTRACCIÓN DE DATOS
# ──────────────────────────────────────────────

def extraer_datos(ayer):
    mes_num      = ayer.month
    primer_dia   = ayer.replace(day=1)
    dias_trans   = (ayer - primer_dia).days + 1
    dias_totales = 25
    dias_rest    = max(dias_totales - dias_trans, 0)

    cal = calendar.Calendar(firstweekday=0)
    semanas_def = []
    for week in cal.monthdayscalendar(ayer.year, mes_num):
        days = [d for d in week if d != 0]
        if days:
            semanas_def.append((days[0], days[-1]))

    engine = get_engine()
    with engine.connect() as conn:
        rows_raw = conn.execute(sa.text("""
            SELECT wl.[Fecha programación], wl.[Tipo de domicilio], wl.[Plan],
                   wl.[Zona_KML], wl.[Distrito],
                   ISNULL(
                       (SELECT TOP 1 da.agencia FROM dim_usuarios_Aliv da
                        WHERE da.vendedor = wl.[Vendedor real]),
                       wl.[Agencia]
                   ) AS agencia_raw
            FROM winforce_lima wl
            WHERE wl.[Estado orden] = 'Ejecutada'
              AND TRY_CONVERT(DATE, LEFT(wl.[Fecha programación], 10), 105) >= :primer_dia
              AND TRY_CONVERT(DATE, LEFT(wl.[Fecha programación], 10), 105) <= :ayer
              AND wl.[Departamento] IN ('LIMA', 'CALLAO')
              AND LOWER(wl.[Distrito]) NOT IN ('barranca', 'chancay', 'huacho', 'hualmay', 'huaral')
        """), {"primer_dia": primer_dia, "ayer": ayer}).fetchall()

    parsed = []
    for row in rows_raw:
        fp_str, dom_tipo, plan, zona, distrito, agencia_raw = row
        if not fp_str:
            continue
        try:
            fp_date = datetime.strptime(fp_str[:10].replace('/', '-'), "%d-%m-%Y").date()
        except Exception:
            continue
        parsed.append({
            "date":     fp_date,
            "tipo":     dom_tipo or "",
            "plan":     plan or "—",
            "zona":     zona or "—",
            "distrito": distrito or "—",
            "agencia":  _norm_agencia(agencia_raw),
            "vertical": (dom_tipo or "") in VERTICAL_TIPOS,
        })

    ventas_parsed = []
    with engine.connect() as conn2:
        ventas_raw = conn2.execute(sa.text("""
            SELECT CAST(wl.[Fecha de registro] AS DATE),
                   wl.[Tipo de domicilio], wl.[Plan],
                   ISNULL(
                       (SELECT TOP 1 da.agencia FROM dim_usuarios_Aliv da
                        WHERE da.vendedor = wl.[Vendedor real]),
                       wl.[Agencia]
                   ) AS agencia_raw
            FROM winforce_lima wl
            WHERE MONTH(wl.[Fecha de registro]) = :mes
              AND YEAR(wl.[Fecha de registro]) = :anio
              AND CAST(wl.[Fecha de registro] AS DATE) <= :ayer
              AND wl.[Plan] IS NOT NULL AND wl.[Plan] <> ''
              AND wl.[Departamento] IN ('LIMA', 'CALLAO')
              AND LOWER(wl.[Distrito]) NOT IN ('barranca', 'chancay', 'huacho', 'hualmay', 'huaral')
        """), {"mes": mes_num, "anio": ayer.year, "ayer": ayer}).fetchall()
    for vrow in ventas_raw:
        vfecha, vdom, vplan, vagencia = vrow
        if not vfecha:
            continue
        try:
            vd = vfecha if hasattr(vfecha, 'year') else datetime.strptime(str(vfecha)[:10], "%Y-%m-%d").date()
        except Exception:
            continue
        ventas_parsed.append({
            "date":     vd,
            "plan":     vplan or "—",
            "agencia":  _norm_agencia(vagencia),
            "vertical": (vdom or "") in VERTICAL_TIPOS,
        })

    def top_n(filas, campo, n=8):
        counts = {}
        for r in filas:
            k = r[campo]
            counts[k] = counts.get(k, 0) + 1
        return sorted(counts.items(), key=lambda x: x[1], reverse=True)[:n]

    def sem_altas_area(filas):
        result = []
        for s_ini, s_fin in semanas_def:
            f_i = primer_dia.replace(day=s_ini)
            f_f = min(primer_dia.replace(day=s_fin), ayer)
            if f_i > ayer:
                result.append(None)
            else:
                result.append(sum(1 for r in filas if f_i <= r["date"] <= f_f))
        return result

    def _ag_agg(rows):
        res = {ag: {"mtd": 0, "ayer": 0} for ag in _AGENCIAS}
        for r in rows:
            ag = r.get("agencia", "ALIV")
            if ag not in res:
                ag = "SUB-AGENCIAS"
            res[ag]["mtd"] += 1
            if r["date"] == ayer:
                res[ag]["ayer"] += 1
        return res

    def _plan_ag(rows, n=7):
        pivot = {}
        for r in rows:
            plan = r["plan"]
            ag   = r.get("agencia", "ALIV")
            if ag not in _AGENCIAS:
                ag = "SUB-AGENCIAS"
            if plan not in pivot:
                pivot[plan] = {a: 0 for a in _AGENCIAS}
            pivot[plan][ag] += 1
        items = sorted(pivot.items(), key=lambda x: sum(x[1].values()), reverse=True)[:n]
        return [(pl, v, sum(v.values())) for pl, v in items]

    def _build_daily(rows):
        daily = {}
        for r in rows:
            daily[r["date"]] = daily.get(r["date"], 0) + 1
        DAY_ABBR = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        col_tots = [0] * 7
        grid = []
        for i, (s_ini, s_fin) in enumerate(semanas_def):
            f_i = primer_dia.replace(day=s_ini)
            week_mon = f_i - timedelta(days=f_i.weekday())
            row_g = [f"Sem {i+1}"]
            wk_tot = 0
            for dow in range(7):
                d = week_mon + timedelta(days=dow)
                if d.month != primer_dia.month or d.day < s_ini or d.day > s_fin or d > ayer:
                    row_g.append("—")
                else:
                    cnt = daily.get(d, 0)
                    wk_tot += cnt
                    col_tots[dow] += cnt
                    row_g.append(str(cnt) if cnt else "0")
            row_g.append(str(wk_tot))
            grid.append(row_g)
        grid.append(["Total"] + [str(ct) for ct in col_tots] + [str(sum(daily.values()))])
        return [["Semana"] + DAY_ABBR + ["Total"]] + grid

    def metricas(filas, cuota, ventas_filas=None):
        mtd    = len(filas)
        ayer_c = sum(1 for r in filas if r["date"] == ayer)
        ritmo  = round(mtd / dias_trans, 1) if dias_trans else 0
        proy   = round(mtd / dias_trans * dias_totales) if dias_trans else 0
        pct_esp = dias_trans / dias_totales

        if cuota:
            pct_cuota = mtd / cuota
            ratio     = pct_cuota / pct_esp if pct_esp else 0
            faltantes = max(cuota - mtd, 0)
            req_dia   = round(faltantes / dias_rest, 1) if dias_rest else faltantes
            req_rest  = req_dia
            estado, color_sem = calcular_estado(ratio)
        else:
            pct_cuota = 0
            ratio     = 0
            faltantes = 0
            req_dia   = 0
            req_rest  = 0
            estado, color_sem = "SIN CUOTA", C_GRIS_CLARO

        filas_ayer  = [r for r in filas if r["date"] == ayer]
        ventas_ayer = [r for r in (ventas_filas or []) if r["date"] == ayer]

        return {
            "mtd": mtd, "ayer_c": ayer_c, "cuota": cuota,
            "ritmo": ritmo, "proy": proy,
            "pct_cuota": pct_cuota, "pct_esp": pct_esp,
            "ratio": ratio, "faltantes": faltantes,
            "req_dia": req_dia, "req_rest": req_rest,
            "estado": estado, "color_sem": color_sem,
            "semanas_altas":        sem_altas_area(filas),
            "por_plan_ayer":        top_n(filas_ayer, "plan"),
            "por_plan_mtd":         top_n(filas, "plan"),
            "por_plan_ventas_ayer": top_n(ventas_ayer, "plan"),
            "por_plan_ventas_mtd":  top_n(ventas_filas or [], "plan"),
            "ventas_ayer_total":    len(ventas_ayer),
            "ventas_mtd_total":     len(ventas_filas or []),
            "por_zona_mtd":         top_n(filas, "zona"),
            "por_dist_mtd":         top_n(filas, "distrito"),
            "ag_altas":             _ag_agg(filas),
            "ag_ventas":            _ag_agg(ventas_filas or []),
            "plan_ag_altas":        _plan_ag(filas),
            "plan_ag_ventas":       _plan_ag(ventas_filas or []),
            "daily_altas":          _build_daily(filas),
            "daily_ventas":         _build_daily(ventas_filas or []),
        }

    rows_v   = [r for r in parsed if r["vertical"]]
    rows_h   = [r for r in parsed if not r["vertical"]]
    ventas_v = [r for r in ventas_parsed if r["vertical"]]
    ventas_h = [r for r in ventas_parsed if not r["vertical"]]

    return {
        "ayer": ayer,
        "mes_num": mes_num,
        "dias_trans": dias_trans,
        "dias_totales": dias_totales,
        "dias_rest": dias_rest,
        "semanas_def": semanas_def,
        "total_mtd":   len(parsed),
        "total_ayer":  sum(1 for r in parsed if r["date"] == ayer),
        "vertical":    metricas(rows_v, cuota_lima(mes_num, 'Vertical'), ventas_v),
        "horizontal":  metricas(rows_h, cuota_lima(mes_num, 'Horizontal'), ventas_h),
    }


# ──────────────────────────────────────────────
# SECCIÓN DEL PDF (Vertical u Horizontal)
# ──────────────────────────────────────────────

def seccion_area(story, label, m, ayer, datos, S, color_acento, is_vertical):
    semanas_def  = datos["semanas_def"]
    dias_trans   = datos["dias_trans"]
    dias_totales = datos["dias_totales"]
    dias_rest    = datos["dias_rest"]

    ESTADO_COLOR = {
        "EN RITMO": C_VERDE, "LIGERAMENTE BAJO": C_AMARILLO,
        "BAJO RITMO": C_ROJO, "OK": C_VERDE, "RIESGO": C_ROJO,
    }

    story.append(cabecera_seccion(f"  {label.upper()}", color_acento))
    story.append(Spacer(1, 8))

    # ── Tabla de indicadores ─────────────────────
    ind = [["Indicador", "Valor MTD", "Referencia", "Estado"]]
    ind.append(["Altas instaladas MTD", str(m["mtd"]),
                f"Meta: {m['cuota']}" if m["cuota"] else "sin cuota asignada", m["estado"]])
    ind.append(["Altas ayer", str(m["ayer_c"]),
                f"Ritmo: {m['ritmo']}/día",
                "OK" if m["ayer_c"] >= m["ritmo"] else "RIESGO"])
    if m["cuota"]:
        ind.append(["% Avance cuota", f"{m['pct_cuota']*100:.1f}%",
                    f"Ideal día {dias_trans}: {m['pct_esp']*100:.0f}%", m["estado"]])
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

    # ── Semanas ──────────────────────────────────
    sem_altas = m["semanas_altas"]
    cuota     = m["cuota"]
    mes_corto = ayer.strftime("%b").lower()
    virtual_cum = 0
    sh, sv, ss, sv_col = [], [], [], []

    for i, (s_ini, s_fin) in enumerate(semanas_def):
        altas_real   = sem_altas[i]
        days_in_week = s_fin - s_ini + 1

        if altas_real is not None:
            past = ayer.day > s_fin
            sh.append(f"Sem {i+1} ({'ya pasó' if past else 'en curso'})")
            sv.append(str(altas_real))
            ss.append("Real" if past else "Actual")
            sv_col.append(C_GRIS_CLARO if past else color_acento)
            virtual_cum += altas_real
        else:
            if cuota:
                remaining   = cuota - virtual_cum
                future_days = sum(
                    semanas_def[j][1] - semanas_def[j][0] + 1
                    for j in range(i, len(semanas_def))
                    if sem_altas[j] is None
                )
                needed = (remaining if i == len(semanas_def)-1 or future_days == 0
                          else round(remaining * days_in_week / future_days))
                needed = max(needed, 0)
                virtual_cum += needed
                sv.append(f"+{needed}")
                ss.append(f"Meta: {virtual_cum:,}")
            else:
                sv.append("—")
                ss.append("")
            sh.append(f"Sem {i+1} · {s_ini}-{s_fin} {mes_corto}")
            sv_col.append(color_acento)

    nw  = len(semanas_def)
    cw_s = 17 / nw * cm
    t_sem = Table(
        [[Paragraph(h, S["kpi_lbl"]) for h in sh],
         [Paragraph(sv[i], S["kpi_val16"]) for i in range(nw)],
         [Paragraph(ss[i], S["kpi_lbl"]) for i in range(nw)]],
        colWidths=[cw_s] * nw, rowHeights=[0.62*cm, 1.25*cm, 0.62*cm],
    )
    sem_st = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.white),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#E0E0E0")),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ])
    for i, altas_real in enumerate(sem_altas):
        sem_st.add("TEXTCOLOR", (i, 1), (i, 1), sv_col[i])
        if altas_real is not None:
            if ayer.day > semanas_def[i][1]:
                sem_st.add("BACKGROUND", (i, 0), (i, -1), colors.HexColor("#F0F0F0"))
            else:
                sem_st.add("BOX", (i, 0), (i, -1), 1.5, color_acento)
    t_sem.setStyle(sem_st)
    story.append(t_sem)
    story.append(Spacer(1, 10))

    # ── Planes ayer ──────────────────────────────
    if m["por_plan_ayer"]:
        story.append(Paragraph("Planes instalados — Ayer", S["sub_sec"]))
        ventas_ayer_d  = dict(m["por_plan_ventas_ayer"])
        total_v_ayer   = m["ventas_ayer_total"] or 1
        total_a_ayer   = m["ayer_c"] or 1
        p_data = [["Plan", "Ventas", "%V", "Altas", "%A"]]
        v_tot_p = 0
        a_tot_p = 0
        for plan, cnt in m["por_plan_ayer"]:
            v_cnt = ventas_ayer_d.get(plan, 0)
            v_tot_p += v_cnt
            a_tot_p += cnt
            p_data.append([str(plan)[:40],
                           str(v_cnt), f"{v_cnt/total_v_ayer*100:.1f}%",
                           str(cnt),   f"{cnt/total_a_ayer*100:.1f}%"])
        p_data.append(["TOTAL", str(m["ventas_ayer_total"]), "—", str(m["ayer_c"]), "—"])
        t = Table(p_data, colWidths=[7*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm])
        st_p = tabla_base()
        st_p.add("BACKGROUND", (1, 0), (2, 0), C_AZUL)
        st_p.add("BACKGROUND", (3, 0), (4, 0), C_VERDE)
        _total_row_style(st_p, len(p_data) - 1)
        t.setStyle(st_p)
        story.append(t)
        story.append(Spacer(1, 6))

    # ── Planes MTD ───────────────────────────────
    if m["por_plan_mtd"]:
        story.append(Paragraph("Planes instalados — Mes actual", S["sub_sec"]))
        ventas_mtd_d = dict(m["por_plan_ventas_mtd"])
        total_v_mtd  = m["ventas_mtd_total"] or 1
        total_a_mtd  = m["mtd"] or 1
        p_data = [["Plan", "Ventas", "%V", "Altas", "%A"]]
        v_tot_m = 0
        a_tot_m = 0
        for plan, cnt in m["por_plan_mtd"]:
            v_cnt = ventas_mtd_d.get(plan, 0)
            v_tot_m += v_cnt
            a_tot_m += cnt
            p_data.append([str(plan)[:40],
                           str(v_cnt), f"{v_cnt/total_v_mtd*100:.1f}%",
                           str(cnt),   f"{cnt/total_a_mtd*100:.1f}%"])
        p_data.append(["TOTAL", str(m["ventas_mtd_total"]), "—", str(m["mtd"]), "—"])
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
        ["Ventas ayer"] + [str(ag_v[ag]["ayer"]) for ag in _AGENCIAS]
                        + [str(sum(ag_v[ag]["ayer"] for ag in _AGENCIAS))],
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
        ["Altas ayer"] + [str(ag_a[ag]["ayer"]) for ag in _AGENCIAS]
                       + [str(sum(ag_a[ag]["ayer"] for ag in _AGENCIAS))],
    ]
    t_aga = Table(ag_adata, colWidths=[3*cm] + [1.9*cm]*6 + [2.6*cm])
    t_aga.setStyle(tabla_altas())
    story.append(t_aga)
    story.append(Spacer(1, 4))

    # ── Pivot Ventas Plan × Agencia ──────────────
    piv_hdr = ["Plan"] + _AGENCIAS + ["Total"]
    if m["plan_ag_ventas"]:
        story.append(Paragraph("Ventas por plan y agencia — Mes actual", S["sub_v"]))
        piv_v = [piv_hdr]
        for plan, ag_cnts, total in m["plan_ag_ventas"]:
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
    if m["plan_ag_altas"]:
        story.append(Paragraph("Altas por plan y agencia — Mes actual", S["sub_a"]))
        piv_a = [piv_hdr]
        for plan, ag_cnts, total in m["plan_ag_altas"]:
            piv_a.append([str(plan)[:28]] + [str(ag_cnts[ag]) for ag in _AGENCIAS] + [str(total)])
        piv_a.append(["TOTAL"]
                     + [str(ag_a[ag]["mtd"]) for ag in _AGENCIAS]
                     + [str(sum(ag_a[ag]["mtd"] for ag in _AGENCIAS))])
        t_pa = Table(piv_a, colWidths=[4*cm] + [1.8*cm]*6 + [2.2*cm])
        st_pa = tabla_altas()
        _total_row_style(st_pa, len(piv_a) - 1)
        t_pa.setStyle(st_pa)
        story.append(t_pa)
        story.append(Spacer(1, 4))

    # ── Registros diarios ─────────────────────────
    story.append(Paragraph("Registros diarios — Ventas", S["sub_v"]))
    gv = m["daily_ventas"]
    t_gv = Table(gv, colWidths=[1.5*cm] + [2*cm]*7 + [1.5*cm])
    st_gv = tabla_ventas()
    _total_row_style(st_gv, len(gv) - 1)
    t_gv.setStyle(st_gv)
    story.append(t_gv)
    story.append(Spacer(1, 4))

    story.append(Paragraph("Registros diarios — Altas", S["sub_a"]))
    ga = m["daily_altas"]
    t_ga = Table(ga, colWidths=[1.5*cm] + [2*cm]*7 + [1.5*cm])
    st_ga = tabla_altas()
    _total_row_style(st_ga, len(ga) - 1)
    t_ga.setStyle(st_ga)
    story.append(t_ga)
    story.append(Spacer(1, 6))


# ──────────────────────────────────────────────
# PDF PRINCIPAL
# ──────────────────────────────────────────────

def generar_pdf(datos):
    ayer = datos["ayer"]
    nombre = f"Reporte_Gerente_Aliv_{ayer.strftime('%Y-%m-%d')}.pdf"

    S = {}
    S["titulo"]   = ParagraphStyle("t",  fontName="Helvetica-Bold", fontSize=17,
                                   textColor=C_NARANJA, alignment=TA_CENTER, spaceAfter=3)
    S["sub"]      = ParagraphStyle("s",  fontName="Helvetica", fontSize=9,
                                   textColor=C_GRIS_CLARO, alignment=TA_CENTER, spaceAfter=8)
    S["bar_lbl"]  = ParagraphStyle("bl", fontName="Helvetica", fontSize=7,
                                   textColor=C_GRIS_CLARO, spaceAfter=3)
    S["nota"]     = ParagraphStyle("n",  fontName="Helvetica-Oblique", fontSize=7,
                                   textColor=C_GRIS_CLARO, spaceAfter=4)
    S["kpi_lbl"]  = ParagraphStyle("kl", fontName="Helvetica", fontSize=7,
                                   textColor=C_GRIS_CLARO, alignment=TA_CENTER)
    S["kpi_val16"] = ParagraphStyle("kv", fontName="Helvetica-Bold", fontSize=16,
                                    alignment=TA_CENTER)
    S["sub_sec"]  = ParagraphStyle("ss", fontName="Helvetica-Bold", fontSize=8.5,
                                   textColor=C_OSCURO, spaceBefore=4, spaceAfter=2)
    S["sub_v"]    = ParagraphStyle("sv", fontName="Helvetica-Bold", fontSize=8.5,
                                   textColor=C_AZUL,  spaceBefore=6, spaceAfter=2)
    S["sub_a"]    = ParagraphStyle("sa", fontName="Helvetica-Bold", fontSize=8.5,
                                   textColor=C_VERDE, spaceBefore=6, spaceAfter=2)

    doc = SimpleDocTemplate(nombre, pagesize=A4,
                            rightMargin=1.8*cm, leftMargin=1.8*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    story = []

    ayer_d       = datos["ayer"]
    dias_trans   = datos["dias_trans"]
    dias_totales = datos["dias_totales"]
    mes_nombre   = ayer_d.strftime("%B %Y").capitalize()
    mv = datos["vertical"]
    mh = datos["horizontal"]

    def encabezado_pagina():
        story.append(Paragraph("ALIV TELECOM — REPORTE GERENCIAL DIARIO", S["titulo"]))
        story.append(Paragraph(
            f"{ayer_d.strftime('%d/%m/%Y')} · {mes_nombre} · "
            f"Día {dias_trans} de {dias_totales} (base 25)",
            S["sub"]
        ))
        story.append(HRFlowable(width="100%", thickness=1.5, color=C_NARANJA))
        story.append(Spacer(1, 8))

    # ── PÁGINA 1 — Lima Total + Vertical ─────────
    encabezado_pagina()

    # Resumen Lima Total — tabla comparativa
    total_mtd  = datos["total_mtd"]
    total_ayer = datos["total_ayer"]
    _ec = {"EN RITMO": C_VERDE, "LIGERAMENTE BAJO": C_AMARILLO,
           "BAJO RITMO": C_ROJO, "SIN CUOTA": C_GRIS_CLARO}

    res_data = [
        ["Métrica",                "Lima Total",   "Vertical",                                       "Horizontal"],
        ["Altas instaladas MTD",   str(total_mtd), str(mv["mtd"]),                                   str(mh["mtd"])],
        ["Altas ayer",             str(total_ayer),str(mv["ayer_c"]),                                str(mh["ayer_c"])],
        ["Cuota del mes",          "—",            str(mv["cuota"]) if mv["cuota"] else "—",          str(mh["cuota"]) if mh["cuota"] else "—"],
        ["% Avance cuota",         "—",            f"{mv['pct_cuota']*100:.1f}%" if mv["cuota"] else "—", f"{mh['pct_cuota']*100:.1f}%" if mh["cuota"] else "—"],
        ["Proyección cierre",      "—",            str(mv["proy"]),                                  str(mh["proy"]) if mh["cuota"] else "—"],
        ["% Proyección / cuota",   "—",            f"{mv['proy']/mv['cuota']*100:.1f}%" if mv["cuota"] else "—", f"{mh['proy']/mh['cuota']*100:.1f}%" if mh["cuota"] else "—"],
        ["Ritmo actual/día",       "—",            str(mv["ritmo"]),                                 str(mh["ritmo"])],
        ["Estado",                 "—",            mv["estado"],                                     mh["estado"]],
    ]
    t_res = Table(res_data, colWidths=[5.5*cm, 3.5*cm, 4*cm, 4*cm])
    est_res = tabla_base()
    # Negritas en filas de altas
    for i in [1, 2]:
        est_res.add("FONTNAME", (1, i), (3, i), "Helvetica-Bold")
    # Color columna Vertical y Horizontal en cabecera
    est_res.add("TEXTCOLOR", (2, 0), (2, 0), C_NARANJA)
    est_res.add("TEXTCOLOR", (3, 0), (3, 0), C_AZUL)
    # Color estado
    est_res.add("TEXTCOLOR", (2, len(res_data)-1), (2, len(res_data)-1), _ec.get(mv["estado"], C_GRIS_CLARO))
    est_res.add("TEXTCOLOR", (3, len(res_data)-1), (3, len(res_data)-1), _ec.get(mh["estado"], C_GRIS_CLARO))
    t_res.setStyle(est_res)
    story.append(t_res)
    story.append(Spacer(1, 12))

    seccion_area(story, "Vertical", mv, ayer_d, datos, S, C_NARANJA, is_vertical=True)

    # ── PÁGINA 2 — Horizontal ────────────────────
    story.append(PageBreak())
    encabezado_pagina()

    seccion_area(story, "Horizontal", mh, ayer_d, datos, S, C_AZUL, is_vertical=False)

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
    ayer = datetime.now().date() - timedelta(days=1)
    print(f"Generando reporte gerencial para: {ayer.strftime('%d/%m/%Y')}")

    try:
        datos = extraer_datos(ayer)
        v = datos["vertical"]
        h = datos["horizontal"]
        print(f"  Lima Total — MTD: {datos['total_mtd']}  |  Ayer: {datos['total_ayer']}")
        print(f"  Vertical   — MTD: {v['mtd']}  |  Ayer: {v['ayer_c']}  |  Ritmo: {v['ritmo']}/día  |  Proy: {v['proy']}")
        print(f"  Horizontal — MTD: {h['mtd']}  |  Ayer: {h['ayer_c']}  |  Ritmo: {h['ritmo']}/día  |  Proy: {h['proy']}")
    except Exception as e:
        print(f"Error extrayendo datos: {e}")
        sys.exit(1)

    generar_pdf(datos)
