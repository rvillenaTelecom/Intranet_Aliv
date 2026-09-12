import os
import threading
import pymssql  # carga el driver real una sola vez, antes que exista concurrencia --
                  # el dialecto de SQLAlchemy lo importa perezosamente, y si varios hilos
                  # disparan esa primera carga a la vez (justo al arrancar un worker nuevo,
                  # con el ThreadPoolExecutor de dashboard_ventas/reporte_gerente) queda a
                  # medio inicializar y truena "circular import"
import sqlalchemy as sa
import sqlalchemy.dialects.mssql  # mismo motivo, un nivel mas arriba (el dialecto en si)
import pandas as pd
import urllib

_engine = None
_connect_lock = threading.Lock()  # ver _serializar_conexiones() mas abajo


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
        if '.database.windows.net' not in azure_server and not azure_server.endswith('.net'):
            azure_server = f"{azure_server}.database.windows.net"
        azure_db   = os.environ.get('AZURE_SQL_DATABASE', 'Aliv_DB')
        azure_user = os.environ.get('AZURE_SQL_USER')
        azure_pass = os.environ.get('AZURE_SQL_PASSWORD')
        conn_str = (
            f"mssql+pymssql://{urllib.parse.quote_plus(azure_user)}:{urllib.parse.quote_plus(azure_pass)}"
            f"@{azure_server}:1433/{azure_db}"
        )
        _engine = sa.create_engine(
            conn_str,
            pool_size=8,
            max_overflow=8,       # subido de 5+5 -- con varios usuarios reales a la vez, cada
                                   # carga de dashboard pide 2 conexiones (ThreadPoolExecutor) y
                                   # el pool se llenaba rapido ("QueuePool limit... reached").
                                   # Sigue acotado para no volver al extremo de 60 de antes.
            pool_pre_ping=True,   # descarta conexiones muertas del pool antes de usarlas
            pool_recycle=280,     # recicla conexiones antes de que Azure las cierre por inactividad
            connect_args={'timeout': 30, 'login_timeout': 15},  # pymssql: query / conexión, en segundos
                                   # -- la base es Standard (Provisioned), no se auto-pausa,
                                   # asi que no hace falta un login_timeout largo
        )

        @sa.event.listens_for(_engine, "do_connect")
        def _serializar_conexiones(dialect, conn_rec, cargs, cparams):
            # pymssql (via FreeTDS) no es seguro para abrir dos conexiones NUEVAS
            # a la vez desde hilos distintos -- se vio en producción el
            # 2026-09-12: con 2 hilos pidiendo su primera conexión al mismo
            # tiempo (dashboard_ventas/reporte_gerente arrancan con
            # ThreadPoolExecutor), UNA se conectaba bien y la otra se quedaba
            # colgada para siempre (ni error ni éxito, sin usar DTU). Esto
            # serializa solo el hand-shake de conexión (con el candado); una
            # vez que una conexión ya está abierta y en el pool, reusarla o
            # ejecutar consultas en paralelo sobre conexiones distintas sigue
            # funcionando normal, no pasa por acá.
            with _connect_lock:
                return pymssql.connect(*cargs, **cparams)

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
