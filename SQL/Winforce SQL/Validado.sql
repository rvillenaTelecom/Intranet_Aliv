SELECT COUNT(*),
    [Estado orden]
FROM winforce_lima
WHERE [Fecha de registro] LIKE '%-07-%'
    AND [Fecha programación] LIKE '%-08-%' --AND [Estado orden] LIKE 'Ejecutada'
    AND [Estado del Pedido] LIKE 'Validado'
GROUP BY [Estado orden]
SELECT COUNT(*),
    [Estado orden]
FROM winforce_lima
WHERE [Fecha de registro] LIKE '%-08-%'
    AND [Fecha programación] LIKE '%-08-%' --AND [Estado orden] LIKE 'Ejecutada'
    AND [Estado del Pedido] LIKE 'Validado'
GROUP BY [Estado orden]