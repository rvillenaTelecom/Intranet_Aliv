import sqlalchemy as sa
import pandas as pd
import urllib

_engine = None


def get_engine():
    """Crea (o reutiliza) el motor de conexión a SQL Server local."""
    global _engine
    if _engine is not None:
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


def get_data(query, params=None):
    """Ejecuta una consulta SQL Server y devuelve un DataFrame."""
    engine = get_engine()
    if params is not None:
        return pd.read_sql(sa.text(query), engine, params=params)
    else:
        return pd.read_sql(sa.text(query), engine)
