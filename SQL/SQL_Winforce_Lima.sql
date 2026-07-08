SELECT * FROM dbo.winforce_lima

SELECT COUNT(*) FROM dbo.winforce_lima
SELECT COUNT(*) FROM dbo.winforce_provincia

/** Altas raras fuera de lima **/
SELECT [N° doc cliente], [Fecha de registro], [Fecha programación], Cliente, Departamento, Distrito, [Estado orden]
FROM dbo.winforce_lima
WHERE Departamento NOT LIKE '%LIMA%'
    AND Departamento NOT LIKE '%CALLAO%'
    AND [Fecha programación] LIKE  '%-05-%'

/** Registro durante el día **/
SELECT [Tipo de domicilio], COUNT(*) AS Conteo
FROM dbo.winforce_lima
WHERE [Fecha de registro] LIKE '%-05-22%'
GROUP BY [Tipo de domicilio]

/** Altas ejecutadas según fecha de programación **/
SELECT [Estado orden], COUNT(*) AS CONTEO 
FROM dbo.winforce_lima
WHERE [Fecha programación] LIKE '%-06-%'
AND [Estado orden] LIKE '%Ejecutada%'
GROUP BY [Estado orden]

SELECT *
FROM dbo.winforce_lima
WHERE [Fecha programación] LIKE '%-06-%'
AND [Estado orden] LIKE '%Ejecutada%'
AND [Tipo de domicilio] LIKE '%Condominio/Edificio%'
AND [Tipo de domicilio] NOT LIKE '%Condominio/Edificio No Habilitado%'


/** Ventas según fecha de registro **/
SELECT COUNT(*) AS CONTEO 
FROM dbo.winforce_lima
WHERE [Fecha de registro] LIKE '%-05-%'

/** Altas Según distrito **/
SELECT [Fecha de registro], [Fecha programación], [Estado orden] , Distrito
FROM dbo.winforce_lima
WHERE [Fecha programación] LIKE '%-05-%'
AND [Estado orden] LIKE '%Ejecutada%'
AND Distrito LIKE '%San Juan De Lurigancho%'
ORDER BY [Fecha programación] ASC


/** Cruce vendedores **/
SELECT TOP(100) *
FROM dbo.winforce_lima wl
LEFT JOIN dbo.Usuarios_win u ON wl.[Vendedor real] = u.Vendedor


/** Cruce vendedores PROV**/
SELECT [Vendedor real], u.VENDEDOR, u.SUPERVISOR, u.AGENCIA
FROM dbo.winforce_lima wl
LEFT JOIN dbo.Usuarios_win u ON wl.[Vendedor real] = u.Vendedor

/** Altas Según Plan **/
SELECT [plan] as Planes ,COUNT(*) AS Conteo 
FROM dbo.winforce_lima
WHERE [Fecha programación] LIKE '%-05-%'
AND [Estado orden] LIKE '%Ejecutada%'
GROUP BY [Plan]
ORDER BY Conteo DESC


/** Planes según velocidad y % **/
SELECT 
    LEFT([plan], CHARINDEX(' ', [plan] + ' ') - 1) AS Velocidad,
    COUNT(*) AS Conteo,
    ROUND(
        100.0 * COUNT(*) 
        / SUM(COUNT(*)) OVER (),
        2
    ) AS Porcentaje
FROM dbo.winforce_lima
WHERE [Fecha programación] LIKE '%-05-%'
  AND [Estado orden] LIKE '%Ejecutada%'
GROUP BY LEFT([plan], CHARINDEX(' ', [plan] + ' ') - 1)
ORDER BY Conteo DESC;

SELECT COUNT(*) AS conteo, [plan] FROM winforce_lima
WHERE [Fecha programación] >= '2026-05-23'
GROUP BY [plan]
SELECT DISTINCT [Fecha programación] FROM winforce_lima

SELECT 
    CASE 
        WHEN [plan] LIKE '%primerop%' THEN '1000'
        WHEN [plan] LIKE '%1000%' THEN '1000'
        WHEN [plan] LIKE '%850%' THEN '850'
        WHEN [plan] LIKE '%750%' THEN '750'
        WHEN [plan] LIKE '%550%' THEN '550'
        WHEN [plan] LIKE '%500%' THEN '500'
        WHEN [plan] LIKE '%350%' THEN '350'
        ELSE 'OTROS'
    END AS Velocidad,
    COUNT(*) AS Conteo,
    ROUND(
        100.0 * COUNT(*) 
        / SUM(COUNT(*)) OVER (),
        2
    ) AS Porcentaje
