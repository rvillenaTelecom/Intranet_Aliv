try:
    from db_config import get_data
except ImportError:
    from .db_config import get_data
import calendar
from datetime import datetime


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


def get_kpi_lima(mes, anio):
    """KPIs completos para Lima."""
    dias_trans, dias_tot, dias_rest = _dias_mes(mes, anio)
    try:
        # Cada métrica usa su propio filtro: ventas por Fecha de registro, altas por Fecha programación
        df = get_data(f"""
            SELECT
                (SELECT COUNT(*) FROM dbo.winforce_lima
                 WHERE MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
                ) AS ventas,
                (SELECT COUNT(*) FROM dbo.winforce_lima
                 WHERE [Estado orden] = 'Ejecutada'
                   AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
                   AND {_FP} IS NOT NULL
                ) AS altas,
                (SELECT COUNT(*) FROM dbo.winforce_lima
                 WHERE [Estado orden] = 'Anulado'
                   AND MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
                ) AS anulaciones,
                (SELECT DATEDIFF(DAY, DATEFROMPARTS(:anio, :mes, 1),
                         MAX(CAST([Fecha de registro] AS DATE))) + 1
                 FROM dbo.winforce_lima
                 WHERE MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
                ) AS dias_trans_db
        """, params={'mes': mes, 'anio': anio})
        r = df.iloc[0]
        altas       = _safe_int(r['altas'])
        ventas      = _safe_int(r['ventas'])
        anulaciones = _safe_int(r['anulaciones'])
        conversion  = round(altas / ventas * 100, 1) if ventas > 0 else 0

        # Usar días desde el último registro real; fallback al día de hoy si falla
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
            """, params={'mes': mes, 'anio': anio})
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
            """, params={'mes': mes, 'anio': anio})
            score = _safe_int(df2.iloc[0]['score_prom'])
        except:
            pass

        # Cuota Lima
        try:
            dc = get_data("SELECT SUM(Cuota) AS c FROM dbo.Cuota_Prov WHERE Mes_num=:mes AND Region='Lima'", params={'mes': mes})
            cuota = _safe_int(dc.iloc[0, 0], default=2332)
        except:
            cuota = 2332

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


def get_daily_trend_lima(mes, anio):
    """Ventas por Fecha de registro y altas por Fecha programación — Lima."""
    try:
        df = get_data(f"""
            SELECT dia, SUM(es_venta) AS ventas, SUM(es_alta) AS altas
            FROM (
                SELECT DAY([Fecha de registro]) AS dia, 1 AS es_venta, 0 AS es_alta
                FROM dbo.winforce_lima
                WHERE MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio

                UNION ALL

                SELECT DAY({_FP}) AS dia, 0 AS es_venta, 1 AS es_alta
                FROM dbo.winforce_lima
                WHERE [Estado orden] = 'Ejecutada'
                  AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
                  AND {_FP} IS NOT NULL
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


def get_distribucion_estados_lima(mes, anio):
    """Distribución de estados actuales basados en la Fecha de Registro."""
    try:
        df = get_data(f"""
            SELECT 
                ISNULL([Estado orden], '') AS estado,
                COUNT(*) AS registro
            FROM dbo.winforce_lima
            WHERE MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
            GROUP BY [Estado orden]
            ORDER BY [Estado orden]
        """, params={'mes': mes, 'anio': anio})
        
        if df.empty:
            return []
            
        total_registros = df['registro'].sum()
        df['pct_registro'] = df['registro'] / total_registros * 100
        df['pct_registro'] = df['pct_registro'].round(2)
        
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error get_distribucion_estados_lima: {e}")
        return []


def get_top_distritos_lima(mes, anio, top=10):
    """Top N distritos por altas en Lima."""
    try:
        df = get_data(f"""
            SELECT TOP {top} Distrito, COUNT(*) AS altas
            FROM dbo.winforce_lima
            WHERE [Estado orden] = 'Ejecutada'
              AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
              AND {_FP} IS NOT NULL
              AND Distrito IS NOT NULL AND Distrito <> ''
            GROUP BY Distrito
            ORDER BY altas DESC
        """, params={'mes': mes, 'anio': anio})
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error get_top_distritos_lima: {e}")
        return []


def get_top_vendedores_lima(mes, anio, top=10):
    """Top N vendedores por altas en Lima, con supervisor y agencia de Usuarios_win."""
    _fpa = "TRY_CONVERT(DATE, LEFT(wl.[Fecha programación], 10), 105)"
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
            GROUP BY wl.[Vendedor real], ISNULL(u.AGENCIA, wl.[Agencia]), ISNULL(u.SUPERVISOR, '')
            ORDER BY altas DESC
        """, params={'mes': mes, 'anio': anio})
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error get_top_vendedores_lima: {e}")
        return []


