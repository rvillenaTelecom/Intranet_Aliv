from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import sqlalchemy as sa
import pandas as pd
import urllib
import math
import os

app = FastAPI(title="Morosidad Dashboard — Aliv Telecom")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── DB ─────────────────────────────────────────────────────
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_engine():
    if DATABASE_URL:
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return sa.create_engine(url)
    cs = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        r"SERVER=.\SQLEXPRESS;"
        "DATABASE=Aliv_DB;Trusted_Connection=yes;"
    )
    return sa.create_engine(
        f"mssql+pyodbc:///?odbc_connect={urllib.parse.quote_plus(cs)}",
        fast_executemany=True
    )

def q(sql, params=None):
    engine = get_engine()
    if params:
        return pd.read_sql(sa.text(sql), engine, params=params)
    return pd.read_sql(sa.text(sql), engine)

def sf(v):
    try:
        f = float(v)
        return 0.0 if (math.isnan(f) or math.isinf(f)) else f
    except Exception:
        return 0.0

# ── SQL constants ──────────────────────────────────────────
V = 'dbo.v_ventas_aliv_completa'
NPNF   = "([Estado M1] IN ('Churn','Cliente De Baja') AND [R1_Ya_Vencio] = 1)"
PAG_R1 = "([Estado M1] IN ('Cliente Pago','Tercero Pago'))"
PAG_R2 = "([Estado M1] IN ('Cliente Pago','Tercero Pago') AND [Estado M2] IN ('Cliente Pago','Tercero Pago'))"
PAG_R3 = ("([Estado M1] IN ('Cliente Pago','Tercero Pago')"
          " AND [Estado M2] IN ('Cliente Pago','Tercero Pago')"
          " AND [Estado M3] IN ('Cliente Pago','Tercero Pago'))")
NO_R2  = "([Estado M1] IN ('Cliente Pago','Tercero Pago') AND [Estado M2] IN ('Churn','Cliente De Baja'))"
NO_R3  = ("([Estado M1] IN ('Cliente Pago','Tercero Pago')"
          " AND [Estado M2] IN ('Cliente Pago','Tercero Pago')"
          " AND [Estado M3] IN ('Churn','Cliente De Baja'))")
# NO_R3 variant used in perdidas (reads [Estado M2] as base, not M1 paid chain)
NO_R3V = "([Estado M2] IN ('Cliente Pago','Tercero Pago') AND [Estado M3] IN ('Churn','Cliente De Baja'))"


def build_where(mes=None, grupo='', departamento='', supervisor='', tipo_domicilio=''):
    c, p = [], {}
    if mes:
        c.append("AND [Mes_Num_Recibo] = :mes");           p['mes']           = int(mes)
    if grupo:
        c.append("AND [Grupo_Facturacion] = :grupo");      p['grupo']         = grupo
    if departamento:
        c.append("AND [Departamento] = :departamento");    p['departamento']  = departamento
    if supervisor:
        c.append("AND [Supervisor] = :supervisor");        p['supervisor']    = supervisor
    if tipo_domicilio:
        c.append("AND [Tipo de domicilio] = :tdm");        p['tdm']           = tipo_domicilio
    return ' '.join(c), p or None


# ── Endpoints ──────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index():
    html = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/api/filtros")
