-- ALTAS POR PLAN
SELECT wf.[Plan],
    COUNT(*) AS total_altas,
    CAST(
        COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER (), 0) AS DECIMAL(5, 1)
    ) AS pct_altas
FROM winforce_lima wf
WHERE YEAR(TRY_CONVERT(DATE, wf.[Fecha programación], 105)) = 2026
    AND MONTH(TRY_CONVERT(DATE, wf.[Fecha programación], 105)) = 7
    AND wf.[Estado orden] = 'Ejecutada'
GROUP BY wf.[Plan]
ORDER BY total_altas DESC;