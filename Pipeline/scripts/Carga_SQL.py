"""
Carga_SQL.py
======================
Módulo compartido de conexión a base de datos y carga de DataFrames.
  - Azure SQL (aliv-server-2, via pymssql) si AZURE_SQL_SERVER está en .env — base "en línea", la que lee Render.
  - Si no, SQL Server Express local (.\\SQLEXPRESS / Aliv_DB) — respaldo para pruebas sin internet.

Además, cuando SÍ hay Azure configurado, upload_to_sql/upload_incremental_to_sql
suben también una copia a SQL Server local -- respaldo para casos de emergencia
(ej. Azure free-tier pausada o sin internet). Esa segunda subida es best-effort:
si el local no está disponible, se avisa por consola pero no frena el pipeline
ni afecta el resultado (lo único crítico es Azure, la base que lee Render/Intranet).

Funciones disponibles:
  get_engine()                          → motor SQLAlchemy listo para usar (Azure si hay credenciales, si no local)
  upload_to_sql(df, tabla)              → reemplaza toda la tabla (Azure + respaldo local)
  upload_incremental_to_sql(df, tabla, col_fecha) → borra desde la fecha mínima del df y re-inserta (Azure + respaldo local)
"""

from dotenv import load_dotenv
import os
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

import sqlalchemy as sa
import pandas as pd
import urllib


def _get_azure_engine():
    azure_server = os.environ.get('AZURE_SQL_SERVER')
    if not azure_server:
        return None
    azure_db   = os.environ.get('AZURE_SQL_DATABASE', 'Aliv_DB')
    azure_user = os.environ.get('AZURE_SQL_USER')
    azure_pass = os.environ.get('AZURE_SQL_PASSWORD')
    conn_str = (
        f"mssql+pymssql://{urllib.parse.quote_plus(azure_user)}:{urllib.parse.quote_plus(azure_pass)}"
        f"@{azure_server}:1433/{azure_db}"
    )
    return sa.create_engine(conn_str)


def _get_local_engine():
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


def get_engine():
    """Crea el motor de conexión a SQL Server (Azure si hay credenciales en .env, si no local)."""
    return _get_azure_engine() or _get_local_engine()


def _replace_upload(engine, df, table_name, if_exists, label):
    """Sube df a `engine`, reemplazando la tabla si if_exists='replace'. Devuelve True/False.

    Si la tabla ya existe y sus columnas coinciden con el DataFrame, se vacía con
    TRUNCATE en vez de DROP+recrear -- así se conservan los tipos de columna e
    índices definidos a mano (ver winforce_lima: columnas VARCHAR(MAX) acotadas
    + índices agregados para que el dashboard no haga table scans -- un DROP
    los perdería, porque to_sql recrea la tabla con tipos auto-inferidos y sin
    índices). Si las columnas no coinciden (cambió el formato de origen), cae
    de vuelta a DROP+recrear como antes."""
    try:
        nombre = table_name
        insp = sa.inspect(engine)
        if if_exists == 'replace' and insp.has_table(nombre, schema='dbo'):
            cols_tabla = {c['name'] for c in insp.get_columns(nombre, schema='dbo')}
            if cols_tabla == set(df.columns):
                with engine.begin() as conn:
                    conn.execute(sa.text(f"TRUNCATE TABLE [dbo].[{nombre}]"))
            else:
                print(f"  [DB {label}] Columnas de '{nombre}' cambiaron -- se recrea la tabla "
                      f"(se pierden tipos/índices definidos a mano).")
                with engine.begin() as conn:
                    conn.execute(sa.text(f"DROP TABLE [dbo].[{nombre}]"))
        df.to_sql(nombre, engine, index=False, if_exists='append', schema='dbo')
        print(f"  [DB {label}] Carga exitosa en: {nombre} ({len(df)} registros)")
        return True
    except Exception as e:
        print(f"  [DB {label}] ERROR upload_to_sql({table_name}): {e}")
        return False


def upload_to_sql(df, table_name, if_exists='replace'):
    """Sube un DataFrame a SQL Server. Si hay Azure configurado, sube ahí (destino
    principal) y además intenta un respaldo en SQL local para emergencias -- ese
    respaldo es best-effort y no afecta el resultado devuelto."""
    azure_engine = _get_azure_engine()
    if azure_engine is not None:
        ok = _replace_upload(azure_engine, df, table_name, if_exists, label='Azure')
        _replace_upload(_get_local_engine(), df, table_name, if_exists, label='Local-respaldo')
        return ok
    return _replace_upload(_get_local_engine(), df, table_name, if_exists, label='Local')


