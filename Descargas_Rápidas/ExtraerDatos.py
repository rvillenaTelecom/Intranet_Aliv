"""
extraer_datos_pbi.py
====================
Extrae datos en vivo de Power BI Desktop via SSAS/ADOMD
y los guarda en data.json para que reporte_mensual_aliv.py lo use.

Requisitos:
    pip install pythonnet
    Power BI Desktop abierto con el archivo "Reporte Aliv Data AB"

Uso (cada vez que quieras actualizar el reporte):
    python extraer_datos_pbi.py
"""

import calendar
import json
import subprocess
import sys
from datetime import datetime, timedelta

# ──────────────────────────────────────────────
# DETECCIÓN AUTOMÁTICA DEL PUERTO DE POWER BI
# ──────────────────────────────────────────────

def encontrar_puerto_pbi():
    """Busca el puerto local de Power BI Desktop (msmdsrv.exe)."""
    try:
        task_res = subprocess.run(
            ["tasklist", "/fi", "imagename eq msmdsrv.exe", "/fo", "csv", "/nh"],
            capture_output=True, text=True
        )
        if "msmdsrv.exe" not in task_res.stdout:
            return None

        import csv, io
        reader = csv.reader(io.StringIO(task_res.stdout))
        pids = [row[1] for row in reader if row]
        if not pids:
            return None
        target_pid = pids[0]

        net_res = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
        for line in net_res.stdout.split("\n"):
            if "LISTENING" in line and target_pid in line:
                parts = line.split()
                if len(parts) >= 5 and parts[-1] == target_pid:
                    port = int(parts[1].split(":")[-1])
                    return port
    except Exception as e:
        print(f"Error detectando puerto: {e}")
    return None


# ──────────────────────────────────────────────
# CONEXIÓN ADOMD
# ──────────────────────────────────────────────

