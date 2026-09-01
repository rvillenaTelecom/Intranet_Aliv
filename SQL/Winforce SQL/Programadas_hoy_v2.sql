-- [1.1] Ventas programadas Hoy (Vendidas Hoy)
SELECT [Fecha de registro],
    [Tipo Documento],
    [N° doc cliente],
    [Estado orden],
    [Fecha programación],
    [Tramo Horario],
    [Vendedor real]
FROM winforce_lima
WHERE [Fecha programación] LIKE '%08-08-%'
    AND [Estado orden] LIKE '%Programada%'
    AND [Fecha de registro] LIKE '%-08-08%'
ORDER BY [Fecha programación]