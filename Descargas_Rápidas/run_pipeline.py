import subprocess
import sys
import os
import io
import logging
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

log_file = LOG_DIR / f"pipeline_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

_stdout_utf8 = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(_stdout_utf8),
    ],
)
log = logging.getLogger(__name__)


def correr_script(nombre_script: str, critico: bool = True, incremental: bool = False) -> bool:
    script_path = BASE_DIR / nombre_script
    log.info(f"Iniciando: {nombre_script} {'[INCREMENTAL]' if incremental else ''}")
    inicio = datetime.now()

    args = [sys.executable, str(script_path)]
    if incremental:
        args.append("--incremental")

    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    duracion = (datetime.now() - inicio).seconds
    salida = (result.stdout + result.stderr).strip()

    if result.returncode == 0:
        log.info(f"OK ({duracion}s): {nombre_script}")
        if salida:
            for linea in salida.splitlines():
                log.info(f"    {linea}")
        return True
    else:
        log.error(f"FALLO ({duracion}s): {nombre_script}")
        if salida:
            for linea in salida.splitlines():
                log.error(f"    {linea}")
        if critico:
            log.error("Paso critico fallido — pipeline detenido.")
        return False


def separador(titulo: str):
    linea = "=" * 55
    log.info(linea)
    log.info(f"  {titulo}")
    log.info(linea)


def main(fase: str = "bd"):
    log.info(f"Log guardado en: {log_file}")
    log.info(f"Fecha de ejecucion: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # ------------------------------------------------------------------
    # FASE BD — Descargas + Zonificacion + subida a BD (sin consolidar)
    # ------------------------------------------------------------------
    if fase == "bd":
        separador("DESCARGA 2026 + ZONIFICACION + BD")

        for script in ["WinforceLima2026.py", "WinforceProvincia2026.py", "Zonificación_Lima.py"]:
            ok = correr_script(script, critico=True, incremental=False)
            if not ok:
                log.error("Pipeline detenido.")
                sys.exit(1)

        log.info("Fase BD completada.")

    # ------------------------------------------------------------------
    # FASE DESCARGAS — Solo descarga Lima + Provincia (sin Zonificacion ni BD)
    # ------------------------------------------------------------------
    if fase == "descargas":
        separador("SOLO DESCARGAS (Lima + Provincia)")

        for script in ["WinforceLima2026.py", "WinforceProvincia2026.py"]:
            ok = correr_script(script, critico=True, incremental=False)
            if not ok:
                log.error("Pipeline detenido.")
                sys.exit(1)

        log.info("Descargas completadas.")

    # ------------------------------------------------------------------
    # FASE SEMANAL — Incremental (esta semana) + Zonificacion
    # ------------------------------------------------------------------
    if fase == "daily":
        separador("SEMANAL: ESTA SEMANA")

        for script in ["WinforceLima2026.py", "WinforceProvincia2026.py", "Zonificación_Lima.py"]:
            ok = correr_script(script, critico=True, incremental=True)
            if not ok:
                log.error("Pipeline detenido.")
                sys.exit(1)

        log.info("Fase semanal completada.")

    # ------------------------------------------------------------------
    # FASE CONSOLIDAR — Solo consolida ventas Lima + Provincia
    # ------------------------------------------------------------------
    if fase == "consolidar":
        separador("CONSOLIDAR VENTAS")

        ok = correr_script("Consolidar_Ventas.py", critico=True)
        if not ok:
            log.error("Pipeline detenido.")
            sys.exit(1)

        log.info("Consolidacion completada.")

    # ------------------------------------------------------------------
    # FASE REPORTE — Extraccion de KPIs y reporte semanal (requiere Power BI)
    # ------------------------------------------------------------------
    if fase == "reporte":
        separador("REPORTE SEMANAL (Power BI debe estar abierto)")
        log.info("IMPORTANTE: Asegurate de tener abierto 'Reporte Aliv Data AB' en Power BI Desktop.")

        ok = correr_script("ExtraerDatos.py", critico=True)
        if not ok:
            log.error("No se pudo extraer datos de Power BI. Verifica que Power BI Desktop este abierto.")
            sys.exit(1)

        ok = correr_script("ReporteSemanal.py", critico=True)
        if not ok:
            sys.exit(1)

        log.info("Reporte semanal completado.")

    # ------------------------------------------------------------------
    # FASE MAESTROS — Sube Cuota_Prov y Usuarios_Win a SQL
    # ------------------------------------------------------------------
    if fase == "maestros":
        separador("SUBIR USUARIOS WIN + MAESTROS")

        ok = correr_script("Cargar_Maestros_SQL.py", critico=True)
        if not ok:
            log.error("Pipeline detenido.")
            sys.exit(1)

        log.info("Carga de maestros completada.")

    # ------------------------------------------------------------------
    # FASE REPORTE DIARIO — Altas de ayer, promedio, top vendedores
    # ------------------------------------------------------------------
    if fase == "reporte_diario":
        separador("REPORTE DIARIO (ayer)")

        for script in ["ReporteDiarioLima.py", "ReporteDiarioProvincia.py", "ReporteDiarioProvinciaNorte.py"]:
            ok = correr_script(script, critico=True)
            if not ok:
                log.error("Pipeline detenido.")
                sys.exit(1)

        log.info("Reporte diario completado.")

    separador("PIPELINE FINALIZADO")
    log.info(f"Log completo en: {log_file}")


if __name__ == "__main__":
    arg = sys.argv[1].lower() if len(sys.argv) > 1 else "bd"
    if arg == "descargas":
        main("descargas")
    elif arg == "daily":
        main("daily")
    elif arg == "reporte":
        main("reporte")
    elif arg == "consolidar":
        main("consolidar")
    elif arg == "maestros":
        main("maestros")
    elif arg == "reporte_diario":
        main("reporte_diario")
    else:
        main("bd")
