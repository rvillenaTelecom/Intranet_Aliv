import os
import json
from datetime import datetime

try:
    import db_helper
except ImportError:
    from . import db_helper

_client = None
_MES_HOY  = datetime.now().month
_ANIO_HOY = datetime.now().year
_FECHA_HOY = datetime.now().strftime('%d/%m/%Y')

SYSTEM_PROMPT = f"""Eres el asistente virtual de AlivTelecom, empresa de telecomunicaciones (internet por fibra óptica) en Perú.
Hoy es {_FECHA_HOY}. El mes activo es {_MES_HOY}/{_ANIO_HOY}.

══════════════════════════════════════
MÓDULO VENTAS
══════════════════════════════════════
MÉTRICAS CLAVE:
- Ventas: clientes registrados en Winforce (sistema CRM). No todas se instalan.
- Altas: instalaciones ejecutadas (Estado orden = 'Ejecutada'). Es la métrica más importante.
- Anulaciones: ventas canceladas (Estado orden = 'Anulado').
- Cuota: meta mensual de altas por región.
- Conversión: % de ventas que se instalaron como altas.
- Proyección: estimación de altas al cierre del mes según ritmo actual.
- Alcance: % de la cuota ya cumplido.
- Alcance ideal: % que deberías tener según los días transcurridos del mes.
- Ritmo actual: altas por día en promedio hasta hoy.
- Ritmo necesario: altas por día que hacen falta para cumplir la cuota.
- Faltantes: altas que faltan para llegar a la cuota.

ÁREAS DE PLANEAMIENTO (solo Lima):
- Vertical: domicilios tipo Condominio/Edificio. Alta densidad, menor costo por cliente.
- Horizontal: casas, quintas y otros. Mayor dispersión geográfica.

LÓGICA DE ANÁLISIS — VENTAS:
- alcance < alcance_ideal → equipo REZAGADO respecto al ritmo esperado del mes.
- alcance >= alcance_ideal → equipo ADELANTADO o en ritmo.
- ritmo_actual < ritmo_necesario → hay que acelerar instalaciones.
- conversión < 40% → problema en proceso de instalación (muchas ventas no se ejecutan).
- anulaciones > 15% de ventas → problemas de calidad o proceso comercial.

══════════════════════════════════════
MÓDULO MOROSIDAD Y CLAWBACK
══════════════════════════════════════
CONCEPTOS CLAVE:
- Recibo / Cobro: cada alta genera 3 recibos mensuales (R1, R2, R3) a los que AlivTelecom hace seguimiento.
- NPNF (No Pago No Facturo): cliente dado de baja o churn antes de pagar el primer recibo (R1). Es el peor escenario → descuento del 100% de la comisión del vendedor.
- Extorno 2: cliente pagó R1 pero cayó en churn/baja en R2. Descuento del 66.6% de la comisión.
- Extorno 3: cliente pagó R1 y R2 pero cayó en churn/baja en R3. Descuento del 33.3% de la comisión.
- Pagaron R1/R2/R3: clientes que pagaron TODOS los recibos hasta ese mes.
- Clawback: mecanismo por el que AlivTelecom descuenta comisiones cuando los clientes no pagan.
- Comisión Bruta: Total Clientes × ARPU Promedio × 3.5 (fórmula DAX).
- Comisión Neta: Comisión Bruta − (Costo NPNF + Costo Extorno2 + Costo Extorno3).
- Descuentos: suma de los 3 costos de clawback. El % sobre Comisión Bruta = impacto total.

UMBRALES DE TOLERANCIA (hasta aquí no hay descuento):
- NPNF: hasta 4.5% del total de clientes → sobre ese umbral se cobra al vendedor.
- Extorno 2: hasta 3.5% de los que pagaron R1 → sobre ese umbral se cobra.
- Extorno 3: hasta 2.5% de los que pagaron R2 → sobre ese umbral se cobra.

FÓRMULA DE COSTO POR EXCESO:
- Costo NPNF    = (npnf − umbral_n)  × ARPU × 3.5 × 1.000
- Costo Extorno2= (no_r2 − umbral_2) × ARPU × 3.5 × 0.666
- Costo Extorno3= (no_r3 − umbral_3) × ARPU × 3.5 × 0.333
- Solo se cobra si el exceso > 0 (no hay descuento si está dentro del umbral).

ESTADOS DE PAGO:
- 'Cliente Pago' / 'Tercero Pago' → el cliente pagó ese recibo.
- 'Churn' / 'Cliente De Baja' → el cliente no pagó y fue dado de baja.

EMBUDO DE RETENCIÓN (interpretación):
- Pagaron R1 / Total → % de clientes que sobrevivieron al primer mes.
- Pagaron R2 / Total → % que llegaron al segundo mes pagando.
- Pagaron R3 / Total → % que completaron los 3 recibos (ideal ≥ 85%).
- Cuántos "faltan pagar": Total − PagaronR1 (sin pagar R1), PagaronR1 − PagaronR2, PagaronR2 − PagaronR3.

ESTADO DEL INDICADOR:
- ok: mora ≤ 70% del umbral → sin riesgo de descuento.
- alerta: mora entre 70% y 100% del umbral → próximo a generar descuento.
- critico: mora > umbral → ya genera costo para el supervisor/agencia.

RIESGO CLAWBACK: Bajo / Medio / Alto → clasificación del riesgo de cada cliente.
TIPO CASO CLAWBACK: Puede ser NPNF, Extorno 2, Extorno 3, etc.
RECIBO ACTUAL: R1, R2 o R3 (recibo en curso del cliente).
GRUPO FACTURACIÓN: agrupamiento de ciclos de facturación.

FILTROS DISPONIBLES PARA MOROSIDAD (todos opcionales):
- mes: número del mes de recibo (Mes_Num_Recibo).
- grupo: Grupo_Facturacion.
- recibo: Recibo_Actual (R1, R2, R3).
- supervisor: nombre exacto del supervisor.
- distrito: nombre del distrito de Lima.
- riesgo: Riesgo_Clawback (ej: 'Alto', 'Medio', 'Bajo').
- caso: Tipo_Caso_Clawback (ej: 'NPNF', 'Extorno 2', 'Extorno 3').
- dni: búsqueda parcial de DNI del cliente.

LÓGICA DE ANÁLISIS — MOROSIDAD:
- Si pct_mora NPNF > 4.5% → el equipo está en zona de descuento real, urgente revisar.
- Si costo_npnf alto en supervisor → ese supervisor está generando pérdidas de comisión.
- Si Extorno 2 > 3.5% → problema de retención a segundo mes, posible fraude o mala calidad de venta.
- Si Extorno 3 > 2.5% → el cliente llega pero no persiste, revisar postventa.
- Impacto % = descuentos / comisión bruta × 100 → indica cuánto se pierde de la comisión total.
- Supervisores con mayor pct_mora son los que más afectan la comisión neta del equipo.

══════════════════════════════════════
CAPACIDADES DE CONSULTA COMPLETAS
══════════════════════════════════════
VENTAS:
- KPIs globales de Lima o Provincia (cualquier mes/año).
- Datos de UN distrito específico de Lima.
- Datos de UNA agencia específica de Lima (altas, ventas, anulaciones, top vendedores y planes).
- Ranking de TODAS las agencias de Lima ordenadas por altas.
- Datos de UN vendedor específico (altas, ventas, agencia, supervisor, top planes y distritos).
- Ranking de vendedores de Lima (con filtro por supervisor o agencia si se usa top alto).
- Distribución Vertical/Horizontal, estados de órdenes, anulaciones por agencia.
- Tabla pivot Planes × Agencias, tabla Provincia por región.
- Comparación entre dos meses.

DIRECTORIO DE USUARIOS (dim_usuarios_Aliv):
- Buscar vendedor por nombre o username.
- Ver todos los vendedores de una agencia o supervisor.
- Consultar cargo, canal y estado de un usuario.

FILTROS DISPONIBLES PARA AGENCIAS Y VENDEDORES:
- agencia: nombre o parte del nombre (ej: 'DEZANET', 'PRINCE', 'FUTURA'). Búsqueda flexible.
- vendedor: username o parte del nombre en Winforce.
- supervisor: nombre del supervisor para filtrar el ranking de vendedores.
- area: 'Vertical' o 'Horizontal' para segmentar por tipo de vivienda.
- dia: número del día del mes (1-31) para consultas diarias. LÓGICA:
  · Ventas registradas ese día → se filtra por DAY(Fecha de registro) = dia.
  · Altas ejecutadas ese día  → se filtra por DAY(Fecha programación)  = dia.
  · Cuando el usuario diga 'ayer', 'hoy', 'el día X', 'el martes pasado' etc., convierte a número de día del mes actual y úsalo como dia.
  · Si no se especifica día, la consulta abarca todo el mes.

MOROSIDAD:
- Resumen general: total clientes, ARPU, comisión bruta/neta, descuentos, días para corte.
- Embudo de retención: cuántos pagaron R1, R2, R3 y cuántos faltan.
- Tabla de pérdidas: NPNF/Extorno2/Extorno3 con umbral, exceso, costo y estado (ok/alerta/crítico).
- Ranking de supervisores por % mora y costo generado.
- Distribución por tipo de caso clawback.
- Top 10 distritos con más NPNF.
- Top 10 paquetes con más mora y deuda.
- Distribución por nivel de riesgo clawback.
- Detalle individual de clientes (con filtros: DNI, supervisor, distrito, recibo, riesgo, caso).
- Cualquier combinación de los anteriores con filtros aplicados.

INSTRUCCIONES DE RESPUESTA:
- Responde siempre en español, de forma directa y ejecutiva (estás hablando con gerentes).
- Usa viñetas para listas de datos o recomendaciones.
- Cuando presentes números usa formato legible (ej: 2,332 altas, S/. 45,320.00).
- Interpreta los datos y da recomendaciones concretas, no solo tablas de números.
- Si el usuario no especifica mes/año, usa el mes y año actual ({_MES_HOY}/{_ANIO_HOY}).
- No menciones el nombre de las funciones internas que usas.
- Si necesitas varios datos para responder completamente, llama múltiples tools en paralelo.
- No límites tu respuesta artificialmente: si el usuario pide un reporte completo, dalo completo.
- Para preguntas de morosidad sin filtro de mes, omite el parámetro mes (trae todos los datos activos).
- Cuando el usuario mencione 'R1', 'R2', 'R3' se refiere al recibo (Recibo_Actual).
- Cuando mencione 'supervisor' busca con el filtro supervisor exacto o ranking de supervisores.
"""

