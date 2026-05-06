import os
import sys
from db_config import upload_to_sql
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
    USUARIO = "aescalantel@alivtelecom.pe"
    PASSWORD = "B^308708891216um"
    
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
            page.wait_for_load_state("networkidle")
            print(f"   Pagina cargada: {page.title()} - URL: {page.url}")
            
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
                page.screenshot(path="Intranet/static/error_winforce.png")
                raise Exception("No se encontro el boton de login con Microsoft. Revisa error_winforce.png en la carpeta static")
            
            # Al hacer clic, nos redirige a login.microsoftonline.com. 
            # Los selectores aquí son estándar:
            print("   Escribiendo correo...")
            page.wait_for_selector("input[type='email']")
            page.fill("input[type='email']", USUARIO)
            page.click("input[type='submit']") # Botón Siguiente
            
            print("   Escribiendo contrasena...")
            password_field = page.locator("input[type='password'], input[name='passwd']")
            password_field.wait_for(state="visible", timeout=15000)
            password_field.click()
            time.sleep(1)
            password_field.press_sequentially(PASSWORD, delay=100)
            
            # Pequeña espera para que Microsoft procese el texto
            time.sleep(2)
            page.click("input[type='submit'], #idSIButton9") # Botón Iniciar sesión
            
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
            page.wait_for_load_state("networkidle")
            
            # A veces hay popups o avisos, intentamos cerrarlos
            try:
                page.get_by_role("button", name="Aceptar").click(timeout=3000)
                print("   Cerrado popup de 'Aceptar'")
            except:
                pass
            
            # Winforce puede mostrar error 500 repetidamente.
            # Reintentamos hasta 10 veces haciendo clic en 'Sign in' cada vez que aparezca.
            for intento in range(10):
                page.wait_for_load_state("networkidle")
                try:
                    sign_in_btn = page.get_by_role("button", name="Sign in")
                    if sign_in_btn.is_visible():
                        print(f"   [AVISO] Error 500 de Winforce (intento {intento+1}/10). Reintentando...")
                        sign_in_btn.click()
                        time.sleep(2)
                        continue  # vuelve al inicio del loop
                except:
                    pass
                # Si no hay boton 'Sign in', salimos del loop (cargó bien)
                print(f"   Dashboard cargado correctamente en intento {intento+1}.")
                break
            else:
                raise Exception("Winforce no cargó tras 10 reintentos de error 500.")

            # 3. Navega a la seccion Ventas -> Ventas
            print("3. Navegando al menu Ventas -> Ventas...")
            page.wait_for_load_state("networkidle")
            
            # Verificamos si ya estamos en la pagina con filtros de fecha
            ya_en_ventas = page.locator(".flatpickr-input").count() > 0
            
            if ya_en_ventas:
                print("   [INFO] Ya estamos en la pagina de ventas. Saltando navegacion.")
            else:
                # Hacemos clic en 'Ventas' en cualquier parte de la pagina (la barra de navegacion)
                print("   Buscando menu Ventas...")
                page.get_by_text("Ventas", exact=True).first.click()
                time.sleep(2)
                
                # Ahora deberia aparecer un dropdown con 'Ventas', lo clickeamos
                ventas_options = page.get_by_text("Ventas", exact=True).all()
                if len(ventas_options) >= 2:
                    ventas_options[1].click()
                    print("   Submenu 'Ventas' clickeado.")
                else:
                    # Si solo hay uno, ya estamos donde queremos
                    print("   [INFO] Un solo elemento 'Ventas', continuando.")
                
                # Esperamos la pagina de ventas con los filtros
                page.wait_for_load_state("networkidle")
                
                # Verificamos que llegamos a la pagina correcta
                if page.locator(".flatpickr-input").count() == 0:
                    page.screenshot(path="error_winforce.png")
                    raise Exception("No se encontraron los filtros de fecha tras navegar a Ventas. Revisa /ver-error")
            
            print("   Esperando que cargue la vista de ventas...")
            page.wait_for_load_state("networkidle")
            time.sleep(3) # Pausa extra para que flatpickr inicialice los calendarios

            # 4. Aplica los filtros de fecha
            print("4. Aplicando filtros (Desde - Hasta del mes actual)...")
            
            hoy = datetime.now()
            incremental = "--incremental" in sys.argv
            
            # Esperamos a que la pagina este lista
            page.wait_for_selector(".flatpickr-input", timeout=30000)
            time.sleep(1)
            
            if incremental:
                # Para modo incremental: clic en "Esta semana" (boton de acceso rapido de Winforce)
                print("   [MODO INCREMENTAL] Usando boton 'Esta semana'...")
                try:
                    esta_semana = page.get_by_text("Esta semana", exact=True).first
                    esta_semana.click()
                    time.sleep(1)
                    print("   Boton 'Esta semana' clickeado.")
                except:
                    # Fallback: poner fechas manualmente
                    from datetime import timedelta
                    siete_dias_atras = hoy - timedelta(days=7)
                    primer_dia = siete_dias_atras.strftime("%d-%m-%Y")
                    ultimo_dia = hoy.strftime("%d-%m-%Y")
                    print(f"   [FALLBACK] Rango manual: {primer_dia} al {ultimo_dia}")
                    page.evaluate(f"""
                        () => {{
                            const inputs = document.querySelectorAll('input.flatpickr-input');
                            if (inputs.length >= 1 && inputs[0]._flatpickr) {{
                                inputs[0]._flatpickr.setDate('{primer_dia}', true, 'd-m-Y');
                            }}
                            if (inputs.length >= 2 && inputs[1]._flatpickr) {{
                                inputs[1]._flatpickr.setDate('{ultimo_dia}', true, 'd-m-Y');
                            }}
                        }}
                    """)
            else:
                # Modo completo: poner fechas 01-01-2026 hasta hoy
                primer_dia = "01-01-2026"
                ultimo_dia = hoy.strftime("%d-%m-%Y")
                print(f"   [MODO COMPLETO] Rango: {primer_dia} al {ultimo_dia}")
                page.evaluate(f"""
                    () => {{
                        const inputs = document.querySelectorAll('input.flatpickr-input');
                        if (inputs.length >= 1 && inputs[0]._flatpickr) {{
                            inputs[0]._flatpickr.setDate('{primer_dia}', true, 'd-m-Y');
                        }} else if (inputs.length >= 1) {{
                            inputs[0].value = '{primer_dia}';
                            inputs[0].dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}
                        if (inputs.length >= 2 && inputs[1]._flatpickr) {{
                            inputs[1]._flatpickr.setDate('{ultimo_dia}', true, 'd-m-Y');
                        }} else if (inputs.length >= 2) {{
                            inputs[1].value = '{ultimo_dia}';
                            inputs[1].dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}
                    }}
                """)
                print(f"   Fechas establecidas via Flatpickr API.")
            
            time.sleep(1)
            
            # 5. Hace clic en "Buscar seguimiento" (nombre exacto del boton naranja)
            print("5. Dando clic en Buscar seguimiento...")
            page.get_by_role("button", name="Buscar seguimiento").click()

            # 6. Espera que carguen los resultados
            print("6. Esperando a que el sistema traiga los registros...")
            time.sleep(8)
            
            # Verificar si hay resultados antes de intentar descargar.
            page_content = page.content()
            page.screenshot(path="error_winforce.png")  # foto de diagnostico
            if 'Sin resultados que listar' in page_content or 'Ningún dato disponible' in page_content:
                print("   [AVISO] No hay datos en el rango de fechas. Saltando descarga.")
                return

            # 7 & 8. Espera por descarga al hacer clic en "Descargar"
            print("7. Haciendo clic en el botón Descargar...")
            with page.expect_download() as download_info:
                page.get_by_role("button", name="Descargar").click()
            
            download = download_info.value

            # 9. Guarda el archivo en tu carpeta con el nombre 'Winforce_Lima'
            # Forzamos a que sea .xlsx
            suggested_name = download.suggested_filename
            temp_path = os.path.join(CARPETA_DESCARGA, suggested_name)
            download.save_as(temp_path)
            
            ruta_final = os.path.join(CARPETA_DESCARGA, "Winforce_Lima.xlsx")
            
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
