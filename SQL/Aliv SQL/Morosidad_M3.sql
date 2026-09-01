DECLARE @fecha_inicio DATE = '2026-05-28';
DECLARE @fecha_fin DATE = '2026-06-05';
SELECT COUNT(
        CASE
            WHEN [Estado M3] = 'CLIENTE PAGO' THEN 1
        END
    ) AS pagaron_M3,
    COUNT(*) AS total_clientes
FROM ventas_aliv
WHERE TRY_CONVERT(DATE, [Fecha pago 3], 105) BETWEEN @fecha_inicio AND @fecha_fin;