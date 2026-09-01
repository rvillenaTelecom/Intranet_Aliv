-- Altas
SELECT COUNT(*)
FROM winforce_lima
WHERE [Fecha programación] LIKE '%-08-%'
    AND [Estado orden] LIKE '%Ejecutada%'
    AND Departamento IN ('CALLAO', 'LIMA')
    AND Distrito NOT IN (
        'barranca',
        'chancay',
        'huacho',
        'hualmay',
        'huaral'
    ) -- Altas
SELECT COUNT(*)
FROM winforce_lima
WHERE [Fecha de registro] LIKE '%-08-%'
    AND [Estado del Pedido] LIKE '%Validado%'
    AND Departamento IN ('CALLAO', 'LIMA')
    AND Distrito NOT IN (
        'barranca',
        'chancay',
        'huacho',
        'hualmay',
        'huaral'
    ) -- Ventas
SELECT COUNT(*)
FROM winforce_lima
WHERE [Fecha de registro] LIKE '%-08-%'
    AND Departamento IN ('CALLAO', 'LIMA')
    AND Distrito NOT IN (
        'barranca',
        'chancay',
        'huacho',
        'hualmay',
        'huaral'
    ) --Pre-Ventas