def filtros():
    try:
        meses_map = {1:'Enero',2:'Febrero',3:'Marzo',4:'Abril',5:'Mayo',6:'Junio',
                     7:'Julio',8:'Agosto',9:'Septiembre',10:'Octubre',11:'Noviembre',12:'Diciembre'}
        mdf  = q(f"SELECT DISTINCT [Mes_Num_Recibo] FROM {V} WHERE [Mes_Num_Recibo] IS NOT NULL ORDER BY [Mes_Num_Recibo]")
        gdf  = q(f"SELECT DISTINCT [Grupo_Facturacion] FROM {V} WHERE [Grupo_Facturacion] IS NOT NULL ORDER BY [Grupo_Facturacion]")
        ddf  = q(f"SELECT DISTINCT [Departamento] FROM {V} WHERE [Departamento] IS NOT NULL ORDER BY [Departamento]")
        sdf  = q(f"SELECT DISTINCT [Supervisor] FROM {V} WHERE [Supervisor] IS NOT NULL ORDER BY [Supervisor]")
        tdf  = q(f"SELECT DISTINCT [Tipo de domicilio] FROM {V} WHERE [Tipo de domicilio] IS NOT NULL ORDER BY [Tipo de domicilio]")
        return {
            'meses':         [{'value': int(r['Mes_Num_Recibo']),
                               'label': meses_map.get(int(r['Mes_Num_Recibo']), str(int(r['Mes_Num_Recibo'])))}
                              for _, r in mdf.iterrows()],
            'grupos':        [r['Grupo_Facturacion'] for _, r in gdf.iterrows()],
            'departamentos': [r['Departamento'] for _, r in ddf.iterrows()],
            'supervisores':  [r['Supervisor'] for _, r in sdf.iterrows()],
            'tipos_domicilio': [r['Tipo de domicilio'] for _, r in tdf.iterrows()],
        }
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@app.get("/api/kpis")
def kpis(
    mes:           str = Query(default=''),
    grupo:         str = Query(default=''),
    departamento:  str = Query(default=''),
    supervisor:    str = Query(default=''),
    tipo_domicilio:str = Query(default=''),
):
    try:
        opt, p = build_where(mes or None, grupo, departamento, supervisor, tipo_domicilio)
        df = q(f"""
            SELECT
                COUNT(*) AS total,
                ISNULL(AVG(CAST(ARPU AS FLOAT)), 0) AS arpu,
                SUM(CASE WHEN [Estado M1] = 'Cliente Pago'   THEN 1 ELSE 0 END) AS m1_cp,
                SUM(CASE WHEN [Estado M1] = 'Tercero Pago'   THEN 1 ELSE 0 END) AS m1_tp,
                SUM(CASE WHEN [Estado M1] = 'Churn'          THEN 1 ELSE 0 END) AS m1_churn,
                SUM(CASE WHEN [Estado M1] = 'Cliente De Baja'THEN 1 ELSE 0 END) AS m1_baja,
                SUM(CASE WHEN {NPNF}   THEN 1 ELSE 0 END) AS npnf,
                SUM(CASE WHEN {PAG_R1} THEN 1 ELSE 0 END) AS pag_r1,
                SUM(CASE WHEN {NO_R2}  THEN 1 ELSE 0 END) AS no_r2,
                SUM(CASE WHEN {PAG_R2} THEN 1 ELSE 0 END) AS pag_r2,
                SUM(CASE WHEN {NO_R3}  THEN 1 ELSE 0 END) AS no_r3,
                SUM(CASE WHEN {PAG_R3} THEN 1 ELSE 0 END) AS pag_r3
            FROM {V} WHERE 1=1 {opt}
        """, p)
        r      = df.iloc[0]
        total  = int(r['total']   or 0)
        arpu   = sf(r['arpu'])
        m1_cp  = int(r['m1_cp']   or 0)
        m1_tp  = int(r['m1_tp']   or 0)
        m1_ch  = int(r['m1_churn']or 0)
        m1_bj  = int(r['m1_baja'] or 0)
        npnf   = int(r['npnf']    or 0)
        pag_r1 = int(r['pag_r1']  or 0)
        no_r2  = int(r['no_r2']   or 0)
        pag_r2 = int(r['pag_r2']  or 0)
        no_r3  = int(r['no_r3']   or 0)
        pag_r3 = int(r['pag_r3']  or 0)

        m1_act = m1_cp + m1_tp
        m1_npnf = m1_ch + m1_bj

        umb_n  = math.floor(total  * 0.045)
        umb_2  = math.floor(pag_r1 * 0.035)
        umb_3  = math.floor(pag_r2 * 0.025)
        exc_n  = max(0, npnf  - umb_n)
        exc_2  = max(0, no_r2 - umb_2)
        exc_3  = max(0, no_r3 - umb_3)

        def pct(a, b): return round(a / b * 100, 2) if b else 0.0

        return {
            'total': total, 'arpu': round(arpu, 2),
            # M1
            'm1_cli_pago':     m1_cp,  'm1_pct_cli_pago': pct(m1_cp, total),
            'm1_tercero_pago': m1_tp,  'm1_pct_tercero':  pct(m1_tp, total),
            'm1_activos':      m1_act, 'm1_historial_pct':pct(m1_act, total),
            'm1_churn':        m1_ch,  'm1_pct_churn':    pct(m1_ch, total),
            'm1_baja':         m1_bj,  'm1_pct_baja':     pct(m1_bj, total),
            'm1_npnf':         m1_npnf,'m1_pct_npnf':     pct(m1_npnf, total),
            'm1_umbral': umb_n, 'm1_diferencia': m1_npnf - umb_n,
            'm1_exceso': exc_n, 'm1_costo': round(exc_n * arpu * 3.5 * 1.0, 2),
            # M2
            'pag_r1': pag_r1, 'no_r2': no_r2, 'pag_r2': pag_r2,
            'm2_historial_pct': pct(pag_r2, pag_r1),
            'm2_pct_morosos':   pct(no_r2, pag_r1),
            'm2_umbral': umb_2, 'm2_diferencia': no_r2 - umb_2,
            'm2_exceso': exc_2, 'm2_costo': round(exc_2 * arpu * 3.5 * 0.666, 2),
            # M3
            'no_r3': no_r3, 'pag_r3': pag_r3,
            'm3_historial_pct': pct(pag_r3, pag_r2),
            'm3_pct_morosos':   pct(no_r3, pag_r2),
            'm3_umbral': umb_3, 'm3_diferencia': no_r3 - umb_3,
            'm3_exceso': exc_3, 'm3_costo': round(exc_3 * arpu * 3.5 * 0.333, 2),
        }
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({'error': str(e)}, status_code=500)


