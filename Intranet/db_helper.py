try:
    from db_config import get_data
except ImportError:
    from .db_config import get_data
import calendar
from datetime import datetime

# Cuota Lima por área — fuente: DAX DATATABLE (no existe en SQL)
# Clave: (mes_num, area)  area='' para el total Lima
_CUOTA_LIMA = {
    (1, ''):  2010,  (1, 'Horizontal'): 1780,  (1, 'Vertical'):  230,
    (2, ''):  2210,  (2, 'Horizontal'): 1950,  (2, 'Vertical'):  260,
    (3, ''):  1920,  (3, 'Horizontal'): 1689,  (3, 'Vertical'):  231,
    (4, ''):  1838,  (4, 'Horizontal'): 1528,  (4, 'Vertical'):  310,
    (5, ''):  2332,  (5, 'Horizontal'): 2012,  (5, 'Vertical'):  320,
    (6, ''):  2500,  (6, 'Horizontal'): 2186,  (6, 'Vertical'):  314,
}


def _dias_mes(mes, anio):
    """Días transcurridos, totales y restantes del mes."""
    hoy = datetime.now()
    dias_tot = calendar.monthrange(anio, mes)[1]
    dias_trans = hoy.day if (hoy.month == mes and hoy.year == anio) else dias_tot
    dias_rest = max(dias_tot - dias_trans, 1)
    return dias_trans, dias_tot, dias_rest


def _safe_int(val, default=0):
    try:
        v = float(val)
        return default if (v != v) else int(v)  # NaN check
    except:
        return default


# Fecha programación almacenada como VARCHAR en formato DD-MM-YYYY
# TRY_CONVERT con estilo 105 = dd-mm-yyyy (evita que SQL Server la lea como MM-DD-YYYY)
_FP = "TRY_CONVERT(DATE, LEFT([Fecha programación], 10), 105)"


def _area_clause(area, col='[Tipo de domicilio]'):
    """SQL AND fragment for Área de planeamiento (Vertical = C/E Habilitado, Horizontal = resto)."""
    if area == 'Vertical':
        return f"AND ({col} = 'Condominio/Edificio' OR {col} = 'C/E Habilitado')"
    elif area == 'Horizontal':
        return f"AND ({col} NOT IN ('Condominio/Edificio', 'C/E Habilitado') OR {col} IS NULL)"
    return ""


def _dept_lima(alias=''):
    """SQL AND fragment to restrict winforce_lima to Lima + Callao departments."""
    p = f"{alias}." if alias else ""
    return f"AND {p}[Departamento] IN ('Lima', 'Callao')"


def get_kpi_lima(mes, anio, area='', dia=None):
    """KPIs completos para Lima. dia(1-31): filtra ventas/altas de ese día."""
    dias_trans, dias_tot, dias_rest = _dias_mes(mes, anio)
    _ac = _area_clause(area)
    _dr = "AND DAY([Fecha de registro]) = :dia" if dia else ""
    _da = f"AND DAY({_FP}) = :dia" if dia else ""
    p   = {'mes': mes, 'anio': anio}
    if dia:
        p['dia'] = int(dia)
    try:
        _dl = _dept_lima()
        df = get_data(f"""
            SELECT
                (SELECT COUNT(*) FROM dbo.winforce_lima
                 WHERE MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
                 {_dl} {_ac} {_dr}
                ) AS ventas,
                (SELECT COUNT(*) FROM dbo.winforce_lima
                 WHERE [Estado orden] = 'Ejecutada'
                   AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
                   AND {_FP} IS NOT NULL
                 {_dl} {_ac} {_da}
                ) AS altas,
                (SELECT COUNT(*) FROM dbo.winforce_lima
                 WHERE [Estado orden] = 'Anulado'
                   AND MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
                 {_dl} {_ac} {_dr}
                ) AS anulaciones,
                (SELECT DATEDIFF(DAY, DATEFROMPARTS(:anio, :mes, 1),
                         MAX(CAST([Fecha de registro] AS DATE))) + 1
                 FROM dbo.winforce_lima
                 WHERE MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
                 {_dl}
                ) AS dias_trans_db
        """, params=p)
        r = df.iloc[0]
        altas       = _safe_int(r['altas'])
        ventas      = _safe_int(r['ventas'])
        anulaciones = _safe_int(r['anulaciones'])
        conversion  = round(altas / ventas * 100, 1) if ventas > 0 else 0

        # Para el mes actual, usar el último día con datos en BD (no el día de hoy si hay delay).
        # Para meses cerrados, siempre usar dias_tot — el mes ya terminó.
        hoy = datetime.now()
        if hoy.month == mes and hoy.year == anio:
            dias_trans_db = _safe_int(r['dias_trans_db'], default=dias_trans)
            if dias_trans_db > 0:
                dias_trans = dias_trans_db
        dias_rest = max(dias_tot - dias_trans, 1)

        # Instalados el mismo día (Fecha de registro = Fecha programación)
        instalados_mismo_dia = 0
        try:
            df_id = get_data(f"""
                SELECT COUNT(*) AS cnt
                FROM dbo.winforce_lima
                WHERE [Estado orden] = 'Ejecutada'
                  AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
                  AND {_FP} IS NOT NULL
                  AND CAST([Fecha de registro] AS DATE) = {_FP}
                  {_dl} {_ac} {_da}
            """, params=p)
            instalados_mismo_dia = _safe_int(df_id.iloc[0, 0])
        except:
            pass

        # Score_Minimo_KML
        score = 0
        try:
            df2 = get_data(f"""
                SELECT AVG(TRY_CAST([Score_Minimo_KML] AS FLOAT)) AS score_prom
                FROM dbo.winforce_lima
                WHERE MONTH([Fecha de registro])=:mes AND YEAR([Fecha de registro])=:anio
                  AND [Score_Minimo_KML] IS NOT NULL
                  {_dl} {_ac} {_dr}
            """, params=p)
            score = _safe_int(df2.iloc[0]['score_prom'])
        except:
            pass

        # En modo día, las proyecciones mensuales no aplican
        if dia:
            cuota = proyeccion = pct_proyeccion = alcance = alcance_ideal = 0
            ritmo_actual = ritmo_necesario = faltantes = 0
        else:
            cuota = _CUOTA_LIMA.get((mes, area), 0)
            proyeccion      = round(altas / dias_trans * 30) if dias_trans > 0 else 0
            alcance         = round(altas / cuota * 100, 1) if cuota > 0 else 0
            alcance_ideal   = round(dias_trans / dias_tot * 100, 1)
            ritmo_actual    = round(altas / dias_trans, 1) if dias_trans > 0 else 0
            ritmo_necesario = round(max(cuota - altas, 0) / dias_rest, 1)
            faltantes       = max(cuota - altas, 0)
            pct_proyeccion  = round(proyeccion / cuota * 100, 1) if cuota > 0 else 0

        return {
            'ventas': ventas, 'altas': altas, 'cuota': cuota,
            'anulaciones': anulaciones, 'conversion': conversion,
            'instalados_mismo_dia': instalados_mismo_dia,
            'proyeccion': proyeccion, 'pct_proyeccion': pct_proyeccion,
            'alcance': alcance, 'alcance_ideal': alcance_ideal,
            'ritmo_actual': ritmo_actual, 'ritmo_necesario': ritmo_necesario,
            'faltantes': faltantes, 'score': score,
            'en_riesgo': 0, 'riesgo_pct': 0,
            'dias_trans': dias_trans, 'dias_tot': dias_tot,
        }
    except Exception as e:
        print(f"Error get_kpi_lima: {e}")
        return None


def get_kpi_provincia(mes, anio):
    """KPIs completos para Provincia."""
    dias_trans, dias_tot, dias_rest = _dias_mes(mes, anio)
    try:
        df = get_data(f"""
            SELECT
                (SELECT COUNT(*) FROM dbo.winforce_provincia
                 WHERE MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
                ) AS ventas,
                (SELECT COUNT(*) FROM dbo.winforce_provincia
                 WHERE [Estado orden] = 'Ejecutada'
                   AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
                   AND {_FP} IS NOT NULL
                ) AS altas,
                (SELECT DATEDIFF(DAY, DATEFROMPARTS(:anio, :mes, 1),
                         MAX(CAST([Fecha de registro] AS DATE))) + 1
                 FROM dbo.winforce_provincia
                 WHERE MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
                ) AS dias_trans_db
        """, params={'mes': mes, 'anio': anio})
        r = df.iloc[0]
        altas      = _safe_int(r['altas'])
        ventas     = _safe_int(r['ventas'])
        conversion = round(altas / ventas * 100, 1) if ventas > 0 else 0

        hoy = datetime.now()
        if hoy.month == mes and hoy.year == anio:
            dias_trans_db = _safe_int(r['dias_trans_db'], default=dias_trans)
            if dias_trans_db > 0:
                dias_trans = dias_trans_db
        dias_rest = max(dias_tot - dias_trans, 1)

        try:
            dc = get_data("SELECT SUM(Cuota) AS c FROM dbo.Cuota_Prov WHERE Mes_num=:mes AND Region='Provincia'", params={'mes': mes})
            cuota = _safe_int(dc.iloc[0, 0], default=1054)
        except:
            cuota = 1054

        proyeccion      = round(altas / dias_trans * 30) if dias_trans > 0 else 0
        alcance         = round(altas / cuota * 100, 1) if cuota > 0 else 0
        alcance_ideal   = round(dias_trans / dias_tot * 100, 1)
        ritmo_actual    = round(altas / dias_trans, 1) if dias_trans > 0 else 0
        ritmo_necesario = round(max(cuota - altas, 0) / dias_rest, 1)
        faltantes       = max(cuota - altas, 0)
        pct_proyeccion  = round(proyeccion / cuota * 100, 1) if cuota > 0 else 0

        return {
            'ventas': ventas, 'altas': altas, 'cuota': cuota,
            'conversion': conversion,
            'proyeccion': proyeccion, 'pct_proyeccion': pct_proyeccion,
            'alcance': alcance, 'alcance_ideal': alcance_ideal,
            'ritmo_actual': ritmo_actual, 'ritmo_necesario': ritmo_necesario,
            'faltantes': faltantes,
            'dias_trans': dias_trans, 'dias_tot': dias_tot,
        }
    except Exception as e:
        print(f"Error get_kpi_provincia: {e}")
        return None


def get_daily_trend_lima(mes, anio, area=''):
    """Ventas por Fecha de registro y altas por Fecha programación — Lima."""
    _ac = _area_clause(area)
    _dl = _dept_lima()
    try:
        df = get_data(f"""
            SELECT dia, SUM(es_venta) AS ventas, SUM(es_alta) AS altas
            FROM (
                SELECT DAY([Fecha de registro]) AS dia, 1 AS es_venta, 0 AS es_alta
                FROM dbo.winforce_lima
                WHERE MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
                {_dl} {_ac}

                UNION ALL

                SELECT DAY({_FP}) AS dia, 0 AS es_venta, 1 AS es_alta
                FROM dbo.winforce_lima
                WHERE [Estado orden] = 'Ejecutada'
                  AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
                  AND {_FP} IS NOT NULL
                {_dl} {_ac}
            ) t
            GROUP BY dia
            ORDER BY dia
        """, params={'mes': mes, 'anio': anio})
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error get_daily_trend_lima: {e}")
        return []


