SELECT rsw.vendedor,
    wf.[Vendedor real],
    rsw.supervisor,
    wf.[Telf. cliente],
    wf.[N° doc cliente],
    wf.[Fecha de registro],
    wf.[Fecha programación],
    wf.Cliente,
    wf.[Motivo rechazo orden],
    wf.[Motivo Rechazo Pedido],
    wf.[Estado del Pedido],
    wf.[Estado orden],
    wf.[Dirección de Instalación],
    wf.Distrito,
    COALESCE(
        NULLIF(wf.[Motivo rechazo orden], ''),
        NULLIF(wf.[Motivo Rechazo Pedido], '')
    ) AS motivo_rechazo
FROM dim_usuarios_Aliv rsw
    LEFT JOIN winforce_lima wf ON rsw.vendedor = wf.[Vendedor real]
WHERE DAY(TRY_CONVERT(DATE, [Fecha programación], 105)) = DAY(GETDATE()) -1
    AND MONTH(TRY_CONVERT(DATE, [Fecha programación], 105)) = MONTH(GETDATE())
    AND wf.[Estado orden] NOT LIKE '%Ejecutada%'
ORDER BY wf.[Fecha de registro];