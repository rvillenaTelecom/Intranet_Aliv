
/** Altas ejecutadas según fecha de programación PROV**/
SELECT [Estado orden], COUNT(*) AS CONTEO 
FROM dbo.winforce_provincia
WHERE [Fecha programación] LIKE '%-05-%'
AND [Estado orden] LIKE '%Ejecutada%'
AND Departamento NOT LIKE 'LIMA'
GROUP BY [Estado orden]

/** Ventas según fecha de registro PROV**/
SELECT COUNT(*) AS CONTEO 
FROM dbo.winforce_provincia
WHERE [Fecha de registro] LIKE '%-05-%'


/** Altas Según distrito PROV**/
SELECT [Fecha de registro], [Fecha programación], [Estado orden] , Distrito
FROM dbo.winforce_provincia
WHERE [Fecha programación] LIKE '%-05-%'
AND [Estado orden] LIKE '%Ejecutada%'
AND Distrito LIKE '%San Juan De Lurigancho%'
ORDER BY [Fecha programación] ASC

/** Cruce vendedores PROV**/
SELECT [Vendedor real], u.VENDEDOR, u.SUPERVISOR, u.AGENCIA
FROM dbo.winforce_provincia wl
LEFT JOIN dbo.Usuarios_win u ON wl.[Vendedor real] = u.Vendedor