def get_daily_trend_provincia(mes, anio):
    """Ventas por Fecha de registro y altas por Fecha programación — Provincia."""
    try:
        df = get_data(f"""
            SELECT dia, SUM(es_venta) AS ventas, SUM(es_alta) AS altas
            FROM (
                SELECT DAY([Fecha de registro]) AS dia, 1 AS es_venta, 0 AS es_alta
                FROM dbo.winforce_provincia
                WHERE MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio

                UNION ALL

                SELECT DAY({_FP}) AS dia, 0 AS es_venta, 1 AS es_alta
                FROM dbo.winforce_provincia
                WHERE [Estado orden] = 'Ejecutada'
                  AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
                  AND {_FP} IS NOT NULL
            ) t
            GROUP BY dia
            ORDER BY dia
        """, params={'mes': mes, 'anio': anio})
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error get_daily_trend_provincia: {e}")
        return []


def get_distribucion_estados_lima(mes, anio, area='', dia=None):
    """Distribución de estados actuales basados en la Fecha de Registro."""
    _ac = _area_clause(area)
    _dl = _dept_lima()
    _dr = "AND DAY([Fecha de registro]) = :dia" if dia else ""
    p   = {'mes': mes, 'anio': anio}
    if dia:
        p['dia'] = int(dia)
    try:
        df = get_data(f"""
            SELECT
                ISNULL([Estado orden], '') AS estado,
                COUNT(*) AS registro
            FROM dbo.winforce_lima
            WHERE MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
            {_dl} {_ac} {_dr}
            GROUP BY [Estado orden]
            ORDER BY [Estado orden]
        """, params=p)
        
        if df.empty:
            return []
            
        total_registros = df['registro'].sum()
        df['pct_registro'] = df['registro'] / total_registros * 100
        df['pct_registro'] = df['pct_registro'].round(2)
        
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error get_distribucion_estados_lima: {e}")
        return []


def get_top_distritos_lima(mes, anio, top=10, area='', dia=None):
    """Top N distritos por altas en Lima."""
    _ac = _area_clause(area)
    _dl = _dept_lima()
    _da = f"AND DAY({_FP}) = :dia" if dia else ""
    p   = {'mes': mes, 'anio': anio}
    if dia:
        p['dia'] = int(dia)
    try:
        df = get_data(f"""
            SELECT TOP {top} Distrito, COUNT(*) AS altas
            FROM dbo.winforce_lima
            WHERE [Estado orden] = 'Ejecutada'
              AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
              AND {_FP} IS NOT NULL
              AND Distrito IS NOT NULL AND Distrito <> ''
              {_dl} {_ac} {_da}
            GROUP BY Distrito
            ORDER BY altas DESC
        """, params=p)
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error get_top_distritos_lima: {e}")
        return []


def get_velocidad_planes_lima(mes, anio, area='', dia=None):
    """Distribución de altas de Lima por velocidad de plan (Mbps)."""
    _ac = _area_clause(area)
    _dl = _dept_lima()
    _vel = "LEFT([Plan], CHARINDEX(' ', [Plan] + ' ') - 1)"
    _da = f"AND DAY({_FP}) = :dia" if dia else ""
    p   = {'mes': mes, 'anio': anio}
    if dia:
        p['dia'] = int(dia)
    try:
        df = get_data(f"""
            SELECT
                {_vel} AS velocidad,
                COUNT(*) AS altas,
                ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
            FROM dbo.winforce_lima
            WHERE [Estado orden] = 'Ejecutada'
              AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
              AND {_FP} IS NOT NULL
              AND [Plan] IS NOT NULL AND [Plan] <> ''
              {_dl} {_ac} {_da}
            GROUP BY {_vel}
            ORDER BY altas DESC
        """, params=p)
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error get_velocidad_planes_lima: {e}")
        return []


def get_top_vendedores_lima(mes, anio, top=10, dia=None):
    """Top N vendedores por altas en Lima, con supervisor y agencia.
    dia (1-31): filtra altas instaladas en ese día (Fecha programación)."""
    _fpa = "TRY_CONVERT(DATE, LEFT(wl.[Fecha programación], 10), 105)"
    _dlw = _dept_lima('wl')
    _da  = f"AND DAY({_fpa}) = :dia" if dia else ""
    params = {'mes': mes, 'anio': anio}
    if dia:
        params['dia'] = int(dia)
    try:
        df = get_data(f"""
            SELECT TOP {top}
                wl.[Vendedor real]               AS vendedor,
                ISNULL(u.AGENCIA, wl.[Agencia])  AS agencia,
                ISNULL(u.SUPERVISOR, '')          AS supervisor,
                COUNT(*)                          AS altas
            FROM dbo.winforce_lima wl
            LEFT JOIN dbo.Usuarios_win u ON wl.[Vendedor real] = u.VENDEDOR
            WHERE wl.[Estado orden] = 'Ejecutada'
              AND MONTH({_fpa}) = :mes AND YEAR({_fpa}) = :anio
              AND {_fpa} IS NOT NULL
              AND wl.[Vendedor real] IS NOT NULL AND wl.[Vendedor real] <> ''
              {_dlw} {_da}
            GROUP BY wl.[Vendedor real], ISNULL(u.AGENCIA, wl.[Agencia]), ISNULL(u.SUPERVISOR, '')
            ORDER BY altas DESC
        """, params=params)
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error get_top_vendedores_lima: {e}")
        return []


def get_tipo_vivienda_lima(mes, anio, area='', dia=None):
    """Altas, Ventas y % Inst Mismo Día por Tipo de Domicilio — Lima."""
    _fpa = "TRY_CONVERT(DATE, LEFT(wl.[Fecha programación], 10), 105)"
    _ac  = _area_clause(area)
    _acw = _area_clause(area, col='wl.[Tipo de domicilio]')
    _dl  = _dept_lima()
    _dlw = _dept_lima('wl')
    _dr  = "AND DAY([Fecha de registro]) = :dia" if dia else ""
    _da  = f"AND DAY({_fpa}) = :dia" if dia else ""
    p    = {'mes': mes, 'anio': anio}
    if dia:
        p['dia'] = int(dia)
    try:
        query_ventas = f"""
            SELECT
                ISNULL([Tipo de domicilio], 'Desconocido') AS vivienda,
                COUNT(*) AS ventas
            FROM dbo.winforce_lima
            WHERE MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
            {_dl} {_ac} {_dr}
            GROUP BY [Tipo de domicilio]
        """

        query_altas = f"""
            SELECT
                ISNULL(wl.[Tipo de domicilio], 'Desconocido') AS vivienda,
                COUNT(*) AS altas,
                SUM(CASE WHEN DATEDIFF(DAY, CAST(wl.[Fecha de registro] AS DATE), {_fpa}) = 0 THEN 1 ELSE 0 END) AS inst_mismo_dia
            FROM dbo.winforce_lima wl
            WHERE wl.[Estado orden] = 'Ejecutada'
              AND MONTH({_fpa}) = :mes AND YEAR({_fpa}) = :anio
              AND {_fpa} IS NOT NULL
              {_dlw} {_acw} {_da}
            GROUP BY wl.[Tipo de domicilio]
        """

        import pandas as pd
        df_v = get_data(query_ventas, params=p)
        df_a = get_data(query_altas, params=p)
        
        if df_v.empty and df_a.empty:
            return []
            
        if df_v.empty:
            df = df_a
            df['ventas'] = 0
        elif df_a.empty:
            df = df_v
            df['altas'] = 0
            df['inst_mismo_dia'] = 0
        else:
            df = pd.merge(df_v, df_a, on='vivienda', how='outer').fillna(0)
            
        # Map names
        name_map = {
            'Condominio/Edificio': 'C/E Habilitado',
            'Condominio/Edificio No Habilitado': 'C/E No Habilitado',
            'Multifamiliar': 'Multifamiliar',
            'Hogar': 'Hogar'
        }
        df['vivienda'] = df['vivienda'].apply(lambda x: name_map.get(x, x))
        
        df['ventas'] = df['ventas'].astype(int)
        df['altas'] = df['altas'].astype(int)
        df['inst_mismo_dia'] = df['inst_mismo_dia'].astype(int)
        df['pct_mismo_dia'] = df.apply(lambda r: round(r['inst_mismo_dia'] / r['altas'] * 100, 2) if r['altas'] > 0 else 0.0, axis=1)
        
        # Sort by altas descending
        df = df.sort_values('altas', ascending=False)
        
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error get_tipo_vivienda_lima: {e}")
        return []


def get_pivot_planes_agencia(mes, anio, area='', dia=None):
    """Pivot: altas instaladas por Plan × Agencia (Usuarios_win) — Lima."""
    import pandas as pd
    _fpa = "TRY_CONVERT(DATE, LEFT(wl.[Fecha programación], 10), 105)"
    _dlw = _dept_lima('wl')
    _acw = _area_clause(area, col='wl.[Tipo de domicilio]')
    _da  = f"AND DAY({_fpa}) = :dia" if dia else ""
    p    = {'mes': mes, 'anio': anio}
    if dia:
        p['dia'] = int(dia)
    try:
        df = get_data(f"""
            SELECT
                wl.[Plan]                        AS [plan],
                ISNULL(u.AGENCIA, 'Sin Agencia') AS agencia,
                COUNT(*)                         AS altas
            FROM dbo.winforce_lima wl
            LEFT JOIN dbo.Usuarios_win u ON wl.[Vendedor real] = u.VENDEDOR
            WHERE wl.[Estado orden] = 'Ejecutada'
              AND MONTH({_fpa}) = :mes AND YEAR({_fpa}) = :anio
              AND {_fpa} IS NOT NULL
              AND wl.[Plan] IS NOT NULL AND wl.[Plan] <> ''
              {_dlw} {_acw} {_da}
            GROUP BY wl.[Plan], ISNULL(u.AGENCIA, 'Sin Agencia')
        """, params=p)
        if df.empty:
            return {'columns': ['PLAN', 'TOTAL'], 'rows': [], 'totals': {'TOTAL': 0}}

        pivot = df.pivot_table(index='plan', columns='agencia', values='altas',
                               aggfunc='sum', fill_value=0)
        pivot['TOTAL'] = pivot.sum(axis=1)
        pivot = pivot.sort_values('TOTAL', ascending=False)

        agencias = sorted([c for c in pivot.columns if c != 'TOTAL'])
        columns = ['PLAN'] + agencias + ['TOTAL']

        rows = []
        for plan_name, row in pivot.iterrows():
            r = {'PLAN': plan_name}
            for col in columns[1:]:
                r[col] = int(row.get(col, 0))
            rows.append(r)

        totals = {}
        for col in columns[1:]:
            totals[col] = int(pivot[col].sum()) if col in pivot.columns else 0

        return {'columns': columns, 'rows': rows, 'totals': totals}
    except Exception as e:
        print(f"Error get_pivot_planes_agencia: {e}")
        return {'columns': ['PLAN', 'TOTAL'], 'rows': [], 'totals': {'TOTAL': 0}}


