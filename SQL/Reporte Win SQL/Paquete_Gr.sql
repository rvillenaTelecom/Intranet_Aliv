SELECT [Empaquetado_General] AS grupo,
    COUNT(*) AS ventas,
    CAST(
        COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER (), 0) AS DECIMAL(5, 1)
    ) AS pct_participacion
FROM Win_reporte_semanal
WHERE [Año Venta] = 2026
    AND [Mes Venta] = 7
    AND Estado LIKE 'Instalado'
    AND Departamento LIKE 'Lima'
GROUP BY [Empaquetado_General]
ORDER BY grupo,
    ventas DESC;