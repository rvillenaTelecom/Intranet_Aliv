SELECT * FROM dbo.v_ventas_aliv_completa 
SELECT COUNT(*) as conteo FROM dbo.v_ventas_aliv_completa 

SELECT Tipo_Caso_Clawback, COUNT(*) as conteo FROM dbo.v_ventas_aliv_completa 
GROUP BY Tipo_Caso_Clawback

SELECT * FROM winforce_lima
WHERE [Estado orden] NOT LIKE '%Ejecutada%'
AND [Fecha de registro] LIKE '%-05-%'

/** Data **/
SELECT
	Grupo_Facturacion,
	COUNT(*) as conteo
FROM v_ventas_aliv_completa
WHERE Ultimo_Estado_Pago LIKE 'Cliente Pago'
GROUP BY Grupo_Facturacion



/** Data **/
SELECT
	Grupo_Facturacion,
	COUNT(*) as conteo
FROM v_ventas_aliv_completa
WHERE Ultimo_Estado_Pago LIKE 'Cliente Pago'
GROUP BY Grupo_Facturacion