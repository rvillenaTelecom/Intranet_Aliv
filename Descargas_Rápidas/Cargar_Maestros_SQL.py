import pandas as pd
import os
from db_config import upload_to_sql

def cargar_maestros():
    print("="*60)
    print("  CARGA DE ARCHIVOS MAESTROS A SQL SERVER")
    print("="*60)
    
    # 1. Cuota_Prov
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path_cuota = os.path.join(base_dir, "descargas_winforce_Dept", "Cuota_Prov.xlsx")
    if os.path.exists(path_cuota):
        print(f"Procesando Cuota_Prov...")
        df_cuota = pd.read_excel(path_cuota)
        upload_to_sql(df_cuota, "Cuota_Prov")
    else:
        print(f"No se encontro Cuota_Prov en: {path_cuota}")

    # 2. Usuarios_win
    path_usuarios = r"C:\Users\Usuario\Documents\Code Aliv\Python Automate\Morosidad\Usuarios_Win.xlsx"
    if os.path.exists(path_usuarios):
        print(f"Procesando Usuarios_win...")
        df_usuarios = pd.read_excel(path_usuarios)
        upload_to_sql(df_usuarios, "Usuarios_win")
    else:
        print(f"[AVISO] No se encontro Usuarios_Win en: {path_usuarios}")

    print("\nProceso de carga de maestros finalizado.")
    print("="*60)

if __name__ == "__main__":
    cargar_maestros()
