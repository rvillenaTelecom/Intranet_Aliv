"""
API REST para Aliv Telecom — FastAPI
Expone las funciones de db_helper como endpoints GET.
Ejecutar: uvicorn api:app --host 0.0.0.0 --port 8001 --reload
"""
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from db_helper import (
    get_kpi_lima, get_kpi_provincia,
    get_daily_trend_lima, get_daily_trend_provincia,
    get_distribucion_estados_lima, get_top_distritos_lima,
    get_velocidad_planes_lima, get_top_vendedores_lima,
    get_tipo_vivienda_lima, get_pivot_planes_agencia,
    get_tramo_dias_lima, get_tabla_provincia,
    get_localizacion_lima, get_datos_distrito_lima,
    get_anulaciones_agencia_lima, get_comparacion_meses_lima,
    get_puntos_mapa_lima, get_ranking_agencias_lima,
    get_datos_agencia_lima, get_datos_vendedor_lima,
    get_mora_resumen, get_mora_embudo, get_mora_perdidas,
    get_mora_supervisores, get_mora_casos, get_mora_distritos,
    get_mora_paquetes, get_mora_riesgos, get_mora_detalle,
    get_mora_pagos_dia, get_mora_pagos_acumulado, get_mora_filtros,
    get_usuarios, get_usuarios_stats, get_agencias_list,
    get_supervisores_list, get_departamentos,
)

