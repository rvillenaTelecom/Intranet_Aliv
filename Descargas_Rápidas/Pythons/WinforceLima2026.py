"""
WinforceLima2026.py
===================
Automatiza la descarga del reporte de ventas de Lima desde la plataforma Winforce
usando Playwright (navegador Chromium en modo headless). Realiza login con Microsoft,
aplica filtros de fecha (completo: 01-01-2026 a hoy, o incremental: mes anterior a hoy),
y guarda el Excel en descargas_winforce_Dept/Winforce_Lima.xlsx.

Uso:
    python WinforceLima2026.py              # descarga completa desde 01-01-2026
    python WinforceLima2026.py --incremental # descarga últimos 2 meses

Requisitos:
    pip install playwright && playwright install chromium
"""

import os
import sys
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

def descargar_reporte_winforce():
    # ---------------------------------------------------------
    # CONFIGURACIÓN (Deberás rellenar estos datos con los reales)
    # ---------------------------------------------------------
    URL_LOGIN = "https://accesoventas.win.pe/" # Cambia por la URL real
    USUARIO = "backoffice11@alivtelecom.pe"
    PASSWORD = "C@836235653909oz"
    
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

            # Siempre navegamos: el login puede aterrizar en otra pagina (ej. Seguimiento)
            page.get_by_text("Ventas", exact=True).first.click()
            time.sleep(1)

            ventas_options = page.get_by_text("Ventas", exact=True).all()
            if len(ventas_options) >= 2:
                ventas_options[1].click()
                print("   Submenu 'Ventas' clickeado.")
            else:
                print("   [INFO] Un solo elemento 'Ventas', continuando.")

            # Esperar a que aparezcan los filtros de fecha (no usar networkidle: listaVenta
            # tiene polling continuo que lo bloquea indefinidamente)
            page.wait_for_selector(".flatpickr-input", timeout=20000)
            time.sleep(2)

            # 4. Aplica los filtros de fecha
            print("4. Aplicando filtros (Desde - Hasta del mes actual)...")
            
            hoy = datetime.now()
            incremental = "--incremental" in sys.argv
            
            # Esperamos a que la pagina este lista
            page.wait_for_selector(".flatpickr-input", timeout=30000)
            time.sleep(1)
            
            if incremental:
                # Modo mensual (mes actual y anterior)
                if hoy.month == 1:
                    primer_dia_obj = hoy.replace(year=hoy.year - 1, month=12, day=1)
                else:
                    primer_dia_obj = hoy.replace(month=hoy.month - 1, day=1)
                primer_dia = primer_dia_obj.strftime("%d-%m-%Y")
                ultimo_dia = hoy.strftime("%d-%m-%Y")
                print(f"   [MODO MENSUAL INCREMENTAL] Rango: {primer_dia} al {ultimo_dia}")
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
            
            # Cerrar el calendario Flatpickr si quedó abierto (bloquea el click en Buscar)
            page.keyboard.press("Escape")
            time.sleep(0.5)

            # 5. Hace clic en "Buscar" (boton naranja de Ver ventas)
            print("5. Dando clic en Buscar...")
            page.get_by_role("button", name="Buscar", exact=True).click()

            # 6. Esperar a que la búsqueda termine (el botón se habilite o la tabla quede vacía)
            print("6. Esperando resultados de la busqueda...")
            try:
                res = page.wait_for_function("""() => {
                    const btn = document.querySelector('#descargarventaexcel');
                    const emptyCell = document.querySelector('td.dataTables_empty');
                    
                    // Si el botón no está deshabilitado, terminó la carga y hay datos
                    if (btn && !btn.disabled) {
                        return "ready";
                    }
                    
                    // Si la celda vacía está presente y visible, terminó la carga y no hay datos
                    if (emptyCell && window.getComputedStyle(emptyCell).display !== 'none') {
                        return "empty";
                    }
                    
                    return false;
                }""", timeout=60000)
                
                estado = res.json_value()
                if estado == "empty":
                    print("   [AVISO] No hay datos en el rango de fechas. Saltando descarga.")
                    return
            except Exception as e:
                print(f"   [ERROR] Espera de resultados excedió el tiempo límite: {e}")
                raise
            time.sleep(2)

            # 7. Clic en Descargar
            print("7. Descargando Excel...")
            ruta_final = os.path.join(CARPETA_DESCARGA, "Winforce_Lima.xlsx")
            with page.expect_download(timeout=60000) as dl:
                page.get_by_role("button", name="Descargar", exact=True).click(no_wait_after=True)
            download = dl.value
            ext = os.path.splitext(download.suggested_filename)[1] or ".xlsx"
            ruta_temp = os.path.join(CARPETA_DESCARGA, f"_tmp_lima{ext}")
            download.save_as(ruta_temp)
            import pandas as pd
            with open(ruta_temp, "rb") as f:
                cabecera = f.read(9)
            if cabecera[:5] in (b"<!DOC", b"<html", b"<HTML"):
                # Winforce envia el reporte como tabla HTML (HTML-as-XLS)
                tablas = pd.read_html(ruta_temp, encoding="utf-8")
                if not tablas:
                    os.remove(ruta_temp)
                    raise Exception("HTML descargado pero no contiene tablas de datos.")
                df = tablas[0]
            else:
                try:
                    df = pd.read_excel(ruta_temp, engine="openpyxl")
                except Exception:
                    df = pd.read_excel(ruta_temp, engine="xlrd")
            os.remove(ruta_temp)
            df.to_excel(ruta_final, index=False)
            print(f"8. [OK] {len(df):,} registros guardados en: {ruta_final}")

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
