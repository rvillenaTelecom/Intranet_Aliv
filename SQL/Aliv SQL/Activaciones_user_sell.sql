SELECT Vendedor,
    COUNT(*) AS Cantidad
FROM ventas_aliv
WHERE Vendedor LIKE '%ARTURO EDUARDO JORGE ZEGARRA%'
    AND [Fecha Activacion] LIKE '%-06-%'
GROUP BY Vendedor
ORDER BY Cantidad DESC;