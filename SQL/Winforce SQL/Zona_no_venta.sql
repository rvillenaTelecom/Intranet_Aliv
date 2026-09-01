SELECT wf.[Vendedor real],
    ua.agencia,
    wf.[N° doc cliente],
    wf.Cliente,
    wf.[Dirección de Instalación],
    wf.[Estado orden],
    wf.[Fecha de registro],
    wf.[Fecha programación],
    wf.Zona_KML
FROM winforce_lima wf
    LEFT JOIN dim_usuarios_Aliv ua ON ua.vendedor = wf.[Vendedor real]
WHERE wf.Zona_KML LIKE 'No Venta'
    AND DAY(TRY_CONVERT(DATE, [Fecha programación], 105)) = DAY(GETDATE())
    AND MONTH(TRY_CONVERT(DATE, [Fecha programación], 105)) = MONTH(GETDATE())
ORDER BY wf.[Fecha programación]