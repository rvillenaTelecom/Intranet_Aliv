"""
PIPELINE DE MOROSIDAD — ALIV TELECOM
=====================================
Arquitectura completa de automatización diaria.

Componentes:
  1. scraper.py      → descarga el reporte del sistema Aliv
  2. procesar.py     → limpia y clasifica los datos
  3. cargar_sql.py   → sube a SQL Server
  4. ejecutar.bat    → corre todo en orden (programar con Task Scheduler)

REQUISITOS:
  pip install selenium webdriver-manager pandas pyodbc sqlalchemy

CONFIGURACIÓN:
  Editar el bloque CONFIG antes de usar.
"""

# ─────────────────────────────────────────────────────────────
# CONFIGURACIÓN — editar estos valores
# ─────────────────────────────────────────────────────────────
CONFIG = {
    # Sistema Aliv
    "url_login":    "https://alivtelecom.com/alivsistemaventas/index2.php",   # URL del login
    "url_reporte":  "https://alivtelecom.com/alivsistemaventas/index2.php",  # URL del reporte
    "usuario":      "rramirez",
    "password":     "NUEVO2025",

    # Filtros del reporte (ajustar según el sistema)
    "filtro_estado": "INSTALADO",
    "meses_atras":   4,   # cuántos meses hacia atrás descargar

    # SQL Server
    "sql_server":   r".\SQLEXPRESS",
    "sql_db":       "Aliv_DB",
    "sql_tabla":    "morosidad_diaria",

    # Carpeta de trabajo (se resuelve automáticamente desde la ubicación del script)
    "carpeta":      str(__import__("pathlib").Path(__file__).parent),
}

import os
import time
import pandas as pd
from datetime import datetime, timedelta
from difflib import get_close_matches

# ═══════════════════════════════════════════════════════════
# MÓDULO 1 — SCRAPER
# Hace login en el sistema Aliv y descarga el reporte
# ═══════════════════════════════════════════════════════════

