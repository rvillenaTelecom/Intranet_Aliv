import pandas as pd
import os
from pathlib import Path

def convert_csv_to_excel(directory=None):
    """
    Convierte todos los archivos CSV en el directorio especificado a formato Excel (.xlsx).
    """
    if directory is None:
        # Por defecto usa el directorio donde se encuentra el script
        directory = os.path.dirname(os.path.abspath(__file__))
    
    path = Path(directory)
    archivos_csv = list(path.glob("*.csv"))
    
    if not archivos_csv:
        print(f"No se encontraron archivos CSV en: {directory}")
        return

    print(f"Encontrados {len(archivos_csv)} archivos CSV. Iniciando conversión...\n")

    for archivo_path in archivos_csv:
        try:
            print(f"Procesando: {archivo_path.name}...")
            
            # Intentar leer el CSV detectando el delimitador automáticamente
            # utf-8-sig es ideal para archivos generados por Excel que podrían tener BOM
            try:
                df = pd.read_csv(archivo_path, sep=None, engine='python', encoding='utf-8-sig')
            except Exception:
                # Si falla, intentar con latin-1 que es común en Windows
                df = pd.read_csv(archivo_path, sep=None, engine='python', encoding='latin-1')
            
            # Generar el nombre de salida con extensión .xlsx
            nombre_excel = archivo_path.with_suffix('.xlsx')
            
            # Guardar el DataFrame en formato Excel
            # Se usa el motor openpyxl (ya está en requirements.txt)
            df.to_excel(nombre_excel, index=False)
            
            print(f"✅ Convertido: {nombre_excel.name}")
            
        except Exception as e:
            print(f"❌ Error al procesar {archivo_path.name}: {str(e)}")

if __name__ == "__main__":
    print("========================================")
    print("   AUTOMATE: CONVERSOR CSV A EXCEL")
    print("========================================\n")
    
    convert_csv_to_excel()
    
    print("\n========================================")
    print("Proceso finalizado.")
    input("Presiona Enter para cerrar...")
