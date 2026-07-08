@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
title Reportes Diarios Aliv

echo ============================================
echo   REPORTES DIARIOS ALIV
echo ============================================
echo.

cd /d "%~dp0"

python run_pipeline.py reporte_diario

echo.
if %errorlevel% equ 0 (
    echo Reportes generados correctamente.
) else (
    echo Hubo un error. Revisa el log en la carpeta "logs".
)

pause
