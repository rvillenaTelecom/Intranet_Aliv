try:
    from db_config import get_data
except ImportError:
    from .db_config import get_data
import calendar
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cuotas_config import cuota_lima as _cuota_lima


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
    """SQL AND fragment for Área de planeamiento (Vertical = Condominio/Edificio, Horizontal = resto)."""
    if area == 'Vertical':
        return f"AND {col} = 'Condominio/Edificio'"
    elif area == 'Horizontal':
        return f"AND ({col} <> 'Condominio/Edificio' OR {col} IS NULL)"
    return ""


# Distritos que, aunque figuran bajo Departamento Lima/Callao en WinForce,
# se excluyen del conteo de Lima (criterio de negocio — ver SQL/Winforce SQL/Altas_win.sql).
_DISTRITOS_EXCLUIDOS_LIMA = ("'barranca'", "'chancay'", "'huacho'", "'hualmay'", "'huaral'")


def _dept_lima(alias=''):
    """SQL AND fragment to restrict winforce_lima to Lima + Callao departments, excluyendo distritos norte."""
    p = f"{alias}." if alias else ""
    excl = ", ".join(_DISTRITOS_EXCLUIDOS_LIMA)
    return f"AND {p}[Departamento] IN ('Lima', 'Callao') AND LOWER({p}[Distrito]) NOT IN ({excl})"


def _agencia_clause(agencia_grupo, col='[Vendedor real]'):
    """SQL AND fragment para separar fuerza propia (ALIV) de subagencias,
    usando dim_usuarios_Aliv.agencia (ALIV = directo, cualquier otro valor
    no nulo = subagencia: DEZANET, SIPION, LOTTUS, etc.)."""
    if agencia_grupo == 'Aliv':
        return (f"AND EXISTS (SELECT 1 FROM dbo.dim_usuarios_Aliv da2 "
                f"WHERE da2.vendedor = {col} AND da2.agencia = 'ALIV')")
    elif agencia_grupo == 'Sub':
        return (f"AND EXISTS (SELECT 1 FROM dbo.dim_usuarios_Aliv da2 "
                f"WHERE da2.vendedor = {col} AND da2.agencia IS NOT NULL AND da2.agencia <> 'ALIV')")
    return ""


def get_kpi_lima(mes, anio, area='', dia=None, cumul=False, base_dias=30, agencia_grupo=''):
    """KPIs completos para Lima. dia(1-31): filtra ventas/altas.
    cumul=False → exactamente ese día (para columna ALTAS DD.MM).
    cumul=True  → acumulado del 1 al día (para ALTAS ACUM y proyección).
    base_dias   → base de días para proyección (30 agentes, 28 jefe).
    agencia_grupo → '' (todos), 'Aliv' (fuerza propia) o 'Sub' (subagencias).
    Con agencia_grupo activo la cuota se omite (no existe cuota oficial por
    canal) — el panel de proyección se oculta solo, igual que un mes sin cuota."""
    dias_trans, dias_tot, dias_rest = _dias_mes(mes, anio)
    _ac = _area_clause(area)
    _agc = _agencia_clause(agencia_grupo)
    _op = "<=" if cumul else "="
    _dr = f"AND DAY([Fecha de registro]) {_op} :dia" if dia else ""
    _da = f"AND DAY({_FP}) {_op} :dia" if dia else ""
    p   = {'mes': mes, 'anio': anio}
    if dia:
        p['dia'] = int(dia)
    try:
        _dl = _dept_lima()
        df = get_data(f"""
            SELECT
                (SELECT COUNT(*) FROM dbo.winforce_lima
                 WHERE MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
                 {_dl} {_ac} {_agc} {_dr}
                ) AS ventas,
                (SELECT COUNT(*) FROM dbo.winforce_lima
                 WHERE [Estado orden] = 'Ejecutada'
                   AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
                   AND {_FP} IS NOT NULL
                 {_dl} {_ac} {_agc} {_da}
                ) AS altas,
                (SELECT COUNT(*) FROM dbo.winforce_lima
                 WHERE [Estado orden] = 'Anulado'
                   AND MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
                 {_dl} {_ac} {_agc} {_dr}
                ) AS anulaciones,
                (SELECT COUNT(*) FROM dbo.winforce_lima
                 WHERE [Estado del Pedido] = 'Validado'
                   AND MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
                 {_dl} {_ac} {_agc} {_dr}
                ) AS validado,
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
        validado    = _safe_int(r['validado'])
        conversion  = round(altas / ventas * 100, 1) if ventas > 0 else 0
        # Embudo detallado: Preventa (registro) -> Venta (Estado del Pedido=Validado) -> Alta (Ejecutada).
        conv_preventa_venta = round(validado / ventas * 100, 1) if ventas > 0 else 0
        conv_venta_alta     = round(altas / validado * 100, 1) if validado > 0 else 0

        # Si el usuario filtró por un día específico, ese día es la base de proyección.
        if dia:
            dias_trans = int(dia)
        else:
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
                  {_dl} {_ac} {_agc} {_da}
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
                  {_dl} {_ac} {_agc} {_dr}
            """, params=p)
            score = _safe_int(df2.iloc[0]['score_prom'])
        except:
            pass

        # Modo exacto (dia sin cumul): proyecciones no aplican
        # Modo acumulado (dia+cumul) o sin dia: calcular proyección con base dias_trans
        if dia and not cumul:
            cuota = proyeccion = pct_proyeccion = alcance = alcance_ideal = 0
            ritmo_actual = ritmo_necesario = faltantes = 0
            dias_rest_incl_hoy = 0
            cuota_110 = faltantes_110 = 0
            altas_nec_100 = altas_nec_110 = 0
            ventas_nec_100 = ventas_nec_110 = 0
            conversion_ayer = 0
            faltantes_ayer_100 = faltantes_ayer_110 = 0
            altas_ayer = 0
        else:
            # Cuota por canal: WIN solo da una cuota de Horizontal combinada,
            # que se reparte a mano entre Aliv y Subagencias (áreas
            # 'Horizontal_Aliv'/'Horizontal_Sub' en cuotas_lima). Si no está
            # definido ese reparto, cuota queda en 0 y el panel se oculta solo
            # (mismo comportamiento que un mes sin cuota definida).
            if agencia_grupo and area == 'Horizontal':
                cuota = _cuota_lima(mes, 'Horizontal_Aliv' if agencia_grupo == 'Aliv' else 'Horizontal_Sub')
            elif agencia_grupo:
                cuota = 0
            elif area == 'Horizontal':
                # Vista combinada (ejecutivo/gerencial, sin agencia): usa la
                # cuota real que entrega WIN, no la suma aliv+sub (que es un
                # reparto interno que puede no cuadrar con ese total). Si el
                # mes aún no tiene Horizontal_Win definido (meses viejos, o
                # el mes actual antes de que el admin la cargue), cae de
                # vuelta a la suma aliv+sub para no dejar el panel en 0.
                cuota = _cuota_lima(mes, 'Horizontal_Win') or _cuota_lima(mes, 'Horizontal')
            else:
                cuota = _cuota_lima(mes, area)
            proyeccion      = round(altas / dias_trans * base_dias) if dias_trans > 0 else 0
            alcance         = round(altas / cuota * 100, 1) if cuota > 0 else 0
            alcance_ideal   = round(dias_trans / dias_tot * 100, 1)
            ritmo_actual      = round(altas / dias_trans) if dias_trans > 0 else 0
            dias_base_rest    = max(base_dias - dias_trans, 1)
            ritmo_necesario   = round(max(cuota - altas, 0) / dias_base_rest)
            faltantes       = max(cuota - altas, 0)
            pct_proyeccion  = round(proyeccion / cuota * 100, 1) if cuota > 0 else 0

            # Días reales que quedan para cerrar el mes, incluyendo hoy —
            # es el horizonte que usamos para "cuánto necesito vender/instalar
            # por día" (distinto de dias_base_rest, que usa el proxy 28/30d).
            dias_rest_incl_hoy = max(dias_tot - dias_trans + 1, 1)

            cuota_110      = round(cuota * 1.10)
            faltantes_110  = max(cuota_110 - altas, 0)

            # Corte a cierre de AYER: si estamos viendo el mes en curso en vivo,
            # hoy todavía está a medio registrar/ejecutar en WinForce — usar el
            # avance de hoy a medias como base tanto infla altas de golpe (y hace
            # ver "0 faltantes" antes de tiempo) como hunde la conversión (ventas
            # de hoy que aún no tuvieron tiempo de instalarse). Por eso TODO el
            # panel de "qué necesito" (faltantes, altas/día, ventas/día) usa el
            # mismo corte ya cerrado — igual que el resto de reportes del pipeline
            # (ver Reporte_Proyección.py). "Días restantes" sigue arrancando en
            # hoy (dias_rest_incl_hoy): con lo que había cerrado ayer, hoy es el
            # primer día disponible para cerrar la brecha.
            # `faltantes`/`faltantes_110` (con altas de hoy en vivo) no se tocan
            # — los sigue usando la tarjeta "Altas Faltantes" tal cual antes.
            hoy_real = datetime.now()
            es_hoy_en_vivo = (mes == hoy_real.month and anio == hoy_real.year
                               and dias_trans == hoy_real.day)
            conversion_ayer = conversion
            altas_ayer = altas
            if es_hoy_en_vivo and dias_trans > 1:
                dia_corte_ayer = dias_trans - 1
                try:
                    df_ayer = get_data(f"""
                        SELECT
                            (SELECT COUNT(*) FROM dbo.winforce_lima
                             WHERE MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
                               AND DAY([Fecha de registro]) <= :dia_corte_ayer
                             {_dl} {_ac} {_agc}
                            ) AS ventas_ayer,
                            (SELECT COUNT(*) FROM dbo.winforce_lima
                             WHERE [Estado orden] = 'Ejecutada'
                               AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
                               AND {_FP} IS NOT NULL
                               AND DAY({_FP}) <= :dia_corte_ayer
                             {_dl} {_ac} {_agc}
                            ) AS altas_ayer
                    """, params={'mes': mes, 'anio': anio, 'dia_corte_ayer': dia_corte_ayer})
                    ventas_ayer = _safe_int(df_ayer.iloc[0]['ventas_ayer'])
                    altas_ayer  = _safe_int(df_ayer.iloc[0]['altas_ayer'])
                    if ventas_ayer > 0:
                        conversion_ayer = round(altas_ayer / ventas_ayer * 100, 1)
                except Exception as e:
                    print(f"Error conversion_ayer: {e}")
                    altas_ayer = altas

            faltantes_ayer_100 = max(cuota - altas_ayer, 0)
            faltantes_ayer_110 = max(cuota_110 - altas_ayer, 0)

            altas_nec_100  = round(faltantes_ayer_100 / dias_rest_incl_hoy, 1) if cuota > 0 else 0
            altas_nec_110  = round(faltantes_ayer_110 / dias_rest_incl_hoy, 1) if cuota > 0 else 0

            # Ventas (programadas) necesarias por día = altas necesarias / conversión
            # a cierre de ayer, porque no todas las ventas terminan en alta instalada.
            _conv = conversion_ayer / 100 if conversion_ayer > 0 else 0
            ventas_nec_100 = round(altas_nec_100 / _conv, 1) if _conv > 0 else None
            ventas_nec_110 = round(altas_nec_110 / _conv, 1) if _conv > 0 else None

        return {
            'ventas': ventas, 'altas': altas, 'cuota': cuota,
            'anulaciones': anulaciones, 'conversion': conversion,
            'validado': validado,
            'conv_preventa_venta': conv_preventa_venta, 'conv_venta_alta': conv_venta_alta,
            'instalados_mismo_dia': instalados_mismo_dia,
            'proyeccion': proyeccion, 'pct_proyeccion': pct_proyeccion,
            'alcance': alcance, 'alcance_ideal': alcance_ideal,
            'ritmo_actual': ritmo_actual, 'ritmo_necesario': ritmo_necesario,
            'faltantes': faltantes, 'score': score,
            'en_riesgo': 0, 'riesgo_pct': 0,
            'dias_trans': dias_trans, 'dias_tot': dias_tot,
            'dias_rest_incl_hoy': dias_rest_incl_hoy,
            'cuota_110': cuota_110, 'faltantes_110': faltantes_110,
            'altas_nec_100': altas_nec_100, 'altas_nec_110': altas_nec_110,
            'ventas_nec_100': ventas_nec_100, 'ventas_nec_110': ventas_nec_110,
            'conversion_ayer': conversion_ayer, 'altas_ayer': altas_ayer,
            'faltantes_ayer_100': faltantes_ayer_100, 'faltantes_ayer_110': faltantes_ayer_110,
        }
    except Exception as e:
        print(f"Error get_kpi_lima: {e}")
        return None


