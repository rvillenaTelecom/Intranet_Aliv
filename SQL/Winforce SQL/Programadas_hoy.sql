/*  ============================================================
 [1] VENTAS PROGRAMADAS Y DESAPROBADAS
 ============================================================ */
-- [1.1] Ventas programadas HOY
SELECT [Fecha de registro],
    [Tipo Documento],
    [N° doc cliente],
    [Estado orden],
    [Fecha programación],
    [Tramo Horario],
    [Vendedor real]
FROM winforce_lima
WHERE DAY(TRY_CONVERT(DATE, [Fecha programación], 105)) = DAY(GETDATE())
    AND MONTH(TRY_CONVERT(DATE, [Fecha programación], 105)) = MONTH(GETDATE())
    AND [Estado orden] LIKE '%Programada%'
ORDER BY [Fecha programación]