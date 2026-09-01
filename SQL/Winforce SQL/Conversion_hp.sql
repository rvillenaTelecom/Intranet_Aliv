-- ============================================================
-- Conversión PV→VT y VT→AT — Diario y Mensual
-- PV→VT: registros con Estado del Pedido aprobado
-- VT→AT: ventas aprobadas que pasaron a Ejecutada
--        con Fecha programación en el mes actual
-- ============================================================
-- DIARIO
SELECT CAST(
        TRY_CONVERT(DATE, wf.[Fecha de registro], 120) AS DATE
    ) AS fecha,
    -- Capa 1: Preventas (todos los registros del día)
    COUNT(*) AS preventas,
    -- Capa 2: Ventas aprobadas (Estado del Pedido = Validado/Aprobado)
    SUM(
        CASE
            WHEN wf.[Estado del Pedido] IN ('Validado', 'Aprobado') THEN 1
            ELSE 0
        END
    ) AS ventas_aprobadas,
    -- Capa 3: Altas (Ejecutada con Fecha programación en el mes)
    SUM(
        CASE
            WHEN wf.[Estado orden] = 'Ejecutada'
            AND YEAR(TRY_CONVERT(DATE, wf.[Fecha programación], 105)) = YEAR(GETDATE())
            AND MONTH(TRY_CONVERT(DATE, wf.[Fecha programación], 105)) = MONTH(GETDATE()) THEN 1
            ELSE 0
        END
    ) AS altas,
    -- PV/VT diario
    CAST(
        SUM(
            CASE
                WHEN wf.[Estado del Pedido] IN ('Validado', 'Aprobado') THEN 1
                ELSE 0
            END
        ) * 100.0 / NULLIF(COUNT(*), 0) AS DECIMAL(5, 1)
    ) AS pvvt_pct,
    -- VT/AT diario
    CAST(
        SUM(
            CASE
                WHEN wf.[Estado orden] = 'Ejecutada'
                AND YEAR(TRY_CONVERT(DATE, wf.[Fecha programación], 105)) = YEAR(GETDATE())
                AND MONTH(TRY_CONVERT(DATE, wf.[Fecha programación], 105)) = MONTH(GETDATE()) THEN 1
                ELSE 0
            END
        ) * 100.0 / NULLIF(
            SUM(
                CASE
                    WHEN wf.[Estado del Pedido] IN ('Validado', 'Aprobado') THEN 1
                    ELSE 0
                END
            ),
            0
        ) AS DECIMAL(5, 1)
    ) AS vtat_pct
FROM winforce_lima wf
WHERE YEAR(TRY_CONVERT(DATE, wf.[Fecha de registro], 120)) = YEAR(GETDATE())
    AND MONTH(TRY_CONVERT(DATE, wf.[Fecha de registro], 120)) = MONTH(GETDATE())
GROUP BY CAST(
        TRY_CONVERT(DATE, wf.[Fecha de registro], 120) AS DATE
    )
ORDER BY fecha ASC;