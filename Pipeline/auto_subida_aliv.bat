@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

:: Verificar que el archivo exista antes de ejecutar
set ARCHIVO=descargas_winforce_Dept\Aliv_ventas_activas.xls
if not exist "%~dp0%ARCHIVO%" (
    echo [%date% %time%] ERROR: No se encontro Aliv_ventas_activas.xls - Subida omitida. >> "%~dp0logs\auto_subida_aliv.log"
    exit /b 1
)

python run_pipeline.py subida_aliv
