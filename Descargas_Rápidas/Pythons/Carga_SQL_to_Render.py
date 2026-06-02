"""
Carga_SQL_to_Render.py
======================
Módulo compartido de conexión a base de datos y carga de DataFrames.
Detecta automáticamente el entorno:
  - Local: SQL Server Express (.\SQLEXPRESS / Aliv_DB)
  - Nube:  PostgreSQL via variable de entorno DATABASE_URL (Render/Supabase)

Funciones disponibles:
  get_engine()                          → motor SQLAlchemy listo para usar
  upload_to_sql(df, tabla)              → reemplaza toda la tabla
  upload_incremental_to_sql(df, tabla, col_fecha) → borra desde la fecha mínima del df y re-inserta
"""

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
        # Ajuste para Render/Supabase (SQLAlchemy requiere 'postgresql://')
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
        # Añadimos fast_executemany para mejorar rendimiento en SQL Server
        return sa.create_engine(f"mssql+pyodbc:///?odbc_connect={params}", fast_executemany=True)

def upload_to_sql(df, table_name, if_exists='replace'):
    """Sube un DataFrame a una tabla específica."""
    try:
        engine = get_engine()
        nombre_final = table_name if not DATABASE_URL else table_name.lower()
        esquema = 'dbo' if not DATABASE_URL else None

        # SQLAlchemy 2.x falla al reflejar tablas inexistentes con if_exists='replace'.
        # Manejamos el DROP manualmente para evitar el problema.
        if if_exists == 'replace':
            insp = sa.inspect(engine)
            if insp.has_table(nombre_final, schema=esquema):
                with engine.begin() as conn:
                    tabla_q = f"[{esquema}].[{nombre_final}]" if esquema else f"[{nombre_final}]"
                    conn.execute(sa.text(f"DROP TABLE {tabla_q}"))
            df.to_sql(nombre_final, engine, index=False, if_exists='append', schema=esquema)
        else:
            df.to_sql(nombre_final, engine, index=False, if_exists=if_exists, schema=esquema)

        print(f"  [DB] Carga exitosa en: {nombre_final} ({len(df)} registros)")
        return True
    except Exception as e:
        print(f"  [DB] ERROR: {e}")
        return False

def upload_incremental_to_sql(df, table_name, date_col, days=None):
    """
    Carga incremental inteligente: Borra la data desde la fecha mínima encontrada 
    en el DataFrame y luego sube la nueva información. Esto evita duplicados 
    independientemente de cuántos días se hayan descargado.
    """
    try:
        engine = get_engine()
        
        # Asegurarse de que la columna de fecha sea datetime
        df_temp = df.copy()
        df_temp[date_col] = pd.to_datetime(df_temp[date_col], dayfirst=True, errors='coerce')
        fecha_minima = df_temp[date_col].min()
        
        if pd.isna(fecha_minima):
            # Si no hay fechas válidas, usamos el método tradicional de 7 días como respaldo
            from datetime import datetime, timedelta
            dias_atras = days if days is not None else 7
            fecha_inicio = (datetime.now() - timedelta(days=dias_atras)).strftime('%Y-%m-%d')
            print(f"  [DB] AVISO: No se detectaron fechas en '{date_col}'. Usando respaldo: {fecha_inicio}")
        else:
            fecha_inicio = fecha_minima.strftime('%Y-%m-%d')
        
        # En SQL Server respetamos el nombre, en Postgres minúsculas
        nombre_final = table_name if not DATABASE_URL else table_name.lower()
        esquema = 'dbo' if not DATABASE_URL else None
        
        with engine.begin() as conn:
            # Detectar el tipo de comillas según la base de datos
            if DATABASE_URL:
                # Nube (Postgres): Usa comillas dobles
                query = sa.text(f"DELETE FROM {nombre_final} WHERE \"{date_col}\" >= '{fecha_inicio}'")
            else:
                # Local (SQL Server): Usa corchetes
                query = sa.text(f"DELETE FROM {nombre_final} WHERE [{date_col}] >= '{fecha_inicio}'")
            
            conn.execute(query)
            print(f"  [DB] Limpieza incremental desde {fecha_inicio} en {nombre_final}")
            
        df.to_sql(nombre_final, engine, index=False, if_exists='append', schema=esquema)
        print(f"  [DB] Carga incremental exitosa ({len(df)} registros).")
        return True
    except Exception as e:
        print(f"  [DB] ERROR incremental: {e}")
        return False
