SELECT [Vendedor real],
    COUNT(
        CASE
            WHEN MONTH([Fecha de registro]) = 7 THEN 1
        END
    ) AS ventas_julio,
    COUNT(
        CASE
            WHEN MONTH([Fecha de registro]) = 8 THEN 1
        END
    ) AS ventas_agosto
FROM winforce_lima
WHERE YEAR([Fecha de registro]) = 2026
GROUP BY [Vendedor real]
HAVING COUNT(
        CASE
            WHEN MONTH([Fecha de registro]) = 7 THEN 1
        END
    ) > 0
    AND COUNT(
        CASE
            WHEN MONTH([Fecha de registro]) = 8 THEN 1
        END
    ) > 0
SELECT TRIM([Vendedor real]) AS Vendedor,
    COUNT(
        CASE
            WHEN MONTH([Fecha de registro]) = 7 THEN 1
        END
    ) AS ventas_julio,
    COUNT(
        CASE
            WHEN MONTH([Fecha de registro]) = 8 THEN 1
        END
    ) AS ventas_agosto
FROM winforce_lima
WHERE YEAR([Fecha de registro]) = 2026
GROUP BY TRIM([Vendedor real])
ORDER BY ventas_julio DESC