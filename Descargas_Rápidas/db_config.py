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
        return sa.create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

def upload_to_sql(df, table_name, if_exists='replace'):
    """Sube un DataFrame a una tabla específica."""
    try:
        engine = get_engine()
        df.to_sql(table_name.lower(), engine, index=False, if_exists=if_exists)
        print(f"  [DB] Carga exitosa en: {table_name.lower()} ({len(df)} registros)")
        return True
    except Exception as e:
        print(f"  [DB] ERROR: {e}")
        return False

def upload_incremental_to_sql(df, table_name, date_col, days=7):
    """Carga incremental (Borra últimos días y sube nuevo)."""
    try:
        engine = get_engine()
        from datetime import datetime, timedelta
        fecha_inicio = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        # Ajustar nombre de tabla y columna para PostgreSQL (minúsculas sin espacios es mejor)
        table_name = table_name.lower()
        
        with engine.begin() as conn:
            # Detectar el tipo de comillas según la base de datos
            if DATABASE_URL:
                # Nube (Postgres): Usa comillas dobles
                query = sa.text(f"DELETE FROM {table_name} WHERE \"{date_col}\" >= '{fecha_inicio}'")
            else:
                # Local (SQL Server): Usa corchetes
                query = sa.text(f"DELETE FROM {table_name} WHERE [{date_col}] >= '{fecha_inicio}'")
            
            conn.execute(query)
            print(f"  [DB] Limpieza incremental desde {fecha_inicio} en {table_name}")
            
        df.to_sql(table_name, engine, index=False, if_exists='append')
        print(f"  [DB] Carga incremental exitosa.")
        return True
    except Exception as e:
        print(f"  [DB] ERROR incremental: {e}")
        return False
