/** Altas programadas Lista Hoy**/
SELECT [Fecha de registro],
    [Fecha programación],
    [Tramo Horario],
    [N° doc cliente],
    [Telf. cliente],
    [Estado orden],
    [Tipo de domicilio]
FROM dbo.winforce_lima
WHERE [Fecha programación] LIKE '%06-07-%'
    AND [Estado orden] LIKE '%Programada%' --AND [Fecha de registro] LIKE '%-07-03%'
    --AND [N° doc cliente] LIKE '%931868720%'
    --AND [Tipo de domicilio] LIKE 'Condominio/Edificio'
ORDER BY [Fecha de registro]