SELECT distinct  mes AS Mes     FROM corte_hora ORDER BY mes
SELECT distinct dia AS dia  FROM corte_hora ORDER BY dia
SELECT distinct anio AS año  FROM corte_hora ORDER BY anio
SELECT distinct hora AS hora   FROM corte_hora ORDER BY hora
SELECT Distinct filial   AS Filial  FROM corte_hora ORDER BY Filial

SELECT * FROM corte_hora
                    

SELECT 
	motivo_desaprobado,
	count(*) as conteo
FROM corte_hora
GROUP BY motivo_desaprobado


SELECT 
	estado_ficha_contrato,
	count(*) as conteo
FROM corte_hora
GROUP BY estado_ficha_contrato

SELECT 
	filial as Departamento,
	count(*) as conteo
FROM corte_hora
GROUP BY filial



-- =============================================
-- QUERIES DASHBOARD MIFIBRA_VENTAS
-- Tabla 1: BD_Ventas_Grupo_Pixel_Por_Hora (producción en tiempo real)
-- Tabla 2: BD_Ventas_Grupo_Pixel (ventas históricas)
-- Relación: usuarioIngreso → Usuario → Real_reporte (lider)
-- =============================================


-- ─────────────────────────────────────────────
-- TABLA 1 — PRODUCCIÓN
-- Filas: DEPARTAMENTO (FILIAL)
-- Columnas: Real_reporte (lider del vendedor)
-- Valores: conteo de registros
-- Filtros: ESTADO, Real_reporte
-- ─────────────────────────────────────────────
SELECT
    p.[FILIAL]                              AS Departamento,
    u.[Real_reporte]                        AS Lider,
    COUNT(*)                               AS Total_Registros,

    -- Por estado de ficha
    SUM(CASE WHEN p.[estadoFichaContrato] = 'APROBADO'
             THEN 1 ELSE 0 END)            AS Aprobados,
    SUM(CASE WHEN p.[estadoFichaContrato] = 'EN EVALUACION'
             THEN 1 ELSE 0 END)            AS En_Evaluacion,
    SUM(CASE WHEN p.[estadoFichaContrato] = 'DESAPROBADO'
             THEN 1 ELSE 0 END)            AS Desaprobados,
    SUM(CASE WHEN p.[estadoFichaContrato] = 'OBSERVADO'
             THEN 1 ELSE 0 END)            AS Observados,
    SUM(CASE WHEN p.[estadoFichaContrato] = 'EN EDICION'
             THEN 1 ELSE 0 END)            AS En_Edicion,

    -- Instaladas
    SUM(CASE WHEN p.[INSTALADA] = 'INSTALADA'
             THEN 1 ELSE 0 END)            AS Instaladas,
    SUM(CASE WHEN p.[INSTALADA] = 'NO INSTALADA'
             THEN 1 ELSE 0 END)            AS No_Instaladas

FROM BD_Ventas_Grupo_Pixel_Por_Hora p
LEFT JOIN BD_Ventas_Usuarios u
    ON p.[usuarioIngreso] = u.[Usuario]
WHERE (@estado      IS NULL OR p.[estadoFichaContrato] = @estado)
  AND (@real_reporte IS NULL OR u.[Real_reporte]        = @real_reporte)
  AND (@filial       IS NULL OR p.[FILIAL]              = @filial)
GROUP BY p.[FILIAL], u.[Real_reporte]
ORDER BY p.[FILIAL], u.[Real_reporte]


-- ─────────────────────────────────────────────
-- TABLA 1 PIVOT — PRODUCCIÓN (como en Power BI)
-- Filas: FILIAL · Columnas: Real_reporte
-- Para replicar el matrix exacto del dashboard
-- ─────────────────────────────────────────────
SELECT
    p.[FILIAL]                              AS Departamento,
    SUM(CASE WHEN u.[Real_reporte] = 'DEZANET'
             THEN 1 ELSE 0 END)            AS DEZANET,
    SUM(CASE WHEN u.[Real_reporte] = 'FIBER'
             THEN 1 ELSE 0 END)            AS FIBER,
    SUM(CASE WHEN u.[Real_reporte] = 'FLOR'
             THEN 1 ELSE 0 END)            AS FLOR,
    SUM(CASE WHEN u.[Real_reporte] = 'KELLY SALAZAR'
             THEN 1 ELSE 0 END)            AS KELLY_SALAZAR,
    SUM(CASE WHEN u.[Real_reporte] = 'LUIS SOTO'
             THEN 1 ELSE 0 END)            AS LUIS_SOTO,
    SUM(CASE WHEN u.[Real_reporte] = 'REDES'
             THEN 1 ELSE 0 END)            AS REDES,
    COUNT(*)                               AS Total
FROM BD_Ventas_Grupo_Pixel_Por_Hora p
LEFT JOIN BD_Ventas_Usuarios u
    ON p.[usuarioIngreso] = u.[Usuario]
WHERE (@estado      IS NULL OR p.[estadoFichaContrato] = @estado)
  AND (@filial       IS NULL OR p.[FILIAL]             = @filial)
GROUP BY p.[FILIAL]

UNION ALL

