"""
Carga_dim_usuarios_Aliv.py
===========================
Carga (upsert) el archivo dim_usuarios_Aliv.xlsx a la tabla SQL dim_usuarios_Aliv.

- Actualiza registros existentes (por columna 'vendedor' como clave).
- Inserta vendedores nuevos.
- NO borra registros creados manualmente desde la Intranet.

Archivo fuente: descargas_winforce_Dept/dim_usuarios_Aliv.xlsx
  Columnas esperadas (fila 1 del Excel):
    Supervisor | Usuario Winforce | Vendedor (nombre limpio) | Agencia | Fuente Supervisor | Estado

Uso:
    python Carga_dim_usuarios_Aliv.py
"""

import os
import sys
import pandas as pd
import sqlalchemy as sa
from datetime import date

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XLSX = os.path.join(BASE_DIR, "descargas_winforce_Dept", "dim_usuarios_Aliv.xlsx")
TABLE = "dim_usuarios_Aliv"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_config import get_engine


def cargar_dim_usuarios():
    if not os.path.exists(XLSX):
        print(f"[ERROR] No se encontró el archivo: {XLSX}")
        return

    print(f"Leyendo {os.path.basename(XLSX)}...")
    df_raw = pd.read_excel(XLSX, header=None)
    df_raw.columns = df_raw.iloc[1].tolist()
    df = df_raw.iloc[2:].reset_index(drop=True).dropna(subset=["Usuario Winforce"])

    def _clean(val):
        """Convierte vacíos y valores con emojis de pendiente a None."""
        if pd.isna(val):
            return None
        s = str(val).strip()
        if not s or any(x in s for x in ["PENDIENTE", "Sin agencia", "Sin supervisor", "⏳", "⚠️"]):
            return None
        return s

    df_up = pd.DataFrame({
        "vendedor":        df["Usuario Winforce"].str.strip(),
        "nombre_completo": df["Vendedor (nombre limpio)"].str.strip(),
        "cargo":           "Vendedor",
        "agencia":         df["Agencia"].apply(_clean),
        "supervisor":      df["Supervisor"].apply(_clean),
        "canal":           "Lima",
        "estado":          "Activo",
        "fecha_registro":  date.today().isoformat(),
    })
    df_up = df_up[df_up["vendedor"].notna() & (df_up["vendedor"] != "")]
    print(f"  {len(df_up):,} registros en el Excel.")

    engine = get_engine()
    insertados = actualizados = 0

    with engine.begin() as conn:
        for _, row in df_up.iterrows():
            existing = conn.execute(
                sa.text(f"SELECT id FROM {TABLE} WHERE vendedor = :v"),
                {"v": row["vendedor"]}
            ).fetchone()

            if existing:
                conn.execute(sa.text(f"""
                    UPDATE {TABLE}
                    SET nombre_completo = :n,
                        cargo           = :c,
                        agencia         = :ag,
                        supervisor      = :sv,
                        canal           = :ca,
                        estado          = :es
                    WHERE vendedor = :v
                """), {
                    "v": row["vendedor"], "n": row["nombre_completo"],
                    "c": row["cargo"],    "ag": row["agencia"],
                    "sv": row["supervisor"], "ca": row["canal"], "es": row["estado"],
                })
                actualizados += 1
            else:
                conn.execute(sa.text(f"""
                    INSERT INTO {TABLE}
                        (vendedor, nombre_completo, cargo, agencia, supervisor, canal, estado, fecha_registro)
                    VALUES (:v, :n, :c, :ag, :sv, :ca, :es, :fr)
                """), {
                    "v": row["vendedor"], "n": row["nombre_completo"],
                    "c": row["cargo"],    "ag": row["agencia"],
                    "sv": row["supervisor"], "ca": row["canal"],
                    "es": row["estado"],  "fr": row["fecha_registro"],
                })
                insertados += 1

    print(f"  Insertados: {insertados} | Actualizados: {actualizados}")

    with engine.connect() as conn:
        total = conn.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE}")).fetchone()[0]
    print(f"  Total en tabla: {total:,}")


def main():
    print("=" * 55)
    print("  CARGA dim_usuarios_Aliv (upsert)")
    print("=" * 55)
    cargar_dim_usuarios()
    print("\nCarga completada.")
    print("=" * 55)


if __name__ == "__main__":
    main()