@app.get("/api/supervisores")
def supervisores_api(
    mes:           str = Query(default=''),
    grupo:         str = Query(default=''),
    departamento:  str = Query(default=''),
    supervisor:    str = Query(default=''),
    tipo_domicilio:str = Query(default=''),
):
    try:
        opt, p = build_where(mes or None, grupo, departamento, supervisor, tipo_domicilio)
        df = q(f"""
            SELECT
                ISNULL([Supervisor], 'Sin supervisor') AS supervisor,
                COUNT(*) AS total,
                SUM(CASE WHEN [Estado M1] = 'Cliente Pago'    THEN 1 ELSE 0 END) AS cli_pago,
                SUM(CASE WHEN [Estado M1] = 'Tercero Pago'    THEN 1 ELSE 0 END) AS tercero_pago,
                SUM(CASE WHEN [Estado M1] = 'Churn'           THEN 1 ELSE 0 END) AS churn,
                SUM(CASE WHEN [Estado M1] = 'Cliente De Baja' THEN 1 ELSE 0 END) AS baja,
                SUM(CASE WHEN {PAG_R1} THEN 1 ELSE 0 END) AS pag_r1,
                SUM(CASE WHEN {NO_R2}  THEN 1 ELSE 0 END) AS no_r2,
                SUM(CASE WHEN {PAG_R2} THEN 1 ELSE 0 END) AS pag_r2,
                SUM(CASE WHEN {NO_R3}  THEN 1 ELSE 0 END) AS no_r3
            FROM {V} WHERE 1=1 {opt}
            GROUP BY [Supervisor]
            ORDER BY COUNT(*) DESC
        """, p)
        return [
            {
                'supervisor':   r['supervisor'],
                'total':        int(r['total']       or 0),
                'cli_pago':     int(r['cli_pago']    or 0),
                'tercero_pago': int(r['tercero_pago']or 0),
                'churn':        int(r['churn']       or 0),
                'baja':         int(r['baja']        or 0),
                'pag_r1':       int(r['pag_r1']      or 0),
                'no_r2':        int(r['no_r2']       or 0),
                'pag_r2':       int(r['pag_r2']      or 0),
                'no_r3':        int(r['no_r3']       or 0),
            }
            for _, r in df.iterrows()
        ]
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@app.get("/api/embudo")
def embudo_api(
    mes:           str = Query(default=''),
    grupo:         str = Query(default=''),
    departamento:  str = Query(default=''),
    supervisor:    str = Query(default=''),
    tipo_domicilio:str = Query(default=''),
):
    try:
        opt, p = build_where(mes or None, grupo, departamento, supervisor, tipo_domicilio)
        df = q(f"""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN {PAG_R1} THEN 1 ELSE 0 END) AS pag_r1,
                SUM(CASE WHEN {PAG_R2} THEN 1 ELSE 0 END) AS pag_r2,
                SUM(CASE WHEN {PAG_R3} THEN 1 ELSE 0 END) AS pag_r3
            FROM {V} WHERE 1=1 {opt}
        """, p)
        r = df.iloc[0]
        t = int(r['total'] or 0)
        pct = lambda x: round(x / t * 100, 1) if t else 0
        p1 = int(r['pag_r1'] or 0)
        p2 = int(r['pag_r2'] or 0)
        p3 = int(r['pag_r3'] or 0)
        return {'total': t,
                'pag_r1': p1, 'pct_r1': pct(p1),
                'pag_r2': p2, 'pct_r2': pct(p2),
                'pag_r3': p3, 'pct_r3': pct(p3)}
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@app.get("/api/perdidas")
def perdidas_api(
    mes:           str = Query(default=''),
    grupo:         str = Query(default=''),
    departamento:  str = Query(default=''),
    supervisor:    str = Query(default=''),
    tipo_domicilio:str = Query(default=''),
):
    try:
        opt, p = build_where(mes or None, grupo, departamento, supervisor, tipo_domicilio)
        df = q(f"""
            SELECT
                COUNT(*) AS total,
                ISNULL(AVG(CAST(ARPU AS FLOAT)), 0) AS arpu,
                SUM(CASE WHEN {NPNF}   THEN 1 ELSE 0 END) AS npnf,
                SUM(CASE WHEN {PAG_R1} THEN 1 ELSE 0 END) AS pag_r1,
                SUM(CASE WHEN {NO_R2}  THEN 1 ELSE 0 END) AS no_r2,
                SUM(CASE WHEN {PAG_R2} THEN 1 ELSE 0 END) AS pag_r2,
                SUM(CASE WHEN {NO_R3V} THEN 1 ELSE 0 END) AS no_r3
            FROM {V} WHERE 1=1 {opt}
        """, p)
        r = df.iloc[0]
        total  = int(r['total']  or 0)
        arpu   = sf(r['arpu'])
        npnf   = int(r['npnf']   or 0)
        pag_r1 = int(r['pag_r1'] or 0)
        no_r2  = int(r['no_r2']  or 0)
        pag_r2 = int(r['pag_r2'] or 0)
        no_r3  = int(r['no_r3']  or 0)

        umb_n = math.floor(total  * 0.045)
        umb_2 = math.floor(pag_r1 * 0.035)
        umb_3 = math.floor(pag_r2 * 0.025)
        exc_n = max(0, npnf  - umb_n)
        exc_2 = max(0, no_r2 - umb_2)
        exc_3 = max(0, no_r3 - umb_3)

        def pct(m, b): return round(m / b * 100, 2) if b else 0.0
        def sem(v, u):
            if u == 0: return 'ok'
            ratio = v / u
            return 'ok' if ratio <= 0.7 else ('alerta' if ratio <= 1.0 else 'critico')

        pct_n = pct(npnf,  total)
        pct_2 = pct(no_r2, pag_r1)
        pct_3 = pct(no_r3, pag_r2)

        return [
            {'concepto': 'Extorno 2 — Cayeron en R2',
             'base': pag_r1, 'umbral': umb_2, 'umbral_pct': 3.5,
             'morosos': no_r2, 'pct_mora': pct_2, 'exceso': exc_2,
             'costo': round(exc_2 * arpu * 3.5 * 0.666, 2), 'semaforo': sem(pct_2, 3.5)},
            {'concepto': 'Extorno 3 — Cayeron en R3',
             'base': pag_r2, 'umbral': umb_3, 'umbral_pct': 2.5,
             'morosos': no_r3, 'pct_mora': pct_3, 'exceso': exc_3,
             'costo': round(exc_3 * arpu * 3.5 * 0.333, 2), 'semaforo': sem(pct_3, 2.5)},
            {'concepto': 'NPNF — No pagaron R1',
             'base': total, 'umbral': umb_n, 'umbral_pct': 4.5,
             'morosos': npnf, 'pct_mora': pct_n, 'exceso': exc_n,
             'costo': round(exc_n * arpu * 3.5 * 1.0, 2), 'semaforo': sem(pct_n, 4.5)},
        ]
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({'error': str(e)}, status_code=500)


