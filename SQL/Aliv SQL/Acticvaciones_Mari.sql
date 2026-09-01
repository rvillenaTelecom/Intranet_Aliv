DECLARE @dias_laborales INT = 26;
DECLARE @dias_transcurridos INT = 20;
SELECT Supervisor,
    COUNT(*) AS ventas_mes,
    CAST(
        COUNT(*) * 1.0 / NULLIF(@dias_transcurridos, 0) * @dias_laborales AS INT
    ) AS proyeccion,
    MAX(TRY_CONVERT(DATE, [Fecha Activacion], 105)) AS ultima_activacion
FROM ventas_aliv
WHERE MONTH(TRY_CONVERT(DATE, [Fecha Activacion], 105)) = MONTH(GETDATE())
    AND YEAR(TRY_CONVERT(DATE, [Fecha Activacion], 105)) = YEAR(GETDATE()) --AND [Tipo Servicio] LIKE '%CONDOMINIO HABILITADO%'
    AND Supervisor IN (
        --'LAGOS PONCE EDWIN FRANZ',
        --'SOTO YABAR HRISTO ALAIN PETER',
        --'BOCKOS CERVERA ROBERTO LEONIDAS',
        --'CASTILLON CARHUAYANO LUIS ALBERTO',
        --'SOTELO CASTAÑEDA ANYI CAROLINA',
        'UGARTE . ZOMARCELY JOSEFINA',
        'LUCUMBER LOZANO CRISTINA ISABEL',
        --'MARTICORENA RODRíGUEZ JORGE AUGUSTO',
        'VILLALOBOS RAMÍREZ LUIS GABRIEL' --'PUPPO EGUSQUIZA RONALD ROBERTO'
    )
GROUP BY Supervisor
ORDER BY ventas_mes DESC;