def get_tipo_vivienda_lima(mes, anio):
    """Altas, Ventas y % Inst Mismo Día por Tipo de Domicilio — Lima."""
    _fpa = "TRY_CONVERT(DATE, LEFT(wl.[Fecha programación], 10), 105)"
    try:
        query_ventas = f"""
            SELECT 
                ISNULL([Tipo de domicilio], 'Desconocido') AS vivienda, 
                COUNT(*) AS ventas
            FROM dbo.winforce_lima
            WHERE MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
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
            GROUP BY wl.[Tipo de domicilio]
        """
        
        import pandas as pd
        df_v = get_data(query_ventas, params={'mes': mes, 'anio': anio})
        df_a = get_data(query_altas, params={'mes': mes, 'anio': anio})
        
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


def get_pivot_planes_agencia(mes, anio):
    """Pivot: altas instaladas por Plan × Agencia (Usuarios_win) — Lima."""
    import pandas as pd
    _fpa = "TRY_CONVERT(DATE, LEFT(wl.[Fecha programación], 10), 105)"
    try:
        df = get_data(f"""
            SELECT
                wl.[Plan]                        AS plan,
                ISNULL(u.AGENCIA, 'Sin Agencia') AS agencia,
                COUNT(*)                         AS altas
            FROM dbo.winforce_lima wl
            LEFT JOIN dbo.Usuarios_win u ON wl.[Vendedor real] = u.VENDEDOR
            WHERE wl.[Estado orden] = 'Ejecutada'
              AND MONTH({_fpa}) = :mes AND YEAR({_fpa}) = :anio
              AND {_fpa} IS NOT NULL
              AND wl.[Plan] IS NOT NULL AND wl.[Plan] <> ''
            GROUP BY wl.[Plan], ISNULL(u.AGENCIA, 'Sin Agencia')
        """, params={'mes': mes, 'anio': anio})
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


def get_pivot_planes_agencia(mes, anio):
    """Genera la tabla pivot de Planes vs Agencias (JOIN con Usuarios_win)."""
    try:
        query = f"""
            SELECT 
                l.[Plan], 
                ISNULL(u.[AGENCIA], 'SIN AGENCIA') AS agencia, 
                COUNT(*) AS cnt
            FROM dbo.winforce_lima l
            LEFT JOIN dbo.Usuarios_win u ON l.[Vendedor real] = u.[VENDEDOR]
            WHERE l.[Estado orden] = 'Ejecutada'
              AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
              AND {_FP} IS NOT NULL
            GROUP BY l.[Plan], u.[AGENCIA]
        """
        import pandas as pd
        df_raw = get_data(query, params={'mes': mes, 'anio': anio})
        
        if df_raw.empty:
            return {'columns': [], 'rows': [], 'totals': {}}

        # Pivotar: Filas = Plan, Columnas = Agencia
        pivot = df_raw.pivot(index='Plan', columns='agencia', values='cnt').fillna(0).astype(int)
        
        # Calcular totales por fila (Plan)
        pivot['TOTAL'] = pivot.sum(axis=1)
        
        # Ordenar por Total descendente
        pivot = pivot.sort_values('TOTAL', ascending=False)
        
        # Totales por columna (Agencia)
        col_totals = pivot.sum().to_dict()
        
        # Preparar para el template
        agencias = [c for c in pivot.columns if c != 'TOTAL']
        columns = ['PLAN'] + agencias + ['TOTAL']
        
        rows = []
        for plan, row_data in pivot.iterrows():
            row_dict = {'PLAN': plan}
            for col in pivot.columns:
                row_dict[col] = int(row_data[col])
            rows.append(row_dict)
            
        return {
            'columns': columns,
            'rows': rows,
            'totals': col_totals
        }
    except Exception as e:
        print(f"Error get_pivot_planes_agencia: {e}")
        return {'columns': [], 'rows': [], 'totals': {}}


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
        df_c = get_data("SELECT Departamento AS agencia, Cuota FROM dbo.Cuota_Prov WHERE Mes_num = :mes AND Region = 'Provincia'", params={'mes': mes})

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


def get_localizacion_lima(mes, anio):
    """Score, Zona KML y comparativa P2 — Lima.
    Retorna None si la columna Zona_KML no está disponible."""

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
            WHERE MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
              AND [Zona_KML] IS NOT NULL AND [Zona_KML] <> ''
            GROUP BY [Zona_KML]
            ORDER BY cnt DESC
        """, params={'mes': mes, 'anio': anio})
        zonas = df_zona.to_dict(orient='records')

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