def get_tramo_dias_lima(mes, anio):
    """Distribución por tramo de días entre registro y programación — Lima.
    Calculado con DATEDIFF ya que la columna Tramo Días Instalación no existe en SQL."""
    _dl = _dept_lima()
    try:
        df = get_data(f"""
            SELECT
                CASE
                    WHEN DATEDIFF(DAY, CAST([Fecha de registro] AS DATE), {_FP}) = 0 THEN 'Mismo día'
                    WHEN DATEDIFF(DAY, CAST([Fecha de registro] AS DATE), {_FP}) = 1 THEN '1 día'
                    WHEN DATEDIFF(DAY, CAST([Fecha de registro] AS DATE), {_FP}) = 2 THEN '2 días'
                    WHEN DATEDIFF(DAY, CAST([Fecha de registro] AS DATE), {_FP}) = 3 THEN '3 días'
                    ELSE '4+ días'
                END AS tramo,
                COUNT(*) AS cnt
            FROM dbo.winforce_lima
            WHERE [Estado orden] = 'Ejecutada'
              AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
              AND {_FP} IS NOT NULL
              AND DATEDIFF(DAY, CAST([Fecha de registro] AS DATE), {_FP}) >= 0
              {_dl}
            GROUP BY
                CASE
                    WHEN DATEDIFF(DAY, CAST([Fecha de registro] AS DATE), {_FP}) = 0 THEN 'Mismo día'
                    WHEN DATEDIFF(DAY, CAST([Fecha de registro] AS DATE), {_FP}) = 1 THEN '1 día'
                    WHEN DATEDIFF(DAY, CAST([Fecha de registro] AS DATE), {_FP}) = 2 THEN '2 días'
                    WHEN DATEDIFF(DAY, CAST([Fecha de registro] AS DATE), {_FP}) = 3 THEN '3 días'
                    ELSE '4+ días'
                END
            ORDER BY MIN(DATEDIFF(DAY, CAST([Fecha de registro] AS DATE), {_FP}))
        """, params={'mes': mes, 'anio': anio})
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error get_tramo_dias_lima: {e}")
        return []


def get_tabla_provincia(mes, anio):
    """Altas, ventas y cuota por departamento — Provincia."""
    dias_trans, dias_tot, _ = _dias_mes(mes, anio)
    try:
        df_v = get_data(f"""
            SELECT [Departamento] AS agencia, COUNT(*) AS ventas
            FROM dbo.winforce_provincia
            WHERE MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
              AND [Departamento] NOT IN ('LIMA','Lima','lima')
              AND [Departamento] IS NOT NULL AND [Departamento] <> ''
            GROUP BY [Departamento]
        """, params={'mes': mes, 'anio': anio})
        df_a = get_data(f"""
            SELECT [Departamento] AS agencia, COUNT(*) AS altas
            FROM dbo.winforce_provincia
            WHERE [Estado orden] = 'Ejecutada'
              AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
              AND {_FP} IS NOT NULL
              AND [Departamento] NOT IN ('LIMA','Lima','lima')
              AND [Departamento] IS NOT NULL AND [Departamento] <> ''
            GROUP BY [Departamento]
        """, params={'mes': mes, 'anio': anio})
        try:
            df_c = get_data("SELECT Departamento AS agencia, Cuota FROM dbo.Cuota_Prov WHERE Mes_num = :mes AND Region = 'Provincia'", params={'mes': mes})
        except Exception:
            import pandas as pd
            df_c = pd.DataFrame()

        import pandas as pd
        if df_v.empty:
            return []

        df = df_v.merge(df_a, on='agencia', how='outer').fillna(0)
        if not df_c.empty:
            df = df.merge(df_c, on='agencia', how='left').fillna(0)
            df['cuota'] = df['Cuota'].astype(int)
        else:
            df['cuota'] = 0

        df['ventas'] = df['ventas'].astype(int)
        df['altas']  = df['altas'].astype(int)
        df['proyeccion'] = (df['altas'] / dias_trans * 30).round().astype(int) if dias_trans > 0 else 0
        df['alcance'] = df.apply(
            lambda r: round(r['altas'] / r['cuota'] * 100, 1) if r['cuota'] > 0 else 0.0, axis=1
        )
        df['estado'] = df['alcance'].apply(
            lambda x: 'meta' if x >= 100 else ('riesgo' if x >= 80 else 'bajo')
        )
        df = df.sort_values('altas', ascending=False)
        return df[['agencia', 'ventas', 'altas', 'cuota', 'proyeccion', 'alcance', 'estado']].to_dict(orient='records')
    except Exception as e:
        print(f"Error get_tabla_provincia: {e}")
        return []


import os as _os
import sqlalchemy as _sa

_TABLE = 'dim_usuarios_Aliv'


def _is_pg():
    return bool(_os.environ.get('DATABASE_URL'))


def init_dim_usuarios_table():
    """Crea la tabla dim_usuarios_Aliv si no existe (SQL Server o PostgreSQL)."""
    try:
        from db_config import get_engine
        engine = get_engine()
        with engine.begin() as conn:
            if _is_pg():
                conn.execute(_sa.text(f"""
                    CREATE TABLE IF NOT EXISTS {_TABLE} (
                        id SERIAL PRIMARY KEY,
                        vendedor VARCHAR(100) NOT NULL,
                        nombre_completo VARCHAR(200),
                        cargo VARCHAR(50) NOT NULL DEFAULT 'Vendedor',
                        agencia VARCHAR(100),
                        supervisor VARCHAR(100),
                        canal VARCHAR(50),
                        estado VARCHAR(20) NOT NULL DEFAULT 'Activo',
                        fecha_registro DATE NOT NULL DEFAULT CURRENT_DATE
                    )
                """))
            else:
                conn.execute(_sa.text(f"""
                    IF NOT EXISTS (
                        SELECT 1 FROM INFORMATION_SCHEMA.TABLES
                        WHERE TABLE_NAME = '{_TABLE}'
                    )
                    CREATE TABLE dbo.{_TABLE} (
                        id INT IDENTITY(1,1) PRIMARY KEY,
                        vendedor NVARCHAR(100) NOT NULL,
                        nombre_completo NVARCHAR(200) NULL,
                        cargo NVARCHAR(50) NOT NULL DEFAULT 'Vendedor',
                        agencia NVARCHAR(100) NULL,
                        supervisor NVARCHAR(100) NULL,
                        canal NVARCHAR(50) NULL,
                        estado NVARCHAR(20) NOT NULL DEFAULT 'Activo',
                        fecha_registro DATE NOT NULL DEFAULT GETDATE()
                    )
                """))
    except Exception as e:
        print(f"init_dim_usuarios_table: {e}")


def _fmt_date(x):
    try:
        import pandas as _pd
        return x.strftime('%d/%m/%Y') if _pd.notna(x) else None
    except Exception:
        return None


def get_usuarios(search='', agencia='', supervisor='', cargo='', estado=''):
    """Lista usuarios con filtros opcionales."""
    try:
        conditions, params = [], {}
        if search:
            conditions.append(
                "(LOWER(COALESCE(vendedor,'')) LIKE LOWER(:search) OR LOWER(COALESCE(nombre_completo,'')) LIKE LOWER(:search))"
            )
            params['search'] = f'%{search}%'
        if agencia:
            conditions.append("agencia = :agencia")
            params['agencia'] = agencia
        if supervisor:
            conditions.append("supervisor = :supervisor")
            params['supervisor'] = supervisor
        if cargo:
            conditions.append("cargo = :cargo")
            params['cargo'] = cargo
        if estado:
            conditions.append("estado = :estado")
            params['estado'] = estado

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        df = get_data(
            f"SELECT id, vendedor, nombre_completo, cargo, agencia, supervisor, canal, estado, fecha_registro FROM {_TABLE} {where} ORDER BY cargo, agencia, vendedor",
            params=params or None
        )
        if df.empty:
            return []
        df['fecha_registro'] = df['fecha_registro'].apply(_fmt_date)
        df['id'] = df['id'].astype(int)
        records = df.to_dict(orient='records')
        for r in records:
            for k, v in r.items():
                if v != v:  # NaN != NaN es True
                    r[k] = None
        return records
    except Exception as e:
        print(f"get_usuarios: {e}")
        return []


def get_usuarios_stats():
    """Estadísticas rápidas para el encabezado de la página."""
    try:
        df = get_data(f"""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN estado = 'Activo' THEN 1 ELSE 0 END) AS activos,
                SUM(CASE WHEN cargo = 'Supervisor' THEN 1 ELSE 0 END) AS supervisores,
                COUNT(DISTINCT agencia) AS agencias
            FROM {_TABLE}
        """)
        r = df.iloc[0]
        return {
            'total':        int(r['total'] or 0),
            'activos':      int(r['activos'] or 0),
            'supervisores': int(r['supervisores'] or 0),
            'agencias':     int(r['agencias'] or 0),
        }
    except Exception as e:
        print(f"get_usuarios_stats: {e}")
        return {'total': 0, 'activos': 0, 'supervisores': 0, 'agencias': 0}


def get_agencias_list():
    """Agencias distintas para el dropdown."""
    try:
        df = get_data(f"SELECT DISTINCT agencia FROM {_TABLE} WHERE agencia IS NOT NULL AND agencia <> '' ORDER BY agencia")
        return df['agencia'].tolist()
    except Exception:
        return []


_LISTA_SUPERVISORES_COMPLETA = [
    ".. A&G Ingenieria En Gas Natural S.A.C",
    ".. Dezanet",
    ".. Futura",
    ".. Lottus",
    ".. Prince",
    ".. Protectel",
    "Alfaro Aguilar Andrea",
    "Angeles Nuñez Luis Marcelo",
    "Angulo Quiroz Antonny Luis",
    "Bockos Cervera Roberto Leonidas",
    "Castillo Rodriguez Luis Sebastian",
    "Castillon Carhuayano Luis Alberto",
    "Chiclayo Tejada Victor Adolfo",
    "Chinchay Benites Gino Andre",
    "Chumbe Muñoz Jonathan David",
    "Chuquillanqui Molina Diego",
    "Cornelio Fuentes Alexander Javier",
    "Cosío Chorrillos Jonathan Ray",
    "Figueroa Cordova Kimberly Fatima Milagrito",
    "Gonzales Rodriguez Leonardo",
    "Hidalgo Carrillo Alexis Kent",
    "Lagos Ponce Edwin Franz",
    "Mamani Apaza Edwin Francisco",
    "Marticorena Rodríguez Jorge Augusto",
    "Palacios Calle Maria",
    "Perez Lopez Javier Alexander",
    "Posavac Cerron Jose Maria",
    "Prado Ramos Dany Wiston",
    "Puppo Egusquiza Ronald Roberto",
    "Ramirez Garay Ronald Benjamin",
    "Ramos Chunga Enma Liseth",
    "Rodan Solano Dady Joel",
    "Rodriguez Cuba Carlos",
    "Rodriguez Mendez Yuratzi Pastora",
    "Rodriguez Urtecho Jose Enrique",
    "Saavedra Quintana Mario Junior",
    "Sac . Pixel",
    "Salazar Campos Joshua Carlos Jair",
    "Sanchez Guerrero Mariana Fernanda",
    "Sipion Ñahue Cesar Enrique",
    "Sotelo Castañeda Anyi Carolina",
    "Soto Rodriguez Luis Fernando",
    "Tezen Bruno Lizet Paola",
    "Tovar Ore Ruben",
    "Ugarte . Zomarcely Josefina",
    "Vega Cruz Gerson Ernesto",
    "Vega Fajardo Jonathan Steven",
    "Villalobos Ramírez Luis Gabriel",
    "Villar Alcalde Antonio Marcial"
]


