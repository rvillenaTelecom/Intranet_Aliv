import subprocess
import sys
import os
import logging
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

log_file = LOG_DIR / f"pipeline_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
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


def main(fase: str = "ambas", incremental: bool = False):
    log.info(f"Log guardado en: {log_file}")
    log.info(f"Fecha de ejecucion: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # ------------------------------------------------------------------
    # FASE 1 — Descargas y consolidacion (totalmente automatica)
    # ------------------------------------------------------------------
    if fase in ("ambas", "1"):
        separador("FASE 1: DESCARGAS Y CONSOLIDACION")

        pasos_fase1 = [
            "WinforceLima2026.py",
            "WinforceProvincia2026.py",
            "Zonificación_Lima.py",
            "Consolidar_Ventas.py",
        ]

        for script in pasos_fase1:
            # En modo diario/incremental, saltamos la consolidación de ventas (Opción 4)
            if incremental and "Consolidar_Ventas" in script:
                continue
                
            # Solo aplicamos incremental a los scripts que lo soportan (Winforce y Zonificacion)
            usa_incremental = incremental and ("Winforce" in script or "Zonificacion" in script or "Zonificación" in script)
            ok = correr_script(script, critico=True, incremental=usa_incremental)
            if not ok:
                log.error("Pipeline detenido en Fase 1.")
                sys.exit(1)

        log.info("Fase 1 completada.")

    # ------------------------------------------------------------------
    # FASE 2 — Extraccion de KPIs y reporte (requiere Power BI abierto)
    # ------------------------------------------------------------------
    if fase in ("ambas", "2"):
        separador("FASE 2: REPORTE (Power BI debe estar abierto)")
        log.info("IMPORTANTE: Asegurate de tener abierto 'Reporte Aliv Data AB' en Power BI Desktop.")

        ok = correr_script("ExtraerDatos.py", critico=True)
        if not ok:
            log.error("No se pudo extraer datos de Power BI. Verifica que Power BI Desktop este abierto.")
            log.error("Pipeline detenido en Fase 2.")
            sys.exit(1)

        ok = correr_script("ReporteSemanal.py", critico=True)
        if not ok:
            log.error("Pipeline detenido en Fase 2.")
            sys.exit(1)

        log.info("Fase 2 completada.")

    separador("PIPELINE FINALIZADO")
    log.info(f"Log completo en: {log_file}")


if __name__ == "__main__":
    # Uso:
    #   python run_pipeline.py          -> corre ambas fases
    #   python run_pipeline.py fase1    -> solo descargas
    #   python run_pipeline.py fase2    -> solo reporte (Power BI abierto)
    arg = sys.argv[1].lower() if len(sys.argv) > 1 else "ambas"
    if arg == "fase1":
        main("1")
    elif arg == "fase2":
        main("2")
    elif arg == "daily":
        main("1", incremental=True)
    else:
        main("ambas")