FROM dbo.winforce_lima
/** WHERE [Fecha programación] LIKE '%-05-%' **/
WHERE TRY_CONVERT(DATETIME, [Fecha programación], 103) >= '2026-05-23'
  AND TRY_CONVERT(DATETIME, [Fecha programación], 103) < '2026-06-01'
  AND [Estado orden] LIKE '%Ejecutada%'
GROUP BY 
    CASE 
        WHEN [plan] LIKE '%primerop%' THEN '1000'
        WHEN [plan] LIKE '%1000%' THEN '1000'
        WHEN [plan] LIKE '%850%' THEN '850'
        WHEN [plan] LIKE '%750%' THEN '750'
        WHEN [plan] LIKE '%550%' THEN '550'
        WHEN [plan] LIKE '%500%' THEN '500'
        WHEN [plan] LIKE '%350%' THEN '350'
        ELSE 'OTROS'
    END
ORDER BY Conteo DESC;


/*******************************/

/** Altas Según distrito **/
SELECT
    Agencia
FROM dbo.winforce_lima
WHERE [Estado orden] LIKE '%Ejecutada%'
  AND (
        [Fecha programación] LIKE '%-03-%'
     OR [Fecha programación] LIKE '%-04-%'
     OR [Fecha programación] LIKE '%-05-%'
     OR [Fecha programación] LIKE '%-06-%'
      )
ORDER BY [Fecha programación] ASC;


/** Ventas Programadas para hoy **/
SELECT
    [N° doc cliente],
    Cliente,
    [Telf. cliente],
    [Fecha de registro],
    [Fecha programación],
    [Estado orden],
    [Tipo de domicilio]
FROM dbo.winforce_lima
WHERE [Fecha programación] LIKE '%-07-%'
    AND [Estado orden] LIKE '%Programada%'
    AND [Tipo de domicilio] LIKE 'Condominio/Edificio'
ORDER BY [Fecha programación]
--    AND [N° doc cliente] LIKE '%48643182%'

/** Ventas Desaprobadas para hoy **/
SELECT
    [N° doc cliente],
    Cliente,
    [Telf. cliente],
    [Fecha de registro],
    [Fecha programación],
    [Estado orden],
    [Tipo de domicilio],
    [Motivo rechazo orden],
    [Motivo Rechazo Pedido]
FROM dbo.winforce_lima
WHERE [Fecha de registro] LIKE '%-07-%'
    AND [Estado orden] IN ('Anulado', 'Cancelada', 'Rescate')
    AND [Tipo de domicilio] LIKE 'Condominio/Edificio'
ORDER BY [Fecha de registro]
--    AND [N° doc cliente] LIKE '%48643182%'


/** Ventas Programadas para hoy Conteo **/
SELECT
    [Estado orden],
    [Tipo de domicilio],
    COUNT(*) AS Ventas_a_Instalar
FROM dbo.winforce_lima
WHERE [Fecha programación] LIKE '%30-06%'
    AND [Estado orden] LIKE '%Programada%'
GROUP BY [Estado orden],[Tipo de domicilio]

SELECT
    [Estado orden],
    CASE
        WHEN [Tipo de domicilio] = 'Multifamiliar' THEN 'Horizontal'
        WHEN [Tipo de domicilio] = 'Condominio/Edificio' THEN 'Vertical'
        WHEN [Tipo de domicilio] = 'Condominio/Edificio No Habilitado' THEN 'Horizontal'
        ELSE [Tipo de domicilio]
    END AS [Tipo de domicilio],
    COUNT(*) AS Ventas_a_Instalar
FROM dbo.winforce_lima
WHERE [Fecha programación] LIKE '%30-06%'
  AND [Estado orden] LIKE '%Programada%'
GROUP BY
    [Estado orden],
    CASE
        WHEN [Tipo de domicilio] = 'Multifamiliar' THEN 'Horizontal'
        WHEN [Tipo de domicilio] = 'Condominio/Edificio' THEN 'Vertical'
        WHEN [Tipo de domicilio] = 'Condominio/Edificio No Habilitado' THEN 'Horizontal'
        ELSE [Tipo de domicilio]
    END;



