DECLARE @dias_transcurridos INT = 27;
DECLARE @dias_proyeccion INT = 28;
WITH altas_agencia AS (
    SELECT CASE
            WHEN u.agencia = '2TRATOS' THEN 'SUB-AGENCIAS'
            ELSE u.agencia
        END AS agencia,
        COUNT(*) AS altas_actuales
    FROM winforce_lima wf
        INNER JOIN dim_usuarios_Aliv u ON u.vendedor = wf.[Vendedor real]
    WHERE wf.[Estado orden] = 'Ejecutada'
        AND YEAR(TRY_CONVERT(DATE, wf.[Fecha programación], 105)) = YEAR(GETDATE())
        AND MONTH(TRY_CONVERT(DATE, wf.[Fecha programación], 105)) = MONTH(GETDATE())
        AND [Tipo de domicilio] NOT LIKE 'Condominio/Edificio'
        AND Distrito NOT IN (
            'barranca',
            'chancay',
            'huacho',
            'hualmay',
            'huaral'
        )
    GROUP BY CASE
            WHEN u.agencia = '2TRATOS' THEN 'SUB-AGENCIAS'
            ELSE u.agencia
        END
)
SELECT agencia,
    altas_actuales,
    CAST(
        altas_actuales * 1.0 / NULLIF(@dias_transcurridos, 0) AS DECIMAL(5, 1)
    ) AS ritmo_actual_dia,
    CAST(
        altas_actuales * 1.0 / NULLIF(@dias_transcurridos, 0) * @dias_proyeccion AS INT
    ) AS proyeccion
FROM altas_agencia
ORDER BY altas_actuales DESC;