def _incremental_upload(engine, df, table_name, date_col, days, start_date, label):
    """
    Carga incremental en `engine`: borra desde start_date y re-inserta. Devuelve True/False.

    IMPORTANTE: date_col se guarda como texto, no como columna de tipo fecha,
    y el formato varia segun la tabla -- 'dd-mm-yyyy' en los reportes de Aliv
    (ventas_aliv/ventas_referidos), 'yyyy-mm-dd[ hh:mi:ss]' en winforce_lima.
    El DELETE prueba ambos formatos (TRY_CONVERT con estilo 105 y 120) antes
    de comparar, porque una comparacion de texto plano -- o asumir un solo
    formato -- puede borrar de mas, o (como paso una vez) no borrar nada y
    dejar filas duplicadas.
    """
    try:
        if start_date is not None:
            if hasattr(start_date, 'strftime'):
                fecha_inicio = start_date.strftime('%Y-%m-%d')
            else:
                fecha_inicio = str(start_date)
            print(f"  [DB {label}] Usando fecha de inicio explícita: {fecha_inicio}")
        else:
            df_temp = df.copy()
            df_temp[date_col] = pd.to_datetime(df_temp[date_col], dayfirst=True, errors='coerce')
            fecha_minima = df_temp[date_col].min()

            if pd.isna(fecha_minima):
                from datetime import datetime, timedelta
                dias_atras = days if days is not None else 7
                fecha_inicio = (datetime.now() - timedelta(days=dias_atras)).strftime('%Y-%m-%d')
                print(f"  [DB {label}] AVISO: sin fechas en '{date_col}'. Usando: {fecha_inicio}")
            else:
                fecha_inicio = fecha_minima.strftime('%Y-%m-%d')

        nombre = table_name
        tabla_del = f'[dbo].[{nombre}]'
        if not sa.inspect(engine).has_table(nombre, schema='dbo'):
            # Primera vez que esta tabla existe en este motor (típico del respaldo
            # local recién estrenado) -- no hay nada que borrar, solo insertar.
            print(f"  [DB {label}] '{nombre}' no existe todavía -- se crea con esta carga.")
        else:
            with engine.begin() as conn:
                col_q = f'[{date_col}]'
                antes = conn.execute(sa.text(f"SELECT COUNT(*) FROM {tabla_del}")).scalar()
                # COALESCE de dos formatos conocidos: 105=dd-mm-yyyy (Aliv), 120=yyyy-mm-dd[ hh:mi:ss] (Winforce).
                # Si ninguno matchea (formato desconocido), TRY_CONVERT da NULL en ambos y no se borra nada --
                # se avisa explicitamente abajo en vez de fallar en silencio otra vez.
                conn.execute(sa.text(
                    f"DELETE FROM {tabla_del} WHERE "
                    f"COALESCE(TRY_CONVERT(date, {col_q}, 105), TRY_CONVERT(date, {col_q}, 120)) >= :fecha"
                ), {"fecha": fecha_inicio})
                despues = conn.execute(sa.text(f"SELECT COUNT(*) FROM {tabla_del}")).scalar()
                borradas = antes - despues
                print(f"  [DB {label}] Limpieza incremental desde {fecha_inicio} en {tabla_del}: "
                      f"{antes} -> {despues} filas ({borradas} borradas)")
                if borradas == 0 and antes > 0:
                    print(f"  [DB {label}] AVISO: no se borro ninguna fila. Si esperabas reemplazar datos existentes, "
                          f"revisa el formato real de '{date_col}' -- puede estar duplicando filas.")
        df.to_sql(nombre, engine, index=False, if_exists='append', schema='dbo')
        print(f"  [DB {label}] Carga incremental exitosa ({len(df)} registros).")
        return True
    except Exception as e:
        print(f"  [DB {label}] ERROR upload_incremental_to_sql({table_name}): {e}")
        return False


def upload_incremental_to_sql(df, table_name, date_col, days=None, start_date=None):
    """Carga incremental. Si hay Azure configurado, sube ahí (destino principal) y
    además intenta el mismo incremental en SQL local para emergencias -- ese
    respaldo es best-effort y no afecta el resultado devuelto."""
    azure_engine = _get_azure_engine()
    if azure_engine is not None:
        ok = _incremental_upload(azure_engine, df, table_name, date_col, days, start_date, label='Azure')
        _incremental_upload(_get_local_engine(), df, table_name, date_col, days, start_date, label='Local-respaldo')
        return ok
    return _incremental_upload(_get_local_engine(), df, table_name, date_col, days, start_date, label='Local')
