SELECT wf.[N° doc cliente],
    wf.Cliente,
    vr.[Telefono contacto],
    vr.[Telefono referencia],
    wf.[Fecha programación],
    vr.agendado
FROM winforce_lima wf
    LEFT JOIN ventas_referidos vr ON wf.[N° doc cliente] = TRY_CONVERT(BIGINT, vr.[DNI/Carnet Extraj.])
    LEFT JOIN dim_usuarios_Aliv ua ON wf.[Vendedor real] = ua.vendedor
WHERE wf.[Estado orden] LIKE 'Ejecutada'
    AND ua.agencia LIKE 'ALIV'
    AND wf.[Fecha programación] LIKE '%13-08-%'
    AND vr.Agendado NOT LIKE '%NULL%'
ORDER BY wf.[Fecha programación]