#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reporte_Proyección.py
======================
Reporte diario de proyección — Aliv Lima (Horizontal / Vertical).

Situación actual frente a la cuota oficial, metas (oficial + estirada para
incentivos), BAC día por día, necesidad diaria neta y la proyección de
cierre a dos métodos (ritmo actual / tendencia).

Se alimenta 100% de SQL Server a través de Intranet/db_helper.py — la misma
fuente que usa la Intranet (dashboard, /pipeline → Resumen Lima y su gráfica
de proyección) — así que cuota, altas y proyección siempre coinciden con lo
que se ve en la web. No hay inputs manuales que editar cada día.

Uso:
    python Reporte_Proyección.py

El corte es el día anterior a hoy (día ya cerrado), igual que
ReporteDiarioGerente.py. El PDF se guarda como Reporte_Proyeccion_Aliv_<fecha>.pdf
"""

import calendar
import os
import sys
from datetime import datetime, timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch, Ellipse

# Intranet/db_helper.py no depende de Flask (solo de SQLAlchemy) — se puede
# importar tal cual desde un script standalone. Es la misma fuente que usa
# el dashboard web y el modal "Resumen Lima" de /pipeline.
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'Intranet'
))
import db_helper

# ======================================================================
# CONFIG — se ajusta rara vez (metas de incentivo, horizonte interno)
# ======================================================================

STRETCH_PCT = 1.10                 # meta "estirada" para diseño de incentivos (10% sobre la cuota oficial)
DIAS_PROYECCION_INTERNA = 29       # horizonte conservador — el más exigente para medir el ritmo
AREAS = ["Horizontal", "Vertical"]

# Paleta — mismos tokens que el tema oscuro de la Intranet (style.css), para
# que el PDF y la web se lean como un solo sistema en vez de inventar un
# tema nuevo para el reporte.
COLORS = {
    "bg":      "#101012",  # --bg-app
    "panel":   "#1B1B1F",  # --bg-card
    "panel2":  "#222227",  # --bg-card-hover
    "line":    "#2A2A30",  # --border
    "text":    "#F2F0EC",  # --text-primary
    "muted":   "#ABA8A2",  # --text-secondary
    "accent":  "#F47920",  # --brand
    "success": "#1D9E75",
    "danger":  "#E24B4A",
    "warning": "#EF9F27",
    "slate":   "#7C8B99",
}

PAGE_SIZE = (13.33, 7.5)  # pulgadas, 16:9

MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre",
    12: "diciembre",
}


def mes_es(d):
    return MESES_ES[d.month]


def fmt(n, dec=0):
    if dec == 0:
        return f"{n:,.0f}"
    return f"{n:,.{dec}f}"


# ----------------------------------------------------------------------
# Extracción de datos (100% SQL Server vía db_helper)
# ----------------------------------------------------------------------

def calcular_meta(label, area, mult, kpi, bac_total, dia_corte, dias_mes_real):
    cuota = kpi.get("cuota", 0)
    altas = kpi.get("altas", 0)
    cuota_meta = round(cuota * mult)
    faltante_bruto = cuota_meta - altas
    dias_rest_29 = max(DIAS_PROYECCION_INTERNA - dia_corte, 1)
    dias_rest_31 = max(dias_mes_real - dia_corte, 1)
    faltante_neto = faltante_bruto - bac_total
    return {
        "label": label, "area": area, "cuota": cuota, "pct_meta": round(mult * 100),
        "cuota_meta": cuota_meta, "altas": altas,
        "faltante_bruto": faltante_bruto,
        "dias_rest_29": dias_rest_29, "necesidad_bruta_29": faltante_bruto / dias_rest_29,
        "dias_rest_31": dias_rest_31, "necesidad_bruta_31": faltante_bruto / dias_rest_31,
        "bac": bac_total, "faltante_neto": faltante_neto,
        "necesidad_neta_29": faltante_neto / dias_rest_29,
        "necesidad_neta_31": faltante_neto / dias_rest_31,
    }


def pct_actual(kpi):
    """% de la cuota oficial que estamos proyectando cerrar (horizonte interno)."""
    cuota = kpi.get("cuota", 0)
    proy = kpi.get("proyeccion", 0)
    return (proy / cuota * 100) if cuota else 0


def extraer_datos(fecha_corte):
    mes, anio = fecha_corte.month, fecha_corte.year
    dia_corte = fecha_corte.day
    dias_mes_real = calendar.monthrange(anio, mes)[1]

    areas = {}
    for area in AREAS:
        kpi = db_helper.get_kpi_lima(mes, anio, area=area, dia=dia_corte, cumul=True,
                                      base_dias=DIAS_PROYECCION_INTERNA) or {}
        bac = db_helper.get_bac_lima(mes, anio, dia_corte, area=area)
        proy = db_helper.get_proyeccion_cierre_lima(mes, anio, dia_ref=dia_corte,
                                                      base_dias=DIAS_PROYECCION_INTERNA, area=area)
        areas[area] = {"kpi": kpi, "bac": bac, "bac_total": sum(bac.values()), "proy": proy}

    metas = []
    for area in AREAS:
        kpi = areas[area]["kpi"]
        bac_total = areas[area]["bac_total"]
        metas.append(calcular_meta(f"{area} 100% (cuota oficial)", area, 1.00,
                                    kpi, bac_total, dia_corte, dias_mes_real))
        metas.append(calcular_meta(f"{area} {round(STRETCH_PCT * 100)}% (estirada)", area, STRETCH_PCT,
                                    kpi, bac_total, dia_corte, dias_mes_real))

    return {
        "fecha_corte": fecha_corte, "dia_corte": dia_corte, "mes": mes, "anio": anio,
        "dias_mes_real": dias_mes_real, "areas": areas, "metas": metas,
    }


# ----------------------------------------------------------------------
# Helpers de dibujo
# ----------------------------------------------------------------------

def new_page():
    fig = plt.figure(figsize=PAGE_SIZE, facecolor=COLORS["bg"])
    fig.patch.set_facecolor(COLORS["bg"])
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_facecolor(COLORS["bg"])
    return fig, ax


def eyebrow(ax, text, y=0.90):
    ax.text(0.045, y, text.upper(), color=COLORS["accent"], fontsize=12,
             fontweight="bold", family="sans-serif")


def title(ax, text, y=0.82):
    ax.text(0.045, y, text, color=COLORS["text"], fontsize=25,
             fontweight="bold", family="sans-serif", va="top")


def subtitle(ax, text, y=0.755):
    ax.text(0.045, y, text, color=COLORS["muted"], fontsize=13,
             family="sans-serif", va="top")


def footer(ax, page_n, total, fecha):
    ax.text(0.045, 0.035, f"ALIV · {mes_es(fecha).upper()} {fecha.year}",
             color=COLORS["muted"], fontsize=9, fontweight="bold", family="sans-serif")
    ax.text(0.955, 0.035, f"{page_n} / {total}", color=COLORS["muted"],
             fontsize=9, family="sans-serif", ha="right")


def note(ax, text, y=0.06, color=None):
    ax.text(0.045, y, text, color=color or COLORS["muted"], fontsize=10,
             family="sans-serif", style="italic")


def card(ax, x, y, w, h, facecolor=None):
    box = FancyBboxPatch((x, y), w, h,
                          boxstyle="round,pad=0.004,rounding_size=0.012",
                          linewidth=1, edgecolor=COLORS["line"],
                          facecolor=facecolor or COLORS["panel"], zorder=2)
    ax.add_patch(box)


def barra_meta(ax, x, y, w, h, pct, color, pct_ideal=None):
    """Barra de avance real hacia la cuota (0-100%+), con una marca del
    avance ideal a la fecha de corte — para responder de un vistazo
    '¿vamos a llegar a la meta?'."""
    card(ax, x, y, w, h, facecolor=COLORS["panel2"])
    filled = w * min(max(pct, 0) / 100, 1.0)
    if filled > 0.0015:
        bar = FancyBboxPatch((x, y), filled, h,
                              boxstyle="round,pad=0.0015,rounding_size=0.009",
                              linewidth=0, facecolor=color, zorder=3)
        ax.add_patch(bar)
    if pct_ideal is not None:
        xi = x + w * min(max(pct_ideal, 0) / 100, 1.0)
        ax.plot([xi, xi], [y - 0.007, y + h + 0.007], color=COLORS["text"],
                 linewidth=1.5, zorder=4, solid_capstyle="round")


def draw_table(ax, x, y, w, headers, rows, col_widths, row_h=0.09, fontsize=11):
    """Tabla simple con header oscuro y filas alternadas."""
    n_rows = len(rows) + 1
    hx = x
    for h_text, cw in zip(headers, col_widths):
        ax.add_patch(FancyBboxPatch((hx, y - row_h), cw, row_h,
                                     boxstyle="square,pad=0",
                                     linewidth=0, facecolor=COLORS["panel2"], zorder=2))
        align = "left" if h_text == headers[0] else "right"
        tx = hx + 0.01 if align == "left" else hx + cw - 0.01
        ax.text(tx, y - row_h / 2, h_text, color=COLORS["muted"], fontsize=fontsize - 1,
                 fontweight="bold", va="center", ha=align, zorder=3, family="sans-serif")
        hx += cw

    for i, row in enumerate(rows):
        ry = y - row_h * (i + 2)
        hx = x
        rowfill = COLORS["panel"]
        for cell, cw in zip(row, col_widths):
            ax.add_patch(FancyBboxPatch((hx, ry), cw, row_h,
                                         boxstyle="square,pad=0",
                                         linewidth=0.6, edgecolor=COLORS["line"],
                                         facecolor=rowfill, zorder=2))
            text = cell if isinstance(cell, str) else str(cell)
            bold = False
            color = COLORS["text"]
            if isinstance(cell, tuple):
                text, bold, color = cell
            align = "left" if cw == col_widths[0] else "right"
            tx = hx + 0.01 if align == "left" else hx + cw - 0.01
            ax.text(tx, ry + row_h / 2, text, color=color, fontsize=fontsize,
                     fontweight=("bold" if bold else "normal"), va="center", ha=align,
                     zorder=3, family="sans-serif")
            hx += cw
    return y - row_h * (n_rows)


def bar_chart_page(fig, ax, bac_dict, color_ok=COLORS["accent"]):
    dias = sorted(bac_dict.keys())
    vals = [bac_dict[d] for d in dias]
    maxv = max(vals) if vals and max(vals) > 0 else 1

    chart_ax = fig.add_axes([0.045, 0.20, 0.91, 0.52])
    chart_ax.set_facecolor(COLORS["bg"])
    xs = range(len(dias))
    bar_colors = [color_ok if v > 0 else COLORS["panel2"] for v in vals]
    chart_ax.bar(xs, vals, color=bar_colors, width=0.62, zorder=3,
                  edgecolor=[COLORS["line"] if v == 0 else color_ok for v in vals],
                  linewidth=1)
    for i, v in enumerate(vals):
        chart_ax.text(i, v + maxv * 0.02, str(v), ha="center", va="bottom",
                       color=COLORS["text"], fontsize=10, fontweight="bold")
    chart_ax.set_xticks(list(xs))
    chart_ax.set_xticklabels([str(d) for d in dias], color=COLORS["muted"], fontsize=10)
    chart_ax.set_yticks([])
    for spine in ["top", "right", "left"]:
        chart_ax.spines[spine].set_visible(False)
    chart_ax.spines["bottom"].set_color(COLORS["line"])
    chart_ax.set_ylim(0, maxv * 1.25)
    chart_ax.tick_params(axis="x", length=0)


def _dibujar_proyeccion(fig, ax_page, rect, area, proy):
    """Proyección de cierre — mismos 2 métodos y mismo lenguaje visual que la
    gráfica de la Intranet (/pipeline → Resumen Lima): Cuota, Tendencia
    (regresión), Ritmo actual (plano) y Acumulado real."""
    x, y, w, h = rect
    ax_page.text(x, y + h + 0.028, area.upper(), color=COLORS["text"], fontsize=13,
                 fontweight="bold", family="sans-serif")

    cax = fig.add_axes(rect)
    cax.set_facecolor(COLORS["bg"])

    dias = proy["dias"]
    base_dias = proy["base_dias"]
    real = [v if v is not None else float("nan") for v in proy["real"]]

    if proy["cuota"] > 0:
        cax.axhline(proy["cuota"], color=COLORS["slate"], linewidth=1.2,
                     linestyle=(0, (5, 4)), zorder=2)
    cax.plot(dias, proy["tendencia"], color=COLORS["accent"], linewidth=2, zorder=3)
    cax.plot(dias, proy["plano"], color=COLORS["muted"], linewidth=1.6,
              linestyle=(0, (2, 2)), zorder=3)
    cax.plot(dias, real, color=COLORS["success"], linewidth=2.4, zorder=4)
    cax.fill_between(dias, 0, real, color=COLORS["success"], alpha=0.14, zorder=1)

    vals = list(proy["plano"]) + list(proy["tendencia"]) + [v for v in real if v == v]
    if proy["cuota"] > 0:
        vals.append(proy["cuota"])
    ymax = max(vals) * 1.18 if vals else 10
    cax.set_ylim(0, ymax)
    cax.set_xlim(1, base_dias)

    dia_hoy = proy["dias_trans"]
    if 0 < dia_hoy < base_dias:
        cax.axvline(dia_hoy, color=COLORS["text"], alpha=0.22, linewidth=1,
                     linestyle=(0, (3, 3)), zorder=2)
        cax.text(dia_hoy, ymax * 0.97, "HOY", color=COLORS["text"], fontsize=8,
                  fontweight="bold", ha="center", va="top", alpha=0.75)
        if dia_hoy - 1 < len(real) and real[dia_hoy - 1] == real[dia_hoy - 1]:
            cax.annotate(fmt(real[dia_hoy - 1]), xy=(dia_hoy, real[dia_hoy - 1]), xytext=(0, 9),
                         textcoords="offset points", ha="center", color=COLORS["text"],
                         fontsize=9, fontweight="bold")

    end_items = [
        {"value": proy["tendencia"][-1], "y": proy["tendencia"][-1], "color": COLORS["accent"]},
        {"value": proy["plano"][-1], "y": proy["plano"][-1], "color": COLORS["muted"]},
    ]
    if proy["cuota"] > 0:
        end_items.append({"value": proy["cuota"], "y": proy["cuota"], "color": COLORS["slate"]})
    end_items.sort(key=lambda it: it["y"])
    min_gap = ymax * 0.08
    for i in range(1, len(end_items)):
        if end_items[i]["y"] - end_items[i - 1]["y"] < min_gap:
            end_items[i]["y"] = end_items[i - 1]["y"] + min_gap
    for it in end_items:
        cax.annotate(fmt(it["value"]), xy=(base_dias, it["y"]), xytext=(5, 0),
                     textcoords="offset points", va="center", ha="left",
                     color=it["color"], fontsize=8.5, fontweight="bold", clip_on=False)

    cax.set_xticks(list(range(1, base_dias + 1, 4)))
    cax.tick_params(colors=COLORS["muted"], labelsize=8, length=0)
    cax.grid(axis="y", color=COLORS["line"], linewidth=0.6, alpha=0.6)
    for s in ("top", "right"):
        cax.spines[s].set_visible(False)
    cax.spines["left"].set_color(COLORS["line"])
    cax.spines["bottom"].set_color(COLORS["line"])

    piso = min(proy["plano"][-1], proy["tendencia"][-1])
    techo = max(proy["plano"][-1], proy["tendencia"][-1])
    linea = f"Piso {fmt(piso)} · techo {fmt(techo)}"
    if proy["cuota"] > 0 and techo > piso:
        pct_rango = (proy["cuota"] - piso) / (techo - piso) * 100
        ubic = ("bajo" if pct_rango <= 20 else "medio-bajo" if pct_rango <= 45
                else "medio" if pct_rango <= 55 else "medio-alto" if pct_rango <= 80 else "alto")
        linea += f" — la cuota está en el rango {ubic}"
    ax_page.text(x, y - 0.03, linea, color=COLORS["muted"], fontsize=9, family="sans-serif")


def _leyenda_proyeccion(ax_page, y):
    items = [
        ("Cuota", COLORS["slate"], (0, (5, 4))),
        ("Tendencia (regresión)", COLORS["accent"], "solid"),
        ("Ritmo actual (plano)", COLORS["muted"], (0, (2, 2))),
        ("Acumulado real", COLORS["success"], "solid"),
    ]
    xs = [0.045, 0.255, 0.545, 0.775]
    for (label, color, style), x in zip(items, xs):
        ax_page.plot([x, x + 0.022], [y, y], color=color, linewidth=2.6,
                      linestyle=style, solid_capstyle="round")
        ax_page.text(x + 0.028, y, label, color=COLORS["muted"], fontsize=9.5,
                     va="center", family="sans-serif")


# ----------------------------------------------------------------------
# Construcción del PDF
# ----------------------------------------------------------------------

def build(datos):
    fecha_corte = datos["fecha_corte"]
    dia_corte = datos["dia_corte"]
    dias_mes_real = datos["dias_mes_real"]
    metas = datos["metas"]
    out_path = f"Reporte_Proyeccion_Aliv_{fecha_corte.isoformat()}.pdf"
    TOTAL_PAGES = 9

    with PdfPages(out_path) as pdf:

        # ---------------- Página 1: Portada ----------------
        fig, ax = new_page()
        ax.text(0.5, 0.62, "REPORTE COMERCIAL · CONECTADO A SQL SERVER", color=COLORS["accent"],
                 fontsize=13, fontweight="bold", ha="center", family="sans-serif")
        ax.text(0.5, 0.53, "Proyección diaria y\nnecesidad de incentivos", color=COLORS["text"],
                 fontsize=30, fontweight="bold", ha="center", va="center", family="sans-serif",
                 linespacing=1.3)
        ax.text(0.5, 0.40, "Horizontal y Vertical — qué falta para llegar a la cuota, cuánto por día, y qué ya está agendado.",
                 color=COLORS["muted"], fontsize=13, ha="center", family="sans-serif")
        ax.text(0.5, 0.10, f"Corte: {fecha_corte.day} de {mes_es(fecha_corte)} de {fecha_corte.year} (día {dia_corte} del mes)"
                            "  ·  Fuente: SQL Server (winforce_lima)",
                 color=COLORS["muted"], fontsize=11, ha="center", family="sans-serif")
        footer(ax, 1, TOTAL_PAGES, fecha_corte)
        pdf.savefig(fig, facecolor=COLORS["bg"]); plt.close(fig)

        # ---------------- Página 2: Situación ----------------
        fig, ax = new_page()
        eyebrow(ax, "01 · El objetivo")
        title(ax, "¿Vamos a llegar a la meta?")
        subtitle(ax, f"Proyección a {DIAS_PROYECCION_INTERNA} días con el ritmo actual, y avance real frente a la cuota oficial.")

        card_w, card_h, gap = 0.435, 0.46, 0.035
        x0 = 0.045
        for i, area in enumerate(AREAS):
            x = x0 + i * (card_w + gap)
            y = 0.20
            kpi = datos["areas"][area]["kpi"]
            pct_proy = pct_actual(kpi)
            color = COLORS["danger"] if pct_proy < 100 else COLORS["success"]
            card(ax, x, y, card_w, card_h)
            ax.text(x + 0.03, y + card_h - 0.06, area.upper(), color=COLORS["muted"],
                     fontsize=12, fontweight="bold", family="sans-serif")
            ax.text(x + 0.03, y + card_h - 0.20, f"{pct_proy:.1f}%", color=color,
                     fontsize=42, fontweight="bold", family="sans-serif")
            ax.text(x + 0.03, y + card_h - 0.245,
                     f"Proyectado a {DIAS_PROYECCION_INTERNA}d vs. cuota oficial",
                     color=COLORS["muted"], fontsize=10, family="sans-serif")
            ax.text(x + 0.03, y + 0.175,
                     f"Cuota: {fmt(kpi.get('cuota', 0))}   ·   Altas: {fmt(kpi.get('altas', 0))}",
                     color=COLORS["muted"], fontsize=11, family="sans-serif")

            cuota = kpi.get("cuota", 0)
            pct_real = (kpi.get("altas", 0) / cuota * 100) if cuota else 0
            pct_ideal = dia_corte / dias_mes_real * 100
            barra_meta(ax, x + 0.03, y + 0.105, card_w - 0.06, 0.032, pct_real, color, pct_ideal=pct_ideal)
            ax.text(x + 0.03, y + 0.075, f"Avance real: {pct_real:.1f}%   ·   ideal a hoy: {pct_ideal:.1f}%",
                     color=COLORS["muted"], fontsize=9, family="sans-serif")

            msg = ("Proyectando por debajo de la cuota oficial" if pct_proy < 100
                   else "Encaminado — mantener o mejorar el ritmo")
            ax.text(x + 0.03, y + 0.035, msg, color=color, fontsize=11,
                     family="sans-serif", style="italic")

        note(ax, f"% Proyectado = (Altas ÷ días transcurridos × {DIAS_PROYECCION_INTERNA}) ÷ Cuota × 100"
                  "   ·   la barra muestra el avance real de hoy frente a la cuota; la marca blanca es el avance ideal al día de corte.")
        footer(ax, 2, TOTAL_PAGES, fecha_corte)
        pdf.savefig(fig, facecolor=COLORS["bg"]); plt.close(fig)

        # ---------------- Página 3: Metas + necesidad bruta ----------------
        fig, ax = new_page()
        eyebrow(ax, "02 · Metas y necesidad diaria")
        title(ax, "A dónde necesitamos llegar", y=0.85)
        subtitle(ax, "Cuota oficial primero, meta estirada para incentivos después — dos escenarios de días restantes.", y=0.795)

        headers = ["Meta", "Cuota Meta", "Faltante", f"{DIAS_PROYECCION_INTERNA}d /día",
                   f"{dias_mes_real}d /día"]
        col_w = [0.30, 0.15, 0.15, 0.16, 0.15]
        rows = []
        for m in metas:
            rows.append([
                m["label"],
                fmt(m["cuota_meta"]),
                fmt(m["faltante_bruto"]),
                (f"{fmt(m['necesidad_bruta_29'], 1)}", True, COLORS["text"]),
                fmt(m["necesidad_bruta_31"], 1),
            ])
        draw_table(ax, 0.045, 0.72, 0.91, headers, rows, col_w, row_h=0.085, fontsize=12)
        note(ax, "Ritmo total necesario, sin descontar el BAC ya agendado (siguiente página).", y=0.16)
        footer(ax, 3, TOTAL_PAGES, fecha_corte)
        pdf.savefig(fig, facecolor=COLORS["bg"]); plt.close(fig)

        # ---------------- Página 4: BAC concepto ----------------
        fig, ax = new_page()
        eyebrow(ax, "03 · BAC")
        title(ax, "Lo que ya está vendido, solo falta instalar")
        subtitle(ax, "BAC = ventas ya cerradas y agendadas. No requieren vender más — "
                      "requieren que la cita se cumpla.")

        for i, area in enumerate(AREAS):
            x = x0 + i * (card_w + gap)
            y = 0.30    
            card(ax, x, y, card_w, 0.35)
            ax.text(x + 0.03, y + 0.24, fmt(datos["areas"][area]["bac_total"]), color=COLORS["accent"],
                     fontsize=46, fontweight="bold", family="sans-serif")
            ax.text(x + 0.03, y + 0.06, f"Instalaciones {area} agendadas (días restantes)",
                     color=COLORS["muted"], fontsize=11, family="sans-serif")
        footer(ax, 4, TOTAL_PAGES, fecha_corte)
        pdf.savefig(fig, facecolor=COLORS["bg"]); plt.close(fig)

        # ---------------- Página 5 y 6: BAC por día ----------------
        for page_n, area in zip([5, 6], AREAS):
            fig, ax = new_page()
            eyebrow(ax, f"03 · BAC — {area}")
            title(ax, "Instalaciones ya programadas por día", y=0.85)
            bac = datos["areas"][area]["bac"]
            bar_chart_page(fig, ax, bac)
            dias_vacios = [str(d) for d, v in bac.items() if v == 0]
            if dias_vacios:
                note(ax, f"⚠ Sin nada agendado el {', '.join(dias_vacios)} de este mes.",
                     y=0.12, color=COLORS["danger"])
            footer(ax, page_n, TOTAL_PAGES, fecha_corte)
            pdf.savefig(fig, facecolor=COLORS["bg"]); plt.close(fig)

        # ---------------- Página 7: Proyección de cierre — dos métodos ----------------
        fig, ax = new_page()
        eyebrow(ax, "04 · Proyección de cierre")
        title(ax, "¿El ritmo actual nos lleva a la meta?", y=0.85)
        subtitle(ax, f"Dos métodos a {DIAS_PROYECCION_INTERNA} días: ritmo actual (plano) y tendencia (regresión). "
                      f"Corte: día {dia_corte}.", y=0.795)

        # Cada mitad reserva su propio "gutter" a la derecha para las etiquetas
        # de valor final — si no, las del panel izquierdo se montan sobre los
        # ticks del eje Y del panel derecho.
        rects = [[0.045, 0.24, 0.36, 0.46], [0.50, 0.24, 0.36, 0.46]]
        for area, rect in zip(AREAS, rects):
            _dibujar_proyeccion(fig, ax, rect, area, datos["areas"][area]["proy"])
        _leyenda_proyeccion(ax, y=0.155)
        footer(ax, 7, TOTAL_PAGES, fecha_corte)
        pdf.savefig(fig, facecolor=COLORS["bg"]); plt.close(fig)

        # ---------------- Página 8: necesidad neta ----------------
        fig, ax = new_page()
        eyebrow(ax, "05 · El número real")
        title(ax, "Necesidad diaria neta (después del BAC)", y=0.85)
        subtitle(ax, "Esto es lo que debe apuntar el incentivo: ventas nuevas, no lo ya agendado.", y=0.795)

        headers = ["Meta", "BAC", "Faltante neto", f"{DIAS_PROYECCION_INTERNA}d", f"{dias_mes_real}d"]
        col_w = [0.28, 0.13, 0.16, 0.17, 0.17]
        rows = []
        for m in metas:
            rows.append([
                m["label"],
                fmt(m["bac"]),
                fmt(m["faltante_neto"]),
                (f"{fmt(m['necesidad_neta_29'], 1)} /día", True, COLORS["accent"]),
                f"{fmt(m['necesidad_neta_31'], 1)} /día",
            ])
        draw_table(ax, 0.045, 0.72, 0.91, headers, rows, col_w, row_h=0.085, fontsize=12)
        note(ax, f"Recomendación: usar el escenario de {DIAS_PROYECCION_INTERNA} días para diseñar "
                  "el incentivo — es el más exigente.", y=0.16)
        footer(ax, 8, TOTAL_PAGES, fecha_corte)
        pdf.savefig(fig, facecolor=COLORS["bg"]); plt.close(fig)

        # ---------------- Página 9: cierre / recomendación ----------------
        fig, ax = new_page()
        eyebrow(ax, "06 · Recomendación")
        title(ax, "Cómo estructurar el incentivo hoy", y=0.85)

        h_meta = next(m for m in metas if m["area"] == "Horizontal" and m["pct_meta"] == 100)
        v_meta = next(m for m in metas if m["area"] == "Vertical" and m["pct_meta"] == 100)
        h_meta_stretch = next(m for m in metas if m["area"] == "Horizontal" and m["pct_meta"] != 100)
        v_meta_stretch = next(m for m in metas if m["area"] == "Vertical" and m["pct_meta"] != 100)
        items = [
            f"Primero la cuota oficial: ~{fmt(h_meta['necesidad_neta_29'], 0)}/día horizontal y "
            f"~{fmt(v_meta['necesidad_neta_29'], 0)}/día vertical, netos de BAC.",
            f"Si eso está encaminado, empujar hacia la meta estirada ({h_meta_stretch['pct_meta']}%): "
            f"~{fmt(h_meta_stretch['necesidad_neta_29'], 0)}/día horizontal y "
            f"~{fmt(v_meta_stretch['necesidad_neta_29'], 0)}/día vertical.",
            "Push específico para llenar el BAC de los días sin nada agendado (ver páginas 5 y 6).",
            f"Medir contra el escenario de {DIAS_PROYECCION_INTERNA} días — el más exigente.",
            "Revisar el BAC diario junto con el equipo de agendamiento, no sólo con ventas.",
        ]
        y = 0.68
        for i, text in enumerate(items):
            circ = Ellipse(
                (0.075, y), width=0.056, height=0.056 * PAGE_SIZE[0] / PAGE_SIZE[1],
                facecolor=COLORS["panel2"], edgecolor=COLORS["accent"], linewidth=1.4,
                zorder=3, transform=ax.transData)
            ax.add_patch(circ)
            ax.text(0.075, y, str(i + 1), color=COLORS["accent"], fontsize=13,
                     fontweight="bold", ha="center", va="center", zorder=4, family="sans-serif")
            ax.text(0.13, y, text, color=COLORS["text"], fontsize=12.5, va="center",
                     family="sans-serif", wrap=True)
            y -= 0.12
        footer(ax, 9, TOTAL_PAGES, fecha_corte)
        pdf.savefig(fig, facecolor=COLORS["bg"]); plt.close(fig)

    print(f"Listo: {out_path}")
    return out_path


if __name__ == "__main__":
    fecha_corte = datetime.now().date() - timedelta(days=1)
    print(f"Generando reporte de proyección para el corte: {fecha_corte.strftime('%d/%m/%Y')}")

    try:
        datos = extraer_datos(fecha_corte)
        for area in AREAS:
            k = datos["areas"][area]["kpi"]
            print(f"  {area} — Altas: {k.get('altas')}  Cuota: {k.get('cuota')}  "
                  f"Ritmo: {k.get('ritmo_actual')}/día  BAC: {datos['areas'][area]['bac_total']}")
    except Exception as e:
        print(f"Error extrayendo datos: {e}")
        sys.exit(1)

    build(datos)