_TOOL_DECLARATIONS = [
    {
        "name": "obtener_kpi_lima",
        "description": "Obtiene KPIs de Lima: ventas, altas, cuota, conversión, proyección, alcance, ritmo actual/necesario, faltantes, score y días del mes.",
        "parameters": {
            "type": "object",
            "properties": {
                "mes":  {"type": "integer", "description": "Número de mes (1-12)"},
                "anio": {"type": "integer", "description": "Año (ej: 2026)"},
                "area": {"type": "string",  "description": "Área: 'Vertical', 'Horizontal' o '' para todas"},
            },
            "required": ["mes", "anio"],
        },
    },
    {
        "name": "obtener_kpi_provincia",
        "description": "Obtiene KPIs de Provincia: ventas, altas, cuota, conversión, proyección, alcance, ritmo actual/necesario y faltantes.",
        "parameters": {
            "type": "object",
            "properties": {
                "mes":  {"type": "integer", "description": "Número de mes (1-12)"},
                "anio": {"type": "integer", "description": "Año (ej: 2026)"},
            },
            "required": ["mes", "anio"],
        },
    },
    {
        "name": "obtener_top_distritos_lima",
        "description": "Obtiene los distritos de Lima con más altas (instalaciones ejecutadas) en el período indicado.",
        "parameters": {
            "type": "object",
            "properties": {
                "mes":  {"type": "integer", "description": "Número de mes (1-12)"},
                "anio": {"type": "integer", "description": "Año (ej: 2026)"},
                "top":  {"type": "integer", "description": "Cantidad de distritos (default 10)"},
                "area": {"type": "string",  "description": "Área: 'Vertical', 'Horizontal' o '' para todas"},
            },
            "required": ["mes", "anio"],
        },
    },
    {
        "name": "obtener_tipo_vivienda_lima",
        "description": "Obtiene la distribución de ventas y altas de Lima por tipo de domicilio (Vertical vs Horizontal).",
        "parameters": {
            "type": "object",
            "properties": {
                "mes":  {"type": "integer", "description": "Número de mes (1-12)"},
                "anio": {"type": "integer", "description": "Año (ej: 2026)"},
            },
            "required": ["mes", "anio"],
        },
    },
    {
        "name": "obtener_distribucion_estados_lima",
        "description": "Obtiene la distribución de estados de órdenes de Lima (Ejecutada, Anulado, En proceso, etc.).",
        "parameters": {
            "type": "object",
            "properties": {
                "mes":  {"type": "integer", "description": "Número de mes (1-12)"},
                "anio": {"type": "integer", "description": "Año (ej: 2026)"},
                "area": {"type": "string",  "description": "Área: 'Vertical', 'Horizontal' o '' para todas"},
            },
            "required": ["mes", "anio"],
        },
    },
    {
        "name": "obtener_tabla_provincia",
        "description": "Obtiene la tabla de ventas y altas de Provincia desglosada por región o agencia.",
        "parameters": {
            "type": "object",
            "properties": {
                "mes":  {"type": "integer", "description": "Número de mes (1-12)"},
                "anio": {"type": "integer", "description": "Año (ej: 2026)"},
            },
            "required": ["mes", "anio"],
        },
    },
    {
        "name": "obtener_pivot_agencias_lima",
        "description": "Obtiene tabla de altas de Lima desglosada por Plan y Agencia. Ideal para saber qué agencia tiene más instalaciones o qué planes venden más por agencia.",
        "parameters": {
            "type": "object",
            "properties": {
                "mes":  {"type": "integer", "description": "Número de mes (1-12)"},
                "anio": {"type": "integer", "description": "Año (ej: 2026)"},
                "area": {"type": "string",  "description": "Área: 'Vertical', 'Horizontal' o '' para todas"},
            },
            "required": ["mes", "anio"],
        },
    },
    {
        "name": "obtener_top_vendedores_lima",
        "description": "Ranking de vendedores de Lima ordenados por altas (instalaciones ejecutadas). Incluye agencia y supervisor. Usa top=50 o más para ver todos.",
        "parameters": {
            "type": "object",
            "properties": {
                "mes":  {"type": "integer", "description": "Número de mes (1-12)"},
                "anio": {"type": "integer", "description": "Año (ej: 2026)"},
                "top":  {"type": "integer", "description": "Cantidad de vendedores (default 10)"},
                "dia":  {"type": "integer", "description": "Día del mes (1-31). Altas: filtra por Fecha programación de ese día."},
            },
            "required": ["mes", "anio"],
        },
    },
    {
        "name": "obtener_datos_distrito_lima",
        "description": "Datos completos de UN distrito específico de Lima: altas, ventas, % conversión, top 5 planes y top 5 vendedores del distrito. La búsqueda es flexible (no necesitas el nombre exacto: 'ATE' encuentra 'ATE VITARTE', 'SAN BORJA' encuentra 'SAN BORJA', etc.). Úsalo cuando el usuario pregunta por un distrito concreto.",
        "parameters": {
            "type": "object",
            "properties": {
                "mes":      {"type": "integer", "description": "Número de mes (1-12)"},
                "anio":     {"type": "integer", "description": "Año (ej: 2026)"},
                "distrito": {"type": "string",  "description": "Nombre o parte del nombre del distrito en mayúsculas (ej: 'ATE', 'SAN BORJA', 'MIRAFLORES', 'COMAS')"},
                "area":     {"type": "string",  "description": "Área: 'Vertical', 'Horizontal' o '' para todas"},
            },
            "required": ["mes", "anio", "distrito"],
        },
    },
    {
        "name": "obtener_anulaciones_agencia_lima",
        "description": "Anulaciones de Lima agrupadas por agencia, con porcentaje sobre el total de anulaciones. Útil para detectar qué agencias generan más cancelaciones.",
        "parameters": {
            "type": "object",
            "properties": {
                "mes":  {"type": "integer", "description": "Número de mes (1-12)"},
                "anio": {"type": "integer", "description": "Año (ej: 2026)"},
                "area": {"type": "string",  "description": "Área: 'Vertical', 'Horizontal' o '' para todas"},
            },
            "required": ["mes", "anio"],
        },
    },
    {
        "name": "obtener_comparacion_meses_lima",
        "description": "Compara KPIs de Lima entre dos meses distintos: diferencia de altas, ventas y ratios. Útil para preguntas como '¿cómo estuvo mayo vs abril?'.",
        "parameters": {
            "type": "object",
            "properties": {
                "mes1":  {"type": "integer", "description": "Mes del primer período (1-12)"},
                "anio1": {"type": "integer", "description": "Año del primer período"},
                "mes2":  {"type": "integer", "description": "Mes del segundo período (1-12)"},
                "anio2": {"type": "integer", "description": "Año del segundo período"},
                "area":  {"type": "string",  "description": "Área: 'Vertical', 'Horizontal' o '' para todas"},
            },
            "required": ["mes1", "anio1", "mes2", "anio2"],
        },
    },

    # ── AGENCIAS Y VENDEDORES ─────────────────────────────────────────────────
    {
        "name": "obtener_datos_agencia_lima",
        "description": (
            "Datos completos de UNA agencia específica de Lima: altas, ventas, anulaciones, "
            "conversión, top 10 vendedores, top 5 planes y supervisores de esa agencia. "
            "Búsqueda flexible: 'DEZANET' encuentra 'Dezanet', 'PRINCE' encuentra 'Prince', etc. "
            "Úsalo cuando el usuario pregunte por una agencia concreta: "
            "'cuántas ventas tiene Dezanet ayer', 'top vendedores de Prince el día 11', 'resultados de Futura'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mes":     {"type": "integer", "description": "Número de mes (1-12)"},
                "anio":    {"type": "integer", "description": "Año (ej: 2026)"},
                "agencia": {"type": "string",  "description": "Nombre o parte del nombre de la agencia (ej: 'DEZANET', 'PRINCE', 'FUTURA', 'LOTTUS')"},
                "area":    {"type": "string",  "description": "Área: 'Vertical', 'Horizontal' o '' para todas"},
                "dia":     {"type": "integer", "description": "Día del mes (1-31). Ventas: filtra por Fecha de registro. Altas: filtra por Fecha programación (ejecutadas ese día)."},
            },
            "required": ["mes", "anio", "agencia"],
        },
    },
    {
        "name": "obtener_ranking_agencias_lima",
        "description": (
            "Ranking de TODAS las agencias de Lima ordenadas por altas, con ventas, "
            "anulaciones y % de conversión. Úsalo cuando el usuario quiera comparar agencias, "
            "ver cuál tiene más instalaciones, o pedir el ranking/tabla de agencias."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mes":  {"type": "integer", "description": "Número de mes (1-12)"},
                "anio": {"type": "integer", "description": "Año (ej: 2026)"},
                "area": {"type": "string",  "description": "Área: 'Vertical', 'Horizontal' o '' para todas"},
                "dia":  {"type": "integer", "description": "Día del mes (1-31). Ventas: Fecha de registro. Altas: Fecha programación."},
            },
            "required": ["mes", "anio"],
        },
    },
    {
        "name": "obtener_datos_vendedor",
        "description": (
            "Datos de UN vendedor específico de Lima: altas, ventas, anulaciones, "
            "agencia, supervisor, top 5 planes y top 5 distritos. "
            "Búsqueda flexible por username o parte del nombre. "
            "Úsalo cuando el usuario pregunte por un vendedor concreto: "
            "'cuántas altas tiene JPEREZ ayer', 'rendimiento de Juan Pérez el día 5', 'datos del vendedor X'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mes":      {"type": "integer", "description": "Número de mes (1-12)"},
                "anio":     {"type": "integer", "description": "Año (ej: 2026)"},
                "vendedor": {"type": "string",  "description": "Username o parte del nombre del vendedor en Winforce"},
                "dia":      {"type": "integer", "description": "Día del mes (1-31). Ventas: Fecha de registro. Altas: Fecha programación."},
            },
            "required": ["mes", "anio", "vendedor"],
        },
    },
    {
        "name": "buscar_directorio",
        "description": (
            "Busca en el directorio interno de usuarios AlivTelecom (dim_usuarios_Aliv). "
            "Retorna nombre completo, agencia, supervisor, cargo, canal y estado. "
            "Útil para: '¿a qué agencia pertenece el vendedor X?', "
            "'¿quién es el supervisor de la agencia Y?', "
            "'lista de vendedores de la agencia Z', '¿qué cargo tiene fulano?'. "
            "No requiere mes ni año — es el directorio actual."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "vendedor":   {"type": "string", "description": "Username o nombre del vendedor a buscar"},
                "agencia":    {"type": "string", "description": "Nombre exacto de la agencia"},
                "cargo":      {"type": "string", "description": "Cargo: Vendedor, Supervisor, Jefe de Agencia, Admin"},
                "supervisor": {"type": "string", "description": "Nombre exacto del supervisor"},
                "estado":     {"type": "string", "description": "Estado: Activo o Inactivo"},
            },
            "required": [],
        },
    },

    # ── MOROSIDAD ────────────────────────────────────────────────────────────
    {
        "name": "obtener_mora_resumen",
        "description": (
            "Resumen general de morosidad/clawback: total clientes, ARPU promedio, "
            "comisión bruta (Total×ARPU×3.5), comisión neta, total descuentos, "
            "% impacto y días para el corte de comisiones. "
            "Úsalo cuando el usuario pregunte por KPIs de morosidad, comisiones, clawback general."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mes":        {"type": "integer", "description": "Mes de recibo (Mes_Num_Recibo), omitir para todos"},
                "grupo":      {"type": "string",  "description": "Grupo de facturación"},
                "recibo":     {"type": "string",  "description": "Recibo actual: R1, R2 o R3"},
                "supervisor": {"type": "string",  "description": "Nombre exacto del supervisor"},
                "distrito":   {"type": "string",  "description": "Nombre del distrito"},
                "riesgo":     {"type": "string",  "description": "Riesgo_Clawback: Alto, Medio, Bajo"},
                "caso":       {"type": "string",  "description": "Tipo_Caso_Clawback: NPNF, Extorno 2, Extorno 3"},
                "dni":        {"type": "string",  "description": "Búsqueda parcial de DNI"},
            },
            "required": [],
        },
    },
    {
        "name": "obtener_mora_embudo",
        "description": (
            "Embudo de retención de cobros: total clientes, cuántos pagaron R1, R2, R3 "
            "y su porcentaje sobre el total. Sirve para responder '¿cuántos clientes pagaron "
            "el segundo recibo?', '¿cuál es la tasa de retención en R3?', etc."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mes":        {"type": "integer", "description": "Mes de recibo, omitir para todos"},
                "grupo":      {"type": "string",  "description": "Grupo de facturación"},
                "recibo":     {"type": "string",  "description": "R1, R2 o R3"},
                "supervisor": {"type": "string",  "description": "Nombre del supervisor"},
                "distrito":   {"type": "string",  "description": "Nombre del distrito"},
                "riesgo":     {"type": "string",  "description": "Alto, Medio, Bajo"},
                "caso":       {"type": "string",  "description": "NPNF, Extorno 2, Extorno 3"},
            },
            "required": [],
        },
    },
    {
        "name": "obtener_mora_perdidas",
        "description": (
            "Tabla de pérdidas por clawback: para NPNF, Extorno 2 y Extorno 3 muestra "
            "la base, umbral permitido, clientes morosos, exceso sobre umbral, costo en soles "
            "y estado (ok/alerta/critico). Úsalo para '¿cuánto estamos perdiendo?', "
            "'¿estamos dentro del umbral?', '¿cuál es el costo de los NPNF?'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mes":        {"type": "integer", "description": "Mes de recibo, omitir para todos"},
                "grupo":      {"type": "string",  "description": "Grupo de facturación"},
                "recibo":     {"type": "string",  "description": "R1, R2 o R3"},
                "supervisor": {"type": "string",  "description": "Nombre del supervisor"},
                "distrito":   {"type": "string",  "description": "Nombre del distrito"},
                "riesgo":     {"type": "string",  "description": "Alto, Medio, Bajo"},
                "caso":       {"type": "string",  "description": "NPNF, Extorno 2, Extorno 3"},
            },
            "required": [],
        },
    },
    {
        "name": "obtener_mora_supervisores",
        "description": (
            "Ranking de supervisores ordenado por % de mora (NPNF). Incluye: total clientes, "
            "NPNF, Sin R2, Sin R3, % mora y costo NPNF en soles. Úsalo cuando el usuario "
            "pregunte '¿qué supervisor tiene más morosidad?', ranking de supervisores por mora, "
            "o quiera ver el impacto por supervisor."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mes":      {"type": "integer", "description": "Mes de recibo, omitir para todos"},
                "grupo":    {"type": "string",  "description": "Grupo de facturación"},
                "recibo":   {"type": "string",  "description": "R1, R2 o R3"},
                "distrito": {"type": "string",  "description": "Nombre del distrito"},
                "riesgo":   {"type": "string",  "description": "Alto, Medio, Bajo"},
                "caso":     {"type": "string",  "description": "NPNF, Extorno 2, Extorno 3"},
            },
            "required": [],
        },
    },
    {
        "name": "obtener_mora_casos",
        "description": (
            "Distribución de clientes morosos por tipo de caso clawback "
            "(NPNF, Extorno 2, Extorno 3, etc.) con porcentaje. "
            "Úsalo para '¿cuántos son NPNF vs Extorno?', distribución de tipos de mora."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mes":        {"type": "integer", "description": "Mes de recibo, omitir para todos"},
                "grupo":      {"type": "string",  "description": "Grupo de facturación"},
                "recibo":     {"type": "string",  "description": "R1, R2 o R3"},
                "supervisor": {"type": "string",  "description": "Nombre del supervisor"},
                "distrito":   {"type": "string",  "description": "Nombre del distrito"},
                "riesgo":     {"type": "string",  "description": "Alto, Medio, Bajo"},
            },
            "required": [],
        },
    },
    {
        "name": "obtener_mora_distritos",
        "description": (
            "Top 10 distritos de Lima con más clientes NPNF. Incluye total, NPNF y % mora. "
            "Úsalo para '¿en qué distritos hay más morosidad?', '¿qué zonas tienen más NPNF?'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mes":        {"type": "integer", "description": "Mes de recibo, omitir para todos"},
                "grupo":      {"type": "string",  "description": "Grupo de facturación"},
                "recibo":     {"type": "string",  "description": "R1, R2 o R3"},
                "supervisor": {"type": "string",  "description": "Nombre del supervisor"},
                "riesgo":     {"type": "string",  "description": "Alto, Medio, Bajo"},
                "caso":       {"type": "string",  "description": "NPNF, Extorno 2, Extorno 3"},
            },
            "required": [],
        },
    },
    {
        "name": "obtener_mora_paquetes",
        "description": (
            "Top 10 paquetes/planes con más clientes NPNF y mayor deuda total. "
            "Úsalo para '¿qué paquete tiene más mora?', '¿cuánta deuda acumula el plan X?', "
            "análisis de mora por plan de internet."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mes":        {"type": "integer", "description": "Mes de recibo, omitir para todos"},
                "grupo":      {"type": "string",  "description": "Grupo de facturación"},
                "recibo":     {"type": "string",  "description": "R1, R2 o R3"},
                "supervisor": {"type": "string",  "description": "Nombre del supervisor"},
                "distrito":   {"type": "string",  "description": "Nombre del distrito"},
                "riesgo":     {"type": "string",  "description": "Alto, Medio, Bajo"},
                "caso":       {"type": "string",  "description": "NPNF, Extorno 2, Extorno 3"},
            },
            "required": [],
        },
    },
    {
        "name": "obtener_mora_riesgos",
        "description": (
            "Distribución de clientes por nivel de riesgo clawback (Alto/Medio/Bajo): "
            "cantidad de clientes, deuda total y costo de comisión en riesgo. "
            "Úsalo para '¿cuántos clientes están en riesgo alto?', análisis de exposición por riesgo."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mes":        {"type": "integer", "description": "Mes de recibo, omitir para todos"},
                "grupo":      {"type": "string",  "description": "Grupo de facturación"},
                "recibo":     {"type": "string",  "description": "R1, R2 o R3"},
                "supervisor": {"type": "string",  "description": "Nombre del supervisor"},
                "distrito":   {"type": "string",  "description": "Nombre del distrito"},
                "caso":       {"type": "string",  "description": "NPNF, Extorno 2, Extorno 3"},
            },
            "required": [],
        },
    },
    {
        "name": "obtener_mora_detalle_clientes",
        "description": (
            "Lista detallada de clientes morosos individuales (hasta 2000 registros). "
            "Incluye DNI, paquete, precios, fechas y estados M1/M2/M3, deudas, recibo actual, "
            "último estado de pago, tipo de caso y riesgo. "
            "Úsalo cuando el usuario pida ver clientes específicos, buscar por DNI, "
            "ver los casos de un supervisor o distrito concreto, o explorar casos de M2/M3."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mes":        {"type": "integer", "description": "Mes de recibo, omitir para todos"},
                "grupo":      {"type": "string",  "description": "Grupo de facturación"},
                "recibo":     {"type": "string",  "description": "R1, R2 o R3"},
                "supervisor": {"type": "string",  "description": "Nombre del supervisor"},
                "distrito":   {"type": "string",  "description": "Nombre del distrito"},
                "riesgo":     {"type": "string",  "description": "Alto, Medio, Bajo"},
                "caso":       {"type": "string",  "description": "NPNF, Extorno 2, Extorno 3"},
                "dni":        {"type": "string",  "description": "Búsqueda parcial de DNI o número de carnet"},
            },
            "required": [],
        },
    },
]

