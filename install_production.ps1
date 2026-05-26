# Script de instalación para producción
# Ejecutar como Administrador

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Instalación para Producción - Django" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Instalar dependencias
Write-Host "1. Instalando dependencias de Python..." -ForegroundColor Yellow
python -m pip install --upgrade pip
pip install -r requirements.txt

# 2. Recolectar archivos estáticos
Write-Host ""
Write-Host "2. Recolectando archivos estáticos..." -ForegroundColor Yellow
$env:DJANGO_SETTINGS_MODULE = "core.settings_prod"
python manage.py collectstatic --noinput

# 3. Ejecutar migraciones
Write-Host ""
Write-Host "3. Aplicando migraciones de base de datos..." -ForegroundColor Yellow
python manage.py migrate

# 4. Verificar instalación
Write-Host ""
Write-Host "4. Verificando instalación..." -ForegroundColor Yellow
python manage.py check --deploy

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Instalación completada exitosamente!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Para iniciar el servidor en producción, ejecuta:" -ForegroundColor Cyan
Write-Host "  python run_production.py" -ForegroundColor White
Write-Host ""
Write-Host "Para crear un usuario administrador:" -ForegroundColor Cyan
Write-Host "  python manage.py createsuperuser" -ForegroundColor White
Write-Host ""
