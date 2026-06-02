"""
Carga_UsuariosWin.py
====================
Carga el maestro de vendedores a SQL Server (tabla Usuarios_win).
Enriquece Usuarios_Win.xlsx con los supervisores obtenidos cruzando con
Aliv_ventas_activas.xls (descargado manualmente desde Winforce).

Uso:
    python Carga_UsuariosWin.py
"""

import pandas as pd
import os
import sys
from db_config import upload_to_sql

def cargar_maestros():
    print("="*60)
    print("  CARGA DE ARCHIVOS MAESTROS A SQL SERVER")
    print("="*60)
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # 2. Usuarios_win (Consolidado con Ventas Aliv para obtener Supervisor)
    path_usuarios = r"C:\Users\Usuario\Documents\Code Aliv\Python Automate\Morosidad\Usuarios_Win.xlsx"
    path_aliv = os.path.join(base_dir, "descargas_winforce_Dept", "Aliv_ventas_activas.xls")
    
    if os.path.exists(path_usuarios):
        print(f"\nProcesando Maestro de Usuarios...")
        try:
            # Leer archivo base de Usuarios (Vendedor y Agencia)
            df_u = pd.read_excel(path_usuarios)
            df_u.columns = [c.upper() for c in df_u.columns] # [VENDEDOR, AGENCIA]
            
            if os.path.exists(path_aliv):
                print(f"  Enriqueciendo con información de supervisores desde Ventas Aliv...")
                # Leer Ventas Aliv (manejar formato HTML de Winforce)
                with open(path_aliv, "rb") as f:
                    cabecera = f.read(9)
                
                if cabecera.strip().startswith(b"<"):
                    tablas = pd.read_html(path_aliv, encoding="utf-8")
                    df_a = tablas[0]
                    if str(df_a.columns[0]) == "0":
                        df_a.columns = df_a.iloc[0]
                        df_a = df_a.iloc[1:].reset_index(drop=True)
                else:
                    df_a = pd.read_excel(path_aliv)
                
                # Limpiar nombres de columnas
                df_a.columns = [str(c).strip() for c in df_a.columns]
                
                # Normalización de nombres para el join
                def limpiar_nombre(n):
                    if pd.isna(n): return ""
                    n = str(n).strip().upper()
                    replacements = (("Á", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"), ("Ú", "U"))
                    for a, b in replacements:
                        n = n.replace(a, b)
                    return n

                df_u['VENDEDOR_CLEAN'] = df_u['VENDEDOR'].apply(limpiar_nombre)
                
                # Preparar Ventas Aliv
                if 'Vendedor' in df_a.columns and 'Supervisor' in df_a.columns:
                    df_a = df_a[['Vendedor', 'Supervisor', 'Fecha Ingreso']].copy()
                    df_a.columns = ['VENDEDOR_ORIG', 'SUPERVISOR', 'FECHA_INGRESO']
                    df_a['VENDEDOR_CLEAN'] = df_a['VENDEDOR_ORIG'].apply(limpiar_nombre)
                    
                    # Quedarse con el último supervisor por vendedor
                    df_a['FECHA_INGRESO'] = pd.to_datetime(df_a['FECHA_INGRESO'], dayfirst=True, errors='coerce')
                    df_a = df_a.sort_values(by='FECHA_INGRESO', ascending=False)
                    df_a = df_a.drop_duplicates(subset=['VENDEDOR_CLEAN'], keep='first')
                    
                    # OUTER JOIN para incluir a los que están en ventas pero no en el maestro (ej: Corina)
                    df_final = pd.merge(df_u, df_a[['VENDEDOR_CLEAN', 'SUPERVISOR', 'VENDEDOR_ORIG']], on='VENDEDOR_CLEAN', how='outer')
                    
                    # Rellenar datos para los nuevos (los que no estaban en df_u)
                    df_final['VENDEDOR'] = df_final['VENDEDOR'].fillna(df_final['VENDEDOR_ORIG'])
                    df_final['AGENCIA'] = df_final['AGENCIA'].fillna('ALIV')
                    
                    print(f"  Consolidación completada. Total vendedores: {len(df_final)}")
                else:
                    print("  [AVISO] No se encontraron columnas 'Vendedor' o 'Supervisor' en Ventas Aliv.")
                    df_final = df_u.copy()
                    df_final['SUPERVISOR'] = 'SIN ASIGNAR'
            else:
                print(f"  [AVISO] No se encontro {path_aliv}. Se subirá sin supervisor.")
                df_final = df_u.copy()
                df_final['SUPERVISOR'] = 'SIN ASIGNAR'

            # Limpieza final
            df_final['SUPERVISOR'] = df_final['SUPERVISOR'].fillna('SIN ASIGNAR')
            df_final['VENDEDOR'] = df_final['VENDEDOR'].str.upper().str.strip()
            
            # Reordenar columnas según pedido: SUPERVISOR, VENDEDOR, AGENCIA
            columnas_finales = ['SUPERVISOR', 'VENDEDOR', 'AGENCIA']
            for col in columnas_finales:
                if col not in df_final.columns: df_final[col] = 'N/A'
            
            df_final = df_final[columnas_finales].drop_duplicates()
            
            # Subir a SQL
            upload_to_sql(df_final, "Usuarios_win")
            
        except Exception as e:
            print(f"Error al procesar Usuarios_win: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"No se encontro Usuarios_Win en: {path_usuarios}")

    print("\nProceso de carga de maestros finalizado.")
    print("="*60)

if __name__ == "__main__":
    cargar_maestros()