def descargar_reporte(config):
    """
    Abre el navegador, hace login, aplica filtros y descarga el reporte.
    Devuelve la ruta del archivo descargado.

    NOTA: Esta función se completa una vez que tengamos la URL
    y capturas del sistema. Los selectores CSS/XPath se ajustan
    al HTML real del sistema.
    """
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    carpeta_descarga = config["carpeta"]
    os.makedirs(carpeta_descarga, exist_ok=True)

    # Configurar Chrome para descargar automáticamente
    opciones = webdriver.ChromeOptions()
    # Desactivamos el modo headless temporalmente para evitar bloqueos anti-bots de la web
    # opciones.add_argument('--headless')
    opciones.add_argument('--no-sandbox')
    opciones.add_argument('--disable-dev-shm-usage')
    
    # Configurar directorio de descarga por defecto
    carpeta_descarga = config["carpeta"]
    prefs = {"download.default_directory": carpeta_descarga,
             "download.prompt_for_download":    False,
             "download.directory_upgrade":      True,
             "safebrowsing.enabled":            True}
    opciones.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=opciones
    )
    wait = WebDriverWait(driver, 15)

    try:
        print("  🌐 Abriendo sistema Aliv...")
        driver.get(config["url_login"])

        # ── LOGIN ──────────────────────────────────────────
        time.sleep(2)
        
        # La web usa frames. Cambiamos al frame de contenido
        try:
            driver.switch_to.frame("abajo")
        except:
            pass
            
        # Encontrar y llenar usuario y contraseña con sus IDs reales
        user_input = driver.find_element(By.ID, "usuario")
        pass_input = driver.find_element(By.ID, "clave")
        
        user_input.clear()
        user_input.send_keys(config["usuario"])
        pass_input.clear()
        pass_input.send_keys(config["password"])
        
        # El botón de login llama a la función Procesa()
        driver.execute_script("Procesa();")
        print("  ✓ Login exitoso")

        # ── NAVEGAR AL REPORTE ────────────────────────────
        time.sleep(3)
        print("  Navegando a VENTAS WIN > Ventas Win Activas...")

        # Recargar para que la sesión quede activa en ambos frames
        driver.get(config["url_login"])
        time.sleep(3)

        # Menú está en frame "arriba"
        driver.switch_to.default_content()
        driver.switch_to.frame("arriba")

        menu_win = wait.until(EC.presence_of_element_located(
            (By.XPATH, "//*[contains(text(),'VENTAS WIN') or contains(text(),'Ventas Win')]")
        ))
        driver.execute_script("arguments[0].click();", menu_win)
        time.sleep(1.5)

        submenu = wait.until(EC.presence_of_element_located(
            (By.XPATH, "//*[contains(text(),'Ventas Win Activas') or contains(text(),'VENTAS WIN ACTIVAS')]")
        ))
        driver.execute_script("arguments[0].click();", submenu)

        # Esperar que el frame "abajo" cargue la página de Ventas Win Activas
        # (se detecta cuando aparece el botón "Exportar Datos")
        print("  Esperando que cargue la pagina...")
        driver.switch_to.default_content()
        wait_carga = WebDriverWait(driver, 30)
        for _ in range(10):
            try:
                driver.switch_to.default_content()
                driver.switch_to.frame("abajo")
                driver.find_element(By.XPATH, "//*[contains(text(),'Exportar Datos') or contains(text(),'VENTAS WIN ACTIVAS')]")
                break
            except:
                time.sleep(2)
        else:
            raise Exception("Timeout: la pagina de Ventas Win Activas no cargo en 20 segundos.")

        # ── APLICAR FILTROS ───────────────────────────────
        print("  Aplicando filtros de fecha...")
        fecha_inicio = "01-01-2026"
        fecha_fin    = datetime.now().strftime("%d-%m-%Y")

        try:
            # La página tiene estos inputs de texto en orden:
            # [0] Filtro 1 texto, [1] Filtro 2 texto ("win"),
            # [2] F. Instalación/Activación Desde  ← estos necesitamos
            # [3] F. Instalación/Activación Hasta  ←
            all_inputs = driver.find_elements(By.XPATH, "//input[@type='text']")
            if len(all_inputs) >= 4:
                for inp in (all_inputs[2], all_inputs[3]):
                    driver.execute_script("arguments[0].value='';", inp)
                    inp.clear()
                all_inputs[2].send_keys(fecha_inicio)
                all_inputs[3].send_keys(fecha_fin)
                print(f"  Fechas aplicadas: {fecha_inicio} — {fecha_fin}")
            else:
                print(f"  [AVISO] Solo {len(all_inputs)} inputs encontrados.")
        except Exception as e:
            print(f"  [AVISO] No se pudieron establecer fechas: {e}")

        # Botón Buscar
        try:
            btn_buscar = driver.find_element(
                By.XPATH,
                "//input[contains(translate(@value,'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'BUSCAR')]"
                " | //button[contains(translate(.,'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'BUSCAR')]"
            )
            driver.execute_script("arguments[0].click();", btn_buscar)
            print("  Buscar clickeado, esperando resultados...")
            time.sleep(5)
        except Exception as e:
            print(f"  [AVISO] No se encontro boton Buscar: {e}")

        # ── EXPORTAR ──────────────────────────────────────
        print("  Iniciando descarga...")
        try:
            driver.save_screenshot(os.path.join(carpeta_descarga, "_debug_exportar.png"))
        except:
            pass

        # Ya estamos en frame "abajo" — esperar el botón "Exportar Datos" (hasta 90s)
        wait_export = WebDriverWait(driver, 90)
        btn_exportar = wait_export.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//*[contains(text(),'Exportar Datos')] | //input[contains(@value,'Exportar Datos')]")
            )
        )
        print("  Boton 'Exportar Datos' encontrado.")
        driver.execute_script("arguments[0].click();", btn_exportar)

        # Esperar que el archivo se descargue
        print("  ⏳ Esperando que termine la descarga...")
        tiempo_limite = 120  # segundos
        archivo_descargado = None
        for _ in range(tiempo_limite):
            archivos = [f for f in os.listdir(carpeta_descarga)
                       if f.endswith((".xls", ".xlsx", ".csv")) and "part" not in f and "crdownload" not in f
                       and not f.lower().startswith(("usuarios", "ventas", "winforce", "zonas", "morosidad"))]
            if archivos:
                # Tomar el modificado más recientemente (recién descargado)
                rutas_completas = [os.path.join(carpeta_descarga, a) for a in archivos]
                archivo_descargado = max(rutas_completas, key=os.path.getmtime)
                break
            time.sleep(1)

        if not archivo_descargado:
            raise Exception("Tiempo de espera agotado — el archivo no se descargó")

        print(f"  ✓ Archivo descargado exitosamente: {archivo_descargado}")
        return archivo_descargado

    finally:
        driver.quit()


# ═══════════════════════════════════════════════════════════
# MÓDULO 2 — PROCESAMIENTO
# Lee el archivo, limpia y clasifica los datos
# ═══════════════════════════════════════════════════════════

def procesar_reporte(ruta_archivo, *args, **kwargs):
    """
    Lee el archivo crudo descargado de Aliv Telecom y lo prepara
    únicamente sanitizando los nombres de las columnas para SQL Server.
    No realiza cruces ni filtros de negocio, manteniendo el Excel 'tal cual'.
    """
    print(f"\n📖 Procesando {ruta_archivo} (Carga cruda)...")
    
    # Leer el archivo (es un HTML disfrazado de .xls)
    try:
        tablas = pd.read_html(ruta_archivo, encoding="utf-8")
        df = tablas[0]
        # Si las columnas son 0, 1, 2... o "Unnamed", la primera fila es el header real
        if str(df.columns[0]) == "0" or "Unnamed" in str(df.columns[0]):
            df.columns = df.iloc[0]
            df = df.iloc[1:].reset_index(drop=True)
    except Exception:
        df = pd.read_excel(ruta_archivo)

    print(f"  Total registros leídos: {len(df):,}")

    # Sanitizar nombres de columnas para SQL
    df.columns = (
        df.columns
        .astype(str)
        .str.replace(r"[^a-zA-Z0-9_]", "_", regex=True)
        .str.replace(r"_+", "_", regex=True)
        .str.strip("_")
    )

    # Fecha de actualización
    df["Fecha_Actualizacion"] = datetime.now().strftime("%Y-%m-%d")

    print(f"  ✓ Procesado: {len(df):,} registros listos")
    return df


