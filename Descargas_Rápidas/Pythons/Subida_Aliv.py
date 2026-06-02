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
            # Usamos read_html para extraer la tabla de datos
            tablas = pd.read_html(archivo, encoding="utf-8")
            if not tablas:
                print("Error: El archivo HTML no contiene ninguna tabla de datos.")
                return
            df = tablas[0]
            
            # ARREGLO DE HEADERS:
            # Si el DataFrame tiene columnas numéricas (0, 1, 2...), 
            # significa que los nombres reales están en la primera fila.
            if str(df.columns[0]) == "0":
                print("  Corrigiendo headers (promoviendo primera fila)...")
                df.columns = df.iloc[0]
                df = df.iloc[1:].reset_index(drop=True)
        else:
            print("Detectado formato Excel estándar.")
            try:
                # Intentamos con openpyxl (xlsx) o xlrd (xls viejo)
                df = pd.read_excel(archivo)
            except Exception:
                df = pd.read_excel(archivo, engine="xlrd")
                
        print(f"Lectura exitosa: {len(df):,} registros encontrados.")
        
        # Opcional: Limpieza básica de columnas si es necesario
        # (A veces read_html trae columnas vacías al final)
        df = df.dropna(axis=1, how='all')
        
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