def get_equipo_ventas_kpis(mes, anio):
    """KPIs resumen para la página Equipo Ventas: cuota Lima total, Vertical,
    Horizontal y zonas activas (distritos de Lima con ventas este mes)."""
    kpi_lima = get_kpi_lima(mes, anio, area='')
    kpi_vert = get_kpi_lima(mes, anio, area='Vertical')
    kpi_horiz = get_kpi_lima(mes, anio, area='Horizontal')

    zonas_activas = 0
    try:
        _dl = _dept_lima()
        df_zl = get_data(f"""
            SELECT COUNT(DISTINCT [Distrito]) AS n
            FROM dbo.winforce_lima
            WHERE [Estado orden] = 'Ejecutada'
              AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
              AND {_FP} IS NOT NULL
              AND [Distrito] IS NOT NULL AND [Distrito] <> ''
              {_dl}
        """, params={'mes': mes, 'anio': anio})
        zonas_activas = _safe_int(df_zl.iloc[0, 0])
    except Exception as e:
        print(f"Error get_equipo_ventas_kpis (zonas): {e}")

    def _proy(kpi):
        kpi = kpi or {}
        return {
            'dias_rest_incl_hoy': kpi.get('dias_rest_incl_hoy', 0),
            'conversion':      kpi.get('conversion', 0),
            'conversion_ayer': kpi.get('conversion_ayer', 0),
            'altas_ayer':      kpi.get('altas_ayer', 0),
            'altas_hoy':       kpi.get('altas', 0),
            'cuota_110':       kpi.get('cuota_110', 0),
            'faltantes':       kpi.get('faltantes_ayer_100', 0),
            'faltantes_110':   kpi.get('faltantes_ayer_110', 0),
            'altas_nec_100':   kpi.get('altas_nec_100', 0),
            'altas_nec_110':   kpi.get('altas_nec_110', 0),
            'ventas_nec_100':  kpi.get('ventas_nec_100'),
            'ventas_nec_110':  kpi.get('ventas_nec_110'),
        }

    return {
        'cuota_lima':    kpi_lima.get('cuota', 0) if kpi_lima else 0,
        'altas_lima':    kpi_lima.get('altas', 0) if kpi_lima else 0,
        'alcance_lima':  kpi_lima.get('alcance', 0) if kpi_lima else 0,
        'cuota_vertical':    kpi_vert.get('cuota', 0) if kpi_vert else 0,
        'altas_vertical':    kpi_vert.get('altas', 0) if kpi_vert else 0,
        'alcance_vertical':  kpi_vert.get('alcance', 0) if kpi_vert else 0,
        'cuota_horizontal':    kpi_horiz.get('cuota', 0) if kpi_horiz else 0,
        'altas_horizontal':    kpi_horiz.get('altas', 0) if kpi_horiz else 0,
        'alcance_horizontal':  kpi_horiz.get('alcance', 0) if kpi_horiz else 0,
        'zonas_activas': zonas_activas,
        'proy_vertical':   _proy(kpi_vert),
        'proy_horizontal': _proy(kpi_horiz),
    }


_MESES_NOMBRE = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio',
                 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']