def extraer_via_adomd(puerto):
    """Extrae datos MTD (mes hasta hoy) usando Microsoft.AnalysisServices.AdomdClient."""
    try:
        import clr, os

        dll_paths = [
            r"C:\Users\Usuario\AppData\Local\Microsoft\On-premises data gateway (personal mode)\Microsoft.AnalysisServices.AdomdClient.dll",
            r"C:\Program Files\Microsoft Analysis Services\AS ADOMD\160\Microsoft.AnalysisServices.AdomdClient.dll",
            r"C:\Program Files\Microsoft Analysis Services\AS ADOMD\150\Microsoft.AnalysisServices.AdomdClient.dll",
            r"C:\Program Files\Microsoft Analysis Services\AS ADOMD\140\Microsoft.AnalysisServices.AdomdClient.dll",
        ]

        adomd_cargado = False
        try:
            clr.AddReference("Microsoft.AnalysisServices.AdomdClient")
            adomd_cargado = True
        except:
            for path in dll_paths:
                if os.path.exists(path):
                    try:
                        clr.AddReference(path)
                        adomd_cargado = True
                        break
                    except:
                        continue

        if not adomd_cargado:
            raise Exception("No se encontró Microsoft.AnalysisServices.AdomdClient.dll")

        from Microsoft.AnalysisServices.AdomdClient import AdomdConnection, AdomdCommand

        conn = AdomdConnection(f"Data Source=127.0.0.1:{puerto};")
        conn.Open()

        # ── Fechas MTD ────────────────────────────────
        hoy = datetime.now()
        primer_dia_mes = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        dias_totales_mes = calendar.monthrange(hoy.year, hoy.month)[1]
        dias_transcurridos = hoy.day

        f_ini_mtd = f"DATE({primer_dia_mes.year}, {primer_dia_mes.month}, {primer_dia_mes.day})"
        f_hoy_dax = f"DATE({hoy.year}, {hoy.month}, {hoy.day})"
        filtro_mtd = (
            f"WinForce_Lima[Fecha de registro] >= {f_ini_mtd} && "
            f"WinForce_Lima[Fecha de registro] <= {f_hoy_dax}"
        )

        # Semanas del mes: lunes→domingo, recortadas al inicio del mes y a hoy
        def semanas_del_mes():
            semanas = []
            lunes = primer_dia_mes - timedelta(days=primer_dia_mes.weekday())
            while lunes <= hoy:
                inicio = max(lunes, primer_dia_mes)
                fin = min(lunes + timedelta(days=6), hoy)
                if inicio <= fin:
                    semanas.append((inicio, fin))
                lunes += timedelta(days=7)
            return semanas

        def ejecutar_dax(query):
            cmd = AdomdCommand(query, conn)
            reader = cmd.ExecuteReader()
            cols = []
            for i in range(reader.FieldCount):
                name = reader.GetName(i)
                if "[" in name and "]" in name:
                    name = name.split("[")[-1].split("]")[0]
                cols.append(name)
            rows = []
            while reader.Read():
                rows.append({c: reader[i] for i, c in enumerate(cols)})
            reader.Close()
            return rows

        def _int(val):
            """Convierte a int de forma segura — maneja None/DBNull del ADOMD reader."""
            return int(val) if val is not None else 0

        # ── KPIs — MTD ────────────────────────────────
        kpi_rows = ejecutar_dax(f"""
            EVALUATE
            CALCULATETABLE(
                ROW(
                    "total_altas",        CALCULATE(COUNTROWS(WinForce_Lima), WinForce_Lima[Estado orden] = "Ejecutada"),
                    "total_preventas",    COUNTROWS(WinForce_Lima),
                    "total_anulaciones",  CALCULATE(COUNTROWS(WinForce_Lima), WinForce_Lima[Estado orden] = "Anulado"),
                    "score_promedio",     AVERAGEX(FILTER(WinForce_Lima, NOT ISBLANK(WinForce_Lima[Score Cliente])), WinForce_Lima[Score Cliente]),
                    "ventas_en_riesgo",   CALCULATE(COUNTROWS(WinForce_Lima), WinForce_Lima[Cumple Score Zona] = "No cumple"),
                    "sin_score",          CALCULATE(COUNTROWS(WinForce_Lima), WinForce_Lima[Cumple Score Zona] = "Sin score"),
                    "no_venta",           CALCULATE(COUNTROWS(WinForce_Lima), WinForce_Lima[Zona_KML] = "No Venta"),
                    "altas_ceh",          CALCULATE(COUNTROWS(WinForce_Lima), WinForce_Lima[Estado orden] = "Ejecutada", WinForce_Lima[Tipo de domicilio] = "C/E Habilitado")
                ),
                FILTER(ALL(WinForce_Lima), {filtro_mtd})
            )
        """)

        # ── Planes — MTD ──────────────────────────────
        planes_rows = ejecutar_dax(f"""
            EVALUATE SUMMARIZECOLUMNS(
                WinForce_Lima[Plan],
                FILTER(ALL(WinForce_Lima), {filtro_mtd}),
                "altas",      CALCULATE(COUNTROWS(WinForce_Lima), WinForce_Lima[Estado orden] = "Ejecutada"),
                "preventas",  COUNTROWS(WinForce_Lima)
            ) ORDER BY [altas] DESC
        """)

        # ── Zonas — MTD ───────────────────────────────
        zonas_rows = ejecutar_dax(f"""
            EVALUATE SUMMARIZECOLUMNS(
                WinForce_Lima[Zona_KML],
                FILTER(ALL(WinForce_Lima), {filtro_mtd}),
                "altas",      CALCULATE(COUNTROWS(WinForce_Lima), WinForce_Lima[Estado orden] = "Ejecutada"),
                "preventas",  COUNTROWS(WinForce_Lima),
                "en_riesgo",  CALCULATE(COUNTROWS(WinForce_Lima), WinForce_Lima[Cumple Score Zona] = "No cumple"),
                "sin_score",  CALCULATE(COUNTROWS(WinForce_Lima), WinForce_Lima[Cumple Score Zona] = "Sin score")
            ) ORDER BY [preventas] DESC
        """)

        # ── Tramos — MTD ──────────────────────────────
        tramos_rows = ejecutar_dax(f"""
            EVALUATE SUMMARIZECOLUMNS(
                WinForce_Lima[Tramo Días Instalación],
                WinForce_Lima[Orden Tramo],
                FILTER(ALL(WinForce_Lima), {filtro_mtd}),
                "altas", CALCULATE(COUNTROWS(WinForce_Lima), WinForce_Lima[Estado orden] = "Ejecutada")
            ) ORDER BY WinForce_Lima[Orden Tramo] ASC
        """)

        # ── Top vendedores — MTD ──────────────────────
        vend_rows = ejecutar_dax(f"""
            EVALUATE TOPN(5,
                SUMMARIZECOLUMNS(
                    WinForce_Lima[Vendedor real],
                    FILTER(ALL(WinForce_Lima), {filtro_mtd}),
                    "altas",      CALCULATE(COUNTROWS(WinForce_Lima), WinForce_Lima[Estado orden] = "Ejecutada"),
                    "en_riesgo",  CALCULATE(COUNTROWS(WinForce_Lima), WinForce_Lima[Cumple Score Zona] = "No cumple")
                ),
                [altas], DESC
            )
        """)

        # ── Breakdown semanal del mes ──────────────────
        semanas_data = []
        for ini, fin in semanas_del_mes():
            f_s_ini = f"DATE({ini.year}, {ini.month}, {ini.day})"
            f_s_fin = f"DATE({fin.year}, {fin.month}, {fin.day})"
            filtro_s = (
                f"WinForce_Lima[Fecha de registro] >= {f_s_ini} && "
                f"WinForce_Lima[Fecha de registro] <= {f_s_fin}"
            )
            s_rows = ejecutar_dax(f"""
                EVALUATE
                CALCULATETABLE(
                    ROW(
                        "altas",     CALCULATE(COUNTROWS(WinForce_Lima), WinForce_Lima[Estado orden] = "Ejecutada"),
                        "altas_ceh", CALCULATE(COUNTROWS(WinForce_Lima), WinForce_Lima[Estado orden] = "Ejecutada", WinForce_Lima[Tipo de domicilio] = "C/E Habilitado"),
                        "preventas", COUNTROWS(WinForce_Lima)
                    ),
                    FILTER(ALL(WinForce_Lima), {filtro_s})
                )
            """)
            s = s_rows[0] if s_rows else {}
            semanas_data.append({
                "label":     f"{ini.strftime('%d/%m')} – {fin.strftime('%d/%m')}",
                "altas":     _int(s.get("altas")),
                "altas_ceh": _int(s.get("altas_ceh")),
                "preventas": _int(s.get("preventas")),
                "en_curso":  ini.replace(hour=0) <= hoy <= fin.replace(hour=23, minute=59),
            })

        conn.Close()

        # ── Proyección al cierre del mes ──────────────
        kpi = kpi_rows[0] if kpi_rows else {}
        total_altas  = _int(kpi.get("total_altas"))
        altas_ceh    = _int(kpi.get("altas_ceh"))
        ritmo_diario = total_altas / dias_transcurridos if dias_transcurridos > 0 else 0
        ritmo_ceh    = altas_ceh / dias_transcurridos if dias_transcurridos > 0 else 0
        proyeccion     = round(ritmo_diario * dias_totales_mes)
        proyeccion_ceh = round(ritmo_ceh * dias_totales_mes)

        datos = {
            "fecha_reporte":      hoy.strftime("%d/%m/%Y"),
            "mes":                hoy.strftime("%B %Y"),
            "dias_transcurridos": dias_transcurridos,
            "dias_totales_mes":   dias_totales_mes,
            "cuota_mes":          310,  # cuota mensual de C/E Habilitado — actualizar cada mes
            "kpis": {
                "total_altas":        total_altas,
                "altas_ceh":          altas_ceh,
                "total_preventas":    _int(kpi.get("total_preventas")),
                "total_anulaciones":  _int(kpi.get("total_anulaciones")),
                "score_promedio":     _int(kpi.get("score_promedio")),
                "ventas_en_riesgo":   _int(kpi.get("ventas_en_riesgo")),
                "sin_score":          _int(kpi.get("sin_score")),
                "no_venta":           _int(kpi.get("no_venta")),
                "ritmo_diario":       round(ritmo_diario, 1),
                "ritmo_ceh":          round(ritmo_ceh, 1),
                "proyeccion_fin_mes": proyeccion,
                "proyeccion_ceh":     proyeccion_ceh,
            },
            "semanas_mes": semanas_data,
            "planes": [
                {
                    "plan":      r.get("WinForce_Lima[Plan]", r.get("Plan", "")),
                    "altas":     _int(r.get("altas")),
                    "preventas": _int(r.get("preventas")),
                }
                for r in planes_rows
            ],
            "zonas": [
                {
                    "zona":      r.get("WinForce_Lima[Zona_KML]", r.get("Zona_KML", "")),
                    "altas":     _int(r.get("altas")),
                    "preventas": _int(r.get("preventas")),
                    "en_riesgo": _int(r.get("en_riesgo")),
                    "sin_score": _int(r.get("sin_score")),
                }
                for r in zonas_rows
            ],
            "tramos": [
                {
                    "tramo": r.get("WinForce_Lima[Tramo Días Instalación]", r.get("Tramo Días Instalación", "")),
                    "altas": _int(r.get("altas")),
                }
                for r in tramos_rows
            ],
            "top_vendedores": [
                {
                    "vendedor":  r.get("WinForce_Lima[Vendedor real]", r.get("Vendedor real", "")),
                    "altas":     _int(r.get("altas")),
                    "en_riesgo": _int(r.get("en_riesgo")),
                }
                for r in vend_rows
            ],
        }

        return datos

    except Exception as e:
        print(f"No se pudo conectar via ADOMD: {e}")
        print("   Usando datos de ejemplo (data.json con valores del último reporte)")
        return None


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("Buscando Power BI Desktop...")
    puerto = encontrar_puerto_pbi()

    if puerto:
        print(f"Power BI encontrado en puerto {puerto}")
        datos = extraer_via_adomd(puerto)
    else:
        print("No se encontró Power BI Desktop abierto")
        datos = None

    if datos:
        with open("data.json", "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        print("data.json generado correctamente")
    else:
        print("No se generó data.json — revisa que Power BI esté abierto")
        sys.exit(1)
