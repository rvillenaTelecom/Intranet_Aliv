SELECT wf.[Vendedor real],
    va.Vendedor,
    va.Supervisor,
    va.[DNI/Carnet Extraj.],
    wf.[N° doc cliente]
FROM winforce_lima wf
    LEFT JOIN ventas_aliv va ON wf.[N° doc cliente] = TRY_CONVERT(BIGINT, va.[DNI/Carnet Extraj.])
WHERE wf.[Vendedor real] LIKE '%Diego Danelli Giraldo Coronel%';
SELECT ua.Supervisor,
    COUNT(*) AS ventas_mes,
    ua.agencia
FROM winforce_lima wf
    LEFT JOIN dim_usuarios_Aliv ua ON wf.[Vendedor real] = ua.vendedor
WHERE MONTH(TRY_CONVERT(DATE, wf.[Fecha programación], 105)) = MONTH(GETDATE())
    AND YEAR(TRY_CONVERT(DATE, wf.[Fecha programación], 105)) = YEAR(GETDATE())
    AND DAY(TRY_CONVERT(DATE, wf.[Fecha programación], 105)) <= 24
    AND ua.agencia LIKE 'ALIV'
    AND wf.[Estado orden] LIKE 'Ejecutada'
GROUP BY ua.Supervisor,
    ua.agencia
ORDER BY ventas_mes DESC;
SELECT Supervisor,
    COUNT(*) AS ventas_mes,
    MAX(TRY_CONVERT(DATE, [Fecha Activacion], 105)) AS ultima_activacion
FROM ventas_aliv
WHERE MONTH(TRY_CONVERT(DATE, [Fecha Activacion], 105)) = MONTH(GETDATE())
    AND YEAR(TRY_CONVERT(DATE, [Fecha Activacion], 105)) = YEAR(GETDATE())
    AND Supervisor IN (
        'LAGOS PONCE EDWIN FRANZ',
        'SOTO YABAR HRISTO ALAIN PETER',
        'BOCKOS CERVERA ROBERTO LEONIDAS',
        'CASTILLON CARHUAYANO LUIS ALBERTO',
        'SOTELO CASTAÑEDA ANYI CAROLINA',
        'UGARTE . ZOMARCELY JOSEFINA',
        'LUCUMBER LOZANO CRISTINA ISABEL',
        'MARTICORENA RODRíGUEZ JORGE AUGUSTO',
        'VILLALOBOS RAMÍREZ LUIS GABRIEL',
        'PUPPO EGUSQUIZA RONALD ROBERTO',
        'RAMIREZ GARAY RONALD BENJAMIN'
    )
GROUP BY Supervisor
ORDER BY ventas_mes DESC;
SELECT ua.Supervisor,
    COUNT(*) AS ventas_mes,
    ua.agencia
FROM winforce_lima wf
    LEFT JOIN dim_usuarios_Aliv ua ON wf.[Vendedor real] = ua.vendedor
WHERE MONTH(TRY_CONVERT(DATE, wf.[Fecha programación], 105)) = MONTH(GETDATE())
    AND YEAR(TRY_CONVERT(DATE, wf.[Fecha programación], 105)) = YEAR(GETDATE())
    AND DAY(TRY_CONVERT(DATE, wf.[Fecha programación], 105)) <= 24
    AND ua.agencia LIKE 'ALIV'
    AND ua.nombre_aliv LIKE 'Roberto Leonidas Bockos Cervera'
    AND wf.[Estado orden] LIKE 'Ejecutada'
GROUP BY ua.Supervisor,
    ua.agencia
ORDER BY ventas_mes DESC;