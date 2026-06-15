# setup_task_scheduler.ps1
# Configura Windows Task Scheduler para el pipeline de Aliv.
# Ejecutar como Administrador (o el usuario actual con permisos).

$PYTHON   = 'C:\Users\rvillena\AppData\Local\Programs\Python\Python314\python.exe'
$SCRIPT   = 'C:\Users\rvillena\Documents\Aliv_codes\Intranet_Aliv\Descargas_Rápidas\run_pipeline.py'
$WORK_DIR = 'C:\Users\rvillena\Documents\Aliv_codes\Intranet_Aliv\Descargas_Rápidas'

# Configuracion comun
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew

# ─── TAREA 1: Actualización incremental — Lun-Vie a las 7:30 AM ───────────────
$action1  = New-ScheduledTaskAction `
    -Execute $PYTHON `
    -Argument "`"$SCRIPT`" daily" `
    -WorkingDirectory $WORK_DIR

$trigger1 = New-ScheduledTaskTrigger `
    -Weekly `
    -WeeksInterval 1 `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At "07:30AM"

Register-ScheduledTask `
    -TaskName   "Aliv_Pipeline_Incremental" `
    -TaskPath   "\Aliv\" `
    -Action     $action1 `
    -Trigger    $trigger1 `
    -Settings   $settings `
    -RunLevel   Highest `
    -Force | Out-Null

Write-Host "[OK] Tarea creada: Aliv_Pipeline_Incremental (Lun-Vie 7:30 AM)"

# ─── TAREA 2: Recarga completa — Domingo a las 6:00 AM ────────────────────────
$action2  = New-ScheduledTaskAction `
    -Execute $PYTHON `
    -Argument "`"$SCRIPT`" bd" `
    -WorkingDirectory $WORK_DIR

$trigger2 = New-ScheduledTaskTrigger `
    -Weekly `
    -WeeksInterval 1 `
    -DaysOfWeek Sunday `
    -At "06:00AM"

Register-ScheduledTask `
    -TaskName   "Aliv_Pipeline_Full_Semanal" `
    -TaskPath   "\Aliv\" `
    -Action     $action2 `
    -Trigger    $trigger2 `
    -Settings   $settings `
    -RunLevel   Highest `
    -Force | Out-Null

Write-Host "[OK] Tarea creada: Aliv_Pipeline_Full_Semanal (Domingo 6:00 AM)"

# ─── Verificar ────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Tareas registradas:"
Get-ScheduledTask -TaskPath "\Aliv\" | Format-Table TaskName, State, TaskPath -AutoSize