@app.get("/api/pagos-dia")
def pagos_dia_api(
    mes:           str = Query(default=''),
    grupo:         str = Query(default=''),
    departamento:  str = Query(default=''),
    supervisor:    str = Query(default=''),
    tipo_domicilio:str = Query(default=''),
):
    try:
        from datetime import date
        opt, p = build_where(mes or None, grupo, departamento, supervisor, tipo_domicilio)
        df = q(f"""
            WITH base AS (
                SELECT
                    DAY(TRY_CAST([Fecha pago 1] AS DATE)) AS d1,
                    DAY(TRY_CAST([Fecha pago 2] AS DATE)) AS d2,
                    DAY(TRY_CAST([Fecha pago 3] AS DATE)) AS d3
                FROM {V} WHERE 1=1 {opt}
            ),
            r1 AS (SELECT d1 AS dia, COUNT(*) AS n FROM base WHERE d1 IS NOT NULL GROUP BY d1),
            r2 AS (SELECT d2 AS dia, COUNT(*) AS n FROM base WHERE d2 IS NOT NULL GROUP BY d2),
            r3 AS (SELECT d3 AS dia, COUNT(*) AS n FROM base WHERE d3 IS NOT NULL GROUP BY d3),
            dias AS (SELECT n FROM (VALUES
                (1),(2),(3),(4),(5),(6),(7),(8),(9),(10),(11),
                (12),(13),(14),(15),(16),(17),(18),(19),(20),(21),
                (22),(23),(24),(25),(26),(27),(28),(29),(30),(31)
            ) v(n))
            SELECT
                d.n              AS dia,
                ISNULL(r1.n, 0) AS pagaron_r1,
                ISNULL(r2.n, 0) AS pagaron_r2,
                ISNULL(r3.n, 0) AS pagaron_r3
            FROM dias d
            LEFT JOIN r1 ON r1.dia = d.n
            LEFT JOIN r2 ON r2.dia = d.n
            LEFT JOIN r3 ON r3.dia = d.n
            ORDER BY d.n
        """, p)
        # Corte WIN: día 18 del mes; si el mes filtrado es el mes actual y ya pasó el 18,
        # usamos hoy para marcar hasta dónde hay datos.
        hoy = date.today()
        corte_dia = 18
        return {
            'corte_dia': corte_dia,
            'dias': [
                {
                    'dia':        int(r['dia']),
                    'pagaron_r1': int(r['pagaron_r1'] or 0),
                    'pagaron_r2': int(r['pagaron_r2'] or 0),
                    'pagaron_r3': int(r['pagaron_r3'] or 0),
                }
                for _, r in df.iterrows()
            ],
        }
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({'error': str(e)}, status_code=500)


