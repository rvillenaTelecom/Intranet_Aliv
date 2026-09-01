DECLARE @cuota INT = 1980;
DECLARE @meta_pct FLOAT = 0.84;
DECLARE @dias_habiles INT = 2;
-- ← ajusta según feriados
WITH altas_mes AS (
    SELECT COUNT(*) AS altas_actuales
    FROM winforce_lima
    WHERE [Estado orden] = 'Ejecutada'
        AND YEAR(TRY_CONVERT(DATE, [Fecha programación], 105)) = YEAR(GETDATE())
        AND MONTH(TRY_CONVERT(DATE, [Fecha programación], 105)) = MONTH(GETDATE())
        AND [Tipo de domicilio] NOT LIKE 'Condominio/Edificio'
)
SELECT @cuota AS cuota,
    CAST(@cuota * @meta_pct AS INT) AS meta_84pct,
    altas_actuales,
    CAST(@cuota * @meta_pct AS INT) - altas_actuales AS altas_faltantes,
    @dias_habiles AS dias_habiles_restantes,
    CAST(
        (CAST(@cuota * @meta_pct AS INT) - altas_actuales) * 1.0 / NULLIF(@dias_habiles, 0) AS DECIMAL(5, 1)
    ) AS altas_dia_necesarias
FROM altas_mes;