_FUNC_MAP = {
    "obtener_kpi_lima": lambda a: db_helper.get_kpi_lima(
        a["mes"], a["anio"], area=a.get("area", "")
    ),
    "obtener_kpi_provincia": lambda a: db_helper.get_kpi_provincia(
        a["mes"], a["anio"]
    ),
    "obtener_top_distritos_lima": lambda a: db_helper.get_top_distritos_lima(
        a["mes"], a["anio"], top=int(a.get("top", 10)), area=a.get("area", "")
    ),
    "obtener_tipo_vivienda_lima": lambda a: db_helper.get_tipo_vivienda_lima(
        a["mes"], a["anio"]
    ),
    "obtener_distribucion_estados_lima": lambda a: db_helper.get_distribucion_estados_lima(
        a["mes"], a["anio"], area=a.get("area", "")
    ),
    "obtener_tabla_provincia": lambda a: db_helper.get_tabla_provincia(
        a["mes"], a["anio"]
    ),
    "obtener_pivot_agencias_lima": lambda a: db_helper.get_pivot_planes_agencia(
        a["mes"], a["anio"], area=a.get("area", "")
    ),
    "obtener_top_vendedores_lima": lambda a: db_helper.get_top_vendedores_lima(
        a["mes"], a["anio"], top=int(a.get("top", 10)), dia=a.get("dia")
    ),
    "obtener_datos_distrito_lima": lambda a: db_helper.get_datos_distrito_lima(
        a["mes"], a["anio"], a["distrito"], area=a.get("area", "")
    ),
    "obtener_anulaciones_agencia_lima": lambda a: db_helper.get_anulaciones_agencia_lima(
        a["mes"], a["anio"], area=a.get("area", "")
    ),
    "obtener_comparacion_meses_lima": lambda a: db_helper.get_comparacion_meses_lima(
        a["mes1"], a["anio1"], a["mes2"], a["anio2"], area=a.get("area", "")
    ),

    # ── AGENCIAS Y VENDEDORES ─────────────────────────────────────────────────
    "obtener_datos_agencia_lima": lambda a: db_helper.get_datos_agencia_lima(
        a["mes"], a["anio"], a["agencia"], area=a.get("area", ""), dia=a.get("dia")
    ),
    "obtener_ranking_agencias_lima": lambda a: db_helper.get_ranking_agencias_lima(
        a["mes"], a["anio"], area=a.get("area", ""), dia=a.get("dia")
    ),
    "obtener_datos_vendedor": lambda a: db_helper.get_datos_vendedor_lima(
        a["mes"], a["anio"], a["vendedor"], dia=a.get("dia")
    ),
    "buscar_directorio": lambda a: db_helper.get_usuarios(
        search=a.get("vendedor", ""),
        agencia=a.get("agencia", ""),
        cargo=a.get("cargo", ""),
        estado=a.get("estado", ""),
    ),

    # ── MOROSIDAD ────────────────────────────────────────────────────────────
    "obtener_mora_resumen": lambda a: db_helper.get_mora_resumen(
        **{k: v for k, v in a.items() if v not in (None, "")}
    ),
    "obtener_mora_embudo": lambda a: db_helper.get_mora_embudo(
        **{k: v for k, v in a.items() if v not in (None, "")}
    ),
    "obtener_mora_perdidas": lambda a: db_helper.get_mora_perdidas(
        **{k: v for k, v in a.items() if v not in (None, "")}
    ),
    "obtener_mora_supervisores": lambda a: db_helper.get_mora_supervisores(
        **{k: v for k, v in a.items() if v not in (None, "")}
    ),
    "obtener_mora_casos": lambda a: db_helper.get_mora_casos(
        **{k: v for k, v in a.items() if v not in (None, "")}
    ),
    "obtener_mora_distritos": lambda a: db_helper.get_mora_distritos(
        **{k: v for k, v in a.items() if v not in (None, "")}
    ),
    "obtener_mora_paquetes": lambda a: db_helper.get_mora_paquetes(
        **{k: v for k, v in a.items() if v not in (None, "")}
    ),
    "obtener_mora_riesgos": lambda a: db_helper.get_mora_riesgos(
        **{k: v for k, v in a.items() if v not in (None, "")}
    ),
    "obtener_mora_detalle_clientes": lambda a: db_helper.get_mora_detalle(
        **{k: v for k, v in a.items() if v not in (None, "")}
    ),
}