def get_cuotas_lima_historial(anio):
    """Cuota Vertical/Horizontal/Total de Lima para los 12 meses de `anio`,
    junto con las altas reales logradas ese mes (si ya hay datos)."""
    import cuotas_config

    altas_por_mes = {}
    try:
        _dl = _dept_lima()
        df = get_data(f"""
            SELECT MONTH({_FP}) AS mes,
                   SUM(CASE WHEN [Tipo de domicilio] = 'Condominio/Edificio' THEN 1 ELSE 0 END) AS vertical,
                   SUM(CASE WHEN [Tipo de domicilio] <> 'Condominio/Edificio' OR [Tipo de domicilio] IS NULL THEN 1 ELSE 0 END) AS horizontal,
                   COUNT(*) AS total
            FROM dbo.winforce_lima
            WHERE [Estado orden] = 'Ejecutada'
              AND YEAR({_FP}) = :anio AND {_FP} IS NOT NULL
              {_dl}
            GROUP BY MONTH({_FP})
        """, params={'anio': anio})
        for _, r in df.iterrows():
            altas_por_mes[int(r['mes'])] = {
                'vertical': _safe_int(r['vertical']),
                'horizontal': _safe_int(r['horizontal']),
                'total': _safe_int(r['total']),
            }
    except Exception as e:
        print(f"Error get_cuotas_lima_historial (altas): {e}")

    hoy = datetime.now()
    out = []
    for m in range(1, 13):
        cuota_vert = cuotas_config.cuota_lima(m, 'Vertical')
        cuota_horiz = cuotas_config.cuota_lima(m, 'Horizontal')
        cuota_horiz_aliv = cuotas_config.cuota_lima(m, 'Horizontal_Aliv')
        cuota_horiz_sub = cuotas_config.cuota_lima(m, 'Horizontal_Sub')
        cuota_horiz_win = cuotas_config.cuota_lima(m, 'Horizontal_Win')
        cuota_total = cuotas_config.cuota_lima(m, '')
        altas = altas_por_mes.get(m, {'vertical': 0, 'horizontal': 0, 'total': 0})
        out.append({
            'mes': m,
            'nombre': _MESES_NOMBRE[m - 1],
            'cuota_vertical': cuota_vert,
            'cuota_horizontal': cuota_horiz,
            'cuota_horizontal_aliv': cuota_horiz_aliv,
            'cuota_horizontal_sub': cuota_horiz_sub,
            'cuota_horizontal_win': cuota_horiz_win,
            'cuota_total': cuota_total,
            'altas_vertical': altas['vertical'],
            'altas_horizontal': altas['horizontal'],
            'altas_total': altas['total'],
            'alcance': round(altas['total'] / cuota_total * 100, 1) if cuota_total > 0 else None,
            'definida': cuotas_config.cuota_definida(m),
            'es_mes_actual': (m == hoy.month and anio == hoy.year),
            'es_futuro': (anio, m) > (hoy.year, hoy.month),
        })
    return out


def set_cuota_lima(mes, vertical, horizontal_aliv, horizontal_sub, horizontal_win=None):
    """Define/actualiza la cuota de Lima de un mes: Vertical + Horizontal
    repartida entre Aliv y Subagencias, más la cuota real de Horizontal que
    entrega WIN (en Azure SQL)."""
    import cuotas_config
    return cuotas_config.set_cuota_lima(mes, vertical, horizontal_aliv, horizontal_sub, horizontal_win)


def get_daily_trend_lima(mes, anio, area='', agencia_grupo=''):
    """Ventas por Fecha de registro y altas por Fecha programación — Lima."""
    _ac = _area_clause(area)
    _dl = _dept_lima()
    _agc = _agencia_clause(agencia_grupo)
    try:
        df = get_data(f"""
            SELECT dia, SUM(es_venta) AS ventas, SUM(es_alta) AS altas
            FROM (
                SELECT DAY([Fecha de registro]) AS dia, 1 AS es_venta, 0 AS es_alta
                FROM dbo.winforce_lima
                WHERE MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
                {_dl} {_ac} {_agc}

                UNION ALL

                SELECT DAY({_FP}) AS dia, 0 AS es_venta, 1 AS es_alta
                FROM dbo.winforce_lima
                WHERE [Estado orden] = 'Ejecutada'
                  AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
                  AND {_FP} IS NOT NULL
                {_dl} {_ac} {_agc}
            ) t
            GROUP BY dia
            ORDER BY dia
        """, params={'mes': mes, 'anio': anio})
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error get_daily_trend_lima: {e}")
        return []


def get_proyeccion_cierre_lima(mes, anio, dia_ref=None, base_dias=29, area=''):
    """Serie diaria acumulada de altas Lima (area='' = total, o 'Vertical'/'Horizontal')
    + proyección a `base_dias` por dos métodos: ritmo actual (plano) y tendencia
    (regresión lineal simple). dia_ref limita cuántos días del mes se consideran
    'reales' (None = todos los transcurridos)."""
    dias_trans_mes, _, _ = _dias_mes(mes, anio)
    dias_trans = int(dia_ref) if dia_ref else dias_trans_mes

    trend = get_daily_trend_lima(mes, anio, area=area)
    altas_por_dia = {int(r['dia']): _safe_int(r.get('altas')) for r in trend if r.get('dia') is not None}

    dias = list(range(1, dias_trans + 1))
    acumulado = []
    total = 0
    for d in dias:
        total += altas_por_dia.get(d, 0)
        acumulado.append(total)

    n = len(dias)
    altas_totales = acumulado[-1] if acumulado else 0
    ritmo_actual = round(altas_totales / dias_trans, 2) if dias_trans > 0 else 0

    # Regresión lineal simple (mínimos cuadrados) sobre (día, acumulado): y = a + b*x
    if n >= 2:
        sum_x = sum(dias)
        sum_y = sum(acumulado)
        sum_xy = sum(x * y for x, y in zip(dias, acumulado))
        sum_x2 = sum(x * x for x in dias)
        denom = n * sum_x2 - sum_x ** 2
        if denom != 0:
            b = (n * sum_xy - sum_x * sum_y) / denom
            a = (sum_y - b * sum_x) / n
        else:
            a, b = 0, ritmo_actual
    else:
        a, b = 0, ritmo_actual

    dias_full = list(range(1, base_dias + 1))
    serie_plano     = [round(ritmo_actual * d) for d in dias_full]
    serie_tendencia = [max(round(a + b * d), 0) for d in dias_full]
    serie_real      = [acumulado[d - 1] if d <= n else None for d in dias_full]

    cuota = _cuota_lima(mes, area)
    fin_plano     = serie_plano[-1] if serie_plano else 0
    fin_tendencia = serie_tendencia[-1] if serie_tendencia else 0
    piso  = min(fin_plano, fin_tendencia)
    techo = max(fin_plano, fin_tendencia)

    return {
        'dias': dias_full, 'dias_trans': dias_trans, 'base_dias': base_dias,
        'cuota': cuota, 'ritmo_actual': ritmo_actual,
        'plano': serie_plano, 'tendencia': serie_tendencia, 'real': serie_real,
        'piso': piso, 'techo': techo,
    }


def get_bac_lima(mes, anio, dia_corte, area=''):
    """BAC (Backlog Agendado Comprometido): instalaciones ya vendidas, programadas
    y VALIDADAS (Estado orden LIKE 'Programada' + Estado del Pedido LIKE 'Validado'
    — una Programada sin validar aún puede caer o no confirmarse), agrupadas por
    día de Fecha de programación, desde el día siguiente al corte hasta fin de mes.
    area: '', 'Vertical', 'Horizontal'.
    Devuelve {dia: cantidad} con todos los días restantes presentes (0 si no hay nada)."""
    _ac = _area_clause(area)
    _dl = _dept_lima()
    dias_tot = calendar.monthrange(anio, mes)[1]
    try:
        df = get_data(f"""
            SELECT DAY({_FP}) AS dia, COUNT(*) AS n
            FROM dbo.winforce_lima
            WHERE [Estado orden] LIKE '%Programada%'
              AND [Estado del Pedido] LIKE '%Validado%'
              AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
              AND {_FP} IS NOT NULL
              AND DAY({_FP}) > :dia_corte
              {_dl} {_ac}
            GROUP BY DAY({_FP})
            ORDER BY DAY({_FP})
        """, params={'mes': mes, 'anio': anio, 'dia_corte': int(dia_corte)})
        conteo = {int(r['dia']): _safe_int(r['n']) for r in df.to_dict(orient='records')}
        return {d: conteo.get(d, 0) for d in range(int(dia_corte) + 1, dias_tot + 1)}
    except Exception as e:
        print(f"Error get_bac_lima: {e}")
        return {}


