"""
Carga_SQL.py
======================
Módulo compartido de conexión a base de datos y carga de DataFrames.
  - Azure SQL (aliv-server-2, via pymssql) si AZURE_SQL_SERVER está en .env — base "en línea", la que lee Render.
  - Si no, SQL Server Express local (.\\SQLEXPRESS / Aliv_DB) — respaldo para pruebas sin internet.

Funciones disponibles:
  get_engine()                          → motor SQLAlchemy listo para usar
  upload_to_sql(df, tabla)              → reemplaza toda la tabla
  upload_incremental_to_sql(df, tabla, col_fecha) → borra desde la fecha mínima del df y re-inserta
"""

from dotenv import load_dotenv
import os
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

import sqlalchemy as sa
import pandas as pd
import urllib


def get_engine():
    """Crea el motor de conexión a SQL Server (Azure si hay credenciales en .env, si no local)."""
    azure_server = os.environ.get('AZURE_SQL_SERVER')
    if azure_server:
        azure_db   = os.environ.get('AZURE_SQL_DATABASE', 'Aliv_DB')
        azure_user = os.environ.get('AZURE_SQL_USER')
        azure_pass = os.environ.get('AZURE_SQL_PASSWORD')
        conn_str = (
            f"mssql+pymssql://{urllib.parse.quote_plus(azure_user)}:{urllib.parse.quote_plus(azure_pass)}"
            f"@{azure_server}:1433/{azure_db}"
        )
        return sa.create_engine(conn_str)

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


def upload_to_sql(df, table_name, if_exists='replace'):
    """Sube un DataFrame a SQL Server local."""
    try:
        engine = get_engine()
        nombre = table_name
        insp = sa.inspect(engine)
        if if_exists == 'replace':
            if insp.has_table(nombre, schema='dbo'):
                with engine.begin() as conn:
                    conn.execute(sa.text(f"DROP TABLE [dbo].[{nombre}]"))
        df.to_sql(nombre, engine, index=False, if_exists='append', schema='dbo')
        print(f"  [DB] Carga exitosa en: {nombre} ({len(df)} registros)")
        return True
    except Exception as e:
        print(f"  [DB] ERROR upload_to_sql({table_name}): {e}")
        return False


def upload_incremental_to_sql(df, table_name, date_col, days=None, start_date=None):
    """
    Carga incremental: borra desde start_date y re-inserta.

    IMPORTANTE: date_col se guarda como texto, no como columna de tipo fecha,
    y el formato varia segun la tabla -- 'dd-mm-yyyy' en los reportes de Aliv
    (ventas_aliv/ventas_referidos), 'yyyy-mm-dd[ hh:mi:ss]' en winforce_lima.
    El DELETE prueba ambos formatos (TRY_CONVERT con estilo 105 y 120) antes
    de comparar, porque una comparacion de texto plano -- o asumir un solo
    formato -- puede borrar de mas, o (como paso una vez) no borrar nada y
    dejar filas duplicadas.
    """
    try:
        engine = get_engine()

        if start_date is not None:
            if hasattr(start_date, 'strftime'):
                fecha_inicio = start_date.strftime('%Y-%m-%d')
            else:
                fecha_inicio = str(start_date)
            print(f"  [DB] Usando fecha de inicio explícita: {fecha_inicio}")
        else:
            df_temp = df.copy()
            df_temp[date_col] = pd.to_datetime(df_temp[date_col], dayfirst=True, errors='coerce')
            fecha_minima = df_temp[date_col].min()

            if pd.isna(fecha_minima):
                from datetime import datetime, timedelta
                dias_atras = days if days is not None else 7
                fecha_inicio = (datetime.now() - timedelta(days=dias_atras)).strftime('%Y-%m-%d')
                print(f"  [DB] AVISO: sin fechas en '{date_col}'. Usando: {fecha_inicio}")
            else:
                fecha_inicio = fecha_minima.strftime('%Y-%m-%d')

        def _do_incremental(eng, tabla_del, tabla_ins, col_quote_fn):
            with eng.begin() as conn:
                col_q = col_quote_fn(date_col)
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
                print(f"  [DB] Limpieza incremental desde {fecha_inicio} en {tabla_del}: "
                      f"{antes} -> {despues} filas ({borradas} borradas)")
                if borradas == 0 and antes > 0:
                    print(f"  [DB] AVISO: no se borro ninguna fila. Si esperabas reemplazar datos existentes, "
                          f"revisa el formato real de '{date_col}' -- puede estar duplicando filas.")
            df.to_sql(tabla_ins, eng, index=False, if_exists='append', schema='dbo')
            print(f"  [DB] Carga incremental exitosa ({len(df)} registros).")

        nombre = table_name
        _do_incremental(engine, f'[dbo].[{nombre}]', nombre, lambda c: f'[{c}]')

        return True
    except Exception as e:
        print(f"  [DB] ERROR upload_incremental_to_sql({table_name}): {e}")
        return False