@app.get("/api/perdidas-recibo")
def perdidas_recibo_api(
    mes:           str = Query(default=''),
    grupo:         str = Query(default=''),
    departamento:  str = Query(default=''),
    supervisor:    str = Query(default=''),
    tipo_domicilio:str = Query(default=''),
):
    try:
        opt, p = build_where(mes or None, grupo, departamento, supervisor, tipo_domicilio)
        df = q(f"""
            SELECT
                ISNULL(CAST(Recibo_Actual AS VARCHAR(20)), 'Sin recibo') AS recibo,
                COUNT(*) AS total,
                ISNULL(AVG(CAST(ARPU AS FLOAT)), 0) AS arpu,
                SUM(CASE WHEN {NPNF}   THEN 1 ELSE 0 END) AS npnf,
                SUM(CASE WHEN {PAG_R1} THEN 1 ELSE 0 END) AS pag_r1,
                SUM(CASE WHEN {NO_R2}  THEN 1 ELSE 0 END) AS no_r2,
                SUM(CASE WHEN {PAG_R2} THEN 1 ELSE 0 END) AS pag_r2,
                SUM(CASE WHEN {NO_R3V} THEN 1 ELSE 0 END) AS no_r3
            FROM {V} WHERE 1=1 {opt}
            GROUP BY Recibo_Actual
            ORDER BY Recibo_Actual
        """, p)
        rows = []
        for _, r in df.iterrows():
            total  = int(r['total']  or 0)
            arpu   = sf(r['arpu'])
            npnf   = int(r['npnf']   or 0)
            pag_r1 = int(r['pag_r1'] or 0)
            no_r2  = int(r['no_r2']  or 0)
            pag_r2 = int(r['pag_r2'] or 0)
            no_r3  = int(r['no_r3']  or 0)
            umb = math.floor(total * 0.045)
            exc = max(0, npnf - umb)
            pct = round(npnf / total * 100, 2) if total else 0.0
            def sem(v, u):
                if u == 0: return 'ok'
                ratio = v / u
                return 'ok' if ratio <= 0.7 else ('alerta' if ratio <= 1.0 else 'critico')
            rows.append({
                'recibo': r['recibo'],
                'base': total, 'umbral': umb, 'umbral_pct': 4.5,
                'morosos': npnf, 'pct_mora': pct,
                'exceso': exc, 'costo': round(exc * arpu * 3.5 * 1.0, 2),
                'semaforo': sem(pct, 4.5),
                # extra for tooltip
                'no_r2': no_r2, 'no_r3': no_r3,
            })
        return rows
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)
