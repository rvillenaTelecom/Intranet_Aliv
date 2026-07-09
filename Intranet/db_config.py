import sqlalchemy as sa
import pandas as pd
import urllib
import os
import re as _re_sql

DATABASE_URL = os.environ.get('DATABASE_URL')

_engine = None


def get_engine():
    """Crea (o reutiliza) el motor de conexión automático (Local o Nube)."""
    global _engine
    if _engine is not None:
        return _engine
    if DATABASE_URL:
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        _engine = sa.create_engine(url, pool_size=10, max_overflow=5, pool_pre_ping=True)
    else:
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


# ─── SQL DIALECT ADAPTER (SQL Server → PostgreSQL) ───────────────────────────

def _is_pg():
    return bool(DATABASE_URL)


def _extract_sql_arg(sql, pos):
    """Extrae un argumento SQL respetando paréntesis anidados y strings."""
    depth = 0
    i = pos
    while i < len(sql):
        c = sql[i]
        if c == "'":
            i += 1
            while i < len(sql):
                if sql[i] == "'" and (i + 1 >= len(sql) or sql[i + 1] != "'"):
                    break
                if sql[i] == "'" and i + 1 < len(sql) and sql[i + 1] == "'":
                    i += 2
                    continue
                i += 1
        elif c == '(':
            depth += 1
        elif c == ')':
            if depth == 0:
                break
            depth -= 1
        elif c == ',' and depth == 0:
            break
        i += 1
    return sql[pos:i].strip(), i


def _replace_sql_func1(sql, func_name, repl_fn):
    """Reemplaza func_name(arg) usando repl_fn — respeta paréntesis anidados."""
    result = []
    pat = _re_sql.compile(r'\b' + func_name + r'\s*\(', _re_sql.IGNORECASE)
    i = 0
    while i < len(sql):
        m = pat.search(sql, i)
        if not m:
            result.append(sql[i:])
            break
        result.append(sql[i:m.start()])
        pos = m.end()
        arg, end = _extract_sql_arg(sql, pos)
        if end < len(sql) and sql[end] == ')':
            end += 1
        result.append(repl_fn(arg))
        i = end
    return ''.join(result)


def _replace_datediff_pg(sql):
    """Reemplaza DATEDIFF(DAY, a, b) → (b::DATE - a::DATE), con soporte de parens anidados."""
    result = []
    i = 0
    pat = _re_sql.compile(r'\bDATEDIFF\s*\(\s*DAY\s*,\s*', _re_sql.IGNORECASE)
    while i < len(sql):
        m = pat.search(sql, i)
        if not m:
            result.append(sql[i:])
            break
        result.append(sql[i:m.start()])
        pos = m.end()
        a, pos = _extract_sql_arg(sql, pos)
        if pos < len(sql) and sql[pos] == ',':
            pos += 1
        while pos < len(sql) and sql[pos] in ' \t\n':
            pos += 1
        b, pos = _extract_sql_arg(sql, pos)
        if pos < len(sql) and sql[pos] == ')':
            pos += 1
        result.append(f'({b.strip()}::DATE - {a.strip()}::DATE)')
        i = pos
    return ''.join(result)