_ORDEN_TURNO = ['08:00:00', '12:00:00', '16:00:00']
_NOMBRES_TURNO = {'08:00:00': 'Mañana (8-12)', '12:00:00': 'Mediodía (12-16)', '16:00:00': 'Tarde (16-20)'}


def get_activaciones_hoy(fecha=None):
    """Instalaciones (ALTAS) de un día (por defecto HOY): ejecutadas vs.
    pendientes VALIDADAS (mismo criterio que el BAC: Estado orden LIKE
    'Programada' + Estado del Pedido LIKE 'Validado' — no cuenta Canceladas,
    Rescates ni Programadas sin validar). Desglosado por Tramo Horario (turno
    agendado: 08:00 mañana, 12:00 mediodía, 16:00 tarde) — el sistema no
    guarda la hora exacta de ejecución, solo el turno — y por área
    (Vertical/Horizontal), para el cuadro de avance del día."""
    fecha = fecha or datetime.now().date()
    _dl = _dept_lima()
    try:
        df = get_data(f"""
            SELECT
                [Tramo Horario] AS turno,
                CASE WHEN [Tipo de domicilio] = 'Condominio/Edificio' THEN 'Vertical' ELSE 'Horizontal' END AS area,
                SUM(CASE WHEN [Estado orden] = 'Ejecutada' THEN 1 ELSE 0 END) AS ejecutadas,
                SUM(CASE WHEN [Estado orden] LIKE '%Programada%' AND [Estado del Pedido] LIKE '%Validado%' THEN 1 ELSE 0 END) AS pendientes
            FROM dbo.winforce_lima
            WHERE {_FP} = :fecha
            {_dl}
            GROUP BY [Tramo Horario],
                     CASE WHEN [Tipo de domicilio] = 'Condominio/Edificio' THEN 'Vertical' ELSE 'Horizontal' END
        """, params={'fecha': fecha})
        por_turno_area = {}
        for r in df.to_dict(orient='records'):
            t = r.get('turno')
            if not t:
                continue
            por_turno_area[(str(t), r['area'])] = {
                'ejecutadas': _safe_int(r['ejecutadas']), 'pendientes': _safe_int(r['pendientes']),
            }

        claves_vistas = {t for (t, _a) in por_turno_area}
        claves = _ORDEN_TURNO + sorted(claves_vistas - set(_ORDEN_TURNO))

        turnos = []
        total_ej = total_pend = 0
        total_ej_v = total_ej_h = total_pend_v = total_pend_h = 0
        for k in claves:
            ej_v = por_turno_area.get((k, 'Vertical'), {}).get('ejecutadas', 0)
            ej_h = por_turno_area.get((k, 'Horizontal'), {}).get('ejecutadas', 0)
            pend_v = por_turno_area.get((k, 'Vertical'), {}).get('pendientes', 0)
            pend_h = por_turno_area.get((k, 'Horizontal'), {}).get('pendientes', 0)
            ej = ej_v + ej_h
            pend = pend_v + pend_h
            if ej == 0 and pend == 0:
                continue
            total_ej += ej
            total_pend += pend
            total_ej_v += ej_v
            total_ej_h += ej_h
            total_pend_v += pend_v
            total_pend_h += pend_h
            turnos.append({
                'turno': _NOMBRES_TURNO.get(k, k), 'ejecutadas': ej, 'pendientes': pend,
                'ejecutadas_vertical': ej_v, 'ejecutadas_horizontal': ej_h,
                'pendientes_vertical': pend_v, 'pendientes_horizontal': pend_h,
            })

        return {
            'ejecutadas': total_ej, 'pendientes': total_pend,
            'agendadas': total_ej + total_pend, 'faltan': total_pend,
            'ejecutadas_vertical': total_ej_v, 'ejecutadas_horizontal': total_ej_h,
            'pendientes_vertical': total_pend_v, 'pendientes_horizontal': total_pend_h,
            'turnos': turnos,
        }
    except Exception as e:
        print(f"Error get_activaciones_hoy: {e}")
        return {'ejecutadas': 0, 'pendientes': 0, 'agendadas': 0, 'faltan': 0,
                'ejecutadas_vertical': 0, 'ejecutadas_horizontal': 0,
                'pendientes_vertical': 0, 'pendientes_horizontal': 0, 'turnos': []}


def get_distribucion_estados_lima(mes, anio, area='', dia=None, agencia_grupo=''):
    """Distribución de estados actuales basados en la Fecha de Registro."""
    _ac = _area_clause(area)
    _dl = _dept_lima()
    _agc = _agencia_clause(agencia_grupo)
    _dr = "AND DAY([Fecha de registro]) <= :dia" if dia else ""
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
            {_dl} {_ac} {_agc} {_dr}
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


def get_top_distritos_lima(mes, anio, top=10, area='', dia=None, cumul=True, agencia_grupo=''):
    """Top N distritos por altas en Lima. cumul=False filtra exactamente ese día."""
    _ac = _area_clause(area)
    _dl = _dept_lima()
    _agc = _agencia_clause(agencia_grupo)
    _op = "<=" if cumul else "="
    _da = f"AND DAY({_FP}) {_op} :dia" if dia else ""
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
              {_dl} {_ac} {_agc} {_da}
            GROUP BY Distrito
            ORDER BY altas DESC
        """, params=p)
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error get_top_distritos_lima: {e}")
        return []


def get_velocidad_planes_lima(mes, anio, area='', dia=None, cumul=True, agencia_grupo=''):
    """Distribución de altas de Lima por velocidad de plan (Mbps). cumul=False filtra exactamente ese día."""
    _ac = _area_clause(area)
    _dl = _dept_lima()
    _agc = _agencia_clause(agencia_grupo)
    _vel = "LEFT([Plan], CHARINDEX(' ', [Plan] + ' ') - 1)"
    _op = "<=" if cumul else "="
    _da = f"AND DAY({_FP}) {_op} :dia" if dia else ""
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
              {_dl} {_ac} {_agc} {_da}
            GROUP BY {_vel}
            ORDER BY altas DESC
        """, params=p)
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error get_velocidad_planes_lima: {e}")
        return []


def get_velocidad_planes_ventas_lima(mes, anio, area='', dia=None):
    """Distribución de ventas (registros) de Lima por velocidad de plan (Mbps)."""
    _ac = _area_clause(area)
    _dl = _dept_lima()
    _vel = "LEFT([Plan], CHARINDEX(' ', [Plan] + ' ') - 1)"
    _dr = "AND DAY([Fecha de registro]) <= :dia" if dia else ""
    p   = {'mes': mes, 'anio': anio}
    if dia:
        p['dia'] = int(dia)
    try:
        df = get_data(f"""
            SELECT
                {_vel} AS velocidad,
                COUNT(*) AS ventas,
                ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
            FROM dbo.winforce_lima
            WHERE MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
              AND [Plan] IS NOT NULL AND [Plan] <> ''
              {_dl} {_ac} {_dr}
            GROUP BY {_vel}
            ORDER BY ventas DESC
        """, params=p)
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error get_velocidad_planes_ventas_lima: {e}")
        return []