# ═══════════════════════════════════════════════════════════
# MÓDULO 3 — CARGA A SQL SERVER
# Sube el DataFrame a SQL Server, reemplazando datos del día
# ═══════════════════════════════════════════════════════════

def cargar_sql(df, config):
    """
    Sube el DataFrame a SQL Server.
    Estrategia: reemplaza TODA la tabla cada día (full refresh).
    Así Power BI siempre lee el estado más reciente.
    """
    try:
        from sqlalchemy import create_engine, text
        import urllib
    except ImportError:
        print("❌ Instala: pip install sqlalchemy pyodbc")
        return False

    print(f"\n💾 Subiendo a SQL Server ({config['sql_server']}/{config['sql_db']})...")

    # Cadena de conexión (Autenticación de Windows)
    params = urllib.parse.quote_plus(
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={config['sql_server']};"
        f"DATABASE={config['sql_db']};"
        f"Trusted_Connection=yes;"
    )
    engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

    # Limpiar columnas para SQL (sin caracteres especiales)
    df.columns = (
        df.columns
        .str.replace(r"[^a-zA-Z0-9_]", "_", regex=True)
        .str.replace(r"_+", "_", regex=True)
        .str.strip("_")
    )

    # Subir (reemplaza la tabla completa)
    df.to_sql(
        name      = config["sql_tabla"],
        con       = engine,
        if_exists = "replace",   # reemplaza cada día con datos frescos
        index     = False,
        chunksize = 1000,        # sube de a 1000 filas para no saturar
    )

    print(f"  ✓ {len(df):,} registros subidos a [{config['sql_tabla']}]")

    # Crear índices para que Power BI consulte rápido
    with engine.connect() as conn:
        try:
            conn.execute(text(f"""
                IF NOT EXISTS (
                    SELECT * FROM sys.indexes
                    WHERE name='idx_dni' AND object_id = OBJECT_ID('{config["sql_tabla"]}')
                )
                CREATE INDEX idx_dni ON {config["sql_tabla"]} (DNI_Carnet_Extraj)
            """))
            conn.execute(text(f"""
                IF NOT EXISTS (
                    SELECT * FROM sys.indexes
                    WHERE name='idx_mes' AND object_id = OBJECT_ID('{config["sql_tabla"]}')
                )
                CREATE INDEX idx_mes ON {config["sql_tabla"]} (Mes_Cohorte)
            """))
            conn.commit()
            print("  ✓ Índices creados (DNI, Mes_Cohorte)")
        except Exception as e:
            print(f"  ⚠️  Índices: {e}")

    return True


# ═══════════════════════════════════════════════════════════
# PROGRAMA PRINCIPAL — ejecuta todo el pipeline
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":

    inicio = datetime.now()
    print("=" * 60)
    print("  PIPELINE MOROSIDAD — ALIV TELECOM")
    print(f"  {inicio.strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 60)

    carpeta      = CONFIG["carpeta"]
    usuarios_win = os.path.join(carpeta, "Usuarios_Win.xlsx")

    # ── PASO 1: Descargar reporte desde la web ────────────
    print("\n📥 PASO 1: Descargando reporte...")
    # Ejecuta el robot web
    ruta_archivo = descargar_reporte(CONFIG)

    # ── PASO 2: Procesar datos ────────────────────────────
    print("\n⚙️  PASO 2: Procesando reporte descargado...")
    df = procesar_reporte(ruta_archivo, usuarios_win)

    # ── PASO 3: Subir a SQL ───────────────────────────────
    print("\n🗄️  PASO 3: Subiendo a SQL Server...")
    exito = cargar_sql(df, CONFIG)

    # ── RESUMEN ───────────────────────────────────────────
    duracion = (datetime.now() - inicio).seconds
    tasa = df["Es_Moroso_M1"].mean() if "Es_Moroso_M1" in df.columns else 0

    print("\n" + "=" * 60)
    print("  RESUMEN")
    print("=" * 60)
    print(f"  Registros procesados : {len(df):,}")
    print(f"  Tasa morosidad M1    : {tasa:.1%}")
    print(f"  SQL Server           : {'✅ OK' if exito else '❌ Error'}")
    print(f"  Duración total       : {duracion} segundos")
    print(f"  Próxima ejecución    : mañana a las 06:00 AM")
    print("=" * 60)