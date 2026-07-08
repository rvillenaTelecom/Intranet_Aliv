"""
SCRIPT: Procesador de Morosidad - Aliv Telecom / Win
=====================================================
Versión completa con:
- Detección automática de archivos de recibos
- Selección automática del recibo más reciente por cohorte
- Cruce con Usuarios_Win (agencias)
- Cruce con Ventas_Aliv (paquetes, estado, conversión)
- Cruce con Winforce_Lima (rechazos, motivos)
- Cruce con Zonas_KML (zonas de riesgo)

ARCHIVOS REQUERIDOS EN LA MISMA CARPETA:
    - NNN_Mes_-_GrupXX_-_RecibXX.xlsx  (archivos de recibos Win)
    - Usuarios_Win.xlsx                 (vendedores y agencias)
    - Ventas_Aliv.xlsx                  (ventas e instalaciones)
    - Winforce_Lima.xlsx                (pedidos y rechazos Lima)
    - Zonas_KML.xlsx                    (zonas de riesgo geográfico)

CÓMO USAR:
    pip install pandas openpyxl
    python procesar_morosidad.py
"""

import os
import re
import pandas as pd
from difflib import get_close_matches

CARPETA_SALIDA = "Recibos_Resume"
os.makedirs(CARPETA_SALIDA, exist_ok=True)

# ─────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────

PATRON_NOMBRE = re.compile(
    r'^(?P<num>\d+)[ _](?P<mes>[^ _]+)[ _]-[ _]Grup(?P<grupo>\d+)[ _]-[ _]Recib(?P<recibo>\d+)\.xlsx$',
    re.IGNORECASE
)

ORDEN_MESES = [
    "Enero","Febrero","Marzo","Abril","Mayo","Junio",
    "Julio","Agosto","Setiembre","Octubre","Noviembre","Diciembre"
]

COLUMNAS_RECIBO = [
    "DNI/Carnet Extraj.", "Nombre y Apellidos",
    "Departamento", "Provincia", "Distrito",
    "Vendedor", "Supervisor", "Canal", "Precio paquete",
    "Fecha vencimiento M1", "Estado M1", "Deuda M1",
    "Fecha vencimiento M2", "Estado M2", "Deuda M2",
    "Fecha vencimiento M3", "Estado M3", "Deuda M3",
]

COLUMNAS_FECHA = [
    "Fecha vencimiento M1",
    "Fecha vencimiento M2",
    "Fecha vencimiento M3",
]

AGENCIA_DIRECTA = {
    "VENTAS DEZANET .":                  "DEZANET",
    "LOTTUS VENTAS .":                   "LOTTUS",
    "FUTURA . .":                        "FUTURA",
    "CESAR ENRIQUE SIPION NAHUE":        "SIPION",
    "ALEXANDER JAVIER CORNELIO FUENTES": "CORNELIO",
}

UMBRAL_WIN = 0.045


# ─────────────────────────────────────────────────────────────
# FUNCIONES
# ─────────────────────────────────────────────────────────────

def detectar_archivos_recibos(carpeta="."):
    """
    Detecta todos los archivos de recibos y selecciona
    automáticamente el recibo más reciente por cohorte.
    Si existen R1 y R2 de la misma cohorte, usa solo R2.
    """
    candidatos = {}
    ignorados  = []

    for nombre in sorted(os.listdir(carpeta)):
        ruta = os.path.join(carpeta, nombre)
        if not os.path.isfile(ruta):
            continue
        m = PATRON_NOMBRE.match(nombre)
        if not m:
            if nombre.endswith(".xlsx") and not any(
                nombre.lower().startswith(p) for p in
                ["usuarios_win","ventas_aliv","winforce","zonas_kml","recibos"]
            ):
                print(f"  ⚠️  Ignorado (nombre no reconocido): {nombre}")
            continue

        num    = m.group("num")
        mes    = m.group("mes").capitalize()
        grupo  = f"Grupo {m.group('grupo')}"
        recibo = int(m.group("recibo"))
        key    = f"{num}_{mes}_{grupo}"

        if key not in candidatos or recibo > candidatos[key]["recibo"]:
            if key in candidatos:
                ignorados.append(candidatos[key]["nombre"])
            candidatos[key] = {
                "ruta": ruta, "nombre": nombre,
                "mes": mes, "grupo": grupo, "recibo": recibo,
            }
        else:
            ignorados.append(nombre)

    if ignorados:
        print(f"\n  ℹ️  Versiones anteriores ignoradas (se usó la más reciente):")
        for f in ignorados:
            print(f"      - {f}")

    return list(candidatos.values())


