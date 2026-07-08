@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
title Pipeline Aliv - Ventas

echo ============================================
echo   PIPELINE ALIV - VENTAS
echo ============================================
echo.

:: Detectar python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python no encontrado en el sistema.
    pause
    exit /b 1
)

:: Ir a la carpeta del script
cd /d "%~dp0"

:: Menu de opciones
echo   1 - Todo 2026: Lima + Zonificacion + subir a BD (Sin Provincia)
echo   2 - Mensual: Solo esta semana ^(rapido^)
echo   3 - Reporte Semanal ^(Power BI debe estar abierto^)
echo   4 - Consolidar Ventas
echo   5 - Subir Usuarios Win
echo   6 - Reporte Diario ^(altas de ayer^)
echo.
set /p opcion="Elige una opcion (1/2/3/4/5/6): "

if "%opcion%"=="1" (
    python run_pipeline.py
) else if "%opcion%"=="2" (
    python run_pipeline.py daily
) else if "%opcion%"=="3" (
    python run_pipeline.py reporte
) else if "%opcion%"=="4" (
    python run_pipeline.py consolidar
) else if "%opcion%"=="5" (
    python run_pipeline.py maestros
) else if "%opcion%"=="6" (
    python run_pipeline.py reporte_diario
) else (
    echo Opcion invalida. Corriendo todo por defecto...
    python run_pipeline.py
)

echo.
if %errorlevel% equ 0 (
    echo Pipeline finalizado correctamente.
) else (
    echo Pipeline termino con errores. Revisa el log en la carpeta "logs".
)

pause
