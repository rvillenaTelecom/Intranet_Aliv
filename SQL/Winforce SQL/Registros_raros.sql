/*  ============================================================
 [1] Casos Fuera de Lima
 ============================================================ */
SELECT [N° doc cliente],
    [Fecha de registro],
    [Fecha programación],
    Cliente,
    Departamento,
    Distrito,
    [Estado orden]
FROM dbo.winforce_lima
WHERE --Departamento NOT IN ('CALLAO', 'LIMA')
    --AND Departamento NOT LIKE '%CALLAO%'
    [Fecha de registro] LIKE '%-08-%'
    AND Distrito IN (
        'barranca',
        'chancay',
        'huacho',
        'hualmay',
        'huaral'
    )