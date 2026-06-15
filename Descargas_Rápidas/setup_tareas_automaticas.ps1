# SETUP TAREAS AUTOMATICAS - ALIV PIPELINE
# Ejecutar como Administrador una sola vez

$dir = $PSScriptRoot

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable

# 1. SOLO ESTE MES - cada hora
$accion = New-ScheduledTaskAction `
    -Execute 'cmd.exe' `
    -Argument ('/c "' + $dir + '\auto_solo_este_mes.bat"') `
    -WorkingDirectory $dir
$trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Hours 1) -Once -At '00:00'
Register-ScheduledTask -TaskName 'Aliv_SoloesMes' -Action $accion -Trigger $trigger `
    -Settings $settings -Description 'Descarga incremental mensual cada hora' `
    -RunLevel Highest -Force | Out-Null
Write-Host '[OK] Aliv_SoloesMes - cada hora' -ForegroundColor Green

# 2. REPORTE DIARIO - 10:00am
$accion = New-ScheduledTaskAction `
    -Execute 'cmd.exe' `
    -Argument ('/c "' + $dir + '\auto_reporte_diario.bat"') `
    -WorkingDirectory $dir
$trigger = New-ScheduledTaskTrigger -Daily -At '10:00'
Register-ScheduledTask -TaskName 'Aliv_ReporteDiario' -Action $accion -Trigger $trigger `
    -Settings $settings -Description 'Reporte diario altas de ayer' `
    -RunLevel Highest -Force | Out-Null
Write-Host '[OK] Aliv_ReporteDiario - 10:00am diario' -ForegroundColor Green

# 3. SUBIDA ALIV - 11:00am
$accion = New-ScheduledTaskAction `
    -Execute 'cmd.exe' `
    -Argument ('/c "' + $dir + '\auto_subida_aliv.bat"') `
    -WorkingDirectory $dir
$trigger = New-ScheduledTaskTrigger -Daily -At '11:00'
Register-ScheduledTask -TaskName 'Aliv_SubidaAliv' -Action $accion -Trigger $trigger `
    -Settings $settings -Description 'Sube Aliv_ventas_activas.xls a SQL' `
    -RunLevel Highest -Force | Out-Null
Write-Host '[OK] Aliv_SubidaAliv - 11:00am diario' -ForegroundColor Green

# 4. TODO 2026 - dia 1 de cada mes a las 2am
$accion = New-ScheduledTaskAction `
    -Execute 'cmd.exe' `
    -Argument ('/c "' + $dir + '\auto_todo_2026.bat"') `
    -WorkingDirectory $dir
$trigger = New-ScheduledTaskTrigger -Monthly -DaysOfMonth 1 -At '02:00'
Register-ScheduledTask -TaskName 'Aliv_Todo2026' -Action $accion -Trigger $trigger `
    -Settings $settings -Description 'Descarga completa 2026 el dia 1 de cada mes' `
    -RunLevel Highest -Force | Out-Null
Write-Host '[OK] Aliv_Todo2026 - dia 1 de cada mes 2:00am' -ForegroundColor Green

Write-Host ''
Write-Host 'Todas las tareas registradas. Verifica en Task Scheduler buscando Aliv_*' -ForegroundColor Cyan
