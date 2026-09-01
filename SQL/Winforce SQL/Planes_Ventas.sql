-- VENTAS POR PLAN
SELECT wf.[Plan],
    COUNT(*) AS total_ventas,
    CAST(
        COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER (), 0) AS DECIMAL(5, 1)
    ) AS pct_ventas
FROM winforce_lima wf
WHERE YEAR(TRY_CONVERT(DATE, wf.[Fecha de registro], 120)) = 2026
    AND MONTH(TRY_CONVERT(DATE, wf.[Fecha de registro], 120)) = 7
GROUP BY wf.[Plan]
ORDER BY total_ventas DESC;