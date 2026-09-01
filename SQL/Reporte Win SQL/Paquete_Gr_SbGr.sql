SELECT [Empaquetado_General] AS grupo,
    [EmpaquetadoEspecifico] AS subgrupo,
    COUNT(*) AS ventas,
    CAST(
        COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER (), 0) AS DECIMAL(5, 1)
    ) AS pct_participacion
FROM Win_reporte_semanal
WHERE [Año Venta] = 2026
    AND [Mes Venta] = 7
    AND Estado LIKE 'Instalado'
GROUP BY [Empaquetado_General],
    [EmpaquetadoEspecifico]
ORDER BY grupo,
    ventas DESC;