"""
Carga_SQL_to_Render.py
======================
Módulo compartido de conexión a base de datos y carga de DataFrames.
Detecta automáticamente el entorno:
  - Local: SQL Server Express (.\\SQLEXPRESS / Aliv_DB)  — siempre activo
  - Nube:  PostgreSQL via NEON_URL  — carga dual automática si está configurado

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

# CONFIGURACIÓN
# Si estamos en Render, usaremos la variable de entorno DATABASE_URL
# Si estamos local, usaremos SQLEXPRESS + también subiremos a Neon si NEON_URL está configurado
DATABASE_URL = os.environ.get('DATABASE_URL')
NEON_URL     = os.environ.get('NEON_URL')


def get_engine():
    """Crea un motor de conexión automático (Local o Nube)."""
    if DATABASE_URL:
        # CONEXIÓN NUBE (PostgreSQL) — cuando se ejecuta en Render
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


def _get_neon_engine():
    """Motor SQLAlchemy apuntando a Neon PostgreSQL (solo si NEON_URL está configurado)."""
    if not NEON_URL:
        return None
    url = NEON_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return sa.create_engine(url)


def _normalize_for_pg(df):
    """Normaliza valores de texto para PostgreSQL (comparaciones case-sensitive)."""
    df = df.copy()
    df.columns = df.columns.str.lower()
    # Departamento: normalizar a INITCAP ('LIMA' → 'Lima')
    if 'departamento' in df.columns:
        df['departamento'] = df['departamento'].str.title()
    # Estado orden: ya viene en proper case desde Winforce
    return df


def _upload_df(df, table_name, engine, schema=None, if_exists='replace', lowercase_cols=False):
    """Sube un DataFrame a una tabla en el engine dado."""
    try:
        nombre = table_name
        df_up = df.copy()
        if lowercase_cols:
            df_up = _normalize_for_pg(df_up)
        insp = sa.inspect(engine)
        if if_exists == 'replace':
            if insp.has_table(nombre, schema=schema):
                with engine.begin() as conn:
                    tabla_q = f'"{schema}"."{nombre}"' if schema else f'"{nombre}"'
                    conn.execute(sa.text(f"DROP TABLE {tabla_q}"))
        df_up.to_sql(nombre, engine, index=False, if_exists='append', schema=schema)
        return True
    except Exception as e:
        print(f"  [DB] ERROR en _upload_df({table_name}): {e}")
        return False


def upload_to_sql(df, table_name, if_exists='replace'):
    """Sube un DataFrame a SQL (local y/o Neon)."""
    try:
        engine = get_engine()
        if DATABASE_URL:
            # En Render: solo PostgreSQL con columnas en minúsculas
            nombre = table_name.lower()
            ok = _upload_df(df, nombre, engine, schema=None, if_exists=if_exists, lowercase_cols=True)
        else:
            # Local: SQL Server con esquema dbo
            nombre = table_name
            insp = sa.inspect(engine)
            if if_exists == 'replace':
                if insp.has_table(nombre, schema='dbo'):
                    with engine.begin() as conn:
                        conn.execute(sa.text(f"DROP TABLE [dbo].[{nombre}]"))
            df.to_sql(nombre, engine, index=False, if_exists='append', schema='dbo')
            ok = True

        print(f"  [DB] Carga exitosa en: {nombre} ({len(df)} registros)")

        # Carga dual a Neon si está configurado (solo en modo local)
        if not DATABASE_URL and NEON_URL:
            neon = _get_neon_engine()
            if neon:
                _upload_df(df, table_name.lower(), neon, schema=None, if_exists=if_exists, lowercase_cols=True)
                print(f"  [Neon] Carga exitosa en: {table_name.lower()} ({len(df)} registros)")

        return ok
    except Exception as e:
        print(f"  [DB] ERROR upload_to_sql({table_name}): {e}")
        return False


def upload_incremental_to_sql(df, table_name, date_col, days=None, start_date=None):
    """
    Carga incremental: borra desde start_date y re-inserta.
    Sube a SQL Server local Y a Neon si está configurado.
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

        def _do_incremental(eng, tabla, col_quote_fn):
            with eng.begin() as conn:
                col_q = col_quote_fn(date_col)
                conn.execute(sa.text(f"DELETE FROM {tabla} WHERE {col_q} >= '{fecha_inicio}'"))
                print(f"  [DB] Limpieza incremental desde {fecha_inicio} en {tabla}")
            df.to_sql(tabla.strip('"').strip('[').rstrip(']'), eng, index=False, if_exists='append',
                      schema=None if DATABASE_URL else 'dbo')
            print(f"  [DB] Carga incremental exitosa ({len(df)} registros).")

        if DATABASE_URL:
            # Render: PostgreSQL
            nombre = table_name.lower()
            _do_incremental(engine, nombre, lambda c: f'"{c}"')
        else:
            # Local: SQL Server
            nombre = table_name
            _do_incremental(engine, f'[dbo].[{nombre}]', lambda c: f'[{c}]')

            # Carga dual a Neon
            if NEON_URL:
                neon = _get_neon_engine()
                if neon:
                    try:
                        nombre_n = table_name.lower()
                        with neon.begin() as conn:
                            conn.execute(sa.text(f'DELETE FROM "{nombre_n}" WHERE "{date_col}" >= \'{fecha_inicio}\''))
                            print(f"  [Neon] Limpieza desde {fecha_inicio} en {nombre_n}")
                        df.to_sql(nombre_n, neon, index=False, if_exists='append', schema=None)
                        print(f"  [Neon] Carga incremental exitosa ({len(df)} registros).")
                    except Exception as e:
                        print(f"  [Neon] ERROR incremental: {e}")

        return True
    except Exception as e:
        print(f"  [DB] ERROR upload_incremental_to_sql({table_name}): {e}")
        return False