def _adapt_sql(query):
    """Convierte sintaxis SQL Server → PostgreSQL cuando DATABASE_URL está configurado."""
    if not _is_pg():
        return query
    sql = str(query)

    # 1. Eliminar prefijo dbo.
    sql = _re_sql.sub(r'\bdbo\.', '', sql)

    # 2. [nombre columna] → "nombre columna" (en minúsculas para PostgreSQL)
    sql = _re_sql.sub(r'\[([^\]]+)\]', lambda m: f'"{m.group(1).lower()}"', sql)

    # 3. ISNULL → COALESCE
    sql = _re_sql.sub(r'\bISNULL\s*\(', 'COALESCE(', sql)

    # 4. TRY_CONVERT(DATE, LEFT(col, 10), 105) → TO_DATE seguro con regex
    sql = _re_sql.sub(
        r'\bTRY_CONVERT\s*\(\s*DATE\s*,\s*(LEFT\s*\([^)]+\))\s*,\s*105\s*\)',
        lambda m: (
            f"(CASE WHEN {m.group(1)} ~ '^[0-9]{{2}}-[0-9]{{2}}-[0-9]{{4}}'"
            f" THEN TO_DATE({m.group(1)}, 'DD-MM-YYYY') ELSE NULL END)"
        ),
        sql
    )

    # 5. TRY_CAST(x AS FLOAT) → safe cast
    sql = _re_sql.sub(
        r'\bTRY_CAST\s*\((.+?)\s+AS\s+FLOAT\)',
        lambda m: (
            f"(CASE WHEN TRIM(({m.group(1)})::text)"
            f" ~ '^-?[0-9]+([.][0-9]+)?(e[+-]?[0-9]+)?$'"
            f" THEN ({m.group(1)})::text::FLOAT8 ELSE NULL END)"
        ),
        sql
    )

    # 6. TRY_CONVERT(FLOAT, x) → safe cast
    sql = _re_sql.sub(
        r'\bTRY_CONVERT\s*\(\s*FLOAT\s*,\s*(.+?)\)',
        lambda m: (
            f"(CASE WHEN TRIM(({m.group(1)})::text)"
            f" ~ '^-?[0-9]+([.][0-9]+)?(e[+-]?[0-9]+)?$'"
            f" THEN ({m.group(1)})::text::FLOAT8 ELSE NULL END)"
        ),
        sql
    )

    # 7. CONVERT(VARCHAR(n), col, 103) → TO_CHAR con formato DD/MM/YYYY
    sql = _re_sql.sub(
        r'\bCONVERT\s*\(\s*VARCHAR\s*\([^)]+\)\s*,\s*(.+?),\s*103\s*\)',
        lambda m: f"TO_CHAR(({m.group(1).strip()})::DATE, 'DD/MM/YYYY')",
        sql
    )

    # 8. DATEDIFF(DAY, a, b) → (b::DATE - a::DATE)
    sql = _replace_datediff_pg(sql)

    # 9. DATEFROMPARTS(y, m, d) → MAKE_DATE(y, m, d)
    sql = _re_sql.sub(r'\bDATEFROMPARTS\b', 'MAKE_DATE', sql, flags=_re_sql.IGNORECASE)

    # 10. MONTH(x) → EXTRACT(MONTH FROM (x)::DATE)::int
    sql = _replace_sql_func1(sql, 'MONTH', lambda a: f'EXTRACT(MONTH FROM ({a})::DATE)::int')

    # 11. YEAR(x) → EXTRACT(YEAR FROM (x)::DATE)::int
    sql = _replace_sql_func1(sql, 'YEAR', lambda a: f'EXTRACT(YEAR  FROM ({a})::DATE)::int')

    # 12. DAY(x) → EXTRACT(DAY FROM (x)::DATE)::int
    sql = _replace_sql_func1(sql, 'DAY', lambda a: f'EXTRACT(DAY   FROM ({a})::DATE)::int')

    # 13. CHARINDEX(' ', col + ' ') → POSITION(' ' IN col || ' ')
    sql = _re_sql.sub(
        r"\bCHARINDEX\s*\(\s*' '\s*,\s*(.+?)\s*\+\s*' '\s*\)",
        lambda m: f"POSITION(' ' IN ({m.group(1).strip()}) || ' ')",
        sql
    )

    # 14. SELECT TOP N → SELECT ... LIMIT N
    limits = []

    def _top_repl(m):
        limits.append(m.group(1))
        return 'SELECT '

    sql = _re_sql.sub(r'\bSELECT\s+TOP\s+(\d+)\s+', _top_repl, sql, flags=_re_sql.IGNORECASE)
    if limits:
        sql = sql.rstrip().rstrip(';') + f'\nLIMIT {limits[-1]}'

    return sql


# ─── ACCESO A DATOS ───────────────────────────────────────────────────────────

def get_data(query, params=None):
    """Ejecuta una consulta adaptada al dialecto activo y devuelve un DataFrame."""
    engine = get_engine()
    adapted = _adapt_sql(query)
    if params is not None:
        return pd.read_sql(sa.text(adapted), engine, params=params)
    else:
        return pd.read_sql(sa.text(adapted), engine)
