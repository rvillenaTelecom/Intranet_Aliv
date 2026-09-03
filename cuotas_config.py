"""
cuotas_config.py
========================
Fuente única de cuotas mensuales (metas de altas asignadas por WIN a Aliv).

Vive en Azure SQL (tabla dbo.cuotas_lima), no en este archivo -- así Render,
tu PC local y el Pipeline leen/escriben la misma fuente real, sin depender
de un archivo que se reescribía en disco y se perdía en cada deploy de Render.

Usa el mismo patrón de conexión que Intranet/db_config.py y
Pipeline/scripts/Carga_SQL.py: Azure SQL (pymssql) si hay credenciales en
el entorno, si no SQL Server local (pyodbc).

Uso desde otro archivo (Intranet/ o Pipeline/scripts/):
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from cuotas_config import cuota_lima, cuota_definida, set_cuota_lima
"""

import os
import time
import urllib
import sqlalchemy as sa

_engine = None
_cache = None
_cache_ts = 0
_CACHE_TTL = 60  # segundos


def _get_engine():
    global _engine
    if _engine is not None:
        return _engine

    azure_server = os.environ.get('AZURE_SQL_SERVER')
    if azure_server:
        azure_db   = os.environ.get('AZURE_SQL_DATABASE', 'Aliv_DB')
        azure_user = os.environ.get('AZURE_SQL_USER')
        azure_pass = os.environ.get('AZURE_SQL_PASSWORD')
        conn_str = (
            f"mssql+pymssql://{urllib.parse.quote_plus(azure_user)}:{urllib.parse.quote_plus(azure_pass)}"
            f"@{azure_server}:1433/{azure_db}"
        )
        _engine = sa.create_engine(conn_str)
        return _engine

    SERVER = r'.\SQLEXPRESS'
    DATABASE = 'Aliv_DB'
    connection_string = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={SERVER};"
        f"DATABASE={DATABASE};"
        f"Trusted_Connection=yes;"
    )
    params = urllib.parse.quote_plus(connection_string)
    _engine = sa.create_engine(f"mssql+pyodbc:///?odbc_connect={params}", fast_executemany=True)
    return _engine


def _init_tabla():
    engine = _get_engine()
    insp = sa.inspect(engine)
    if not insp.has_table('cuotas_lima', schema='dbo'):
        with engine.begin() as conn:
            conn.execute(sa.text("""
                CREATE TABLE dbo.cuotas_lima (
                    mes  INT NOT NULL,
                    area NVARCHAR(20) NOT NULL,
                    cuota INT NOT NULL,
                    PRIMARY KEY (mes, area)
                )
            """))


def _cargar():
    """Dict {(mes, area): cuota} de todas las cuotas, con cache de 60s en memoria
    (evita una consulta a SQL en cada llamada dentro de un mismo proceso)."""
    global _cache, _cache_ts
    if _cache is not None and time.time() - _cache_ts < _CACHE_TTL:
        return _cache
    try:
        _init_tabla()
        engine = _get_engine()
        with engine.connect() as conn:
            rows = conn.execute(sa.text("SELECT mes, area, cuota FROM dbo.cuotas_lima")).fetchall()
        _cache = {(int(r[0]), r[1]): int(r[2]) for r in rows}
        _cache_ts = time.time()
    except Exception as e:
        print(f"[cuotas_config] Error cargando cuotas de SQL: {e}")
        _cache = _cache or {}
    return _cache


def cuota_lima(mes, area=''):
    return _cargar().get((int(mes), area), 0)


def cuota_definida(mes):
    return (int(mes), '') in _cargar()


def set_cuota_lima(mes, vertical, horizontal_aliv, horizontal_sub, horizontal_win=None):
    """Define/actualiza la cuota de Lima de un mes en SQL: Vertical, y
    Horizontal repartido entre Aliv y Subagencias (el reparto entre canales
    se define a mano acá, porque cambia mes a mes -- ej. 40/60 un mes, otro
    reparto el siguiente, y no siempre suma igual al total real de WIN).

    horizontal_win es la cuota de Horizontal tal cual la entrega WIN (un solo
    total combinado, sin repartir) -- se usa para el total/alcance a nivel
    ejecutivo/gerencial, en vez de la suma aliv+sub, porque esa suma es un
    reparto interno que puede no cuadrar con el número real de WIN. Si no se
    especifica, cae por defecto a aliv+sub (compatibilidad con meses viejos)."""
    global _cache
    mes = int(mes)
    if not 1 <= mes <= 12:
        raise ValueError("Mes fuera de rango (1-12)")
    vertical = max(int(vertical), 0)
    horizontal_aliv = max(int(horizontal_aliv), 0)
    horizontal_sub = max(int(horizontal_sub), 0)
    horizontal = horizontal_aliv + horizontal_sub
    horizontal_win = horizontal if horizontal_win is None else max(int(horizontal_win), 0)
    total = vertical + horizontal_win

    _init_tabla()
    engine = _get_engine()
    with engine.begin() as conn:
        for area, valor in (
            ('', total),
            ('Vertical', vertical),
            ('Horizontal', horizontal),
            ('Horizontal_Aliv', horizontal_aliv),
            ('Horizontal_Sub', horizontal_sub),
            ('Horizontal_Win', horizontal_win),
        ):
            conn.execute(sa.text("""
                MERGE dbo.cuotas_lima AS t
                USING (SELECT :mes AS mes, :area AS area, :cuota AS cuota) AS s
                ON t.mes = s.mes AND t.area = s.area
                WHEN MATCHED THEN UPDATE SET cuota = s.cuota
                WHEN NOT MATCHED THEN INSERT (mes, area, cuota) VALUES (s.mes, s.area, s.cuota);
            """), {"mes": mes, "area": area, "cuota": valor})

    _cache = None  # forzar recarga en la próxima lectura
    return {
        'mes': mes, 'vertical': vertical, 'horizontal': horizontal,
        'horizontal_aliv': horizontal_aliv, 'horizontal_sub': horizontal_sub,
        'horizontal_win': horizontal_win, 'total': total,
    }
