"""
DescargaAlivSistemaVentas.py
=============================
Modulo compartido para automatizar el login y la descarga de "Ventas Win
Activas" y "Ventas Win Referidos" desde el Sistema de Ventas Aliv
(https://alivtelecom.com/alivsistemaventas) usando Playwright.

Lo usan Subida_Aliv.py y Subida_Referidos.py, que hacen login + descargan
solo el reporte que necesitan + suben a SQL en un solo paso (ya no requieren
descarga manual previa).

A diferencia de WinforceLima2026.py, este sistema no requiere
zonificacion por KML (el reporte ya trae Departamento/Provincia/Distrito).

Replica el flujo manual:
  - Menu VENTAS WIN > Ventas Win Activas / Ventas Win Referidos
  - Filtro 1 = "win" con criterio "Canal empresa"
  - Activas:   fecha F.Instalacion/Activacion  = 1er dia del mes anterior -> hoy
  - Referidos: fecha Venta/Ingreso              = 1er dia de este mes -> hoy
  - Buscar -> Exportar Datos

El login del sistema es intermitente (a veces no entra al primer intento);
se reintenta recargando la pagina.

Uso standalone (descarga ambos reportes sin subir a SQL):
    python DescargaAlivSistemaVentas.py
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

URL_LOGIN = "https://alivtelecom.com/alivsistemaventas/index2.php"
URL_ACTIVAS = "https://alivtelecom.com/alivsistemaventas/VentasWActivas.php"
URL_REFERIDOS = "https://alivtelecom.com/alivsistemaventas/VentasWReferidos.php"

# Usuario/clave vienen de Pipeline/scripts/.env (ALIV_SISTEMA_USUARIO, ALIV_SISTEMA_PASSWORD).
USUARIO = os.environ.get('ALIV_SISTEMA_USUARIO')
PASSWORD = os.environ.get('ALIV_SISTEMA_PASSWORD')
if not USUARIO or not PASSWORD:
    raise RuntimeError(
        "Faltan ALIV_SISTEMA_USUARIO / ALIV_SISTEMA_PASSWORD en Pipeline/scripts/.env"
    )

CARPETA_DESCARGA = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "descargas_winforce_Dept"
)

ARCHIVO_ACTIVAS = os.path.join(CARPETA_DESCARGA, "Aliv_ventas_activas.xls")
ARCHIVO_REFERIDOS = os.path.join(CARPETA_DESCARGA, "Ventas_Referidos.xls")

FILTRO_CRITERIO = "NombreDivisionEmpresa"  # "Canal empresa" en el <select>
FILTRO_TEXTO = "win"

MAX_INTENTOS_LOGIN = 3


def rango_activas():
    """1er dia del mes anterior -> hoy (columna 'Fecha Activacion')."""
    hoy = datetime.now()
    if hoy.month == 1:
        primer_dia = hoy.replace(year=hoy.year - 1, month=12, day=1)
    else:
        primer_dia = hoy.replace(month=hoy.month - 1, day=1)
    return primer_dia.strftime("%d-%m-%Y"), hoy.strftime("%d-%m-%Y")


def rango_referidos():
    """1er dia de este mes -> hoy (columna 'Fecha Ingreso')."""
    hoy = datetime.now()
    primer_dia = hoy.replace(day=1)
    return primer_dia.strftime("%d-%m-%Y"), hoy.strftime("%d-%m-%Y")


def nuevo_browser(p):
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        accept_downloads=True,
        viewport={"width": 1400, "height": 900},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    )
    return browser, context


def _sesion_activa(page):
    """True si ya estamos logueados (el frame 'abajo' aterrizo en menu.php)."""
    frame_abajo = page.frame(name="abajo")
    return bool(frame_abajo and "menu.php" in (frame_abajo.url or ""))


def login(page):
    """Hace login en el frame 'abajo'. Reintenta recargando si no entra.

    El sistema a veces no procesa el primer intento (hay que refrescar), y si
    un intento anterior si funciono, recargar index2.php aterriza directo en
    menu.php sin formulario de login: ambos casos se manejan aqui.
    """
    for intento in range(1, MAX_INTENTOS_LOGIN + 1):
        print(f"  Intento de login {intento}/{MAX_INTENTOS_LOGIN}...")
        page.goto(URL_LOGIN)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        if _sesion_activa(page):
            print("    Sesion ya activa.")
            return True

        frame_abajo = page.frame(name="abajo")
        if frame_abajo is None or frame_abajo.query_selector("#usuario") is None:
            print("    [AVISO] No se encontro el formulario de login, reintentando...")
            page.wait_for_timeout(1500)
            continue

        try:
            frame_abajo.fill("#usuario", USUARIO, timeout=8000)
            frame_abajo.fill("#clave", PASSWORD, timeout=8000)
            frame_abajo.evaluate("Procesa()")
        except Exception as e:
            print(f"    [AVISO] Error llenando el formulario: {e}")
            page.wait_for_timeout(1500)
            continue

        page.wait_for_timeout(3000)
        page.wait_for_load_state("networkidle")

        if _sesion_activa(page):
            print("    Login exitoso.")
            return True

        print("    [AVISO] Login no confirmado, reintentando...")

    return False


def _descargar_reporte(page, url, fecha_desde, fecha_hasta, ruta_destino, nombre):
    print(f"\n{nombre}: navegando a {url} ...")
    page.goto(url)
    page.wait_for_load_state("networkidle")

    print(f"  Filtro 1 = '{FILTRO_TEXTO}' (Canal empresa), fechas {fecha_desde} -> {fecha_hasta}")
    page.fill('input[name="DatoBuscar"]', FILTRO_TEXTO)
    page.select_option('select[name="criterio1"]', FILTRO_CRITERIO)
    page.fill("#cal-field-1", fecha_desde)
    page.fill("#cal-field-2", fecha_hasta)

    print("  Buscando...")
    page.evaluate("buscaa()")
    page.wait_for_timeout(4000)
    page.wait_for_load_state("networkidle")

    print("  Exportando...")
    with page.expect_download(timeout=60000) as dl_info:
        page.click("#excel")
    download = dl_info.value
    download.save_as(ruta_destino)
    print(f"  [OK] Guardado en: {ruta_destino}")


def descargar_activas(page):
    """Descarga Ventas Win Activas (mes anterior + actual). Devuelve (ruta, fecha_desde, fecha_hasta)."""
    os.makedirs(CARPETA_DESCARGA, exist_ok=True)
    fecha_desde, fecha_hasta = rango_activas()
    _descargar_reporte(page, URL_ACTIVAS, fecha_desde, fecha_hasta, ARCHIVO_ACTIVAS, "VENTAS WIN ACTIVAS")
    return ARCHIVO_ACTIVAS, fecha_desde, fecha_hasta


def descargar_referidos(page):
    """Descarga Ventas Win Referidos (mes actual). Devuelve (ruta, fecha_desde, fecha_hasta)."""
    os.makedirs(CARPETA_DESCARGA, exist_ok=True)
    fecha_desde, fecha_hasta = rango_referidos()
    _descargar_reporte(page, URL_REFERIDOS, fecha_desde, fecha_hasta, ARCHIVO_REFERIDOS, "VENTAS WIN REFERIDOS")
    return ARCHIVO_REFERIDOS, fecha_desde, fecha_hasta


def descargar_aliv_y_referidos():
    """Uso standalone: descarga ambos reportes (sin subir a SQL)."""
    print("=" * 60)
    print("DESCARGA ALIV SISTEMA DE VENTAS (Activas + Referidos)")
    print("=" * 60)

    with sync_playwright() as p:
        browser, context = nuevo_browser(p)
        page = context.new_page()

        try:
            if not login(page):
                raise Exception(f"No se pudo iniciar sesion tras {MAX_INTENTOS_LOGIN} intentos.")

            descargar_activas(page)
            descargar_referidos(page)

            print("\nPROCESO COMPLETADO CON EXITO")

        except Exception as e:
            print(f"\nOcurrio un error en la ejecucion: {e}")
            try:
                page.screenshot(path=os.path.join(CARPETA_DESCARGA, "_error_aliv_sistema_ventas.png"))
                print("Se guardo captura de error en descargas_winforce_Dept/_error_aliv_sistema_ventas.png")
            except Exception:
                pass
            sys.exit(1)

        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    descargar_aliv_y_referidos()