-- Fila de totales
SELECT
    'Total'                                AS Departamento,
    SUM(CASE WHEN u.[Real_reporte] = 'DEZANET'       THEN 1 ELSE 0 END),
    SUM(CASE WHEN u.[Real_reporte] = 'FIBER'         THEN 1 ELSE 0 END),
    SUM(CASE WHEN u.[Real_reporte] = 'FLOR'          THEN 1 ELSE 0 END),
    SUM(CASE WHEN u.[Real_reporte] = 'KELLY SALAZAR' THEN 1 ELSE 0 END),
    SUM(CASE WHEN u.[Real_reporte] = 'LUIS SOTO'     THEN 1 ELSE 0 END),
    SUM(CASE WHEN u.[Real_reporte] = 'REDES'         THEN 1 ELSE 0 END),
    COUNT(*)
FROM BD_Ventas_Grupo_Pixel_Por_Hora p
LEFT JOIN BD_Ventas_Usuarios u
    ON p.[usuarioIngreso] = u.[Usuario]
WHERE (@estado IS NULL OR p.[estadoFichaContrato] = @estado)

ORDER BY Departamento


-- ─────────────────────────────────────────────
-- TABLA 2 — VENTAS MI FIBRA
-- Filas: ESTADO (de BD_Ventas_Grupo_Pixel)
-- Columnas: Real_reporte (lider del vendedor)
-- Filtros: ESTADO, Real_reporte
-- ─────────────────────────────────────────────
SELECT
    v.[ESTADO ORDEN SERVICIO 2]             AS Estado,
    u.[Real_reporte]                        AS Lider,
    COUNT(*)                               AS Total
FROM BD_Ventas_Grupo_Pixel v
LEFT JOIN BD_Ventas_Usuarios u
    ON v.[VENDEDOR] = u.[Usuario]  -- join por vendedor
WHERE (@estado       IS NULL OR v.[ESTADO ORDEN SERVICIO 2] = @estado)
  AND (@real_reporte IS NULL OR u.[Real_reporte]             = @real_reporte)
  AND (@filial       IS NULL OR v.[FILIAL]                   = @filial)
  AND (@mes          IS NULL OR v.[MES_REG]                  = @mes)
GROUP BY v.[ESTADO ORDEN SERVICIO 2], u.[Real_reporte]
ORDER BY v.[ESTADO ORDEN SERVICIO 2], u.[Real_reporte]


-- ─────────────────────────────────────────────
-- TABLA 2 PIVOT — VENTAS MI FIBRA (como en Power BI)
-- Filas: ESTADO · Columnas: Real_reporte
-- ─────────────────────────────────────────────
SELECT
    v.[ESTADO ORDEN SERVICIO 2]             AS Estado,
    SUM(CASE WHEN u.[Real_reporte] = 'DEZANET'       THEN 1 ELSE 0 END) AS DEZANET,
    SUM(CASE WHEN u.[Real_reporte] = 'FIBER'         THEN 1 ELSE 0 END) AS FIBER,
    SUM(CASE WHEN u.[Real_reporte] = 'FLOR'          THEN 1 ELSE 0 END) AS FLOR,
    SUM(CASE WHEN u.[Real_reporte] = 'KELLY SALAZAR' THEN 1 ELSE 0 END) AS KELLY_SALAZAR,
    SUM(CASE WHEN u.[Real_reporte] = 'LUIS SOTO'     THEN 1 ELSE 0 END) AS LUIS_SOTO,
    SUM(CASE WHEN u.[Real_reporte] = 'REDES'         THEN 1 ELSE 0 END) AS REDES,
    COUNT(*)                               AS Total
FROM BD_Ventas_Grupo_Pixel v
LEFT JOIN BD_Ventas_Usuarios u
    ON v.[VENDEDOR] = u.[Usuario]
WHERE (@estado       IS NULL OR v.[ESTADO ORDEN SERVICIO 2] = @estado)
  AND (@real_reporte IS NULL OR u.[Real_reporte]             = @real_reporte)
  AND (@filial       IS NULL OR v.[FILIAL]                   = @filial)
  AND (@mes          IS NULL OR v.[MES_REG]                  = @mes)
GROUP BY v.[ESTADO ORDEN SERVICIO 2]

UNION ALL

SELECT
    'Total'                                AS Estado,
    SUM(CASE WHEN u.[Real_reporte] = 'DEZANET'       THEN 1 ELSE 0 END),
    SUM(CASE WHEN u.[Real_reporte] = 'FIBER'         THEN 1 ELSE 0 END),
    SUM(CASE WHEN u.[Real_reporte] = 'FLOR'          THEN 1 ELSE 0 END),
    SUM(CASE WHEN u.[Real_reporte] = 'KELLY SALAZAR' THEN 1 ELSE 0 END),
    SUM(CASE WHEN u.[Real_reporte] = 'LUIS SOTO'     THEN 1 ELSE 0 END),
    SUM(CASE WHEN u.[Real_reporte] = 'REDES'         THEN 1 ELSE 0 END),
    COUNT(*)
FROM BD_Ventas_Grupo_Pixel v
LEFT JOIN BD_Ventas_Usuarios u
    ON v.[VENDEDOR] = u.[Usuario]
WHERE (@estado       IS NULL OR v.[ESTADO ORDEN SERVICIO 2] = @estado)
  AND (@real_reporte IS NULL OR u.[Real_reporte]             = @real_reporte)
  AND (@mes          IS NULL OR v.[MES_REG]                  = @mes)

ORDER BY Estado


