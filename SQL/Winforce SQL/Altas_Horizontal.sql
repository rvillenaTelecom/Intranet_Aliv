SELECT COUNT(*)
FROM dbo.winforce_lima
WHERE [Fecha programación] LIKE '%-08-%'
    AND [Estado orden] LIKE '%Ejecutada%'
    AND [Tipo de domicilio] NOT LIKE 'Condominio/Edificio'
    AND Distrito NOT IN (
        'barranca',
        'chancay',
        'huacho',
        'hualmay',
        'huaral'
    )