def get_top_vendedores_lima(mes, anio, top=10, dia=None):
    """Top N vendedores por altas en Lima, con supervisor y agencia.
    dia (1-31): filtra altas instaladas en ese día (Fecha programación)."""
    _fpa = "TRY_CONVERT(DATE, LEFT(wl.[Fecha programación], 10), 105)"
    _dlw = _dept_lima('wl')
    _da  = f"AND DAY({_fpa}) <= :dia" if dia else ""
    params = {'mes': mes, 'anio': anio}
    if dia:
        params['dia'] = int(dia)
    try:
        df = get_data(f"""
            SELECT TOP {top}
                wl.[Vendedor real]               AS vendedor,
                ISNULL(u.agencia, wl.[Agencia])  AS agencia,
                ISNULL(u.supervisor, '')          AS supervisor,
                COUNT(*)                          AS altas
            FROM dbo.winforce_lima wl
            LEFT JOIN dbo.dim_usuarios_Aliv u ON wl.[Vendedor real] = u.vendedor
            WHERE wl.[Estado orden] = 'Ejecutada'
              AND MONTH({_fpa}) = :mes AND YEAR({_fpa}) = :anio
              AND {_fpa} IS NOT NULL
              AND wl.[Vendedor real] IS NOT NULL AND wl.[Vendedor real] <> ''
              {_dlw} {_da}
            GROUP BY wl.[Vendedor real], ISNULL(u.agencia, wl.[Agencia]), ISNULL(u.supervisor, '')
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
    _dr  = "AND DAY([Fecha de registro]) <= :dia" if dia else ""
    _da  = f"AND DAY({_fpa}) <= :dia" if dia else ""
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
    """Pivot: altas instaladas por Plan × Agencia (dim_usuarios_Aliv) — Lima."""
    import pandas as pd
    _fpa = "TRY_CONVERT(DATE, LEFT(wl.[Fecha programación], 10), 105)"
    _dlw = _dept_lima('wl')
    _acw = _area_clause(area, col='wl.[Tipo de domicilio]')
    _da  = f"AND DAY({_fpa}) <= :dia" if dia else ""
    p    = {'mes': mes, 'anio': anio}
    if dia:
        p['dia'] = int(dia)
    try:
        df = get_data(f"""
            SELECT
                wl.[Plan]                              AS nombre_plan,
                ISNULL(d.agencia, wl.[Agencia])        AS agencia,
                COUNT(*)                               AS altas
            FROM dbo.winforce_lima wl
            LEFT JOIN dbo.dim_usuarios_Aliv d ON wl.[Vendedor real] = d.vendedor
            WHERE wl.[Estado orden] = 'Ejecutada'
              AND MONTH({_fpa}) = :mes AND YEAR({_fpa}) = :anio
              AND {_fpa} IS NOT NULL
              AND wl.[Plan] IS NOT NULL AND wl.[Plan] <> ''
              {_dlw} {_acw} {_da}
            GROUP BY wl.[Plan], ISNULL(d.agencia, wl.[Agencia])
        """, params=p)
        if df.empty:
            return {'columns': ['PLAN', 'TOTAL'], 'rows': [], 'totals': {'TOTAL': 0}}

        pivot = df.pivot_table(index='nombre_plan', columns='agencia', values='altas',
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


def get_resumen_lima(mes, anio, dia=None, base_dias=30):
    """Resumen Lima: total + Horizontal + Vertical.
    'altas_dia' usa el día seleccionado o el día de hoy si no se especifica."""
    from datetime import datetime as _dt
    hoy = _dt.now()
    _, dias_tot, _ = _dias_mes(mes, anio)
    dia_col = dia if dia else (hoy.day if (hoy.month == mes and hoy.year == anio) else dias_tot)

    rows = []
    for area, label, nivel in [
        ('',           'LIMA',       'lima'),
        ('Horizontal', 'HORIZONTAL', 'lima_sub'),
        ('Vertical',   'VERTICAL',   'lima_sub'),
    ]:
        kpi_d = get_kpi_lima(mes, anio, area=area, dia=dia_col, base_dias=base_dias) or {}
        kpi   = (get_kpi_lima(mes, anio, area=area, dia=dia_col, cumul=True, base_dias=base_dias) or {}) if dia else (get_kpi_lima(mes, anio, area=area, base_dias=base_dias) or {})
        rows.append({
            'departamento': label,
            'nivel':        nivel,
            'altas_dia':    kpi_d.get('altas', 0),
            'altas_acum':   kpi.get('altas', 0),
            'proyeccion':   kpi.get('proyeccion', 0),
            'cuota':        kpi.get('cuota', 0),
            'alcance':      kpi.get('alcance', 0.0),
            'faltantes':    kpi.get('faltantes', 0),
        })

    return {'rows': rows, 'dia_col': dia_col}


def _normalizar_agencia(raw):
    """Normaliza un nombre de agencia raw a uno de los 6 buckets.
    Prioriza dim_usuarios_Aliv → wl.[Agencia]."""
    ag = str(raw).upper().strip() if raw else 'ALIV'
    if 'ALIV'    in ag: return 'ALIV'
    if 'DEZANET' in ag: return 'DEZANET'
    if 'GYA'     in ag: return 'GYA'
    if 'SIPION'  in ag or 'SIPIÓN' in ag: return 'SIPION'
    if 'LOTTUS'  in ag or 'LOTUS'  in ag: return 'LOTTUS'
    if '2TRATO'  in ag or 'LLAMA'  in ag: return 'SUB-AGENCIAS'
    if ag == '' or ag == 'ALIV':           return 'ALIV'
    return 'SUB-AGENCIAS'


def get_tabla_agencias_lima(mes, anio, dia=None):
    """Altas por agencia comercial en Lima (Lima/Horizontal/Vertical).
    SUB-AGENCIAS agrupa Llama Peru + 2Tratos. Normalización en Python para evitar LIKE en GROUP BY."""
    _fpa = "TRY_CONVERT(DATE, LEFT(wl.[Fecha programación], 10), 105)"
    _dlw = _dept_lima('wl')
    _da  = f"AND DAY({_fpa}) <= :dia" if dia else ""
    dias_trans, _, _ = _dias_mes(mes, anio)
    if dia:
        dias_trans = int(dia)
    p = {'mes': mes, 'anio': anio}
    if dia:
        p['dia'] = int(dia)

    try:
        df = get_data(f"""
            SELECT
                ISNULL(d.agencia, wl.[Agencia]) AS raw_agencia,
                CASE
                    WHEN wl.[Tipo de domicilio] = 'Condominio/Edificio' THEN 'VERTICAL'
                    ELSE 'HORIZONTAL'
                END AS area,
                COUNT(*) AS altas
            FROM dbo.winforce_lima wl
            LEFT JOIN dbo.dim_usuarios_Aliv d ON wl.[Vendedor real] = d.vendedor
            WHERE wl.[Estado orden] = 'Ejecutada'
              AND MONTH({_fpa}) = :mes AND YEAR({_fpa}) = :anio
              AND {_fpa} IS NOT NULL
              {_dlw} {_da}
            GROUP BY ISNULL(d.agencia, wl.[Agencia]),
                CASE
                    WHEN wl.[Tipo de domicilio] = 'Condominio/Edificio' THEN 'VERTICAL'
                    ELSE 'HORIZONTAL'
                END
        """, params=p)

        if df.empty:
            return None

        df['agencia'] = df['raw_agencia'].apply(_normalizar_agencia)
        df['altas']   = df['altas'].astype(int)
        df = df.groupby(['agencia', 'area'], as_index=False)['altas'].sum()

        def _make_row(label, nivel, subset):
            def s(ag): return int(subset[subset['agencia'] == ag]['altas'].sum())
            aliv  = s('ALIV')
            total = int(subset['altas'].sum())
            return {
                'label': label, 'nivel': nivel,
                'aliv': aliv, 'dezanet': s('DEZANET'), 'gya': s('GYA'),
                'sipion': s('SIPION'), 'lottus': s('LOTTUS'),
                'sub_ag': s('SUB-AGENCIAS'),
                'total': total, 'sub_total': total - aliv,
            }

        h_df = df[df['area'] == 'HORIZONTAL']
        v_df = df[df['area'] == 'VERTICAL']

        rows = [
            _make_row('LIMA',       'lima',     df),
            _make_row('HORIZONTAL', 'lima_sub', h_df),
            _make_row('VERTICAL',   'lima_sub', v_df),
        ]

        def proy(n): return round(n / dias_trans * 30) if dias_trans > 0 else 0
        lima = rows[0]

        return {
            'rows':         rows,
            'proy_aliv':    proy(lima['aliv']),
            'proy_dezanet': proy(lima['dezanet']),
            'proy_sub':     proy(lima['sub_total']),
        }
    except Exception as e:
        print(f"Error get_tabla_agencias_lima: {e}")
        return None


_AG_JOIN = """LEFT JOIN dbo.dim_usuarios_Aliv ua
                ON CASE wf.[Vendedor real]
                    WHEN 'LUIS ALBERTO CASTILLON CARHUAY' THEN 'LUIS ALBERTO CASTILLON CARHUAYANO'
                    ELSE wf.[Vendedor real]
                   END = ua.vendedor"""

_AG_COLS = """
                SUM(CASE WHEN ua.agencia = 'ALIV' THEN 1 ELSE 0 END) AS aliv,
                SUM(CASE WHEN ua.agencia = 'DEZANET' THEN 1 ELSE 0 END) AS dezanet,
                SUM(CASE WHEN ua.agencia = 'LOTTUS' THEN 1 ELSE 0 END) AS lottus,
                SUM(CASE WHEN ua.agencia = 'SIPION' THEN 1 ELSE 0 END) AS sipion,
                SUM(CASE WHEN ua.agencia = 'SUB-AGENCIAS' THEN 1 ELSE 0 END) AS sub_agencias,
                SUM(CASE WHEN ua.agencia = 'SUB-AGENCIAS 2' THEN 1 ELSE 0 END) AS sub_agencias_2,
                COUNT(*) AS total"""


def _subagencia_conteo(mes, anio, area, dia, metric, cumul=True):
    """Conteo de Ventas o Altas por sub-agencia (ALIV, DEZANET, LOTTUS, SIPION,
    SUB-AGENCIAS, SUB-AGENCIAS 2) para un Área (Vertical/Horizontal), Lima + Callao.
    metric: 'ventas' (Pre-Venta, por Fecha de registro) o 'altas' (Ejecutada, por
    Fecha programación) — mismo criterio que el resto del dashboard.
    cumul=False filtra exactamente ese día (en vez de acumulado 1..día).
    El JOIN corrige a mano el nombre mal tipeado de un vendedor en WinForce
    ('...CARHUAY' -> '...CARHUAYANO') para que no se pierda del JOIN a dim_usuarios_Aliv."""
    _dlw = _dept_lima('wf')
    _ac  = _area_clause(area, col='wf.[Tipo de domicilio]')
    _op  = "<=" if cumul else "="

    if metric == 'altas':
        _fpw = "TRY_CONVERT(DATE, LEFT(wf.[Fecha programación], 10), 105)"
        _dd  = f"AND DAY({_fpw}) {_op} :dia" if dia else ""
        where_extra = f"wf.[Estado orden] = 'Ejecutada' AND MONTH({_fpw}) = :mes AND YEAR({_fpw}) = :anio AND {_fpw} IS NOT NULL"
    else:
        _dd = f"AND DAY(wf.[Fecha de registro]) {_op} :dia" if dia else ""
        where_extra = "MONTH(wf.[Fecha de registro]) = :mes AND YEAR(wf.[Fecha de registro]) = :anio"

    p = {'mes': mes, 'anio': anio}
    if dia:
        p['dia'] = int(dia)
    try:
        df = get_data(f"""
            SELECT {_AG_COLS}
            FROM dbo.winforce_lima wf
            {_AG_JOIN}
            WHERE {where_extra}
              {_dlw} {_ac} {_dd}
        """, params=p)

        if df.empty:
            return None
        r = df.iloc[0]
        return {
            'aliv': _safe_int(r['aliv']), 'dezanet': _safe_int(r['dezanet']),
            'lottus': _safe_int(r['lottus']), 'sipion': _safe_int(r['sipion']),
            'sub_agencias': _safe_int(r['sub_agencias']), 'sub_agencias_2': _safe_int(r['sub_agencias_2']),
            'total': _safe_int(r['total']),
        }
    except Exception as e:
        print(f"Error _subagencia_conteo ({metric}): {e}")
        return None


def get_pivot_subagencias_lima(mes, anio, dia=None, cumul=True):
    """Pivot Ventas/Altas x sub-agencia, con desglose Lima/Horizontal/Vertical
    (Lima = Horizontal + Vertical), para el Reporte Gerencial.
    cumul=False filtra exactamente el día `dia` (en vez de acumulado 1..día)."""
    result = {}
    for metric in ('ventas', 'altas'):
        h = _subagencia_conteo(mes, anio, 'Horizontal', dia, metric, cumul=cumul)
        v = _subagencia_conteo(mes, anio, 'Vertical',   dia, metric, cumul=cumul)
        if h is None or v is None:
            result[metric] = None
            continue
        lima = {key: h[key] + v[key] for key in h}
        result[metric] = {'lima': lima, 'horizontal': h, 'vertical': v}
    return result


def get_pivot_planes_agencias_lima(mes, anio, dia=None):
    """Pivot Plan × Agencia normalizada — Lima. Devuelve altas y ventas por separado.
    Normalización de agencia en Python con _normalizar_agencia para evitar LIKE en GROUP BY."""
    _fpa  = "TRY_CONVERT(DATE, LEFT(wl.[Fecha programación], 10), 105)"
    _dlw  = _dept_lima('wl')
    _da   = f"AND DAY({_fpa}) <= :dia" if dia else ""
    _dr   = f"AND DAY(wl.[Fecha de registro]) <= :dia" if dia else ""
    _joins = "LEFT JOIN dbo.dim_usuarios_Aliv d ON wl.[Vendedor real] = d.vendedor"
    _raw   = "ISNULL(d.agencia, wl.[Agencia])"
    _AG_ORDER = ['ALIV', 'DEZANET', 'GYA', 'SIPION', 'LOTTUS', 'SUB-AGENCIAS']
    p = {'mes': mes, 'anio': anio}
    if dia:
        p['dia'] = int(dia)

    def _build_pivot(df):
        if df.empty:
            return {'columns': ['PLAN'] + _AG_ORDER + ['TOTAL'], 'rows': [], 'totals': {ag: 0 for ag in _AG_ORDER + ['TOTAL']}}
        df['agencia'] = df['raw_agencia'].apply(_normalizar_agencia)
        df = df.groupby(['nombre_plan', 'agencia'], as_index=False)['cnt'].sum()
        pivot = df.pivot_table(index='nombre_plan', columns='agencia', values='cnt',
                               aggfunc='sum', fill_value=0)
        for ag in _AG_ORDER:
            if ag not in pivot.columns:
                pivot[ag] = 0
        pivot['TOTAL'] = pivot[list(_AG_ORDER)].sum(axis=1)
        pivot = pivot.sort_values('TOTAL', ascending=False)
        rows = [{'PLAN': name, **{c: int(row.get(c, 0)) for c in _AG_ORDER + ['TOTAL']}}
                for name, row in pivot.iterrows()]
        totals = {c: int(pivot[c].sum()) for c in _AG_ORDER + ['TOTAL']}
        return {'columns': ['PLAN'] + _AG_ORDER + ['TOTAL'], 'rows': rows, 'totals': totals}

    try:
        df_altas = get_data(f"""
            SELECT wl.[Plan] AS nombre_plan, {_raw} AS raw_agencia, COUNT(*) AS cnt
            FROM dbo.winforce_lima wl {_joins}
            WHERE wl.[Estado orden] = 'Ejecutada'
              AND MONTH({_fpa}) = :mes AND YEAR({_fpa}) = :anio
              AND {_fpa} IS NOT NULL AND wl.[Plan] IS NOT NULL AND wl.[Plan] <> ''
              {_dlw} {_da}
            GROUP BY wl.[Plan], {_raw}
        """, params=p)

        df_ventas = get_data(f"""
            SELECT wl.[Plan] AS nombre_plan, {_raw} AS raw_agencia, COUNT(*) AS cnt
            FROM dbo.winforce_lima wl {_joins}
            WHERE MONTH(wl.[Fecha de registro]) = :mes AND YEAR(wl.[Fecha de registro]) = :anio
              AND wl.[Plan] IS NOT NULL AND wl.[Plan] <> ''
              {_dlw} {_dr}
            GROUP BY wl.[Plan], {_raw}
        """, params=p)

        return {'altas': _build_pivot(df_altas), 'ventas': _build_pivot(df_ventas)}
    except Exception as e:
        print(f"Error get_pivot_planes_agencias_lima: {e}")
        return None


import sqlalchemy as _sa

_TABLE = 'dim_usuarios_Aliv'


def init_dim_usuarios_table():
    """Crea la tabla dim_usuarios_Aliv si no existe."""
    try:
        from db_config import get_engine
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(_sa.text(f"""
                IF NOT EXISTS (
                    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_NAME = '{_TABLE}'
                )
                CREATE TABLE dbo.{_TABLE} (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    vendedor NVARCHAR(100) NOT NULL,
                    nombre_aliv NVARCHAR(200) NULL,
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
                "(LOWER(COALESCE(vendedor,'')) LIKE LOWER(:search) OR LOWER(COALESCE(nombre_aliv,'')) LIKE LOWER(:search))"
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
            f"SELECT id, vendedor, nombre_aliv, cargo, agencia, supervisor, canal, estado, fecha_registro FROM {_TABLE} {where} ORDER BY cargo, agencia, vendedor",
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
        df_cargo = get_data(f"SELECT DISTINCT nombre_aliv FROM {_TABLE} WHERE cargo = 'Supervisor' AND nombre_aliv IS NOT NULL AND nombre_aliv <> ''")
        db_sups_cargo = df_cargo['nombre_aliv'].tolist() if not df_cargo.empty else []
        
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
                INSERT INTO {_TABLE} (vendedor, nombre_aliv, cargo, agencia, supervisor, canal, estado, fecha_registro)
                VALUES (:vendedor, :nombre_aliv, :cargo, :agencia, :supervisor, :canal, :estado, :fecha_registro)
            """), {
                'vendedor':        data.get('vendedor', '').title(),
                'nombre_aliv':     (data.get('nombre_aliv') or '').title() or None,
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
                SET vendedor = :vendedor, nombre_aliv = :nombre_aliv,
                    cargo = :cargo, agencia = :agencia, supervisor = :supervisor,
                    canal = :canal, estado = :estado
                WHERE id = :id
            """), {
                'id':              uid,
                'vendedor':        data.get('vendedor', '').title(),
                'nombre_aliv':     (data.get('nombre_aliv') or '').title() or None,
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


def get_localizacion_lima(mes, anio, area='', agencia_grupo=''):
    """Score, Zona KML y comparativa P2 — Lima.
    Retorna None si la columna Zona_KML no está disponible."""
    _ac = _area_clause(area)
    _dl = _dept_lima()
    _agc = _agencia_clause(agencia_grupo)

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
            {_dl} {_ac} {_agc}
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
              {_dl} {_ac} {_agc}
            GROUP BY [Zona_KML]
            ORDER BY cnt DESC
        """, params={'mes': mes, 'anio': anio})
        zonas = df_zona.to_dict(orient='records')

        _where_p2 = f"WHERE {_dl[4:]} {_ac} {_agc}" if (area or agencia_grupo) else f"WHERE {_dl[4:]}"
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
                ISNULL(u.agencia, l.[Agencia])    AS agencia,
                COUNT(*) AS anulaciones,
                ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_total
            FROM dbo.winforce_lima l
            LEFT JOIN dbo.dim_usuarios_Aliv u ON l.[Vendedor real] = u.vendedor
            WHERE l.[Estado orden] = 'Anulado'
              AND MONTH(l.[Fecha de registro]) = :mes AND YEAR(l.[Fecha de registro]) = :anio
              {_dl} {_ac}
            GROUP BY ISNULL(u.agencia, l.[Agencia])
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


def get_puntos_mapa_lima(mes, anio, area='', agencia_grupo=''):
    """Instalaciones con lat/lon para mapa interactivo — Lima y Callao.
    Latitud/Longitud son TEXT en SQL Server → TRY_CAST para conversión segura."""
    import math
    _ac = _area_clause(area)
    _dl = _dept_lima()
    _agc = _agencia_clause(agencia_grupo)
    _where = f"""
        FROM dbo.winforce_lima
        LEFT JOIN dbo.dim_usuarios_Aliv ua ON [Vendedor real] = ua.vendedor
        WHERE [Estado orden] = 'Ejecutada'
          AND MONTH({_FP}) = :mes AND YEAR({_FP}) = :anio
          AND {_FP} IS NOT NULL
          AND TRY_CAST([Latitud]  AS FLOAT) IS NOT NULL
          AND TRY_CAST([Latitud]  AS FLOAT) <> 0
          AND TRY_CAST([Longitud] AS FLOAT) IS NOT NULL
          AND TRY_CAST([Longitud] AS FLOAT) <> 0
          {_dl} {_ac} {_agc}
    """
    _base = """
        ISNULL([Distrito], 'Sin distrito')             AS distrito,
        ISNULL([Dirección de Instalación], '')         AS direccion,
        ISNULL([Dirección Geofinder], '')              AS geofinder,
        TRY_CAST([Latitud]  AS FLOAT)                  AS lat,
        TRY_CAST([Longitud] AS FLOAT)                  AS lon,
        ISNULL([Plan], '')                             AS [plan],
        ISNULL([Tipo de domicilio], '')                AS tipo,
        ISNULL([Estado orden], '')                     AS estado_orden,
        ISNULL([Condominio / Edificio], '')            AS condominio,
        ISNULL([N° doc cliente], '')                   AS doc,
        ISNULL([Telf. cliente], '')                    AS telefono,
        ISNULL(ua.agencia, '')                         AS agencia
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


def get_registros_lima(mes, anio, area='', agencia_grupo=''):
    """Registros individuales de Lima (cualquier estado, no solo Ejecutada) para
    el buscador por documento/condominio y la tabla de detalle de clientes.
    A diferencia de get_puntos_mapa_lima esto no exige lat/lon ni Estado orden
    'Ejecutada' -- por eso encuentra ventas que aún no se instalaron.
    Tope de 3000 filas más recientes (mismo criterio que get_mora_detalle)."""
    _ac = _area_clause(area)
    _dl = _dept_lima()
    _agc = _agencia_clause(agencia_grupo)
    try:
        df = get_data(f"""
            SELECT TOP 3000
                ISNULL([N° doc cliente], '')             AS doc,
                ISNULL(Cliente, '')                      AS cliente,
                ISNULL([Telf. cliente], '')               AS telefono,
                ISNULL([Fecha de registro], '')           AS fecha_registro,
                ISNULL([Fecha programación], '')          AS fecha_programacion,
                ISNULL([Estado orden], '')                AS estado_orden,
                ISNULL([Estado del Pedido], '')           AS estado_pedido,
                ISNULL([Condominio / Edificio], '')       AS condominio,
                ISNULL(Piso, '')                          AS piso,
                ISNULL([N° departamento], '')              AS departamento,
                ISNULL([Dirección de Instalación], '')    AS direccion,
                ISNULL(Distrito, '')                      AS distrito,
                ISNULL(ua.agencia, '')                    AS agencia
            FROM dbo.winforce_lima
            LEFT JOIN dbo.dim_usuarios_Aliv ua ON [Vendedor real] = ua.vendedor
            WHERE MONTH([Fecha de registro]) = :mes AND YEAR([Fecha de registro]) = :anio
            {_dl} {_ac} {_agc}
            ORDER BY [Fecha de registro] DESC
        """, params={'mes': mes, 'anio': anio})
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error get_registros_lima: {e}")
        return []


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
    Fuente de agencia: dim_usuarios_Aliv > campo Agencia de winforce."""
    _ac  = _area_clause(area)
    _fpa = "TRY_CONVERT(DATE, LEFT(wl.[Fecha programación], 10), 105)"
    _dlw = _dept_lima('wl')
    _dr  = "AND DAY(wl.[Fecha de registro]) <= :dia" if dia else ""
    _da  = f"AND DAY({_fpa}) <= :dia" if dia else ""
    # Expresión de agencia: dim_usuarios_Aliv → winforce campo
    _ag_expr = "ISNULL(d.agencia, wl.[Agencia])"
    _joins   = "LEFT JOIN dbo.dim_usuarios_Aliv d ON wl.[Vendedor real] = d.vendedor"
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
    Fuente de agencia: dim_usuarios_Aliv > campo Agencia de winforce."""
    _ac  = _area_clause(area)
    _fpa = "TRY_CONVERT(DATE, LEFT(wl.[Fecha programación], 10), 105)"
    _dlw = _dept_lima('wl')
    _dr  = "AND DAY(wl.[Fecha de registro]) <= :dia" if dia else ""
    _da  = f"AND DAY({_fpa}) <= :dia" if dia else ""
    _ag_expr = "ISNULL(d.agencia, wl.[Agencia])"
    _joins   = "LEFT JOIN dbo.dim_usuarios_Aliv d ON wl.[Vendedor real] = d.vendedor"
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
    _dr  = "AND DAY(wl.[Fecha de registro]) <= :dia" if dia else ""
    _da  = f"AND DAY({_fpa}) <= :dia" if dia else ""
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
        df_u = get_data("SELECT TOP 1 ISNULL(agencia,'') AS ag, ISNULL(supervisor,'') AS sv FROM dbo.dim_usuarios_Aliv WHERE vendedor = :v", params={'v': vr})
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


def get_prediccion_dia():
    """
    Estima ventas y altas de hoy basado en la mediana histórica
    del mismo día de la semana en las últimas ~20 semanas,
    excluyendo días atípicos (Mundial 2026, día 10 de mes = corte morosidad).
    """
    import pandas as pd
    import math
    import calendar as _cal
    from datetime import timedelta, date as _date

    hoy      = datetime.now()
    hoy_date = hoy.date()
    diaw     = hoy.weekday()  # 0=Lun … 6=Dom
    desde    = (hoy - timedelta(days=180)).strftime('%Y-%m-%d')  # más histórico para compensar filtros
    VERT     = {'Condominio/Edificio'}
    NOMBRES  = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']

    # Días atípicos a excluir del histórico y que generan advertencia si son hoy
    MUNDIAL_INICIO = _date(2026, 6, 11)
    MUNDIAL_FIN    = _date(2026, 7, 19)

    def _es_dia_atipico(d):
        dt = d.date() if hasattr(d, 'date') else d
        # Mundial FIFA 2026
        if MUNDIAL_INICIO <= dt <= MUNDIAL_FIN:
            return True
        # Día 10 de cada mes: corte de registro de morosidad
        if dt.day == 10:
            return True
        return False

    advertencias = []
    if MUNDIAL_INICIO <= hoy_date <= MUNDIAL_FIN:
        advertencias.append('mundial')
    if hoy_date.day == 10:
        advertencias.append('fin_mes')

    def _query_tabla(tabla, tipo):
        """Devuelve DataFrame con columnas [fecha, tipo_dom] para altas o ventas."""
        if tipo == 'altas':
            sql = f"""
                SELECT TRY_CONVERT(DATE, LEFT([Fecha programación], 10), 105) AS fecha,
                       [Tipo de domicilio] AS tipo_dom
                FROM dbo.{tabla}
                WHERE [Estado orden] = 'Ejecutada'
                  AND TRY_CONVERT(DATE, LEFT([Fecha programación], 10), 105) >= :desde
                  AND TRY_CONVERT(DATE, LEFT([Fecha programación], 10), 105) < CAST(GETDATE() AS DATE)
            """
        else:
            sql = f"""
                SELECT CAST([Fecha de registro] AS DATE) AS fecha,
                       [Tipo de domicilio] AS tipo_dom
                FROM dbo.{tabla}
                WHERE [Plan] IS NOT NULL AND [Plan] <> ''
                  AND CAST([Fecha de registro] AS DATE) >= :desde
                  AND CAST([Fecha de registro] AS DATE) < CAST(GETDATE() AS DATE)
            """
        try:
            return get_data(sql, params={'desde': desde})
        except Exception:
            return None

    def _query_hoy(tipo):
        """Cuenta altas o ventas de hoy en la tabla actual (winforce_lima 2026)."""
        if tipo == 'altas':
            sql = """
                SELECT [Tipo de domicilio] AS tipo_dom
                FROM dbo.winforce_lima
                WHERE [Estado orden] = 'Ejecutada'
                  AND TRY_CONVERT(DATE, LEFT([Fecha programación], 10), 105) = CAST(GETDATE() AS DATE)
            """
        else:
            sql = """
                SELECT [Tipo de domicilio] AS tipo_dom
                FROM dbo.winforce_lima
                WHERE [Plan] IS NOT NULL AND [Plan] <> ''
                  AND CAST([Fecha de registro] AS DATE) = CAST(GETDATE() AS DATE)
            """
        try:
            return get_data(sql)
        except Exception:
            return None

    def _count_hoy(df):
        if df is None or df.empty:
            return {'total': 0, 'vertical': 0, 'horizontal': 0}
        df = df.copy()
        df['es_vert'] = df['tipo_dom'].isin(VERT)
        total = len(df)
        vert  = int(df['es_vert'].sum())
        return {'total': total, 'vertical': vert, 'horizontal': total - vert}

    def _stats(dfs):
        """Mediana de días normales (excluye mundial y corte morosidad) para el mismo día de semana."""
        zero = {'total': 0, 'vertical': 0, 'horizontal': 0, 'n': 0,
                'total_lo': 0, 'total_hi': 0, 'vert_lo': 0, 'vert_hi': 0,
                'horiz_lo': 0, 'horiz_hi': 0}
        frames = [df for df in dfs if df is not None and not df.empty]
        if not frames:
            return zero
        df = pd.concat(frames, ignore_index=True)
        df['fecha']   = pd.to_datetime(df['fecha'])
        df['es_vert'] = df['tipo_dom'].isin(VERT)

        daily = df.groupby('fecha').agg(
            total   =('es_vert', 'count'),
            vertical=('es_vert', 'sum'),
        ).reset_index()
        daily['horizontal'] = daily['total'] - daily['vertical']

        same = daily[daily['fecha'].dt.weekday == diaw].sort_values('fecha').tail(20)
        # Excluir días atípicos del histórico
        same = same[~same['fecha'].apply(_es_dia_atipico)].tail(12)
        n = len(same)
        if n == 0:
            return zero

        def _est(col):
            v = same[col].values.astype(float)
            m = float(pd.Series(v).median())   # mediana: más robusta que la media
            s = float(v.std(ddof=1)) if n > 1 else 0.0
            return int(round(m)), int(max(0, math.floor(m - s))), int(math.ceil(m + s))

        tm, tlo, thi = _est('total')
        vm, vlo, vhi = _est('vertical')
        hm, hlo, hhi = _est('horizontal')
        return {'total': tm, 'total_lo': tlo, 'total_hi': thi,
                'vertical': vm, 'vert_lo': vlo, 'vert_hi': vhi,
                'horizontal': hm, 'horiz_lo': hlo, 'horiz_hi': hhi, 'n': n}

    try:
        pa = _stats([_query_tabla('winforce_lima', 'altas'),
                     _query_tabla('winforce_lima_2025', 'altas')])
        pv = _stats([_query_tabla('winforce_lima', 'ventas'),
                     _query_tabla('winforce_lima_2025', 'ventas')])
        ah = _count_hoy(_query_hoy('altas'))
        vh = _count_hoy(_query_hoy('ventas'))
        return {
            'dia_nombre':  NOMBRES[diaw],
            'n_muestras':  pa['n'],
            'altas':       pa,
            'ventas':      pv,
            'altas_hoy':   ah,
            'ventas_hoy':  vh,
            'advertencias': advertencias,
        }
    except Exception as e:
        print(f"Error get_prediccion_dia: {e}")
        return None
