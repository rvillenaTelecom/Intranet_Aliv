SELECT [Fecha de registro],
    [Tipo Documento],
    [N° doc cliente],
    [Telf. cliente],
    [Vendedor real],
    [Estado del Pedido],
    [Estado orden]
FROM winforce_lima
WHERE [Fecha de registro] LIKE '%-07-%'
ORDER BY [Fecha de registro]