def get_supervisores_list():
    """Supervisores distintos para el dropdown (estáticos + dinámicos de base de datos)."""
    try:
        df = get_data(f"SELECT DISTINCT supervisor FROM {_TABLE} WHERE supervisor IS NOT NULL AND supervisor <> ''")
        db_sups = df['supervisor'].tolist() if not df.empty else []
        
        # También incluir los nombres de los usuarios que tienen cargo de supervisor
        df_cargo = get_data(f"SELECT DISTINCT nombre_completo FROM {_TABLE} WHERE cargo = 'Supervisor' AND nombre_completo IS NOT NULL AND nombre_completo <> ''")
        db_sups_cargo = df_cargo['nombre_completo'].tolist() if not df_cargo.empty else []
        
        combined = set(_LISTA_SUPERVISORES_COMPLETA + db_sups + db_sups_cargo)
        return sorted(list(combined))
    except Exception:
        return sorted(_LISTA_SUPERVISORES_COMPLETA)



def create_usuario(data):
    """Inserta un nuevo usuario."""
    try:
        from db_config import get_engine
        from datetime import date
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(_sa.text(f"""
                INSERT INTO {_TABLE} (vendedor, nombre_completo, cargo, agencia, supervisor, canal, estado, fecha_registro)
                VALUES (:vendedor, :nombre_completo, :cargo, :agencia, :supervisor, :canal, :estado, :fecha_registro)
            """), {
                'vendedor':        data.get('vendedor', ''),
                'nombre_completo': data.get('nombre_completo') or None,
                'cargo':           data.get('cargo', 'Vendedor'),
                'agencia':         data.get('agencia') or None,
                'supervisor':      data.get('supervisor') or None,
                'canal':           data.get('canal') or None,
                'estado':          data.get('estado', 'Activo'),
                'fecha_registro':  date.today().isoformat(),
            })
        print(f"[DB] Usuario creado: {data.get('vendedor')}")
        return True
    except Exception as e:
        print(f"[DB ERROR] create_usuario: {e}")
        return False


def update_usuario(uid, data):
    """Actualiza un usuario existente."""
    try:
        from db_config import get_engine
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(_sa.text(f"""
                UPDATE {_TABLE}
                SET vendedor = :vendedor, nombre_completo = :nombre_completo,
                    cargo = :cargo, agencia = :agencia, supervisor = :supervisor,
                    canal = :canal, estado = :estado
                WHERE id = :id
            """), {
                'id':              uid,
                'vendedor':        data.get('vendedor', ''),
                'nombre_completo': data.get('nombre_completo') or None,
                'cargo':           data.get('cargo', 'Vendedor'),
                'agencia':         data.get('agencia') or None,
                'supervisor':      data.get('supervisor') or None,
                'canal':           data.get('canal') or None,
                'estado':          data.get('estado', 'Activo'),
            })
        print(f"[DB] Usuario actualizado id={uid}: {data.get('vendedor')}")
        return True
    except Exception as e:
        print(f"[DB ERROR] update_usuario: {e}")
        return False


def delete_usuario(uid):
    """Elimina un usuario por id."""
    try:
        from db_config import get_engine
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(_sa.text(f"DELETE FROM {_TABLE} WHERE id = :id"), {'id': uid})
        print(f"[DB] Usuario eliminado id={uid}")
        return True
    except Exception as e:
        print(f"[DB ERROR] delete_usuario: {e}")
        return False


def get_localizacion_lima(mes, anio, area=''):
    """Score, Zona KML y comparativa P2 — Lima.
    Retorna None si la columna Zona_KML no está disponible."""
    _ac = _area_clause(area)
    _dl = _dept_lima()

    try:
        get_data("SELECT TOP 1 [Zona_KML] FROM dbo.winforce_lima")
    except Exception:
        print("get_localizacion_lima: columna Zona_KML no disponible")
        return None

    try:
        df = get_data(f"""
            SELECT
                AVG(TRY_CAST([Score_Minimo_KML] AS FLOAT))            AS score_prom,
                SUM(CASE WHEN [Zona_KML] = 'No Venta' THEN 1 ELSE 0 END) AS no_venta,
                COUNT(*)                                               AS total
            FROM dbo.winforce_lima
            WHERE MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
            {_dl} {_ac}
        """, params={'mes': mes, 'anio': anio})
        r = df.iloc[0]
        total    = _safe_int(r['total'])
        no_venta = _safe_int(r['no_venta'])
        kpis = {
            'score_prom':   round(float(r['score_prom'] or 0)),
            'en_riesgo':    0,
            'no_venta':     no_venta,
            'con_problema': no_venta,
            'total':        total,
            'riesgo_pct':   round(no_venta / total * 100, 1) if total > 0 else 0,
        }

        df_zona = get_data(f"""
            SELECT [Zona_KML] AS zona, COUNT(*) AS cnt
            FROM dbo.winforce_lima
            WHERE [Estado orden] = 'Ejecutada'
              AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
              AND {_FP} IS NOT NULL
              AND [Zona_KML] IS NOT NULL AND [Zona_KML] <> ''
              {_dl} {_ac}
            GROUP BY [Zona_KML]
            ORDER BY cnt DESC
        """, params={'mes': mes, 'anio': anio})
        zonas = df_zona.to_dict(orient='records')

        _where_p2 = f"WHERE {_dl[4:]} {_ac}" if area else f"WHERE {_dl[4:]}"
        df_p2 = get_data(f"""
            SELECT
                SUM(CASE WHEN [Fecha de registro] <  '2026-04-15'
                          AND [Zona_KML] = 'Zona P2 (401)' THEN 1 ELSE 0 END) AS antes_v,
                SUM(CASE WHEN [Fecha de registro] >= '2026-04-15'
                          AND [Zona_KML] = 'Zona P2 (401)' THEN 1 ELSE 0 END) AS despues_v,
                SUM(CASE WHEN [Estado orden] = 'Ejecutada'
                          AND {_FP} <  '2026-04-15'
                          AND [Zona_KML] = 'Zona P2 (401)' THEN 1 ELSE 0 END) AS antes_a,
                SUM(CASE WHEN [Estado orden] = 'Ejecutada'
                          AND {_FP} >= '2026-04-15'
                          AND [Zona_KML] = 'Zona P2 (401)' THEN 1 ELSE 0 END) AS despues_a
            FROM dbo.winforce_lima
            {_where_p2}
        """)
        p2r = df_p2.iloc[0]
        antes_a   = _safe_int(p2r['antes_a'])
        despues_a = _safe_int(p2r['despues_a'])
        caida_pct = round((despues_a - antes_a) / antes_a * 100, 1) if antes_a > 0 else 0

        p2 = {
            'antes_ventas':   _safe_int(p2r['antes_v']),
            'despues_ventas': _safe_int(p2r['despues_v']),
            'antes_altas':    antes_a,
            'despues_altas':  despues_a,
            'caida_pct':      caida_pct,
        }

        return {'kpis': kpis, 'zonas': zonas, 'p2': p2}
    except Exception as e:
        print(f"Error get_localizacion_lima: {e}")
        return None


def get_datos_distrito_lima(mes, anio, distrito, area=''):
    """Altas, ventas, conversión, top planes y top vendedores para un distrito específico de Lima.
    La búsqueda es case-insensitive y parcial (LIKE) para tolerar variantes como 'ATE' → 'ATE VITARTE'."""
    _ac  = _area_clause(area)
    _dl  = _dept_lima()
    # Primero resolver el nombre real del distrito en la BD
    p_like = {'mes': mes, 'anio': anio, 'pat': f'%{distrito.upper()}%'}
    _dist_filter = "AND UPPER([Distrito]) LIKE :pat"
    p    = {'mes': mes, 'anio': anio, 'pat': f'%{distrito.upper()}%'}
    try:
        # Obtener nombre real y total de altas (agrupa por distrito para encontrar la variante exacta)
        df_match = get_data(f"""
            SELECT TOP 1 [Distrito] AS nombre_real, COUNT(*) AS altas
            FROM dbo.winforce_lima
            WHERE [Estado orden] = 'Ejecutada'
              AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
              AND {_FP} IS NOT NULL
              AND UPPER([Distrito]) LIKE :pat
              {_dl} {_ac}
            GROUP BY [Distrito]
            ORDER BY altas DESC
        """, params=p)

        nombre_real = df_match.iloc[0]['nombre_real'] if not df_match.empty else distrito
        p_exact = {'mes': mes, 'anio': anio, 'dist': nombre_real}
        _df = "AND [Distrito] = :dist"

        df_altas = get_data(f"""
            SELECT COUNT(*) AS altas
            FROM dbo.winforce_lima
            WHERE [Estado orden] = 'Ejecutada'
              AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
              AND {_FP} IS NOT NULL
              AND [Distrito] = :dist
              {_dl} {_ac}
        """, params=p_exact)
        df_ventas = get_data(f"""
            SELECT COUNT(*) AS ventas
            FROM dbo.winforce_lima
            WHERE MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
              AND [Distrito] = :dist
              {_dl} {_ac}
        """, params=p_exact)
        df_planes = get_data(f"""
            SELECT TOP 5 [Plan], COUNT(*) AS altas
            FROM dbo.winforce_lima
            WHERE [Estado orden] = 'Ejecutada'
              AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
              AND {_FP} IS NOT NULL
              AND [Distrito] = :dist
              {_dl} {_ac}
            GROUP BY [Plan] ORDER BY altas DESC
        """, params=p_exact)
        df_vend = get_data(f"""
            SELECT TOP 5 [Vendedor real] AS vendedor, COUNT(*) AS altas
            FROM dbo.winforce_lima
            WHERE [Estado orden] = 'Ejecutada'
              AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
              AND {_FP} IS NOT NULL
              AND [Distrito] = :dist
              {_dl} {_ac}
            GROUP BY [Vendedor real] ORDER BY altas DESC
        """, params=p_exact)

        altas  = int(df_altas.iloc[0]['altas']) if not df_altas.empty else 0
        ventas = int(df_ventas.iloc[0]['ventas']) if not df_ventas.empty else 0
        conv   = round(altas / ventas * 100, 1) if ventas else 0
        return {
            'distrito': nombre_real, 'mes': mes, 'anio': anio,
            'altas': altas, 'ventas': ventas, 'conversion_pct': conv,
            'top_planes': df_planes.to_dict(orient='records'),
            'top_vendedores': df_vend.to_dict(orient='records'),
        }
    except Exception as e:
        print(f"Error get_datos_distrito_lima: {e}")
        return {}


def get_anulaciones_agencia_lima(mes, anio, area=''):
    """Anulaciones de Lima agrupadas por agencia, con % sobre ventas."""
    _ac = _area_clause(area)
    _dl = _dept_lima()
    try:
        df = get_data(f"""
            SELECT
                ISNULL(u.[AGENCIA], l.[Agencia])    AS agencia,
                COUNT(*) AS anulaciones,
                ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_total
            FROM dbo.winforce_lima l
            LEFT JOIN dbo.Usuarios_win u ON l.[Vendedor real] = u.[VENDEDOR]
            WHERE l.[Estado orden] = 'Anulado'
              AND MONTH(l.[Fecha de registro]) = :mes AND YEAR(l.[Fecha de registro]) = :anio
              {_dl} {_ac}
            GROUP BY ISNULL(u.[AGENCIA], l.[Agencia])
            ORDER BY anulaciones DESC
        """, params={'mes': mes, 'anio': anio})
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error get_anulaciones_agencia_lima: {e}")
        return []