app = FastAPI(
    title="Aliv Telecom API",
    description="KPIs de ventas, morosidad y usuarios para agente de IA",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_HOY = datetime.now()
_MES_ACT = _HOY.month
_ANIO_ACT = _HOY.year


def _mes_default() -> int:
    return datetime.now().month


def _anio_default() -> int:
    return datetime.now().year


def _mora_kw(
    mes: Optional[int],
    grupo: str,
    recibo: str,
    supervisor: str,
    distrito: str,
    riesgo: str,
    caso: str,
    dni: str,
    departamento: str,
    tramo: str,
) -> dict:
    kw = {}
    if mes:
        kw["mes"] = mes
    if grupo:
        kw["grupo"] = grupo
    if recibo:
        kw["recibo"] = recibo
    if supervisor:
        kw["supervisor"] = supervisor
    if distrito:
        kw["distrito"] = distrito
    if riesgo:
        kw["riesgo"] = riesgo
    if caso:
        kw["caso"] = caso
    if dni:
        kw["dni"] = dni
    if departamento:
        kw["departamento"] = departamento
    if tramo:
        kw["tramo"] = tramo
    return kw


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/")
def health():
    return {"status": "ok", "mes_actual": _mes_default(), "anio_actual": _anio_default()}


# ── KPIs principales ─────────────────────────────────────────────────────────

@app.get("/kpi/lima")
def kpi_lima(
    mes: int = Query(default=None),
    anio: int = Query(default=None),
    area: str = Query(default="", description="'' | 'Horizontal' | 'Vertical'"),
    dia: Optional[int] = Query(default=None),
):
    mes = mes or _mes_default()
    anio = anio or _anio_default()
    return get_kpi_lima(mes, anio, area=area, dia=dia)


@app.get("/kpi/provincia")
def kpi_provincia(
    mes: int = Query(default=None),
    anio: int = Query(default=None),
):
    mes = mes or _mes_default()
    anio = anio or _anio_default()
    return get_kpi_provincia(mes, anio)


# ── Tendencias diarias ────────────────────────────────────────────────────────

@app.get("/lima/trend")
def trend_lima(
    mes: int = Query(default=None),
    anio: int = Query(default=None),
    area: str = Query(default=""),
):
    mes = mes or _mes_default()
    anio = anio or _anio_default()
    return get_daily_trend_lima(mes, anio, area=area)


@app.get("/provincia/trend")
def trend_provincia(
    mes: int = Query(default=None),
    anio: int = Query(default=None),
):
    mes = mes or _mes_default()
    anio = anio or _anio_default()
    return get_daily_trend_provincia(mes, anio)


# ── Lima — distribuciones ─────────────────────────────────────────────────────

@app.get("/lima/estados")
def estados_lima(
    mes: int = Query(default=None),
    anio: int = Query(default=None),
    area: str = Query(default=""),
    dia: Optional[int] = Query(default=None),
):
    mes = mes or _mes_default()
    anio = anio or _anio_default()
    return get_distribucion_estados_lima(mes, anio, area=area, dia=dia)


@app.get("/lima/distritos")
def distritos_lima(
    mes: int = Query(default=None),
    anio: int = Query(default=None),
    top: int = Query(default=10),
    area: str = Query(default=""),
    dia: Optional[int] = Query(default=None),
):
    mes = mes or _mes_default()
    anio = anio or _anio_default()
    return get_top_distritos_lima(mes, anio, top=top, area=area, dia=dia)


@app.get("/lima/planes-velocidad")
def planes_velocidad_lima(
    mes: int = Query(default=None),
    anio: int = Query(default=None),
    area: str = Query(default=""),
    dia: Optional[int] = Query(default=None),
):
    mes = mes or _mes_default()
    anio = anio or _anio_default()
    return get_velocidad_planes_lima(mes, anio, area=area, dia=dia)


@app.get("/lima/vendedores")
def top_vendedores_lima(
    mes: int = Query(default=None),
    anio: int = Query(default=None),
    top: int = Query(default=10),
    dia: Optional[int] = Query(default=None),
):
    mes = mes or _mes_default()
    anio = anio or _anio_default()
    return get_top_vendedores_lima(mes, anio, top=top, dia=dia)


@app.get("/lima/vivienda")
def tipo_vivienda_lima(
    mes: int = Query(default=None),
    anio: int = Query(default=None),
    area: str = Query(default=""),
    dia: Optional[int] = Query(default=None),
):
    mes = mes or _mes_default()
    anio = anio or _anio_default()
    return get_tipo_vivienda_lima(mes, anio, area=area, dia=dia)


@app.get("/lima/pivot-planes")
def pivot_planes_lima(
    mes: int = Query(default=None),
    anio: int = Query(default=None),
    area: str = Query(default=""),
    dia: Optional[int] = Query(default=None),
):
    mes = mes or _mes_default()
    anio = anio or _anio_default()
    return get_pivot_planes_agencia(mes, anio, area=area, dia=dia)


@app.get("/lima/tramo-dias")
def tramo_dias_lima(
    mes: int = Query(default=None),
    anio: int = Query(default=None),
):
    mes = mes or _mes_default()
    anio = anio or _anio_default()
    return get_tramo_dias_lima(mes, anio)


@app.get("/lima/localizacion")
def localizacion_lima(
    mes: int = Query(default=None),
    anio: int = Query(default=None),
    area: str = Query(default=""),
):
    mes = mes or _mes_default()
    anio = anio or _anio_default()
    return get_localizacion_lima(mes, anio, area=area)


@app.get("/lima/anulaciones")
def anulaciones_lima(
    mes: int = Query(default=None),
    anio: int = Query(default=None),
    area: str = Query(default=""),
):
    mes = mes or _mes_default()
    anio = anio or _anio_default()
    return get_anulaciones_agencia_lima(mes, anio, area=area)


@app.get("/lima/mapa")
def mapa_lima(
    mes: int = Query(default=None),
    anio: int = Query(default=None),
    area: str = Query(default=""),
):
    mes = mes or _mes_default()
    anio = anio or _anio_default()
    return get_puntos_mapa_lima(mes, anio, area=area)


@app.get("/lima/ranking-agencias")
def ranking_agencias_lima(
    mes: int = Query(default=None),
    anio: int = Query(default=None),
    area: str = Query(default=""),
    dia: Optional[int] = Query(default=None),
):
    mes = mes or _mes_default()
    anio = anio or _anio_default()
    return get_ranking_agencias_lima(mes, anio, area=area, dia=dia)


# ── Lima — detalle por entidad ────────────────────────────────────────────────

@app.get("/lima/distrito/{distrito}")
def datos_distrito_lima(
    distrito: str,
    mes: int = Query(default=None),
    anio: int = Query(default=None),
    area: str = Query(default=""),
):
    mes = mes or _mes_default()
    anio = anio or _anio_default()
    return get_datos_distrito_lima(mes, anio, distrito, area=area)


@app.get("/lima/agencia/{agencia}")
def datos_agencia_lima(
    agencia: str,
    mes: int = Query(default=None),
    anio: int = Query(default=None),
    area: str = Query(default=""),
    dia: Optional[int] = Query(default=None),
):
    mes = mes or _mes_default()
    anio = anio or _anio_default()
    return get_datos_agencia_lima(mes, anio, agencia, area=area, dia=dia)


@app.get("/lima/vendedor/{vendedor}")
def datos_vendedor_lima(
    vendedor: str,
    mes: int = Query(default=None),
    anio: int = Query(default=None),
    dia: Optional[int] = Query(default=None),
):
    mes = mes or _mes_default()
    anio = anio or _anio_default()
    return get_datos_vendedor_lima(mes, anio, vendedor, dia=dia)


@app.get("/lima/comparacion")
def comparacion_lima(
    mes1: int = Query(...),
    anio1: int = Query(...),
    mes2: int = Query(...),
    anio2: int = Query(...),
    area: str = Query(default=""),
):
    return get_comparacion_meses_lima(mes1, anio1, mes2, anio2, area=area)


# ── Provincia ─────────────────────────────────────────────────────────────────

@app.get("/provincia/tabla")
def tabla_provincia(
    mes: int = Query(default=None),
    anio: int = Query(default=None),
):
    mes = mes or _mes_default()
    anio = anio or _anio_default()
    return get_tabla_provincia(mes, anio)


# ── Mora / Clawback ───────────────────────────────────────────────────────────

def _mora_params(
    mes: Optional[int] = Query(default=None, description="Mes número de recibo"),
    grupo: str = Query(default=""),
    recibo: str = Query(default=""),
    supervisor: str = Query(default=""),
    distrito: str = Query(default=""),
    riesgo: str = Query(default=""),
    caso: str = Query(default=""),
    dni: str = Query(default=""),
    departamento: str = Query(default=""),
    tramo: str = Query(default="", description="'' | 'M1' | 'M2' | 'M3'"),
):
    return _mora_kw(mes, grupo, recibo, supervisor, distrito, riesgo, caso, dni, departamento, tramo)


@app.get("/mora/resumen")
def mora_resumen(
    mes: Optional[int] = Query(default=None),
    grupo: str = Query(default=""),
    recibo: str = Query(default=""),
    supervisor: str = Query(default=""),
    distrito: str = Query(default=""),
    riesgo: str = Query(default=""),
    caso: str = Query(default=""),
    dni: str = Query(default=""),
    departamento: str = Query(default=""),
    tramo: str = Query(default=""),
):
    return get_mora_resumen(**_mora_kw(mes, grupo, recibo, supervisor, distrito, riesgo, caso, dni, departamento, tramo))


@app.get("/mora/embudo")
def mora_embudo(
    mes: Optional[int] = Query(default=None),
    grupo: str = Query(default=""),
    recibo: str = Query(default=""),
    supervisor: str = Query(default=""),
    distrito: str = Query(default=""),
    riesgo: str = Query(default=""),
    caso: str = Query(default=""),
    dni: str = Query(default=""),
    departamento: str = Query(default=""),
    tramo: str = Query(default=""),
):
    return get_mora_embudo(**_mora_kw(mes, grupo, recibo, supervisor, distrito, riesgo, caso, dni, departamento, tramo))


@app.get("/mora/perdidas")
def mora_perdidas(
    mes: Optional[int] = Query(default=None),
    grupo: str = Query(default=""),
    recibo: str = Query(default=""),
    supervisor: str = Query(default=""),
    distrito: str = Query(default=""),
    riesgo: str = Query(default=""),
    caso: str = Query(default=""),
    dni: str = Query(default=""),
    departamento: str = Query(default=""),
    tramo: str = Query(default=""),
):
    return get_mora_perdidas(**_mora_kw(mes, grupo, recibo, supervisor, distrito, riesgo, caso, dni, departamento, tramo))


@app.get("/mora/supervisores")
def mora_supervisores(
    mes: Optional[int] = Query(default=None),
    grupo: str = Query(default=""),
    recibo: str = Query(default=""),
    supervisor: str = Query(default=""),
    distrito: str = Query(default=""),
    riesgo: str = Query(default=""),
    caso: str = Query(default=""),
    dni: str = Query(default=""),
    departamento: str = Query(default=""),
    tramo: str = Query(default=""),
):
    return get_mora_supervisores(**_mora_kw(mes, grupo, recibo, supervisor, distrito, riesgo, caso, dni, departamento, tramo))


@app.get("/mora/casos")
def mora_casos(
    mes: Optional[int] = Query(default=None),
    grupo: str = Query(default=""),
    recibo: str = Query(default=""),
    supervisor: str = Query(default=""),
    distrito: str = Query(default=""),
    riesgo: str = Query(default=""),
    caso: str = Query(default=""),
    dni: str = Query(default=""),
    departamento: str = Query(default=""),
    tramo: str = Query(default=""),
):
    return get_mora_casos(**_mora_kw(mes, grupo, recibo, supervisor, distrito, riesgo, caso, dni, departamento, tramo))


@app.get("/mora/distritos")
def mora_distritos(
    mes: Optional[int] = Query(default=None),
    grupo: str = Query(default=""),
    recibo: str = Query(default=""),
    supervisor: str = Query(default=""),
    distrito: str = Query(default=""),
    riesgo: str = Query(default=""),
    caso: str = Query(default=""),
    dni: str = Query(default=""),
    departamento: str = Query(default=""),
    tramo: str = Query(default=""),
):
    return get_mora_distritos(**_mora_kw(mes, grupo, recibo, supervisor, distrito, riesgo, caso, dni, departamento, tramo))


@app.get("/mora/paquetes")
def mora_paquetes(
    mes: Optional[int] = Query(default=None),
    grupo: str = Query(default=""),
    recibo: str = Query(default=""),
    supervisor: str = Query(default=""),
    distrito: str = Query(default=""),
    riesgo: str = Query(default=""),
    caso: str = Query(default=""),
    dni: str = Query(default=""),
    departamento: str = Query(default=""),
    tramo: str = Query(default=""),
):
    return get_mora_paquetes(**_mora_kw(mes, grupo, recibo, supervisor, distrito, riesgo, caso, dni, departamento, tramo))


@app.get("/mora/riesgos")
def mora_riesgos(
    mes: Optional[int] = Query(default=None),
    grupo: str = Query(default=""),
    recibo: str = Query(default=""),
    supervisor: str = Query(default=""),
    distrito: str = Query(default=""),
    riesgo: str = Query(default=""),
    caso: str = Query(default=""),
    dni: str = Query(default=""),
    departamento: str = Query(default=""),
    tramo: str = Query(default=""),
):
    return get_mora_riesgos(**_mora_kw(mes, grupo, recibo, supervisor, distrito, riesgo, caso, dni, departamento, tramo))


@app.get("/mora/detalle")
def mora_detalle(
    mes: Optional[int] = Query(default=None),
    grupo: str = Query(default=""),
    recibo: str = Query(default=""),
    supervisor: str = Query(default=""),
    distrito: str = Query(default=""),
    riesgo: str = Query(default=""),
    caso: str = Query(default=""),
    dni: str = Query(default=""),
    departamento: str = Query(default=""),
    tramo: str = Query(default=""),
):
    return get_mora_detalle(**_mora_kw(mes, grupo, recibo, supervisor, distrito, riesgo, caso, dni, departamento, tramo))


@app.get("/mora/pagos-dia")
def mora_pagos_dia(
    mes: Optional[int] = Query(default=None),
    grupo: str = Query(default=""),
    recibo: str = Query(default=""),
    supervisor: str = Query(default=""),
    distrito: str = Query(default=""),
    riesgo: str = Query(default=""),
    caso: str = Query(default=""),
    dni: str = Query(default=""),
    departamento: str = Query(default=""),
    tramo: str = Query(default=""),
):
    return get_mora_pagos_dia(**_mora_kw(mes, grupo, recibo, supervisor, distrito, riesgo, caso, dni, departamento, tramo))


@app.get("/mora/pagos-acumulado")
def mora_pagos_acumulado(
    mes: Optional[int] = Query(default=None),
    grupo: str = Query(default=""),
    recibo: str = Query(default=""),
    supervisor: str = Query(default=""),
    distrito: str = Query(default=""),
    riesgo: str = Query(default=""),
    caso: str = Query(default=""),
    dni: str = Query(default=""),
    departamento: str = Query(default=""),
    tramo: str = Query(default=""),
):
    return get_mora_pagos_acumulado(**_mora_kw(mes, grupo, recibo, supervisor, distrito, riesgo, caso, dni, departamento, tramo))


@app.get("/mora/filtros")
def mora_filtros():
    return get_mora_filtros()


# ── Usuarios ─────────────────────────────────────────────────────────────────

@app.get("/usuarios")
def usuarios(
    search: str = Query(default=""),
    agencia: str = Query(default=""),
    supervisor: str = Query(default=""),
    cargo: str = Query(default=""),
    estado: str = Query(default=""),
):
    return get_usuarios(search=search, agencia=agencia, supervisor=supervisor, cargo=cargo, estado=estado)


@app.get("/usuarios/stats")
def usuarios_stats():
    return get_usuarios_stats()


@app.get("/usuarios/agencias")
def agencias():
    return get_agencias_list()


@app.get("/usuarios/supervisores")
def supervisores():
    return get_supervisores_list()


# ── Varios ────────────────────────────────────────────────────────────────────

@app.get("/departamentos")
def departamentos():
    return get_departamentos()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8001, reload=True)
