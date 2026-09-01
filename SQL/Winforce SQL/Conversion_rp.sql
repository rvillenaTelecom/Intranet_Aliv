-- ============================================================
-- Conversión PV→VT y VT→AT — Diario y Mensual
-- PV→VT: registros con Estado del Pedido aprobado
-- VT→AT: preventa fecha de registro
--        venta alta fecha prog.
-- ============================================================
-- DIARIO
SELECT v.fecha,
    v.preventas,
    v.ventas_aprobadas,
    ISNULL(a.altas, 0) AS altas,
    CAST(
        v.ventas_aprobadas * 100.0 / NULLIF(v.preventas, 0) AS DECIMAL(5, 1)
    ) AS pvvt_pct,
    CAST(
        ISNULL(a.altas, 0) * 100.0 / NULLIF(v.ventas_aprobadas, 0) AS DECIMAL(5, 1)
    ) AS vtat_pct
FROM (
        -- Preventas y ventas: por Fecha de registro
        SELECT CAST(
                TRY_CONVERT(DATE, [Fecha de registro], 120) AS DATE
            ) AS fecha,
            COUNT(*) AS preventas,
            SUM(
                CASE
                    WHEN [Estado del Pedido] IN ('Validado', 'Aprobado') THEN 1
                    ELSE 0
                END
            ) AS ventas_aprobadas
        FROM winforce_lima
        WHERE YEAR(TRY_CONVERT(DATE, [Fecha de registro], 120)) = YEAR(GETDATE())
            AND MONTH(TRY_CONVERT(DATE, [Fecha de registro], 120)) = MONTH(GETDATE())
        GROUP BY CAST(
                TRY_CONVERT(DATE, [Fecha de registro], 120) AS DATE
            )
    ) v
    LEFT JOIN (
        -- Altas: por Fecha programación
        SELECT CAST(
                TRY_CONVERT(DATE, [Fecha programación], 105) AS DATE
            ) AS fecha,
            COUNT(*) AS altas
        FROM winforce_lima
        WHERE [Estado orden] = 'Ejecutada'
            AND YEAR(TRY_CONVERT(DATE, [Fecha programación], 105)) = YEAR(GETDATE())
            AND MONTH(TRY_CONVERT(DATE, [Fecha programación], 105)) = MONTH(GETDATE())
        GROUP BY CAST(
                TRY_CONVERT(DATE, [Fecha programación], 105) AS DATE
            )
    ) a ON a.fecha = v.fecha
ORDER BY v.fecha ASC;