def get_comparacion_meses_lima(mes1, anio1, mes2, anio2, area=''):
    """Compara KPIs de Lima entre dos meses distintos."""
    k1 = get_kpi_lima(mes1, anio1, area=area)
    k2 = get_kpi_lima(mes2, anio2, area=area)
    if not k1 or not k2:
        return {}
    return {
        'periodo_a': {'mes': mes1, 'anio': anio1, 'kpi': k1},
        'periodo_b': {'mes': mes2, 'anio': anio2, 'kpi': k2},
        'diferencia_altas': k1['altas'] - k2['altas'],
        'diferencia_ventas': k1['ventas'] - k2['ventas'],
    }


def get_puntos_mapa_lima(mes, anio, area=''):
    """Instalaciones con lat/lon para mapa interactivo — Lima y Callao.
    Latitud/Longitud son TEXT en SQL Server → TRY_CAST para conversión segura."""
    import math
    _ac = _area_clause(area)
    _dl = _dept_lima()
    _where = f"""
        FROM dbo.winforce_lima
        WHERE [Estado orden] = 'Ejecutada'
          AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
          AND {_FP} IS NOT NULL
          AND TRY_CAST([Latitud]  AS FLOAT) IS NOT NULL
          AND TRY_CAST([Latitud]  AS FLOAT) <> 0
          AND TRY_CAST([Longitud] AS FLOAT) IS NOT NULL
          AND TRY_CAST([Longitud] AS FLOAT) <> 0
          {_dl} {_ac}
    """
    _base = """
        ISNULL([Distrito], 'Sin distrito')             AS distrito,
        ISNULL([Dirección de Instalación], '')         AS direccion,
        ISNULL([Dirección Geofinder], '')              AS geofinder,
        TRY_CAST([Latitud]  AS FLOAT)                  AS lat,
        TRY_CAST([Longitud] AS FLOAT)                  AS lon,
        ISNULL([Plan], '')                             AS [plan],
        ISNULL([Tipo de domicilio], '')                AS tipo
    """
    _score_cols = """
        ,ISNULL([Zona_KML], '')                        AS zona_kml
        ,TRY_CAST([Score Cliente]    AS FLOAT)         AS score_cliente
        ,TRY_CAST([Score_Minimo_KML] AS FLOAT)         AS score_minimo
    """
    params = {'mes': mes, 'anio': anio}

    def _score_zona(row):
        zona = (row.get('zona_kml') or '').strip()
        if zona == 'No Venta':
            return 'No Venta'
        s = row.get('score_cliente')
        m = row.get('score_minimo')
        if s is None or (isinstance(s, float) and math.isnan(s)):
            return 'Sin score'
        if m is None or (isinstance(m, float) and math.isnan(m)):
            return 'Sin score'
        return 'Cumple' if s >= m else 'No cumple'

    # Intentar con columnas de score; si fallan (columna inexistente) usar solo base
    for cols in (_base + _score_cols, _base):
        try:
            df = get_data(f"SELECT {cols} {_where}", params=params)
            records = df.to_dict(orient='records')
            for r in records:
                r['score_zona'] = _score_zona(r)
            return records
        except Exception as e:
            if cols == _base:
                print(f"Error get_puntos_mapa_lima: {e}")
                return []
            print(f"[mapa] Score cols no disponibles, usando base: {e}")


# ─── MOROSIDAD / CLAWBACK ────────────────────────────────────────────────────

_MORA_VIEW = 'dbo.v_ventas_aliv_completa'

_MORA_BASE_WHERE = "WHERE 1=1"

_NPNF_C  = "([Estado M1] IN ('Churn','Cliente De Baja') AND [R1_Ya_Vencio] = 1)"
_PAGO_R1 = "([Estado M1] IN ('Cliente Pago','Tercero Pago'))"
_PAGO_R2 = "([Estado M1] IN ('Cliente Pago','Tercero Pago') AND [Estado M2] IN ('Cliente Pago','Tercero Pago'))"
_PAGO_R3 = "([Estado M1] IN ('Cliente Pago','Tercero Pago') AND [Estado M2] IN ('Cliente Pago','Tercero Pago') AND [Estado M3] IN ('Cliente Pago','Tercero Pago'))"
_NO_R2   = "([Estado M1] IN ('Cliente Pago','Tercero Pago') AND [Estado M2] IN ('Churn','Cliente De Baja'))"
_NO_R3   = "([Estado M1] IN ('Cliente Pago','Tercero Pago') AND [Estado M2] IN ('Cliente Pago','Tercero Pago') AND [Estado M3] IN ('Churn','Cliente De Baja'))"


def _tramo_mora_expr(tramo):
    if tramo == 'M2': return _NO_R2
    if tramo == 'M3': return _NO_R3
    return _NPNF_C


def _tramo_deuda_col(tramo):
    if tramo == 'M2': return '[Deuda M2]'
    if tramo == 'M3': return '[Deuda M3]'
    return '[Deuda_Total_Cliente]'


def _mora_opt(mes=None, grupo='', recibo='', supervisor='', distrito='', riesgo='', caso='', dni='', departamento='', tramo='', ignorar_tramo=False):
    clauses, p = [], {}
    if departamento:
        clauses.append("AND [Departamento] = :departamento");                             p['departamento'] = departamento
    if mes:
        clauses.append("AND [Mes_Num_Recibo] = :mes");                                   p['mes']        = int(mes)
    if grupo:
        clauses.append("AND [Grupo_Facturacion] = :grupo");                               p['grupo']      = grupo
    if recibo:
        clauses.append("AND Recibo_Actual = :recibo");                                    p['recibo']     = recibo
    if supervisor:
        clauses.append("AND [Supervisor] = :supervisor");                                 p['supervisor'] = supervisor
    if distrito:
        clauses.append("AND [Distrito] = :distrito");                                     p['distrito']   = distrito
    if riesgo:
        clauses.append("AND Riesgo_Clawback = :riesgo");                                  p['riesgo']     = riesgo
    if caso:
        clauses.append("AND Tipo_Caso_Clawback = :caso");                                 p['caso']       = caso
    if dni:
        clauses.append("AND CAST([DNI/Carnet Extraj.] AS VARCHAR(20)) LIKE :dni");        p['dni']        = f'%{dni}%'
    
    if tramo and not ignorar_tramo:
        if tramo == 'M2':
            clauses.append(f"AND {_PAGO_R1}")
        elif tramo == 'M3':
            clauses.append(f"AND {_PAGO_R2}")
            
    return ' '.join(clauses), p or None


def _mora_costs(total, npnf, pag_r1, no_r2, pag_r2, no_r3, arpu):
    umb_n = total  * 0.045;  umb_2 = pag_r1 * 0.035;  umb_3 = pag_r2 * 0.025
    exc_n = max(0.0, npnf  - umb_n)
    exc_2 = max(0.0, no_r2 - umb_2)
    exc_3 = max(0.0, no_r3 - umb_3)
    return {
        'umb_n': umb_n, 'umb_2': umb_2, 'umb_3': umb_3,
        'exc_n': exc_n, 'exc_2': exc_2, 'exc_3': exc_3,
        'c_n': exc_n * arpu * 3.5 * 1.000,
        'c_2': exc_2 * arpu * 3.5 * 0.666,
        'c_3': exc_3 * arpu * 3.5 * 0.333,
    }


def _mora_counts(opt_sql, params):
    import math as _math
    df = get_data(f"""
        SELECT
            COUNT(*) AS total,
            AVG(ARPU) AS arpu,
            SUM(TRY_CONVERT(FLOAT, [Total Comision])) AS com_bruta,
            SUM(CASE WHEN {_NPNF_C}  THEN 1 ELSE 0 END) AS npnf,
            SUM(CASE WHEN {_PAGO_R1} THEN 1 ELSE 0 END) AS pag_r1,
            SUM(CASE WHEN {_PAGO_R2} THEN 1 ELSE 0 END) AS pag_r2,
            SUM(CASE WHEN {_PAGO_R3} THEN 1 ELSE 0 END) AS pag_r3,
            SUM(CASE WHEN {_NO_R2}   THEN 1 ELSE 0 END) AS no_r2,
            SUM(CASE WHEN {_NO_R3}   THEN 1 ELSE 0 END) AS no_r3
        FROM {_MORA_VIEW}
        {_MORA_BASE_WHERE} {opt_sql}
    """, params=params)
    r = df.iloc[0]

    def _sf(v):
        try:
            f = float(v)
            return 0.0 if (_math.isnan(f) or _math.isinf(f)) else f
        except Exception:
            return 0.0

    return {
        'total':    int(r['total']    or 0),
        'arpu':     _sf(r['arpu']),
        'com_bruta':_sf(r['com_bruta']),
        'npnf':     int(r['npnf']     or 0),
        'pag_r1':   int(r['pag_r1']   or 0),
        'pag_r2':   int(r['pag_r2']   or 0),
        'pag_r3':   int(r['pag_r3']   or 0),
        'no_r2':    int(r['no_r2']    or 0),
        'no_r3':    int(r['no_r3']    or 0),
    }


def get_mora_resumen(**kw):
    try:
        from datetime import date
        opt, p = _mora_opt(**kw)
        b  = _mora_counts(opt, p)
        perdidas = get_mora_perdidas(**kw)
        desc   = sum(g['total_penalidades'] for g in perdidas.get('grupos', []))
        com_b  = b['total'] * b['arpu'] * 3.5
        com_n  = com_b - desc
        hoy    = date.today()
        if hoy.day <= 18:
            corte = date(hoy.year, hoy.month, 18)
        elif hoy.month == 12:
            corte = date(hoy.year + 1, 1, 18)
        else:
            corte = date(hoy.year, hoy.month + 1, 18)
        meses_es = ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
                    'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']
        return {
            'total_clientes':   b['total'],
            'arpu_promedio':    round(b['arpu'], 2),
            'comision_bruta':   round(com_b, 2),
            'comision_neta':    round(com_n, 2),
            'total_descuentos': round(desc, 2),
            'dias_para_corte':  (corte - hoy).days,
            'mes_corte':        meses_es[corte.month - 1],
            'impacto_pct':      round(desc / com_b * 100, 2) if com_b else 0,
        }
    except Exception as e:
        print(f"Error get_mora_resumen: {e}")
        return {}


def get_mora_embudo(**kw):
    try:
        kw_copy = kw.copy()
        kw_copy['ignorar_tramo'] = True
        opt, p = _mora_opt(**kw_copy)
        b = _mora_counts(opt, p)
        t = b['total']
        pct = lambda x: round(x / t * 100, 1) if t else 0
        return {
            'total':  t,
            'pag_r1': b['pag_r1'], 'pct_r1': pct(b['pag_r1']),
            'pag_r2': b['pag_r2'], 'pct_r2': pct(b['pag_r2']),
            'pag_r3': b['pag_r3'], 'pct_r3': pct(b['pag_r3']),
        }
    except Exception as e:
        print(f"Error get_mora_embudo: {e}")
        return {}


