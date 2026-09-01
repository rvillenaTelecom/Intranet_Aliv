import os
import sqlalchemy as sa
import pandas as pd
import urllib

_engine = None


def get_engine():
    """Crea (o reutiliza) el motor de conexión a SQL Server.

    Si están definidas AZURE_SQL_SERVER/AZURE_SQL_USER/AZURE_SQL_PASSWORD usa
    Azure SQL vía pymssql (driver puro, sin dependencias del sistema — necesario
    porque Render no permite instalar "ODBC Driver 17 for SQL Server"). Si no,
    usa el SQL Server Express local con autenticación de Windows (comportamiento
    de siempre para desarrollo/Pipeline en la máquina local).
    """
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


def get_data(query, params=None):
    """Ejecuta una consulta SQL Server y devuelve un DataFrame."""
    engine = get_engine()
    if params is not None:
        return pd.read_sql(sa.text(query), engine, params=params)
    else:
        return pd.read_sql(sa.text(query), engine)
