import os
import sys
from db_config import upload_to_sql, upload_incremental_to_sql
import time
import calendar
import pandas as pd
from datetime import datetime
from playwright.sync_api import sync_playwright

def descargar_reporte_winforce():
    # ---------------------------------------------------------
    # CONFIGURACIÓN (Deberás rellenar estos datos con los reales)
    # ---------------------------------------------------------
    URL_LOGIN = "https://accesoventas.win.pe/" # Cambia por la URL real
    USUARIO = "aescalantep@alivtelecom.pe"
    PASSWORD = "Y&956668626747ar"
    
    # Carpeta donde se guardará el Excel descargado (usando la carpeta actual)
    CARPETA_DESCARGA = os.path.join(os.getcwd(), "descargas_winforce_Dept")
    os.makedirs(CARPETA_DESCARGA, exist_ok=True)

    print("Iniciando automatización con Playwright...")
    with sync_playwright() as p:
        # Abrimos Chromium
        # headless=True: se ejecuta en segundo plano (invisible).
        # Para hacer pruebas viendo cómo funciona, pon headless=False.
        # Intentar con Chromium estandar y un User-Agent comun para evitar el bloqueo del WAF
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            accept_downloads=True,
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            # 1. Entra a Winforce
            print("1. Accediendo a la pagina de login...")
            page.goto(URL_LOGIN)

            # 2. Flujo de Login con Microsoft
            print("2. Iniciando sesion con Microsoft...")
            
            # Esperar a que la pagina cargue un poco
            page.wait_for_load_state("domcontentloaded")
            
            # Clic en el boton de login con Microsoft
            ms_clicked = False
            for loc in [
                page.get_by_text("Iniciar con Microsoft", exact=True),
                page.locator("button.login-button.azure"),
                page.get_by_text("Iniciar sesión con Microsoft", exact=False),
                page.get_by_text("Sign in with Microsoft", exact=False),
                page.get_by_role("button").filter(has_text="Microsoft"),
                page.locator("a, button").filter(has_text="Microsoft"),
            ]:
                try:
                    loc.first.wait_for(state="visible", timeout=8000)
                    loc.first.click()
                    ms_clicked = True
                    break
                except:
                    continue
            if not ms_clicked:
                page.screenshot(path="Intranet/static/error_winforce_prov.png")
                raise Exception("No se encontro el boton de login con Microsoft. Revisa error_winforce_prov.png en la carpeta static")
            
            # Al hacer clic, nos redirige a login.microsoftonline.com. 
            # Los selectores aquí son estándar:
            print("   Escribiendo correo...")
            page.wait_for_selector("input[type='email']")
            page.fill("input[type='email']", USUARIO)
            page.click("input[type='submit']") # Botón Siguiente
            
            print("   Escribiendo contrasena...")
            page.wait_for_selector("input[type='password']")
            page.fill("input[type='password']", PASSWORD)
            # Pequeña espera por si hay animaciones
            time.sleep(1)
            page.click("input[type='submit']") # Botón Iniciar sesión
            
            print("   Pantalla '¿Mantener iniciada la sesión?'...")
            # Microsoft a veces pregunta, damos clic en "No" u omitimos si no aparece.
            try:
                page.wait_for_selector("input[value='No']", timeout=5000) 
                page.click("input[value='No']")
            except:
                try: 
                    # Otra variante del botón "No" en Microsoft
                    page.wait_for_selector("input#idBtn_Back", timeout=3000)
                    page.click("input#idBtn_Back")
                except:
                    pass # Si no aparece nada, simplemente seguimos
            
            print("2.5 Redirigiendo de vuelta a Winforce y cargando Dashboard...")
            # Esperamos a que el login finalice y cargue Winforce
            page.wait_for_load_state("networkidle")

            # A veces hay popups o avisos, intentamos cerrarlos
            try:
                page.get_by_role("button", name="Aceptar").click(timeout=3000)
                print("   Cerrado popup de 'Aceptar'")
            except:
                pass

            # 3. Navega a la sección Ventas -> Ventas
            print("3. Navegando al menú Ventas -> Ventas...")
            page.wait_for_load_state("networkidle")
            time.sleep(3) # Pausa para que el JS termine de renderizar el menu
            
            # Buscamos el menu "Ventas" y esperamos a que sea visible
            menu_principal = page.locator("text='Ventas'").first
            try:
                menu_principal.wait_for(state="visible", timeout=30000)
            except:
                page.screenshot(path="Intranet/static/error_winforce_prov.png")
                raise Exception("No se encontro el menu 'Ventas'. Revisa la imagen en static/error_winforce_prov.png")
                
            menu_principal.hover()
            menu_principal.click()
            
            # Esperamos a que el submenú aparezca
            print("   Esperando el submenú...")
            # En Winforce, el submenu suele ser el segundo elemento con texto "Ventas"
            submenu = page.get_by_text("Ventas", exact=True).nth(1)
            submenu.wait_for(state="visible", timeout=20000)
            submenu.click()
            
            print("   Esperando que cargue la vista de ventas...")
            page.wait_for_load_state("networkidle")
            time.sleep(2) # Pausa extra por si el renderizado tarda

            # 4. Aplica los filtros del mes actual
            print("4. Aplicando filtros (Desde - Hasta del mes actual)...")
            
            # Calculamos las fechas
            hoy = datetime.now()
            
            # Detectar modo incremental (por defecto es completo)
            incremental = "--incremental" in sys.argv
            
            if incremental:
                from datetime import timedelta
                siete_dias_atras = hoy - timedelta(days=7)
                primer_dia = siete_dias_atras.strftime("%d-%m-%Y")
                print(f"   [MODO INCREMENTAL] Descargando ultimos 7 dias.")
            else:
                primer_dia = "01-01-2026"
                print(f"   [MODO COMPLETO] Descargando todo el 2026.")

            # El usuario indic que "Hasta" sea hasta la fecha actual (hoy)
            ultimo_dia = hoy.strftime("%d-%m-%Y")
            
            print(f"   Rango calculado: {primer_dia} al {ultimo_dia}")
            
            # Los campos tienen "readonly" (flatpickr-input) por lo que el clásico .fill() falla buscando permitir escritura.
            # Por lo tanto enviamos el valor directamente usando javascript nativo (evaluate) ignorando la restricción,
            # y simulamos un evento 'change' para que la página sea consciente de esta actualización.
            
            loc_desde = page.locator("xpath=//*[contains(text(),'Desde')]/following::input[1]")
            loc_desde.evaluate(f"(el) => {{ el.value = '{primer_dia}'; el.dispatchEvent(new Event('change', {{ bubbles: true }})); }}")
            
            loc_hasta = page.locator("xpath=//*[contains(text(),'Hasta')]/following::input[1]")
            loc_hasta.evaluate(f"(el) => {{ el.value = '{ultimo_dia}'; el.dispatchEvent(new Event('change', {{ bubbles: true }})); }}")
            
            # 5. Hace clic en "Buscar"
            print("5. Dando clic en Buscar...")
            # Buscamos el botón por texto (rol botón con texto visible Buscar)
            page.get_by_role("button", name="Buscar").click()

            # 6. Espera que carguen los resultados
            print("6. Esperando a que el sistema traiga los registros...")
            # Retraso preventivo porque no sabemos cuánto demora Winforce, ajustarlo de ser necesario
            time.sleep(8) 

            # 7 & 8. Espera por descarga al hacer clic en "Descargar"
            print("7. Haciendo clic en el botón Descargar...")
            with page.expect_download() as download_info:
                page.get_by_role("button", name="Descargar").click()
            
            download = download_info.value

            # 9. Guarda el archivo en tu carpeta
            # Forzamos a que sea .xlsx
            suggested_name = download.suggested_filename
            temp_path = os.path.join(CARPETA_DESCARGA, suggested_name)
            download.save_as(temp_path)
            
            ruta_final = os.path.join(CARPETA_DESCARGA, "Winforce_Provincia.xlsx")
            
            if not suggested_name.lower().endswith(".xlsx"):
                print(f"   Convirtiendo {suggested_name} a .xlsx...")
                try:
                    df = None
                    # Leemos el archivo (podría ser .xls, .csv o HTML)
                    if suggested_name.lower().endswith(".csv"):
                        df = pd.read_csv(temp_path)
                    else:
                        try:
                            # Intentamos como Excel real (.xls o .xlsx)
                            df = pd.read_excel(temp_path)
                        except Exception:
                            # Muchos sistemas exportan HTML como .xls
                            try:
                                print("   Detectado posible formato HTML, reintentando lectura...")
                                dfs = pd.read_html(temp_path)
                                if dfs:
                                    df = dfs[0]
                            except Exception as e_html:
                                print(f"   Error leyendo como HTML: {e_html}")
                    
                    if df is not None:
                        df.to_excel(ruta_final, index=False)
                        print(f"   Conversión exitosa.")
                        # Intentamos borrar el temporal
                        try:
                            os.remove(temp_path)
                        except:
                            pass
                    else:
                        raise ValueError("No se pudo extraer data del archivo")

                except Exception as conv_err:
                    print(f"   Error al convertir: {conv_err}. Intentando renombrar...")
                    # Pequeña pausa para liberar el archivo si hay un lock residual
                    time.sleep(2)
                    try:
                        if os.path.exists(ruta_final): os.remove(ruta_final)
                        os.rename(temp_path, ruta_final)
                        print("   Archivo renombrado como alternativa.")
                    except Exception as rename_err:
                        print(f"   No se pudo renombrar: {rename_err}")
            else:
                # Si ya es .xlsx, solo lo movemos al nombre final
                if os.path.exists(ruta_final):
                    os.remove(ruta_final)
                os.rename(temp_path, ruta_final)

            print(f"8. [OK] El reporte se guardo correctamente en: {ruta_final}")
            
            # Carga a SQL Server
            try:
                print("   Iniciando carga a SQL Server...")
                df_sql = pd.read_excel(ruta_final)
                
                incremental = "--incremental" in sys.argv
                if incremental:
                    upload_incremental_to_sql(df_sql, "winforce_provincia", "Fecha de registro")
                else:
                    upload_to_sql(df_sql, "winforce_provincia")
                    
            except Exception as sql_e:
                print(f"   [SQL] Error al cargar: {sql_e}")
            # Tu script de correo que procesa el Excel puede continuar a partir de ver este archivo generado

        except Exception as e:
            print(f"Ocurrio un error en la ejecucion: {e}")
            try:
                page.screenshot(path="error_ejecucion.png")
                print("Se ha guardado 'error_ejecucion.png' para que puedas ver donde fallo.")
            except:
                pass
            sys.exit(1)
        
        finally:
            print("Cerrando navegador...")
            context.close()
            browser.close()

if __name__ == "__main__":
    descargar_reporte_winforce()
