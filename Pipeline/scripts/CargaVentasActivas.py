"""
CargaVentasActivas.py
======================
Carga Aliv_ventas_activas_2024.xls y Aliv_ventas_activas_2025.xls
a SQL en tablas separadas:
  - aliv_ventas_activas_2024
  - aliv_ventas_activas_2025

Uso:
    python CargaVentasActivas.py
"""

import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from db_config import upload_to_sql

BASE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "descargas_winforce_Dept", "Aliv Data 2024 - 2025"
)

ARCHIVOS = {
    "aliv_ventas_activas_2024": "Aliv_ventas_activas_2024.xls",
    "aliv_ventas_activas_2025": "Aliv_ventas_activas_2025.xls",
}


def leer_xls_html(ruta):
    """Lee un .xls que en realidad es HTML (exportado desde Winforce)."""
    for enc in ("utf-8", "latin1", "cp1252"):
        try:
            tablas = pd.read_html(ruta, encoding=enc, header=0)
            if tablas:
                return tablas[0]
        except Exception:
            continue
    raise RuntimeError(f"No se pudo leer el archivo: {ruta}")


def main():
    errores = []
    for tabla, nombre_archivo in ARCHIVOS.items():
        ruta = os.path.join(BASE_DIR, nombre_archivo)
        if not os.path.exists(ruta):
            print(f"[ERROR] Archivo no encontrado: {ruta}")
            errores.append(tabla)
            continue

        print(f"\nLeyendo: {nombre_archivo}...")
        df = leer_xls_html(ruta)
        print(f"  {len(df):,} registros, {len(df.columns)} columnas")

        print(f"  Cargando a SQL -> tabla: {tabla}...")
        ok = upload_to_sql(df, tabla)
        if ok:
            print(f"  [OK] {tabla}")
        else:
            print(f"  [ERROR] Fallo al cargar {tabla}")
            errores.append(tabla)

    if errores:
        print(f"\n[RESUMEN] Fallaron: {errores}")
        sys.exit(1)
    else:
        print("\n[RESUMEN] Ambas tablas cargadas correctamente.")


if __name__ == "__main__":
    main()
