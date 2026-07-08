"""
Carga_Supervisores_Usuarios_Aliv.py
=====================================
Sube a SQL Server dos archivos Excel de la carpeta descargas_winforce_Dept:
  - Colaboradores.xls  → tabla SQL: Colaboradores
  - Usuarios Win.xlsx  → tabla SQL: Agencias_user

Ambos archivos se descargan manualmente desde Winforce y se colocan en
descargas_winforce_Dept/ antes de ejecutar este script.
Colaboradores.xls puede venir en formato HTML disfrazado de XLS (comportamiento
habitual de Winforce).

Uso:
    python Carga_Supervisores_Usuarios_Aliv.py
"""

import os
import pandas as pd
from db_config import upload_to_sql

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARPETA = os.path.join(BASE_DIR, "descargas_winforce_Dept")


def leer_xls_winforce(ruta):
    """Lee un .xls de Winforce que puede ser HTML disfrazado o Excel real."""
    with open(ruta, "rb") as f:
        cabecera = f.read(9)

    if cabecera.strip().startswith(b"<"):
        tablas = pd.read_html(ruta, encoding="utf-8")
        if not tablas:
            raise ValueError(f"El archivo HTML no contiene tablas: {ruta}")
        df = tablas[0]
        if str(df.columns[0]) == "0":
            df.columns = df.iloc[0]
            df = df.iloc[1:].reset_index(drop=True)
    else:
        try:
            df = pd.read_excel(ruta, engine="openpyxl")
        except Exception:
            df = pd.read_excel(ruta, engine="xlrd")

    return df.dropna(axis=1, how="all")


def cargar_colaboradores():
    ruta = os.path.join(CARPETA, "Colaboradores.xls")
    if not os.path.exists(ruta):
        print(f"[AVISO] No se encontró: {ruta}")
        return

    print(f"Leyendo Colaboradores.xls...")
    df = leer_xls_winforce(ruta)
    print(f"  {len(df):,} registros leídos.")
    upload_to_sql(df, "Colaboradores")


def cargar_usuarios_win():
    ruta = os.path.join(CARPETA, "Usuarios Win.xlsx")
    if not os.path.exists(ruta):
        print(f"[AVISO] No se encontró: {ruta}")
        return

    print(f"Leyendo Usuarios Win.xlsx...")
    try:
        df = pd.read_excel(ruta)
    except Exception:
        df = pd.read_excel(ruta, engine="xlrd")
    df = df.dropna(axis=1, how="all")
    print(f"  {len(df):,} registros leídos.")
    upload_to_sql(df, "Agencias_user")


def main():
    print("=" * 55)
    print("  CARGA COLABORADORES Y AGENCIAS/USUARIOS WIN")
    print("=" * 55)

    cargar_colaboradores()
    cargar_usuarios_win()

    print("\nCarga completada.")
    print("=" * 55)


if __name__ == "__main__":
    main()