def _call_tool(name: str, args: dict):
    fn = _FUNC_MAP.get(name)
    if fn is None:
        return {"error": f"Función desconocida: {name}"}
    try:
        result = fn(args)
        if result is None:
            return {"sin_datos": "No hay datos para ese período."}
        return result
    except Exception as e:
        return {"error": str(e)}


def _get_client():
    global _client
    if _client is None:
        from google import genai
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise RuntimeError("GEMINI_API_KEY no está configurada.")
        _client = genai.Client(api_key=key)
    return _client


def generate_chat_response(messages: list, user_role: str = "", user_name: str = "") -> str:
    """
    messages: [{"role": "user"/"assistant", "content": "..."}]
    Retorna el texto de respuesta del asistente.
    """
    from google import genai
    from google.genai import types

    client = _get_client()

    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=m["content"])]))

    fn_decls = [
        types.FunctionDeclaration(
            name=t["name"],
            description=t["description"],
            parameters=t["parameters"],
        )
        for t in _TOOL_DECLARATIONS
    ]
    tool = types.Tool(function_declarations=fn_decls)

    system = SYSTEM_PROMPT
    if user_name:
        system += f"\nEl usuario que consulta se llama **{user_name}** y tiene el rol '{user_role}'."

    config = types.GenerateContentConfig(
        system_instruction=system,
        tools=[tool],
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode="AUTO")
        ),
        temperature=0.4,
    )

    loop_contents = list(contents)
    for _ in range(8):
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=loop_contents,
            config=config,
        )

        parts = response.candidates[0].content.parts
        fn_calls = [p for p in parts if p.function_call]

        if not fn_calls:
            return response.text or "No pude generar una respuesta. Intenta de nuevo."

        loop_contents.append(types.Content(role="model", parts=parts))

        fn_results = []
        for part in fn_calls:
            fc = part.function_call
            result = _call_tool(fc.name, dict(fc.args))
            fn_results.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=fc.name,
                        response={"result": json.dumps(result, ensure_ascii=False, default=str)},
                    )
                )
            )
        loop_contents.append(types.Content(role="user", parts=fn_results))

    return "No pude completar la consulta. Por favor intenta de nuevo."