/** Cruce según vendedor **/
SELECT 
    [Fecha de registro], 
    [Fecha programación], [Estado orden] , [Vendedor real], supervisor
FROM dbo.winforce_lima wf
LEFT JOIN dbo.dim_usuarios_Aliv u ON wf.[Vendedor real] = u.Vendedor
WHERE u.supervisor LIKE '%DEZANET%'

/** Cruce según dni **/
SELECT 
--  [Fecha de registro], 
--  [Fecha programación], 
--  [Estado orden] , 
    DISTINCT wf.[Vendedor real], 
    u.Supervisor,
    u.Vendedor
FROM dbo.winforce_lima wf
LEFT JOIN dbo.ventas_aliv u
    ON wf.[N° doc cliente] =
       TRY_CONVERT(BIGINT, u.[DNI/Carnet Extraj.])
--WHERE Supervisor LIKE '%SIPION%'
--WHERE [Vendedor real] LIKE '%Brenda Rueda Herrera%'
ORDER BY [Vendedor real]

/** Cruce según dni último**/
SELECT 
--  [Fecha de registro], 
--  [Fecha programación], 
--  [Estado orden] , 
    DISTINCT wf.[Vendedor real], 
    u.Supervisor,
    u.Vendedor
FROM dbo.winforce_lima wf
LEFT JOIN dbo.ventas_aliv u
    ON wf.[N° doc cliente] =
       TRY_CONVERT(BIGINT, u.[DNI/Carnet Extraj.])
--WHERE Supervisor LIKE '%SIPION%'
--WHERE [Vendedor real] LIKE '%Brenda Rueda Herrera%'
WHERE [Fecha de registro] LIKE '%-06-%'
ORDER BY [Vendedor real]


SELECT DISTINCT * FROM ventas_aliv
WHERE Supervisor LIKE '%SIPION%'
ORDER BY Supervisor

/** Altas programadas **/
SELECT
    [Fecha programación],
    [Estado orden],
    COUNT(*) AS Conteo
FROM dbo.winforce_lima
WHERE [Fecha programación] LIKE '%-07-%'
AND [Estado orden] LIKE '%Programada%'
GROUP BY [Fecha programación],[Estado orden]
ORDER BY [Fecha programación]


/** Altas programadas Lista**/
SELECT
    [Fecha de registro],
    [Fecha programación],
    [Tramo Horario],
    [N° doc cliente],
    [Telf. cliente],
    [Estado orden]
FROM dbo.winforce_lima
WHERE [Fecha programación] LIKE '%02-07-%'
AND [Estado orden] IN ('Anulado', 'Programada', 'Rescate')
ORDER BY [Fecha programación]

/** Altas programadas Lista Hoy**/
SELECT
    [Fecha de registro],
    [Fecha programación],
    [Tramo Horario],
    [N° doc cliente],
    [Telf. cliente],
    [Estado orden],
    [Tipo de domicilio]
FROM dbo.winforce_lima
WHERE [Fecha programación] LIKE '%06-07-%'
AND [Estado orden] LIKE '%Programada%'
--AND [Fecha de registro] LIKE '%-07-03%'
--AND [N° doc cliente] LIKE '%931868720%'
--AND [Tipo de domicilio] LIKE 'Condominio/Edificio'
ORDER BY [Fecha de registro]

/**  Lista Hoy**/
SELECT
    a.[DNI/Carnet Extraj.]   AS DNI,
    a.[Nombre y Apellidos]   AS Cliente,
    w.[Fecha programación],
    w.[Estado orden],
    a.[Usuario]              AS Usuario_Aliv,
    w.[Vendedor real]        AS Vendedor_Real_WinForce,
    a.Vendedor
FROM ventas_aliv a
LEFT JOIN winforce_lima w
    ON LTRIM(RTRIM(a.[DNI/Carnet Extraj.])) = LTRIM(RTRIM(w.[N° doc cliente]))
WHERE w.[Vendedor real] LIKE '%Krys Melany Sandoval Romero%'

SELECT * FROM dim_usuarios_Aliv
WHERE agencia LIKE 'SIPION'


/** Registro Altas **/
SELECT *
FROM dbo.winforce_lima
WHERE [Fecha programación] LIKE '%-05-%'
AND [Estado orden] LIKE '%Ejecutada%'
AND [Tipo de domicilio] LIKE 'Condominio/Edificio'
ORDER BY [Fecha programación] ASC