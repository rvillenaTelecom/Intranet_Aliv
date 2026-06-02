"""
Carga_WinReporteSemanal.py
==========================
Consolida múltiples archivos Excel de reportes Winforce (carpeta Aliv_Reporte_Win)
en un único archivo, manteniendo un solo registro por contrato con el estado más
reciente (el archivo más nuevo tiene prioridad sobre los anteriores).
Guarda el resultado en descargas_winforce_Dept/Win_reporte_semanal.xlsx
y lo sube a SQL Server en la tabla Win_reporte_semanal.

Uso:
    python Carga_WinReporteSemanal.py
"""

import pandas as pd
import os
import glob
import re
from db_config import upload_to_sql

MESES_ES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
    'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
}

def orden_archivo(filepath):
    name = os.path.basename(filepath).lower()
    mes = next((n for m, n in MESES_ES.items() if m in name), 0)
    nums = re.findall(r'\d+', name)
    version = int(nums[-1]) if nums else 0
    return (mes, version)

def consolidar_ventas():
    input_folder = r"C:\Users\Usuario\Documents\Code Aliv\Python Automate\Descargas_Rápidas\Aliv_Reporte_Win"
    output_file = r"C:\Users\Usuario\Documents\Code Aliv\Python Automate\Descargas_Rápidas\descargas_winforce_Dept\Win_reporte_semanal.xlsx"

    print(f"Buscando archivos en: {input_folder}")

    files = glob.glob(os.path.join(input_folder, "*.xlsx"))
    if not files:
        print("No se encontraron archivos .xlsx en la carpeta.")
        return

    # Ordenar de mas antiguo a mas reciente por mes y numero de version en el nombre
    files_ordenados = sorted(files, key=orden_archivo)
    print("\nOrden de prioridad (el ultimo tiene mayor autoridad sobre el estado de cada contrato):")
    for i, f in enumerate(files_ordenados, 1):
        print(f"  {i}. {os.path.basename(f)}")

    all_data = []
    for orden, file in enumerate(files_ordenados, 1):
        try:
            df = pd.read_excel(file)
            df['_orden_archivo'] = orden
            all_data.append(df)
            print(f"Leido: {os.path.basename(file)} ({len(df)} registros)")
        except Exception as e:
            print(f"Error al leer {file}: {e}")

    if not all_data:
        print("No hay datos para procesar.")
        return

    df_consolidado = pd.concat(all_data, ignore_index=True)
    print(f"\nTotal registros crudos: {len(df_consolidado)}")

    sin_contrato = df_consolidado['contrato'].isna().sum()
    if sin_contrato > 0:
        print(f"Eliminando {sin_contrato} filas sin numero de contrato.")
        df_consolidado = df_consolidado.dropna(subset=['contrato'])

    df_consolidado['fecha_venta'] = pd.to_datetime(df_consolidado['fecha_venta'], errors='coerce')

    # Para cada contrato: conservar el registro del archivo mas reciente.
    # Si hay varios registros del mismo archivo para el mismo contrato, conservar el de fecha_venta mas reciente.
    df_consolidado = df_consolidado.sort_values(
        by=['_orden_archivo', 'fecha_venta'],
        ascending=[False, False]
    )
    df_consolidado = df_consolidado.drop_duplicates(subset=['contrato'], keep='first')
    df_consolidado = df_consolidado.drop(columns=['_orden_archivo'])

    print(f"Registros finales (un registro por contrato): {len(df_consolidado)}")
    print(f"\nDistribucion de Estado:")
    print(df_consolidado['Estado'].value_counts().to_string())
    print(f"\nTotal Altas (Alta=1): {int(df_consolidado['Alta'].sum())}")

    print(f"\nGuardando en: {output_file}")
    df_consolidado.to_excel(output_file, index=False)
    print("Proceso completado exitosamente!")
    
    # 3. Carga a SQL Server
    print("\nIniciando carga a SQL Server...")
    upload_to_sql(df_consolidado, "Win_reporte_semanal")

if __name__ == "__main__":
    consolidar_ventas()
