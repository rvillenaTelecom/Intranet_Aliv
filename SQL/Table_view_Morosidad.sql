
CREATE OR ALTER VIEW dbo.v_ventas_aliv_completa AS
SELECT
    *,

    -- ─── Grupo de facturación ───────────────────────────
    CASE
        WHEN DAY(TRY_CONVERT(DATE, [Fecha Activacion], 105)) >= 23
            THEN 'GRUPO 02'
        ELSE 'GRUPO 01'
    END AS Grupo_Facturacion,

    -- ─── Vencimiento R1 calculado ───────────────────────
    CASE
        WHEN DAY(TRY_CONVERT(DATE, [Fecha Activacion], 105)) >= 23
            THEN DATEFROMPARTS(
                    YEAR(TRY_CONVERT(DATE, [Fecha Activacion], 105)),
                    MONTH(TRY_CONVERT(DATE, [Fecha Activacion], 105)) + 1,
                    28)
        ELSE DATEFROMPARTS(
                    YEAR(TRY_CONVERT(DATE, [Fecha Activacion], 105)),
                    MONTH(TRY_CONVERT(DATE, [Fecha Activacion], 105)),
                    28)
    END AS Vencimiento_R1_Calculado,

    -- ─── R1 ya venció ───────────────────────────────────
    CASE
        WHEN TRY_CONVERT(DATE, [Fecha vencimiento M1], 105) < CAST(GETDATE() AS DATE)
            THEN 1 ELSE 0
    END AS R1_Ya_Vencio,

    -- ─── Mes número del recibo ──────────────────────────
    MONTH(TRY_CONVERT(DATE, [Fecha Activacion], 105)) AS Mes_Num_Recibo,

    -- ─── Recibo actual ──────────────────────────────────
    CASE
        WHEN [Estado M3] IS NOT NULL
             AND [Estado M3] <> 'Pendiente Recibo Anterior' THEN 'M3'
        WHEN [Estado M2] IS NOT NULL
             AND [Estado M2] <> 'Pendiente Recibo Anterior' THEN 'M2'
        WHEN [Estado M1] IS NOT NULL                         THEN 'M1'
        ELSE 'Sin recibo'
    END AS Recibo_Actual,

    -- ─── Último estado de pago ──────────────────────────
    CASE
        WHEN [Estado M3] IS NOT NULL
             AND [Estado M3] <> 'Pendiente Recibo Anterior' THEN [Estado M3]
        WHEN [Estado M2] IS NOT NULL
             AND [Estado M2] <> 'Pendiente Recibo Anterior' THEN [Estado M2]
        WHEN [Estado M1] IS NOT NULL                         THEN [Estado M1]
        ELSE 'Sin estado'
    END AS Ultimo_Estado_Pago,

    -- ─── Tipo caso clawback ─────────────────────────────
    CASE
        WHEN [Estado M1] IS NULL
             AND TRY_CONVERT(DATE, [Fecha vencimiento M1], 105) >= CAST(GETDATE() AS DATE)
            THEN 'Pendiente - R1 no vence'
        WHEN [Estado M1] IN ('Churn','Cliente De Baja')
             AND TRY_CONVERT(DATE, [Fecha vencimiento M1], 105) < CAST(GETDATE() AS DATE)
            THEN 'NPNF'
        WHEN [Estado M1] = 'Churn'
             AND [Estado M2] = 'Pendiente Recibo Anterior'
            THEN 'NPNF'
        WHEN [Estado M1] IN ('Cliente Pago','Tercero Pago')
             AND [Estado M2] IN ('Churn','Cliente De Baja')
            THEN 'Extorno 2 - cayo en R2'
        WHEN [Estado M1] IN ('Cliente Pago','Tercero Pago')
             AND [Estado M2] IN ('Cliente Pago','Tercero Pago')
             AND [Estado M3] IN ('Churn','Cliente De Baja')
            THEN 'Extorno 3 - cayo en R3'
        WHEN [Estado M1] IN ('Cliente Pago','Tercero Pago')
             AND [Estado M2] IN ('Cliente Pago','Tercero Pago')
             AND [Estado M3] IN ('Cliente Pago','Tercero Pago')
            THEN 'Perfecto - pago 3 recibos'
        WHEN [Estado M1] IN ('Cliente Pago','Tercero Pago')
             AND [Estado M2] IN ('Cliente Pago','Tercero Pago')
             AND [Estado M3] IS NULL
            THEN 'Al dia - R3 pendiente'
        WHEN [Estado M1] IN ('Cliente Pago','Tercero Pago')
             AND [Estado M2] IS NULL
            THEN 'Al dia - R2 pendiente'
        ELSE 'Sin clasificar'
    END AS Tipo_Caso_Clawback,

    -- ─── Riesgo clawback ────────────────────────────────
    CASE
        WHEN [Estado M1] IN ('Churn','Cliente De Baja')
             AND TRY_CONVERT(DATE, [Fecha vencimiento M1], 105) < CAST(GETDATE() AS DATE)
            THEN 'Penalidad NPNF'
        WHEN [Estado M1] = 'Churn'
             AND [Estado M2] = 'Pendiente Recibo Anterior'
            THEN 'Penalidad NPNF'
        WHEN [Estado M1] IN ('Cliente Pago','Tercero Pago')
             AND [Estado M2] IN ('Churn','Cliente De Baja')
            THEN 'Extorno 2'
        WHEN [Estado M1] IN ('Cliente Pago','Tercero Pago')
             AND [Estado M2] IN ('Cliente Pago','Tercero Pago')
             AND [Estado M3] IN ('Churn','Cliente De Baja')
            THEN 'Extorno 3'
        WHEN [Estado M1] IN ('Cliente Pago','Tercero Pago')
             AND [Estado M2] IN ('Cliente Pago','Tercero Pago')
             AND [Estado M3] IN ('Cliente Pago','Tercero Pago')
            THEN 'Sin riesgo'
        ELSE 'Pendiente evaluacion'
    END AS Riesgo_Clawback,

    -- ─── ARPU con TRY_CONVERT para evitar overflow ──────
    ROUND(
        CASE
            WHEN [Paquete] LIKE '%Dgo Full%'
                THEN (TRY_CONVERT(DECIMAL(18,2), [Precio paquete]) * 0.5 / 1.18) - (8.77 * 0.85)
            WHEN [Paquete] LIKE '%Dgo Basico%'
                THEN (TRY_CONVERT(DECIMAL(18,2), [Precio paquete]) / 1.18) - (5.97 * 0.85)
            WHEN ([Paquete] LIKE '%1000%' OR [Paquete] LIKE '%600%')
                 AND [Paquete] NOT LIKE '%Hb%'
                 AND [Paquete] NOT LIKE '%Wtv%'
                THEN TRY_CONVERT(DECIMAL(18,2), [Precio paquete]) * 0.5 / 1.18
            ELSE TRY_CONVERT(DECIMAL(18,2), [Precio paquete]) / 1.18
        END
    , 2) AS ARPU,

    -- ─── Deuda total del cliente ─────────────────────────
    ISNULL(TRY_CONVERT(DECIMAL(18,2), [Deuda M1]), 0)
        + ISNULL(TRY_CONVERT(DECIMAL(18,2), [Deuda M2]), 0)
        + ISNULL(TRY_CONVERT(DECIMAL(18,2), [Deuda M3]), 0) AS Deuda_Total_Cliente

FROM dbo.ventas_aliv
WHERE [Departamento] = 'Lima'
  AND [Distrito] NOT IN ('Barranca','Chancay','Huacho','Hualmay','Huaral')

  DROP view dbo.v_ventas_aliv_completa 
