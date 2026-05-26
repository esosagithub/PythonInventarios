# Script para configurar Django como Servicio de Windows usando NSSM
# Ejecutar como Administrador

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Configuración de Servicio de Windows" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Obtener rutas
$PYTHON_PATH = (Get-Command python).Source
$PROJECT_PATH = $PSScriptRoot
$SCRIPT_PATH = Join-Path $PROJECT_PATH "run_production.py"

Write-Host "Ruta de Python: $PYTHON_PATH" -ForegroundColor Gray
Write-Host "Ruta del proyecto: $PROJECT_PATH" -ForegroundColor Gray
Write-Host ""

# Verificar si NSSM está instalado
Write-Host "Verificando NSSM..." -ForegroundColor Yellow
$nssmPath = "C:\nssm\nssm.exe"

if (-not (Test-Path $nssmPath)) {
    Write-Host ""
    Write-Host "NSSM no está instalado. Descargándolo..." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Por favor, descarga NSSM desde: https://nssm.cc/download" -ForegroundColor Red
    Write-Host "Y extrae nssm.exe en C:\nssm\" -ForegroundColor Red
    Write-Host ""
    Write-Host "Pasos:" -ForegroundColor Cyan
    Write-Host "1. Descargar nssm-2.24.zip desde https://nssm.cc/download" -ForegroundColor White
    Write-Host "2. Extraer el archivo" -ForegroundColor White
    Write-Host "3. Copiar nssm.exe (desde win64 o win32) a C:\nssm\" -ForegroundColor White
    Write-Host "4. Ejecutar este script nuevamente" -ForegroundColor White
    Write-Host ""
    pause
    exit
}

# Instalar servicio
$SERVICE_NAME = "DjangoInventarios"

Write-Host "Instalando servicio '$SERVICE_NAME'..." -ForegroundColor Yellow

# Detener y eliminar servicio si existe
& $nssmPath stop $SERVICE_NAME 2>$null
& $nssmPath remove $SERVICE_NAME confirm 2>$null

# Instalar servicio
& $nssmPath install $SERVICE_NAME $PYTHON_PATH $SCRIPT_PATH

# Configurar servicio
& $nssmPath set $SERVICE_NAME AppDirectory $PROJECT_PATH
& $nssmPath set $SERVICE_NAME DisplayName "Django Inventarios"
& $nssmPath set $SERVICE_NAME Description "Aplicación Django de Inventarios"
& $nssmPath set $SERVICE_NAME Start SERVICE_AUTO_START

# Configurar logs
$LOG_PATH = Join-Path $PROJECT_PATH "logs"
& $nssmPath set $SERVICE_NAME AppStdout (Join-Path $LOG_PATH "service_output.log")
& $nssmPath set $SERVICE_NAME AppStderr (Join-Path $LOG_PATH "service_error.log")

# Configurar reinicio automático
& $nssmPath set $SERVICE_NAME AppExit Default Restart
& $nssmPath set $SERVICE_NAME AppRestartDelay 5000

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Servicio instalado exitosamente!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Comandos útiles:" -ForegroundColor Cyan
Write-Host "  Iniciar servicio:   nssm start $SERVICE_NAME" -ForegroundColor White
Write-Host "  Detener servicio:   nssm stop $SERVICE_NAME" -ForegroundColor White
Write-Host "  Reiniciar servicio: nssm restart $SERVICE_NAME" -ForegroundColor White
Write-Host "  Ver estado:         nssm status $SERVICE_NAME" -ForegroundColor White
Write-Host "  Eliminar servicio:  nssm remove $SERVICE_NAME confirm" -ForegroundColor White
Write-Host ""
Write-Host "También puedes gestionar el servicio desde services.msc" -ForegroundColor Gray
Write-Host ""

# Preguntar si iniciar el servicio
$response = Read-Host "¿Deseas iniciar el servicio ahora? (S/N)"
if ($response -eq "S" -or $response -eq "s") {
    Write-Host "Iniciando servicio..." -ForegroundColor Yellow
    & $nssmPath start $SERVICE_NAME
    Start-Sleep -Seconds 3
    & $nssmPath status $SERVICE_NAME
    Write-Host ""
    Write-Host "El servidor debería estar disponible en http://localhost:8000" -ForegroundColor Green
}
