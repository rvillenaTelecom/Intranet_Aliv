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
echo   1 - Correr todo (Fase 1 + Fase 2) - COMPLETO
echo   2 - Solo Fase 1: Descargas y consolidacion - COMPLETO
echo   3 - Solo Fase 2: Reporte (Power BI debe estar abierto)
echo   4 - ACTUALIZACION DIARIA (Solo ultimos 7 dias - Rapido)
echo.
set /p opcion="Elige una opcion (1/2/3/4): "

if "%opcion%"=="1" (
    python run_pipeline.py
) else if "%opcion%"=="2" (
    python run_pipeline.py fase1
) else if "%opcion%"=="3" (
    python run_pipeline.py fase2
) else if "%opcion%"=="4" (
    python run_pipeline.py daily
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