def get_mora_perdidas(**kw):
    try:
        import math as _math
        tramo = kw.get('tramo', '')
        opt, p = _mora_opt(**kw)
        _NO_R3_V = "([Estado M2] IN ('Cliente Pago','Tercero Pago') AND [Estado M3] IN ('Churn','Cliente De Baja'))"
        df = get_data(f"""
            WITH base AS (
                SELECT * FROM {_MORA_VIEW} {_MORA_BASE_WHERE} {opt}
            )
            SELECT
                ISNULL([Grupo_Facturacion], 'Sin Grupo') AS grupo,
                COUNT(*) AS clientes,
                ISNULL(AVG(CAST(ARPU AS FLOAT)), 0) AS arpu_promedio,
                ISNULL(SUM(CAST([Deuda M1] AS FLOAT)), 0) AS deuda_m1,
                ISNULL(SUM(CAST([Deuda M2] AS FLOAT)), 0) AS deuda_m2,
                ISNULL(SUM(CAST([Deuda M3] AS FLOAT)), 0) AS deuda_m3,
                ISNULL(SUM(CAST([Deuda_Total_Cliente] AS FLOAT)), 0) AS deuda_total,

                SUM(CASE WHEN {_NPNF_C}  THEN 1 ELSE 0 END) AS npnf,
                FLOOR(COUNT(*) * 0.045) AS umbral_npnf,
                CASE WHEN SUM(CASE WHEN {_NPNF_C}  THEN 1 ELSE 0 END) - FLOOR(COUNT(*) * 0.045) > 0
                     THEN SUM(CASE WHEN {_NPNF_C}  THEN 1 ELSE 0 END) - FLOOR(COUNT(*) * 0.045)
                     ELSE 0 END AS exceso_npnf,

                SUM(CASE WHEN {_PAGO_R1} THEN 1 ELSE 0 END) AS pagaron_r1,

                SUM(CASE WHEN {_NO_R2}   THEN 1 ELSE 0 END) AS no_pag_r2,
                FLOOR(SUM(CASE WHEN {_PAGO_R1} THEN 1 ELSE 0 END) * 0.035) AS umbral_r2,
                CASE WHEN SUM(CASE WHEN {_NO_R2}   THEN 1 ELSE 0 END)
                          - FLOOR(SUM(CASE WHEN {_PAGO_R1} THEN 1 ELSE 0 END) * 0.035) > 0
                     THEN SUM(CASE WHEN {_NO_R2}   THEN 1 ELSE 0 END)
                          - FLOOR(SUM(CASE WHEN {_PAGO_R1} THEN 1 ELSE 0 END) * 0.035)
                     ELSE 0 END AS exceso_r2,

                SUM(CASE WHEN {_PAGO_R2} THEN 1 ELSE 0 END) AS pagaron_r2,

                SUM(CASE WHEN {_NO_R3_V} THEN 1 ELSE 0 END) AS no_pag_r3,
                FLOOR(SUM(CASE WHEN {_PAGO_R2} THEN 1 ELSE 0 END) * 0.025) AS umbral_r3,
                CASE WHEN SUM(CASE WHEN {_NO_R3_V} THEN 1 ELSE 0 END)
                          - FLOOR(SUM(CASE WHEN {_PAGO_R2} THEN 1 ELSE 0 END) * 0.025) > 0
                     THEN SUM(CASE WHEN {_NO_R3_V} THEN 1 ELSE 0 END)
                          - FLOOR(SUM(CASE WHEN {_PAGO_R2} THEN 1 ELSE 0 END) * 0.025)
                     ELSE 0 END AS exceso_r3
            FROM base
            GROUP BY [Grupo_Facturacion]
            ORDER BY [Grupo_Facturacion]
        """, params=p)

        def _sf(v):
            try:
                f = float(v); return 0.0 if (_math.isnan(f) or _math.isinf(f)) else f
            except Exception: return 0.0

        def _est(pct, umb):
            if umb == 0: return 'ok'
            r = pct / umb
            return 'ok' if r <= 0.7 else ('alerta' if r <= 1.0 else 'critico')

        grupos = []
        for _, r in df.iterrows():
            cli    = int(r['clientes'] or 0)
            arpu   = _sf(r['arpu_promedio'])
            pag_r1 = int(r['pagaron_r1'] or 0)
            pag_r2 = int(r['pagaron_r2'] or 0)
            npnf   = int(r['npnf']       or 0)
            no_r2  = int(r['no_pag_r2']  or 0)
            no_r3  = int(r['no_pag_r3']  or 0)
            exc_n  = int(r['exceso_npnf'] or 0)
            exc_2  = int(r['exceso_r2']   or 0)
            exc_3  = int(r['exceso_r3']   or 0)
            umb_n  = int(r['umbral_npnf'] or 0)
            umb_2  = int(r['umbral_r2']   or 0)
            umb_3  = int(r['umbral_r3']   or 0)

            costo_n = exc_n * arpu * 3.5 * 1.000
            costo_2 = exc_2 * arpu * 3.5 * 0.666
            costo_3 = exc_3 * arpu * 3.5 * 0.333

            if tramo == 'M1':
                total_pen = round(costo_n, 2)
                deuda_val = round(_sf(r['deuda_m1']), 2)
            elif tramo == 'M2':
                total_pen = round(costo_2, 2)
                deuda_val = round(_sf(r['deuda_m2']), 2)
            elif tramo == 'M3':
                total_pen = round(costo_3, 2)
                deuda_val = round(_sf(r['deuda_m3']), 2)
            else:
                total_pen = round(costo_n + costo_2 + costo_3, 2)
                deuda_val = round(_sf(r['deuda_total']), 2)

            pct_n = round(npnf  / cli    * 100, 2) if cli    else 0.0
            pct_2 = round(no_r2 / pag_r1 * 100, 2) if pag_r1 else 0.0
            pct_3 = round(no_r3 / pag_r2 * 100, 2) if pag_r2 else 0.0

            grupos.append({
                'grupo':    r['grupo'],
                'clientes': cli,
                'npnf':     {'morosos': npnf,  'umbral': umb_n, 'umbral_pct': 4.5,
                             'exceso': exc_n,  'costo': round(costo_n, 2),
                             'pct_mora': pct_n, 'estado': _est(pct_n, 4.5)},
                'extorno2': {'base': pag_r1, 'morosos': no_r2,  'umbral': umb_2, 'umbral_pct': 3.5,
                             'exceso': exc_2,  'costo': round(costo_2, 2),
                             'pct_mora': pct_2, 'estado': _est(pct_2, 3.5)},
                'extorno3': {'base': pag_r2, 'morosos': no_r3,  'umbral': umb_3, 'umbral_pct': 2.5,
                             'exceso': exc_3,  'costo': round(costo_3, 2),
                             'pct_mora': pct_3, 'estado': _est(pct_3, 2.5)},
                'deuda_m1':  round(_sf(r['deuda_m1']), 2),
                'deuda_m2':  round(_sf(r['deuda_m2']), 2),
                'deuda_m3':  round(_sf(r['deuda_m3']), 2),
                'deuda_total':        deuda_val,
                'total_penalidades':  total_pen,
                'deuda_vs_penalidad': round(deuda_val - total_pen, 2),
            })
        return {'grupos': grupos}
    except Exception as e:
        print(f"Error get_mora_perdidas: {e}")
        import traceback; traceback.print_exc()
        return {'grupos': []}


def get_mora_supervisores(**kw):
    try:
        opt, p = _mora_opt(**kw)
        df = get_data(f"""
            SELECT
                ISNULL([Supervisor], 'Sin supervisor') AS supervisor,
                COUNT(*) AS total,
                AVG(ARPU) AS arpu,
                SUM(CASE WHEN {_NPNF_C}  THEN 1 ELSE 0 END) AS npnf,
                SUM(CASE WHEN {_PAGO_R1} THEN 1 ELSE 0 END) AS pag_r1,
                SUM(CASE WHEN {_NO_R2}   THEN 1 ELSE 0 END) AS no_r2,
                SUM(CASE WHEN {_PAGO_R2} THEN 1 ELSE 0 END) AS pag_r2,
                SUM(CASE WHEN {_NO_R3}   THEN 1 ELSE 0 END) AS no_r3
            FROM {_MORA_VIEW}
            {_MORA_BASE_WHERE} {opt}
            GROUP BY [Supervisor]
            ORDER BY
                CASE WHEN COUNT(*) > 0
                     THEN SUM(CASE WHEN {_NPNF_C} THEN 1 ELSE 0 END) * 100.0 / COUNT(*)
                     ELSE 0 END DESC
        """, params=p)
        tramo = kw.get('tramo', '')
        rows = []
        for _, r in df.iterrows():
            total  = int(r['total']  or 0)
            npnf   = int(r['npnf']   or 0)
            no_r2  = int(r['no_r2']  or 0)
            no_r3  = int(r['no_r3']  or 0)
            pag_r1 = int(r['pag_r1'] or 0)
            pag_r2 = int(r['pag_r2'] or 0)
            arpu   = float(r['arpu']  or 0)

            if tramo == 'M2':
                morosos_tramo = no_r2
                base_tramo    = pag_r1
                umb_pct       = 0.035
                cost_factor   = 0.666
            elif tramo == 'M3':
                morosos_tramo = no_r3
                base_tramo    = pag_r2
                umb_pct       = 0.025
                cost_factor   = 0.333
            else:
                morosos_tramo = npnf
                base_tramo    = total
                umb_pct       = 0.045
                cost_factor   = 1.000

            exc = max(0.0, morosos_tramo - base_tramo * umb_pct)
            rows.append({
                'supervisor': r['supervisor'],
                'total':      total,
                'npnf':       npnf,
                'no_r2':      no_r2,
                'no_r3':      no_r3,
                'pct_mora':   round(morosos_tramo / base_tramo * 100, 2) if base_tramo else 0,
                'costo_npnf': round(exc * arpu * 3.5 * cost_factor, 2),
            })
        return rows
    except Exception as e:
        print(f"Error get_mora_supervisores: {e}")
        return []


def get_mora_casos(**kw):
    try:
        opt, p = _mora_opt(**kw)
        df_t = get_data(f"SELECT COUNT(*) AS n FROM {_MORA_VIEW} {_MORA_BASE_WHERE} {opt}", params=p)
        total = int(df_t.iloc[0]['n'] or 0)
        df = get_data(f"""
            SELECT ISNULL([Tipo_Caso_Clawback], 'Sin clasificar') AS caso, COUNT(*) AS n
            FROM {_MORA_VIEW} {_MORA_BASE_WHERE} {opt}
            GROUP BY [Tipo_Caso_Clawback] ORDER BY n DESC
        """, params=p)
        return [{'caso': r['caso'], 'clientes': int(r['n'] or 0),
                 'pct': round(int(r['n'] or 0) / total * 100, 1) if total else 0}
                for _, r in df.iterrows()]
    except Exception as e:
        print(f"Error get_mora_casos: {e}")
        return []


def get_mora_distritos(**kw):
    try:
        mora_expr = _tramo_mora_expr(kw.get('tramo', ''))
        opt, p = _mora_opt(**kw)
        df = get_data(f"""
            SELECT TOP 10
                ISNULL([Distrito], 'Sin distrito') AS distrito,
                COUNT(*) AS total,
                SUM(CASE WHEN {mora_expr} THEN 1 ELSE 0 END) AS npnf
            FROM {_MORA_VIEW} {_MORA_BASE_WHERE} {opt}
            GROUP BY [Distrito] ORDER BY npnf DESC
        """, params=p)
        return [{'distrito': r['distrito'], 'total': int(r['total'] or 0), 'npnf': int(r['npnf'] or 0),
                 'pct_mora': round(int(r['npnf'] or 0) / max(int(r['total'] or 1), 1) * 100, 2)}
                for _, r in df.iterrows()]
    except Exception as e:
        print(f"Error get_mora_distritos: {e}")
        return []


