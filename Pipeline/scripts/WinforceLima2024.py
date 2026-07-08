"""
WinforceLima2024.py
===================
Combina los dos Excel de Lima 2024 y los carga a SQL → winforce_lima_2024.

Archivos fuente (descargas_winforce_Dept/Data 2024 - 2025/):
  - Enero - Juniio 2024.xls
  - Julio - Diciembre 2024.xls

Uso:
    python WinforceLima2024.py
"""

import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from db_config import upload_to_sql

BASE_DIR    = os.path.join(os.path.dirname(__file__), "..", "descargas_winforce_Dept", "Data 2024 - 2025")
TABLA_SQL   = "winforce_lima_2024"
ARCHIVOS    = [
    "Enero - Junio 2024.xls",
    "Julio - Diciembre 2024.xls",
]


def leer_excel(ruta):
    with open(ruta, "rb") as f:
        cabecera = f.read(9)
    if cabecera[:5] in (b"<!DOC", b"<html", b"<HTML"):
        tablas = pd.read_html(ruta, encoding="utf-8")
        if not tablas:
            raise Exception(f"HTML sin tablas: {ruta}")
        return tablas[0]
    try:
        return pd.read_excel(ruta, engine="xlrd")
    except Exception:
        return pd.read_excel(ruta, engine="openpyxl")


def main():
    dfs = []
    for nombre in ARCHIVOS:
        ruta = os.path.join(BASE_DIR, nombre)
        if not os.path.exists(ruta):
            print(f"[ERROR] No se encontró el archivo: {ruta}")
            sys.exit(1)
        print(f"Leyendo: {nombre}...")
        df = leer_excel(ruta)
        print(f"  → {len(df):,} registros")
        dfs.append(df)

    df_total = pd.concat(dfs, ignore_index=True)
    print(f"\nTotal combinado: {len(df_total):,} registros")

    print(f"Cargando a SQL → tabla: {TABLA_SQL}...")
    ok = upload_to_sql(df_total, TABLA_SQL)
    if ok:
        print(f"[OK] Tabla {TABLA_SQL} cargada correctamente.")
    else:
        print(f"[ERROR] Fallo al cargar a SQL.")
        sys.exit(1)


if __name__ == "__main__":
    main()
