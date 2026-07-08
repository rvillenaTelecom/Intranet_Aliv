"""
Subida_Aliv.py
==============
Lee el archivo Aliv_ventas_activas.xls descargado manualmente desde Winforce
(puede venir en formato HTML disfrazado de XLS) y lo sube a la tabla
ventas_aliv en SQL Server, reemplazando todos los datos existentes.

Uso:
    1. Descarga manualmente Aliv_ventas_activas.xls desde Winforce
    2. Colócalo en descargas_winforce_Dept/
    3. python Subida_Aliv.py
"""

import os
import pandas as pd
from db_config import upload_to_sql

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def subir_aliv_manual():
    """
    Lee el archivo Aliv_ventas_activas.xls descargado manualmente
    y lo sube a la tabla 'ventas_aliv' en SQL Server, reemplazando los datos.
    """
    archivo = os.path.join(BASE_DIR, "descargas_winforce_Dept", "Aliv_ventas_activas.xls")
    tabla = "ventas_aliv"
    
    print("="*50)
    print("INICIANDO SUBIDA MANUAL DE VENTAS ALIV")
    print("="*50)
    
    if not os.path.exists(archivo):
        print(f"Error: No se encontró el archivo: {archivo}")
        return

    print(f"Leyendo archivo: {archivo}...")

    # 2. Leer archivo (Winforce suele enviar HTML disfrazado de XLS)
    try:
        # Verificamos si es HTML o Excel real
        with open(archivo, "rb") as f:
            cabecera = f.read(9)

        if cabecera.strip().startswith(b"<"):
            print("Detectado formato HTML/XML (Winforce XLS). Procesando tablas...")
            tablas = pd.read_html(archivo, encoding="utf-8", header=None)
            if not tablas:
                print("Error: El archivo HTML no contiene ninguna tabla de datos.")
                return

            # Mostrar todas las tablas encontradas en el HTML
            for i, t in enumerate(tablas):
                primeras = list(t.iloc[0].astype(str))[:6]
                print(f"  Tabla {i}: {t.shape[0]}f x {t.shape[1]}c  -- {primeras}")

            # Seleccionar la tabla con más datos (filas × columnas).
            # Winforce a veces pagina en múltiples <table>, así que tomamos
            # la tabla de referencia y luego concatenamos todas las que
            # tengan el mismo número de columnas (son la misma tabla paginada).
            ref = max(tablas, key=lambda t: t.shape[0] * t.shape[1])
            n_cols = ref.shape[1]
            tablas_datos = [t for t in tablas if t.shape[1] == n_cols and t.shape[0] > 1]
            print(f"  Encontradas {len(tablas_datos)} tabla(s) con {n_cols} columnas.")

            if len(tablas_datos) > 1:
                print(f"  Concatenando {len(tablas_datos)} tablas (posible paginación Winforce)...")
                df = pd.concat(tablas_datos, ignore_index=True)
            else:
                df = tablas_datos[0]

            # Aplanar MultiIndex de columnas si pandas lo generó por merged cells
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [' '.join(str(c) for c in col if str(c) != 'nan').strip()
                              for col in df.columns]

            # La primera fila tiene los nombres de columnas en exports de Winforce
            print(f"  Promoviendo primera fila como headers...")
            df.columns = df.iloc[0].astype(str).str.strip()
            df = df.iloc[1:].reset_index(drop=True)
            print(f"  Tras quitar fila de header: {len(df)} filas")

            # Eliminar columnas cuyo nombre quedó vacío o 'nan'
            df = df.loc[:, ~df.columns.isin(['', 'nan', 'None'])]

            # Eliminar filas de cabecera repetida (Winforce las inserta al paginar)
            primera_col = df.columns[0]
            filas_cabecera = df[primera_col].astype(str) == str(primera_col)
            if filas_cabecera.any():
                print(f"  Eliminando {filas_cabecera.sum()} fila(s) de cabecera repetida...")
                df = df[~filas_cabecera].reset_index(drop=True)
            print(f"  Tras limpiar cabeceras repetidas: {len(df)} filas")

            # Eliminar filas completamente vacías
            antes = len(df)
            df = df.dropna(how='all')
            eliminadas_vacias = antes - len(df)
            if eliminadas_vacias:
                print(f"  Eliminando {eliminadas_vacias} fila(s) completamente vacías...")
            print(f"  Tras limpiar filas vacías: {len(df)} filas")
        else:
            print("Detectado formato Excel estándar.")
            try:
                df = pd.read_excel(archivo)
            except Exception:
                df = pd.read_excel(archivo, engine="xlrd")

        # Eliminar columnas completamente vacías (aplica a HTML y Excel)
        df = df.dropna(axis=1, how='all')

        print(f"Lectura exitosa: {len(df):,} registros, {len(df.columns)} columnas.")
        print(f"  Columnas: {list(df.columns)}")

        # 3. Subir a SQL Server (Reemplaza toda la tabla)
        print(f"Subiendo a la tabla [{tabla}] en SQL Server...")
        success = upload_to_sql(df, tabla, if_exists='replace')
        
        if success:
            print("\nPROCESO COMPLETADO CON EXITO")
        else:
            print("\nEl proceso termino con errores en la carga SQL.")
            
    except Exception as e:
        print(f"Error critico al procesar/subir: {e}")

if __name__ == "__main__":
    subir_aliv_manual()