def get_mora_paquetes(**kw):
    try:
        tramo = kw.get('tramo', '')
        mora_expr = _tramo_mora_expr(tramo)
        deuda_col = _tramo_deuda_col(tramo)
        opt, p = _mora_opt(**kw)
        df = get_data(f"""
            SELECT TOP 10
                ISNULL([Paquete], 'Sin paquete') AS paquete,
                COUNT(*) AS total,
                SUM(CASE WHEN {mora_expr} THEN 1 ELSE 0 END) AS npnf,
                SUM(ISNULL({deuda_col}, 0)) AS deuda
            FROM {_MORA_VIEW} {_MORA_BASE_WHERE} {opt}
            GROUP BY [Paquete] ORDER BY npnf DESC
        """, params=p)
        return [{'paquete': r['paquete'], 'total': int(r['total'] or 0), 'npnf': int(r['npnf'] or 0),
                 'pct_mora':   round(int(r['npnf'] or 0) / max(int(r['total'] or 1), 1) * 100, 2),
                 'deuda_total': round(float(r['deuda'] or 0), 2)}
                for _, r in df.iterrows()]
    except Exception as e:
        print(f"Error get_mora_paquetes: {e}")
        return []


def get_mora_riesgos(**kw):
    try:
        deuda_col = _tramo_deuda_col(kw.get('tramo', ''))
        opt, p = _mora_opt(**kw)
        df = get_data(f"""
            SELECT
                ISNULL([Riesgo_Clawback], 'Sin riesgo') AS riesgo,
                COUNT(*) AS clientes,
                SUM(ISNULL({deuda_col}, 0)) AS deuda,
                AVG(ARPU) AS arpu
            FROM {_MORA_VIEW} {_MORA_BASE_WHERE} {opt}
            GROUP BY [Riesgo_Clawback] ORDER BY clientes DESC
        """, params=p)
        return [{'riesgo': r['riesgo'], 'clientes': int(r['clientes'] or 0),
                 'deuda':     round(float(r['deuda'] or 0), 2),
                 'costo_win': round(float(r['arpu'] or 0) * int(r['clientes'] or 0) * 3.5, 2)}
                for _, r in df.iterrows()]
    except Exception as e:
        print(f"Error get_mora_riesgos: {e}")
        return []


def get_mora_detalle(**kw):
    try:
        opt, p = _mora_opt(**kw)
        df = get_data(f"""
            SELECT TOP 2000
                ISNULL(CAST([DNI/Carnet Extraj.] AS VARCHAR(20)), '')     AS dni,
                ISNULL([Paquete], '')                                     AS paquete,
                ISNULL(CAST([Precio paquete] AS VARCHAR(20)), '')         AS precio_paquete,
                ISNULL([Adicional], '')                                   AS adicional,
                ISNULL([servicio adicional], '')                          AS servicio_adicional,
                ISNULL(CAST([Precio servicio adicional] AS VARCHAR(20)), '') AS precio_adicional,
                CAST(
                    ISNULL(CAST([Precio paquete] AS DECIMAL(18,2)), 0) +
                    ISNULL(CAST([Precio servicio adicional] AS DECIMAL(18,2)), 0)
                AS VARCHAR(20))                                           AS total_precio,
                CONVERT(VARCHAR(10), [Fecha Activacion],     103)        AS fecha_activacion,
                CONVERT(VARCHAR(10), [Fecha de Pago],        103)        AS fecha_pago,
                CONVERT(VARCHAR(10), [Fecha vencimiento M1], 103)        AS fecha_venc_m1,
                CONVERT(VARCHAR(10), [Fecha pago 1],         103)        AS fecha_pago_1,
                ISNULL(CAST([Deuda M1] AS VARCHAR(20)), '')              AS deuda_m1,
                ISNULL([Estado M1], '')                                  AS estado_m1,
                CONVERT(VARCHAR(10), [Fecha vencimiento M2], 103)        AS fecha_venc_m2,
                CONVERT(VARCHAR(10), [Fecha pago 2],         103)        AS fecha_pago_2,
                ISNULL(CAST([Deuda M2] AS VARCHAR(20)), '')              AS deuda_m2,
                ISNULL([Estado M2], '')                                  AS estado_m2,
                CONVERT(VARCHAR(10), [Fecha vencimiento M3], 103)        AS fecha_venc_m3,
                CONVERT(VARCHAR(10), [Fecha pago 3],         103)        AS fecha_pago_3,
                ISNULL(CAST([Deuda M3] AS VARCHAR(20)), '')              AS deuda_m3,
                ISNULL([Estado M3], '')                                  AS estado_m3,
                ISNULL(Recibo_Actual,      '')                           AS recibo,
                ISNULL(Ultimo_Estado_Pago, '')                           AS ultimo_estado,
                ISNULL(Tipo_Caso_Clawback, '')                           AS caso,
                ISNULL(Riesgo_Clawback,    '')                           AS riesgo
            FROM {_MORA_VIEW}
            {_MORA_BASE_WHERE} {opt}
            ORDER BY [Fecha Activacion] DESC
        """, params=p)
        return df.fillna('').to_dict('records')
    except Exception as e:
        print(f"Error get_mora_detalle: {e}")
        return []


def get_mora_pagos_dia(**kw):
    """Counts of R1/R2/R3 payments per calendar day (1–31). Single CTE query."""
    try:
        kw2 = {k: v for k, v in kw.items() if k != 'tramo'}
        opt, p = _mora_opt(**kw2)
        df = get_data(f"""
            WITH base AS (
                SELECT
                    DAY(TRY_CAST([Fecha pago 1] AS DATE)) AS d1,
                    DAY(TRY_CAST([Fecha pago 2] AS DATE)) AS d2,
                    DAY(TRY_CAST([Fecha pago 3] AS DATE)) AS d3
                FROM {_MORA_VIEW}
                {_MORA_BASE_WHERE} {opt}
            ),
            r1 AS (
                SELECT d1 AS dia, COUNT(*) AS n FROM base
                WHERE d1 IS NOT NULL GROUP BY d1
            ),
            r2 AS (
                SELECT d2 AS dia, COUNT(*) AS n FROM base
                WHERE d2 IS NOT NULL GROUP BY d2
            ),
            r3 AS (
                SELECT d3 AS dia, COUNT(*) AS n FROM base
                WHERE d3 IS NOT NULL GROUP BY d3
            ),
            dias AS (
                SELECT n FROM (VALUES
                    (1),(2),(3),(4),(5),(6),(7),(8),(9),(10),(11),
                    (12),(13),(14),(15),(16),(17),(18),(19),(20),(21),
                    (22),(23),(24),(25),(26),(27),(28),(29),(30),(31)
                ) v(n)
            )
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
        """, params=p)
        result = []
        for _, r in df.iterrows():
            v1 = int(r['pagaron_r1'] or 0)
            v2 = int(r['pagaron_r2'] or 0)
            v3 = int(r['pagaron_r3'] or 0)
            result.append({'dia': int(r['dia']), 'pagaron_r1': v1, 'pagaron_r2': v2,
                           'pagaron_r3': v3, 'total_ese_dia': v1 + v2 + v3})
        return result
    except Exception as e:
        print(f"Error get_mora_pagos_dia: {e}")
        import traceback; traceback.print_exc()
        return [{'dia': d, 'pagaron_r1': 0, 'pagaron_r2': 0, 'pagaron_r3': 0, 'total_ese_dia': 0}
                for d in range(1, 32)]


def get_mora_pagos_acumulado(**kw):
    """Cumulative R1/R2/R3 payments day by day."""
    try:
        data = get_mora_pagos_dia(**kw)
        result, acum1, acum2, acum3 = [], 0, 0, 0
        for d in data:
            acum1 += d['pagaron_r1']; acum2 += d['pagaron_r2']; acum3 += d['pagaron_r3']
            result.append({'dia': d['dia'], 'acum_r1': acum1, 'acum_r2': acum2, 'acum_r3': acum3})
        return result
    except Exception as e:
        print(f"Error get_mora_pagos_acumulado: {e}")
        return []


def get_departamentos():
    try:
        df = get_data(f"""
            SELECT DISTINCT [Departamento] AS v FROM {_MORA_VIEW}
            {_MORA_BASE_WHERE} AND [Departamento] IS NOT NULL ORDER BY v
        """)
        return df['v'].dropna().tolist()
    except Exception as e:
        print(f"Error get_departamentos: {e}")
        return []


