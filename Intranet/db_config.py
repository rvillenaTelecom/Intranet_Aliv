import sqlalchemy as sa
import pandas as pd
import urllib
import os

# CONFIGURACIÓN
# Si estamos en Render, usaremos la variable de entorno DATABASE_URL
# Si estamos local, usaremos SQLEXPRESS
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_engine():
    """Crea un motor de conexión automático (Local o Nube)."""
    if DATABASE_URL:
        # CONEXIÓN NUBE (PostgreSQL)
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return sa.create_engine(url)
    else:
        # CONEXIÓN LOCAL (SQL Server)
        SERVER = r'.\SQLEXPRESS'
        DATABASE = 'Aliv_DB'
        connection_string = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={SERVER};"
            f"DATABASE={DATABASE};"
            f"Trusted_Connection=yes;"
        )
        params = urllib.parse.quote_plus(connection_string)
        return sa.create_engine(f"mssql+pyodbc:///?odbc_connect={params}", fast_executemany=True)

def get_data(query, params=None):
    """Ejecuta una consulta y devuelve un DataFrame."""
    engine = get_engine()
    if params is not None:
        return pd.read_sql(sa.text(query), engine, params=params)
    else:
        if isinstance(query, str):
            return pd.read_sql(sa.text(query), engine)
        return pd.read_sql(query, engine)