def detectar_hoja_base(ruta):
    xl    = pd.ExcelFile(ruta)
    hojas = [h for h in xl.sheet_names if "RESUMEN" not in h.upper()]
    if not hojas:
        print(f"  ⚠️  No se encontró hoja BASE en: {ruta}")
        return None
    if len(hojas) > 1:
        print(f"  ⚠️  Múltiples hojas BASE, usando: '{hojas[0]}'")
    return hojas[0]


def clasificar_estado(estado):
    if pd.isna(estado):
        return "Sin dato"
    t = str(estado).strip().upper()
    if "CLIENTE PAGO"  in t: return "Cliente Pago"
    if "TERCERO PAGO"  in t: return "Tercero Pago"
    if "CHURN"         in t: return "Churn"
    if "BAJA"          in t: return "Cliente de Baja"
    if "PENDIENTE"     in t: return "Pendiente"
    if "ANULADO"       in t: return "Anulado"
    return "Otro"


def norm(s):
    return str(s).upper().strip()


# ─────────────────────────────────────────────────────────────
# PROGRAMA PRINCIPAL
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":

    print("=" * 60)
    print("  PROCESADOR DE MOROSIDAD — ALIV TELECOM / WIN")
    print("=" * 60)

    # ── PASO 1: Leer archivos de recibos ─────────────────────
    print("\n📂 Buscando archivos de recibos...\n")
    archivos = detectar_archivos_recibos(".")

    if not archivos:
        print("❌ No se encontraron archivos de recibos.")
        exit()

    print(f"\n  {len(archivos)} cohorte(s) a procesar:\n")
    for a in archivos:
        print(f"  ✓ {a['nombre']}")
        print(f"      {a['mes']} | {a['grupo']} | Recibo {a['recibo']}")

    # ── PASO 2: Unificar en tabla maestra ────────────────────
    print(f"\n📖 Leyendo datos de clientes...\n")
    tablas = []
    for a in archivos:
        hoja = detectar_hoja_base(a["ruta"])
        if not hoja:
            continue
        df = pd.read_excel(a["ruta"], sheet_name=hoja)
        cols_ok = [c for c in COLUMNAS_RECIBO if c in df.columns]
        df = df[cols_ok].copy()
        df["Mes_Cohorte"]       = a["mes"]
        df["Grupo"]             = a["grupo"]
        df["Num_Recibo_Actual"] = a["recibo"]
        tablas.append(df)
        print(f"  ✓ {a['nombre']}: {len(df):,} clientes")

    if not tablas:
        print("❌ No se pudo leer ningún archivo.")
        exit()

    master = pd.concat(tablas, ignore_index=True)
    print(f"\n  Total unificado: {len(master):,} registros")

    # ── PASO 3: Corregir fechas ──────────────────────────────
    print("\n📅 Corrigiendo tipos de fecha...")
    for col in COLUMNAS_FECHA:
        if col in master.columns:
            master[col] = pd.to_datetime(master[col], errors="coerce")
            print(f"  ✓ {col}: {master[col].notna().sum():,} fechas válidas")

    # ── PASO 4: Clasificar estados ───────────────────────────
    print("\n🔍 Clasificando estados de pago...")
    master["Cat_M1"] = master["Estado M1"].apply(clasificar_estado)
    master["Cat_M2"] = master["Estado M2"].apply(clasificar_estado)
    master["Cat_M3"] = master["Estado M3"].apply(clasificar_estado)
    master["Es_Moroso_M1"] = master["Cat_M1"].isin(["Churn","Cliente de Baja"]).astype(int)

    # Morosidad real = Churn + Baja + Tercero Pago
    master["Es_Riesgo_M1"] = master["Cat_M1"].isin(
        ["Churn","Cliente de Baja","Tercero Pago"]
    ).astype(int)

    # ── PASO 5: Clave de ubicación ───────────────────────────
    master["Ubicacion_Key"] = (
        master["Departamento"].str.strip() + " | " +
        master["Provincia"].str.strip()    + " | " +
        master["Distrito"].str.strip()
    )

    # ── PASO 6: Cruce con Usuarios_Win (agencias) ────────────
    archivo_usuarios = next(
        (f for f in os.listdir(".") if f.lower().startswith("usuarios_win") and f.endswith(".xlsx")),
        None
    )

    if archivo_usuarios:
        print(f"\n👥 Cruzando agencias con {archivo_usuarios}...")
        users = pd.read_excel(archivo_usuarios)
        users["VENDEDOR_NORM"]  = users["VENDEDOR"].apply(norm)
        master["VENDEDOR_NORM"] = master["Vendedor"].apply(norm)
        user_list = list(users["VENDEDOR_NORM"].unique())
        lookup    = dict(zip(users["VENDEDOR_NORM"], users["AGENCIA"]))

        fuzzy_map = {}
        for v in master["VENDEDOR_NORM"].unique():
            if v in lookup or v in AGENCIA_DIRECTA:
                continue
            candidates = get_close_matches(v, user_list, n=1, cutoff=0.85)
            if candidates:
                fuzzy_map[v] = candidates[0]

        # Agencia dominante por supervisor (para evitar duplicados)
        def get_agencia(row):
            v, canal = row["VENDEDOR_NORM"], row["Canal"]
            if v in lookup:           return lookup[v]
            if v in AGENCIA_DIRECTA:  return AGENCIA_DIRECTA[v]
            if v in fuzzy_map:        return lookup.get(fuzzy_map[v], "SIN IDENTIFICAR")
            if canal in ("FREELANCE","CAMPO - LIMA","CAMPO-PROVINCIA"):
                return "ALIV"
            return "SIN IDENTIFICAR"

        master["Agencia"] = master.apply(get_agencia, axis=1)
        cobertura = (master["Agencia"] != "SIN IDENTIFICAR").mean()
        print(f"  ✓ Cobertura: {cobertura:.1%}")
    else:
        print("  ⚠️  Usuarios_Win.xlsx no encontrado — Agencia = SIN IDENTIFICAR")
        master["Agencia"] = "SIN IDENTIFICAR"

    # ── PASO 7: Cruce con Ventas_Aliv (paquetes y conversión) 
    archivo_ventas = next(
        (f for f in os.listdir(".") if f.lower().startswith("ventas_aliv") and f.endswith(".xlsx")),
        None
    )

    if archivo_ventas:
        print(f"\n📦 Cruzando paquetes con {archivo_ventas}...")
        va = pd.read_excel(archivo_ventas)
        va["DNI_NORM"] = va["nro_doc"].astype(str).str.strip().str.zfill(8)
        master["DNI_NORM"] = master["DNI/Carnet Extraj."].astype(str).str.strip().str.zfill(8)

        # Quedarnos con columnas útiles de Ventas_Aliv
        va_cols = ["DNI_NORM","plan","EmpaquetadoEspecifico","Empaquetado_General",
                   "Estado","motivo","tipoVivienda","Preventa","Venta","Alta",
                   "Mes Venta","Supervisor"]
        va_slim = va[[c for c in va_cols if c in va.columns]].copy()

        # Si un DNI tiene múltiples registros en Ventas_Aliv, tomar el más reciente
        if "Mes Venta" in va_slim.columns:
            va_slim = va_slim.sort_values("Mes Venta", ascending=False)
        va_slim = va_slim.drop_duplicates("DNI_NORM", keep="first")

        master = master.merge(va_slim, on="DNI_NORM", how="left", suffixes=("","_va"))
        match_pct = master["plan"].notna().mean()
        print(f"  ✓ Match con Ventas_Aliv: {match_pct:.1%} de clientes")
    else:
        print("  ⚠️  Ventas_Aliv.xlsx no encontrado")

    # ── PASO 8: Cruce con Zonas_KML ─────────────────────────
    archivo_kml = next(
        (f for f in os.listdir(".") if f.lower().startswith("zonas_kml") and f.endswith(".xlsx")),
        None
    )

    if archivo_kml:
        print(f"\n🗺️  Cruzando zonas KML con {archivo_kml}...")
        kml = pd.read_excel(archivo_kml, sheet_name="Zonas KML", header=1)
        kml.columns = ["ID_Zona","Segmento","Descripcion","Score_Minimo","Capa_KML",
                       "Distrito","Provincia","Departamento","Color_Mapa","Lat_Centroide","Lon_Centroide"]
        kml = kml[kml["ID_Zona"] != "ID_Zona"].dropna(subset=["Distrito"])
        kml["Score_Minimo"] = pd.to_numeric(kml["Score_Minimo"], errors="coerce")
        kml["DIST_NORM"] = kml["Distrito"].str.upper().str.strip()

        # Resumen de zona por distrito
        zona_dist = kml.groupby("DIST_NORM").agg(
            Zona_KML    = ("Segmento", lambda x: x.mode()[0] if len(x) > 0 else "Sin datos"),
            Score_KML   = ("Score_Minimo", "max"),
        ).reset_index()

        master["DIST_NORM"] = master["Distrito"].str.upper().str.strip()
        master = master.merge(zona_dist, on="DIST_NORM", how="left")
        master["Zona_KML"]  = master["Zona_KML"].fillna("Sin modificación (201)")
        master["Score_KML"] = master["Score_KML"].fillna(201)
        print(f"  ✓ Zonas KML asignadas")
        print(f"  {master['Zona_KML'].value_counts().to_string()}")
    else:
        print("  ⚠️  Zonas_KML.xlsx no encontrado")

    # ── PASO 9: Guardar archivos ─────────────────────────────
    print(f"\n💾 Guardando archivos en {CARPETA_SALIDA}/...\n")

    # Excel 1: Master completo
    cols_drop = [c for c in ["VENDEDOR_NORM","DNI_NORM","DIST_NORM"] if c in master.columns]
    master_out = master.drop(columns=cols_drop)
    master_out.to_excel(os.path.join(CARPETA_SALIDA, "morosidad_master.xlsx"), index=False)
    print(f"  ✓ morosidad_master.xlsx  ({len(master_out):,} filas)")

    # Excel 2: Resumen supervisores
    agencia_sup = (
        master.groupby(["Supervisor","Agencia"]).size()
        .reset_index(name="n").sort_values("n", ascending=False)
        .drop_duplicates("Supervisor")[["Supervisor","Agencia"]]
    )
    resumen_sup = (
        master.groupby("Supervisor").agg(
            Total_Clientes = ("DNI/Carnet Extraj.","count"),
            Morosos        = ("Es_Moroso_M1","sum"),
            En_Riesgo      = ("Es_Riesgo_M1","sum"),
            Deuda_M1       = ("Deuda M1","sum"),
            Deuda_M2       = ("Deuda M2","sum"),
            Deuda_M3       = ("Deuda M3","sum"),
        ).reset_index().merge(agencia_sup, on="Supervisor", how="left")
    )
    resumen_sup["Tasa_Morosidad"] = (resumen_sup["Morosos"] / resumen_sup["Total_Clientes"]).round(4)
    resumen_sup["Tasa_Riesgo"]    = (resumen_sup["En_Riesgo"] / resumen_sup["Total_Clientes"]).round(4)
    resumen_sup["Deuda_Total"]    = resumen_sup["Deuda_M1"] + resumen_sup["Deuda_M2"] + resumen_sup["Deuda_M3"]
    resumen_sup.sort_values("Tasa_Morosidad", ascending=False).to_excel(
        os.path.join(CARPETA_SALIDA, "resumen_supervisores.xlsx"), index=False)
    print(f"  ✓ resumen_supervisores.xlsx  ({len(resumen_sup)} supervisores)")

    # Excel 3: Resumen distritos
    resumen_dist = (
        master.groupby(["Departamento","Provincia","Distrito","Ubicacion_Key"]).agg(
            Total_Clientes = ("DNI/Carnet Extraj.","count"),
            Morosos        = ("Es_Moroso_M1","sum"),
            En_Riesgo      = ("Es_Riesgo_M1","sum"),
            Deuda_M1       = ("Deuda M1","sum"),
        ).reset_index()
    )
    resumen_dist["Tasa_Morosidad"] = (resumen_dist["Morosos"] / resumen_dist["Total_Clientes"]).round(4)
    resumen_dist["Tasa_Riesgo"]    = (resumen_dist["En_Riesgo"] / resumen_dist["Total_Clientes"]).round(4)
    resumen_dist.sort_values("Tasa_Morosidad", ascending=False).to_excel(
        os.path.join(CARPETA_SALIDA, "resumen_distritos.xlsx"), index=False)
    print(f"  ✓ resumen_distritos.xlsx  ({len(resumen_dist)} distritos)")

    # Excel 4: Evolución recibo a recibo
    meses_presentes = [m for m in ORDEN_MESES if m in master["Mes_Cohorte"].unique()]
    filas = []
    for mes in meses_presentes:
        sub = master[master["Mes_Cohorte"] == mes]
        for nr, col_cat in [(1,"Cat_M1"),(2,"Cat_M2"),(3,"Cat_M3")]:
            conteos = sub[col_cat].value_counts()
            total   = len(sub)
            morosos = conteos.get("Churn",0) + conteos.get("Cliente de Baja",0)
            pagaron = conteos.get("Cliente Pago",0) + conteos.get("Tercero Pago",0)
            riesgo  = morosos + conteos.get("Tercero Pago",0)
            filas.append({
                "Mes":            mes,
                "Recibo":         f"R{nr}",
                "Total":          total,
                "Cliente_Pago":   conteos.get("Cliente Pago",0),
                "Tercero_Pago":   conteos.get("Tercero Pago",0),
                "Churn":          conteos.get("Churn",0),
                "Cliente_Baja":   conteos.get("Cliente de Baja",0),
                "Sin_Dato":       conteos.get("Sin dato",0),
                "Morosos":        morosos,
                "En_Riesgo":      riesgo,
                "Tasa_Morosidad": round(morosos/total,4) if total>0 else 0,
                "Tasa_Riesgo":    round(riesgo/total,4)  if total>0 else 0,
                "Tasa_Pago":      round(pagaron/total,4) if total>0 else 0,
            })
    pd.DataFrame(filas).to_excel(
        os.path.join(CARPETA_SALIDA, "evolucion_recibos.xlsx"), index=False)
    print(f"  ✓ evolucion_recibos.xlsx")

    # Excel 5: Resumen agencias
    resumen_ag = (
        master.groupby("Agencia").agg(
            Total_Clientes = ("DNI/Carnet Extraj.","count"),
            Morosos        = ("Es_Moroso_M1","sum"),
            En_Riesgo      = ("Es_Riesgo_M1","sum"),
            Deuda_M1       = ("Deuda M1","sum"),
            Deuda_M2       = ("Deuda M2","sum"),
            Deuda_M3       = ("Deuda M3","sum"),
        ).reset_index()
    )
    resumen_ag["Tasa_Morosidad"] = (resumen_ag["Morosos"] / resumen_ag["Total_Clientes"]).round(4)
    resumen_ag["Tasa_Riesgo"]    = (resumen_ag["En_Riesgo"] / resumen_ag["Total_Clientes"]).round(4)
    resumen_ag["Deuda_Total"]    = resumen_ag["Deuda_M1"] + resumen_ag["Deuda_M2"] + resumen_ag["Deuda_M3"]
    resumen_ag.sort_values("Tasa_Morosidad", ascending=False).to_excel(
        os.path.join(CARPETA_SALIDA, "resumen_agencias.xlsx"), index=False)
    print(f"  ✓ resumen_agencias.xlsx")

    # Excel 6: Resumen paquetes (NUEVO)
    if "EmpaquetadoEspecifico" in master.columns:
        resumen_pkg = (
            master.groupby("EmpaquetadoEspecifico").agg(
                Total_Clientes = ("DNI/Carnet Extraj.","count"),
                Morosos        = ("Es_Moroso_M1","sum"),
                En_Riesgo      = ("Es_Riesgo_M1","sum"),
                Deuda_M1       = ("Deuda M1","sum"),
            ).reset_index()
        )
        resumen_pkg["Tasa_Morosidad"] = (resumen_pkg["Morosos"] / resumen_pkg["Total_Clientes"]).round(4)
        resumen_pkg["Tasa_Riesgo"]    = (resumen_pkg["En_Riesgo"] / resumen_pkg["Total_Clientes"]).round(4)
        resumen_pkg.sort_values("Tasa_Morosidad", ascending=False).to_excel(
            os.path.join(CARPETA_SALIDA, "resumen_paquetes.xlsx"), index=False)
        print(f"  ✓ resumen_paquetes.xlsx  (NUEVO)")

    # Excel 7: Embudo de ventas de Ventas_Aliv (NUEVO)
    if archivo_ventas:
        va_full = pd.read_excel(archivo_ventas)
        embudo_cols = ["plan","EmpaquetadoEspecifico","Empaquetado_General",
                       "Estado","motivo","tipoVivienda","Preventa","Venta","Alta",
                       "Mes Venta","Supervisor","Distrito","AgenciaNombre"]
        va_embudo = va_full[[c for c in embudo_cols if c in va_full.columns]].copy()

        # Resumen por estado
        if "Estado" in va_embudo.columns:
            resumen_estado = va_embudo["Estado"].value_counts().reset_index()
            resumen_estado.columns = ["Estado","Cantidad"]

        # Resumen conversión por supervisor
        if all(c in va_embudo.columns for c in ["Supervisor","Preventa","Venta","Alta"]):
            conv_sup = va_embudo.groupby("Supervisor").agg(
                Preventas = ("Preventa","sum"),
                Ventas    = ("Venta","sum"),
                Altas     = ("Alta","sum"),
            ).reset_index()
            conv_sup["Conv_Venta"] = (conv_sup["Ventas"] / conv_sup["Preventas"]).round(4)
            conv_sup["Conv_Alta"]  = (conv_sup["Altas"]  / conv_sup["Preventas"]).round(4)
            conv_sup.sort_values("Conv_Alta").to_excel(
                os.path.join(CARPETA_SALIDA, "embudo_ventas.xlsx"), index=False)
            print(f"  ✓ embudo_ventas.xlsx  (NUEVO)")

    # Excel 8: Zonas KML resumen (NUEVO)
    if archivo_kml:
        kml_clean = pd.read_excel(archivo_kml, sheet_name="Zonas KML", header=1)
        kml_clean.columns = ["ID_Zona","Segmento","Descripcion","Score_Minimo","Capa_KML",
                             "Distrito","Provincia","Departamento","Color_Mapa","Lat_Centroide","Lon_Centroide"]
        kml_clean = kml_clean[kml_clean["ID_Zona"] != "ID_Zona"].dropna(subset=["Distrito"])
        kml_clean["Score_Minimo"] = pd.to_numeric(kml_clean["Score_Minimo"], errors="coerce")
        kml_clean.to_excel(os.path.join(CARPETA_SALIDA, "zonas_kml_limpio.xlsx"), index=False)
        print(f"  ✓ zonas_kml_limpio.xlsx  (NUEVO)")

    # ── RESUMEN FINAL ────────────────────────────────────────
    tasa_global  = master["Es_Moroso_M1"].mean()
    tasa_riesgo  = master["Es_Riesgo_M1"].mean()

    print("\n" + "=" * 60)
    print("  RESUMEN")
    print("=" * 60)
    print(f"  Clientes procesados   : {len(master):,}")
    print(f"  Morosos (M1)          : {master['Es_Moroso_M1'].sum():,}")
    print(f"  Tasa morosidad        : {tasa_global:.1%}  (umbral Win: {UMBRAL_WIN:.1%})")
    print(f"  Tasa riesgo real      : {tasa_riesgo:.1%}  (Churn+Baja+Tercero)")
    if tasa_global > UMBRAL_WIN:
        print(f"  ⚠️  ALERTA: supera el umbral por {tasa_global - UMBRAL_WIN:.1%}")
    else:
        print(f"  ✅ Dentro del umbral (margen: {UMBRAL_WIN - tasa_global:.1%})")
    print(f"  Deuda total M1        : S/ {master['Deuda M1'].sum():,.2f}")
    print(f"  Meses procesados      : {', '.join(meses_presentes)}")
    print(f"\n  Archivos generados en '{CARPETA_SALIDA}/':")
    for f in sorted(os.listdir(CARPETA_SALIDA)):
        kb = os.path.getsize(os.path.join(CARPETA_SALIDA, f)) // 1024
        print(f"    📄 {f}  ({kb} KB)")
    print("=" * 60)
    print(f"\n✅ Proceso completado.")