def get_datos_agencia_lima(mes, anio, agencia, area='', dia=None):
    """Datos de UNA agencia de Lima: altas, ventas, anulaciones, top 10 vendedores y top 5 planes.
    dia (1-31): filtra ventas por Fecha de registro y altas por Fecha programación.
    Fuente de agencia: dim_usuarios_Aliv > Usuarios_win > campo Agencia de winforce."""
    _ac  = _area_clause(area)
    _fpa = "TRY_CONVERT(DATE, LEFT(wl.[Fecha programación], 10), 105)"
    _dlw = _dept_lima('wl')
    _dr  = "AND DAY(wl.[Fecha de registro]) = :dia" if dia else ""
    _da  = f"AND DAY({_fpa}) = :dia" if dia else ""
    # Expresión de agencia con prioridad: dim_usuarios_Aliv → Usuarios_win → winforce campo
    _ag_expr = "ISNULL(d.agencia, ISNULL(u.[AGENCIA], wl.[Agencia]))"
    _joins   = ("LEFT JOIN dbo.dim_usuarios_Aliv d ON wl.[Vendedor real] = d.vendedor "
                "LEFT JOIN dbo.Usuarios_win u ON wl.[Vendedor real] = u.[VENDEDOR]")
    try:
        # Resolver nombre canónico de la agencia
        df_match = get_data(f"""
            SELECT TOP 1 {_ag_expr} AS ag
            FROM dbo.winforce_lima wl
            {_joins}
            WHERE MONTH({_fpa}) = :mes AND YEAR({_fpa}) = :anio
              AND {_fpa} IS NOT NULL
              AND UPPER({_ag_expr}) LIKE :pat
              {_dlw} {_ac}
            GROUP BY {_ag_expr}
            ORDER BY COUNT(*) DESC
        """, params={'mes': mes, 'anio': anio, 'pat': f'%{agencia.upper()}%'})
        ag_real = df_match.iloc[0]['ag'] if not df_match.empty else agencia
        p = {'mes': mes, 'anio': anio, 'ag': ag_real}
        if dia:
            p['dia'] = int(dia)

        df_a = get_data(f"""
            SELECT COUNT(*) AS altas FROM dbo.winforce_lima wl
            {_joins}
            WHERE wl.[Estado orden] = 'Ejecutada'
              AND MONTH({_fpa}) = :mes AND YEAR({_fpa}) = :anio AND {_fpa} IS NOT NULL
              AND {_ag_expr} = :ag {_dlw} {_ac} {_da}
        """, params=p)
        df_v = get_data(f"""
            SELECT COUNT(*) AS ventas FROM dbo.winforce_lima wl
            {_joins}
            WHERE MONTH(wl.[Fecha de registro]) = :mes AND YEAR(wl.[Fecha de registro]) = :anio
              AND {_ag_expr} = :ag {_dlw} {_dr}
        """, params=p)
        df_n = get_data(f"""
            SELECT COUNT(*) AS anulaciones FROM dbo.winforce_lima wl
            {_joins}
            WHERE wl.[Estado orden] = 'Anulado'
              AND MONTH(wl.[Fecha de registro]) = :mes AND YEAR(wl.[Fecha de registro]) = :anio
              AND {_ag_expr} = :ag {_dlw} {_dr}
        """, params=p)
        df_top = get_data(f"""
            SELECT TOP 10 wl.[Vendedor real] AS vendedor, COUNT(*) AS altas
            FROM dbo.winforce_lima wl
            {_joins}
            WHERE wl.[Estado orden] = 'Ejecutada'
              AND MONTH({_fpa}) = :mes AND YEAR({_fpa}) = :anio AND {_fpa} IS NOT NULL
              AND {_ag_expr} = :ag {_dlw} {_ac} {_da}
            GROUP BY wl.[Vendedor real] ORDER BY altas DESC
        """, params=p)
        df_pl = get_data(f"""
            SELECT TOP 5 wl.[Plan], COUNT(*) AS altas
            FROM dbo.winforce_lima wl
            {_joins}
            WHERE wl.[Estado orden] = 'Ejecutada'
              AND MONTH({_fpa}) = :mes AND YEAR({_fpa}) = :anio AND {_fpa} IS NOT NULL
              AND {_ag_expr} = :ag {_dlw} {_ac} {_da}
            GROUP BY wl.[Plan] ORDER BY altas DESC
        """, params=p)
        df_sv = get_data(f"""
            SELECT TOP 5 ISNULL(u.[SUPERVISOR], '') AS supervisor, COUNT(*) AS altas
            FROM dbo.winforce_lima wl
            {_joins}
            WHERE wl.[Estado orden] = 'Ejecutada'
              AND MONTH({_fpa}) = :mes AND YEAR({_fpa}) = :anio AND {_fpa} IS NOT NULL
              AND {_ag_expr} = :ag
              AND ISNULL(u.[SUPERVISOR], '') <> ''
              {_dlw} {_ac} {_da}
            GROUP BY u.[SUPERVISOR] ORDER BY altas DESC
        """, params=p)

        altas = int(df_a.iloc[0]['altas']) if not df_a.empty else 0
        ventas = int(df_v.iloc[0]['ventas']) if not df_v.empty else 0
        anulaciones = int(df_n.iloc[0]['anulaciones']) if not df_n.empty else 0
        conv = round(altas / ventas * 100, 1) if ventas else 0
        return {
            'agencia': ag_real, 'mes': mes, 'anio': anio, 'dia': dia,
            'altas': altas, 'ventas': ventas, 'anulaciones': anulaciones, 'conversion_pct': conv,
            'top_vendedores': df_top.to_dict(orient='records'),
            'top_planes': df_pl.to_dict(orient='records'),
            'supervisores': df_sv.to_dict(orient='records'),
        }
    except Exception as e:
        print(f"Error get_datos_agencia_lima: {e}")
        return {}


def get_ranking_agencias_lima(mes, anio, area='', dia=None):
    """Ranking de todas las agencias de Lima: altas, ventas, anulaciones y conversión.
    dia (1-31): filtra ventas por Fecha de registro y altas por Fecha programación.
    Fuente de agencia: dim_usuarios_Aliv > Usuarios_win > campo Agencia de winforce."""
    _ac  = _area_clause(area)
    _fpa = "TRY_CONVERT(DATE, LEFT(wl.[Fecha programación], 10), 105)"
    _dlw = _dept_lima('wl')
    _dr  = "AND DAY(wl.[Fecha de registro]) = :dia" if dia else ""
    _da  = f"AND DAY({_fpa}) = :dia" if dia else ""
    _ag_expr = "ISNULL(d.agencia, ISNULL(u.[AGENCIA], wl.[Agencia]))"
    _joins   = ("LEFT JOIN dbo.dim_usuarios_Aliv d ON wl.[Vendedor real] = d.vendedor "
                "LEFT JOIN dbo.Usuarios_win u ON wl.[Vendedor real] = u.[VENDEDOR]")
    p = {'mes': mes, 'anio': anio}
    if dia:
        p['dia'] = int(dia)
    try:
        import pandas as pd
        df_a = get_data(f"""
            SELECT {_ag_expr} AS agencia, COUNT(*) AS altas
            FROM dbo.winforce_lima wl
            {_joins}
            WHERE wl.[Estado orden] = 'Ejecutada'
              AND MONTH({_fpa}) = :mes AND YEAR({_fpa}) = :anio AND {_fpa} IS NOT NULL
              {_dlw} {_ac} {_da}
            GROUP BY {_ag_expr}
        """, params=p)
        df_v = get_data(f"""
            SELECT {_ag_expr} AS agencia, COUNT(*) AS ventas
            FROM dbo.winforce_lima wl
            {_joins}
            WHERE MONTH(wl.[Fecha de registro]) = :mes AND YEAR(wl.[Fecha de registro]) = :anio
              {_dlw} {_dr}
            GROUP BY {_ag_expr}
        """, params=p)
        df_n = get_data(f"""
            SELECT {_ag_expr} AS agencia, COUNT(*) AS anulaciones
            FROM dbo.winforce_lima wl
            {_joins}
            WHERE wl.[Estado orden] = 'Anulado'
              AND MONTH(wl.[Fecha de registro]) = :mes AND YEAR(wl.[Fecha de registro]) = :anio
              {_dlw} {_dr}
            GROUP BY {_ag_expr}
        """, params=p)
        if df_a.empty:
            return []
        df = df_a.merge(df_v, on='agencia', how='outer').fillna(0)
        df = df.merge(df_n, on='agencia', how='outer').fillna(0)
        for col in ('altas', 'ventas', 'anulaciones'):
            df[col] = df[col].astype(int)
        df['conversion_pct'] = df.apply(
            lambda r: round(r['altas'] / r['ventas'] * 100, 1) if r['ventas'] > 0 else 0.0, axis=1
        )
        return df.sort_values('altas', ascending=False).to_dict(orient='records')
    except Exception as e:
        print(f"Error get_ranking_agencias_lima: {e}")
        return []


def get_datos_vendedor_lima(mes, anio, vendedor, dia=None):
    """Datos de UN vendedor específico de Lima: altas, ventas, agencia, supervisor, top planes y distritos.
    dia (1-31): filtra ventas por Fecha de registro y altas por Fecha programación."""
    _fpa = "TRY_CONVERT(DATE, LEFT(wl.[Fecha programación], 10), 105)"
    _dlw = _dept_lima('wl')
    _dr  = "AND DAY(wl.[Fecha de registro]) = :dia" if dia else ""
    _da  = f"AND DAY({_fpa}) = :dia" if dia else ""
    try:
        df_m = get_data(f"""
            SELECT TOP 1 wl.[Vendedor real] AS vr
            FROM dbo.winforce_lima wl
            WHERE UPPER(wl.[Vendedor real]) LIKE :pat
              AND MONTH(wl.[Fecha de registro]) = :mes AND YEAR(wl.[Fecha de registro]) = :anio
              {_dlw}
            GROUP BY wl.[Vendedor real] ORDER BY COUNT(*) DESC
        """, params={'mes': mes, 'anio': anio, 'pat': f'%{vendedor.upper()}%'})
        if df_m.empty:
            return {'error': f'No se encontró el vendedor "{vendedor}" en {mes}/{anio}'}
        vr = df_m.iloc[0]['vr']
        p = {'mes': mes, 'anio': anio, 'v': vr}
        if dia:
            p['dia'] = int(dia)

        df_a = get_data(f"""
            SELECT COUNT(*) AS altas FROM dbo.winforce_lima wl
            WHERE wl.[Estado orden] = 'Ejecutada' AND wl.[Vendedor real] = :v
              AND MONTH({_fpa}) = :mes AND YEAR({_fpa}) = :anio AND {_fpa} IS NOT NULL
              {_dlw} {_da}
        """, params=p)
        df_v = get_data(f"""
            SELECT
                COUNT(*) AS ventas,
                SUM(CASE WHEN [Estado orden] = 'Anulado' THEN 1 ELSE 0 END) AS anulaciones
            FROM dbo.winforce_lima wl
            WHERE [Vendedor real] = :v
              AND MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
              {_dlw} {_dr}
        """, params=p)
        df_u = get_data("SELECT TOP 1 ISNULL([AGENCIA],'') AS ag, ISNULL([SUPERVISOR],'') AS sv FROM dbo.Usuarios_win WHERE [VENDEDOR] = :v", params={'v': vr})
        df_pl = get_data(f"""
            SELECT TOP 5 wl.[Plan], COUNT(*) AS altas FROM dbo.winforce_lima wl
            WHERE wl.[Estado orden] = 'Ejecutada' AND wl.[Vendedor real] = :v
              AND MONTH({_fpa}) = :mes AND YEAR({_fpa}) = :anio AND {_fpa} IS NOT NULL
              {_dlw} {_da}
            GROUP BY wl.[Plan] ORDER BY altas DESC
        """, params=p)
        df_d = get_data(f"""
            SELECT TOP 5 [Distrito], COUNT(*) AS altas FROM dbo.winforce_lima wl
            WHERE wl.[Estado orden] = 'Ejecutada' AND wl.[Vendedor real] = :v
              AND MONTH({_fpa}) = :mes AND YEAR({_fpa}) = :anio AND {_fpa} IS NOT NULL
              AND [Distrito] IS NOT NULL {_dlw} {_da}
            GROUP BY [Distrito] ORDER BY altas DESC
        """, params=p)

        altas = int(df_a.iloc[0]['altas']) if not df_a.empty else 0
        ventas = int(df_v.iloc[0]['ventas']) if not df_v.empty else 0
        anulaciones = int(df_v.iloc[0]['anulaciones']) if not df_v.empty else 0
        return {
            'vendedor': vr, 'mes': mes, 'anio': anio, 'dia': dia,
            'agencia': df_u.iloc[0]['ag'] if not df_u.empty else '',
            'supervisor': df_u.iloc[0]['sv'] if not df_u.empty else '',
            'altas': altas, 'ventas': ventas, 'anulaciones': anulaciones,
            'conversion_pct': round(altas / ventas * 100, 1) if ventas else 0,
            'top_planes': df_pl.to_dict(orient='records'),
            'top_distritos': df_d.to_dict(orient='records'),
        }
    except Exception as e:
        print(f"Error get_datos_vendedor_lima: {e}")
        return {}


def get_mora_filtros():
    try:
        def _distinct(col):
            try:
                return get_data(f"""
                    SELECT DISTINCT {col} AS v FROM {_MORA_VIEW}
                    {_MORA_BASE_WHERE} AND {col} IS NOT NULL ORDER BY v
                """)['v'].dropna().tolist()
            except Exception:
                return []
        return {
            'grupos':       _distinct('[Grupo_Facturacion]'),
            'recibos':      _distinct('[Recibo_Actual]'),
            'supervisores': _distinct('[Supervisor]'),
            'distritos':    _distinct('[Distrito]'),
            'riesgos':      _distinct('[Riesgo_Clawback]'),
            'casos':        _distinct('[Tipo_Caso_Clawback]'),
        }
    except Exception as e:
        print(f"Error get_mora_filtros: {e}")
        return {'grupos': [], 'recibos': [], 'supervisores': [], 'distritos': [], 'riesgos': [], 'casos': []}
