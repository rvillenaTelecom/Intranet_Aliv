"""
test_aliv_login.py
===================
Script de DIAGNOSTICO (no de produccion) para el sistema Aliv Sistema de
Ventas (https://alivtelecom.com/alivsistemaventas/index2.php), previo a
automatizar la descarga de "Ventas Aliv" y "Referidos" (reemplazo de la
descarga manual que hoy alimenta Subida_Aliv.py / Subida_Referidos.py).

La pagina usa framesets clasicos (frame "abajo" = login/contenido, frame
"arriba" = menu), igual que documenta Morosidad/scripts/Morosidad2.py.

Que hace:
    1. Abre el sitio con Playwright (headless=False para poder observar).
    2. Entra al frame "abajo", llena usuario/clave y ejecuta Procesa().
    3. Toma capturas de pantalla antes/despues del login.
    4. Guarda el HTML de cada frame (abajo/arriba) para poder ubicar los
       selectores reales del menu "Ventas Win Activas" y "Referidos".
    5. Reporta si el login parece haber funcionado (busca el mensaje de
       error "No ha iniciado Sesion" que aparece en la captura de referencia).

Uso:
    python test_aliv_login.py
"""

import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

URL_LOGIN = "https://alivtelecom.com/alivsistemaventas/index2.php"
USUARIO = os.environ.get('ALIV_SISTEMA_USUARIO')
PASSWORD = os.environ.get('ALIV_SISTEMA_PASSWORD')

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "descargas_winforce_Dept", "_debug_aliv_login")


def test_login():
    os.makedirs(OUT_DIR, exist_ok=True)

    print("=" * 60)
    print("TEST DE LOGIN - ALIV SISTEMA DE VENTAS")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        try:
            print(f"1. Abriendo {URL_LOGIN} ...")
            page.goto(URL_LOGIN)
            page.wait_for_load_state("networkidle")
            page.screenshot(path=os.path.join(OUT_DIR, "01_antes_login.png"))

            frame_names = [f.name for f in page.frames]
            print(f"   Frames encontrados: {frame_names}")

            frame_abajo = page.frame(name="abajo")
            if frame_abajo is None:
                raise Exception(f"No se encontro el frame 'abajo'. Frames disponibles: {frame_names}")

            print("2. Completando usuario y clave...")
            frame_abajo.fill("#usuario", USUARIO)
            frame_abajo.fill("#clave", PASSWORD)

            print("3. Ejecutando Procesa()...")
            frame_abajo.evaluate("Procesa()")
            page.wait_for_timeout(3000)
            page.wait_for_load_state("networkidle")

            page.screenshot(path=os.path.join(OUT_DIR, "02_despues_login.png"))

            # Volvemos a buscar los frames (pueden haberse recreado tras el login)
            frame_names_post = [f.name for f in page.frames]
            print(f"   Frames tras login: {frame_names_post}")

            frame_abajo_post = page.frame(name="abajo")
            html_abajo = frame_abajo_post.content() if frame_abajo_post else "<sin frame abajo>"
            with open(os.path.join(OUT_DIR, "frame_abajo.html"), "w", encoding="utf-8") as f:
                f.write(html_abajo)

            frame_arriba_post = page.frame(name="arriba")
            html_arriba = frame_arriba_post.content() if frame_arriba_post else "<sin frame arriba>"
            with open(os.path.join(OUT_DIR, "frame_arriba.html"), "w", encoding="utf-8") as f:
                f.write(html_arriba)

            error_login = "No ha iniciado Sesion" in html_abajo or "No ha iniciado Sesión" in html_abajo

            print("\n" + "=" * 60)
            if error_login:
                print("RESULTADO: LOGIN FALLIDO (se detecto 'No ha iniciado Sesion')")
                print(f"Revisa las credenciales. Usuario probado: {USUARIO}")
            else:
                print("RESULTADO: LOGIN OK (no se detecto mensaje de error)")
                print("Revisa frame_arriba.html para ubicar el menu y sus opciones.")
            print(f"Capturas y HTML guardados en: {OUT_DIR}")
            print("=" * 60)

        except Exception as e:
            print(f"\nERROR durante el test: {e}")
            try:
                page.screenshot(path=os.path.join(OUT_DIR, "error.png"))
                print(f"Captura de error guardada en {OUT_DIR}\\error.png")
            except Exception:
                pass
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    test_login()
