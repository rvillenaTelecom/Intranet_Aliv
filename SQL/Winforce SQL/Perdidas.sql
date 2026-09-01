SELECT wf.[N° doc cliente] AS DNI_win,
    rsw.[nro_doc] AS DNI_reporte,
    wf.[Fecha de registro],
    wf.[Fecha programación],
    wf.Cliente,
    wf.[Motivo rechazo orden],
    wf.[Motivo Rechazo Pedido],
    wf.[Motivo Rechazo Pedido],
    WF.[Estado del Pedido],
    wf.[Estado orden],
    rsw.Observación,
    rsw.tipoValidacion,
    rsw.[comentarioValidacion],
    rsw.Estado,
    rsw.motivo,
    rsw.Observaciones,
    rsw.[Pos Arbitraje]
FROM winforce_lima wf
    LEFT JOIN Win_reporte_semanal rsw ON rsw.[nro_doc] = wf.[N° doc cliente]
WHERE YEAR(TRY_CONVERT(DATE, wf.[Fecha de registro], 120)) = 2026
    AND MONTH(TRY_CONVERT(DATE, wf.[Fecha de registro], 120)) = 7 --AND DAY(TRY_CONVERT(DATE, [Fecha de registro], 120)) = 21
    AND wf.[Estado orden] NOT LIKE '%Ejecutada%' --AND wf.[Estado del Pedido] LIKE '%Desaprobado%'