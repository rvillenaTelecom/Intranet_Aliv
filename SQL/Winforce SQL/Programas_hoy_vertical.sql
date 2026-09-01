SELECT [Fecha de registro],
    [Tipo Documento],
    [N° doc cliente],
    [Telf. cliente],
    [Estado orden],
    [Estado del Pedido],
    [Fecha programación],
    [Tramo Horario],
    [Tipo de domicilio],
    [Dirección de Instalación],
    [Vendedor real],
    ua.agencia
FROM winforce_lima wf
    LEFT JOIN dim_usuarios_Aliv ua ON ua.vendedor = wf.[Vendedor real]
WHERE wf.[Fecha programación] LIKE '%27-08-%'
    AND wf.[Tipo de domicilio] LIKE 'Condominio/Edificio'
    AND wf.[Estado orden] NOT LIKE 'Ejecutada'
ORDER BY [Fecha programación] DESC