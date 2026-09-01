"""
Subida_Aliv.py
==============
Descarga "Ventas Win Activas" desde el Sistema de Ventas Aliv (mes anterior
+ mes actual, filtro Canal empresa = win) y la sube a la tabla dbo.ventas_aliv
en SQL Server.

La subida es incremental por fecha: solo borra y reemplaza el rango
descargado (columna 'Fecha Activacion'), sin tocar el historial de meses
anteriores.

Uso:
    python Subida_Aliv.py
"""

import os
import sys
from datetime import datetime
import pandas as pd
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_config import upload_incremental_to_sql
import DescargaAlivSistemaVentas as descarga

TABLA = "ventas_aliv"
COL_FECHA = "Fecha Activacion"


def _leer_reporte(archivo):
    """Lee el .xls exportado (HTML disfrazado de xls, o Excel real)."""
    with open(archivo, "rb") as f:
        cabecera = f.read(9)

    if cabecera.strip().startswith(b"<"):
        print("Detectado formato HTML/XML (Winforce XLS). Procesando tablas...")
        tablas = pd.read_html(archivo, encoding="utf-8", header=None)
        if not tablas:
            raise Exception("El archivo HTML no contiene ninguna tabla de datos.")

        ref = max(tablas, key=lambda t: t.shape[0] * t.shape[1])
        n_cols = ref.shape[1]
        tablas_datos = [t for t in tablas if t.shape[1] == n_cols and t.shape[0] > 1]

        if len(tablas_datos) > 1:
            print(f"  Concatenando {len(tablas_datos)} tablas (posible paginacion)...")
            df = pd.concat(tablas_datos, ignore_index=True)
        else:
            df = tablas_datos[0]

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [' '.join(str(c) for c in col if str(c) != 'nan').strip()
                          for col in df.columns]

        df.columns = df.iloc[0].astype(str).str.strip()
        df = df.iloc[1:].reset_index(drop=True)
        df = df.loc[:, ~df.columns.isin(['', 'nan', 'None'])]

        primera_col = df.columns[0]
        filas_cabecera = df[primera_col].astype(str) == str(primera_col)
        if filas_cabecera.any():
            print(f"  Eliminando {filas_cabecera.sum()} fila(s) de cabecera repetida...")
            df = df[~filas_cabecera].reset_index(drop=True)

        df = df.dropna(how='all')
    else:
        print("Detectado formato Excel estandar.")
        try:
            df = pd.read_excel(archivo)
        except Exception:
            df = pd.read_excel(archivo, engine="xlrd")

    df = df.dropna(axis=1, how='all')
    return df


def subir_aliv():
    print("=" * 50)
    print("SUBIDA ALIV — DESCARGA + CARGA SQL")
    print("=" * 50)

    with sync_playwright() as p:
        browser, context = descarga.nuevo_browser(p)
        page = context.new_page()
        try:
            if not descarga.login(page):
                print("Error: no se pudo iniciar sesion en el Sistema Aliv.")
                return
            archivo, fecha_desde, fecha_hasta = descarga.descargar_activas(page)
        finally:
            context.close()
            browser.close()

    print(f"\nLeyendo archivo: {archivo}...")
    try:
        df = _leer_reporte(archivo)
    except Exception as e:
        print(f"Error critico al procesar el archivo: {e}")
        return

    print(f"Lectura exitosa: {len(df):,} registros, {len(df.columns)} columnas.")
    print(f"  Columnas: {list(df.columns)}")

    if COL_FECHA not in df.columns:
        print(f"Error: no se encontro la columna '{COL_FECHA}' en el reporte descargado.")
        return

    fecha_inicio = datetime.strptime(fecha_desde, "%d-%m-%Y")
    print(f"\nSubiendo a [{TABLA}], reemplazando desde {fecha_desde} (columna '{COL_FECHA}')...")
    success = upload_incremental_to_sql(df, TABLA, date_col=COL_FECHA, start_date=fecha_inicio)

    if success:
        print("\nPROCESO COMPLETADO CON EXITO")
    else:
        print("\nEl proceso termino con errores en la carga SQL.")


if __name__ == "__main__":
    subir_aliv()
