# 🚀 Guía de Instalación en Producción (Windows)

Esta guía te ayudará a instalar y configurar la aplicación Django de Inventarios en un servidor Windows sin usar IIS.

## 📋 Requisitos Previos

1. **Python 3.8 o superior** instalado en el servidor
2. **Acceso a la base de datos Oracle** configurada
3. **Permisos de administrador** en Windows

## 🔧 Componentes Instalados

- **Django 5.2.6**: Framework web
- **Waitress**: Servidor WSGI de producción para Windows
- **Whitenoise**: Servir archivos estáticos eficientemente
- **oracledb**: Conexión a Oracle Database

## 📦 Instalación Paso a Paso

### Opción 1: Instalación Automática (Recomendada)

1. **Abrir PowerShell como Administrador**

2. **Navegar a la carpeta del proyecto:**
   ```powershell
   cd C:\java\PythonProjects\Inventarios
   ```

3. **Ejecutar el script de instalación:**
   ```powershell
   .\install_production.ps1
   ```

### Opción 2: Instalación Manual

1. **Instalar dependencias:**
   ```powershell
   pip install -r requirements.txt
   ```

2. **Recolectar archivos estáticos:**
   ```powershell
   $env:DJANGO_SETTINGS_MODULE = "core.settings_prod"
   python manage.py collectstatic --noinput
   ```

3. **Aplicar migraciones:**
   ```powershell
   python manage.py migrate
   ```

4. **Crear superusuario (opcional):**
   ```powershell
   python manage.py createsuperuser
   ```

## 🏃 Ejecutar la Aplicación

### Modo Manual (Para Pruebas)

```powershell
python run_production.py
```

La aplicación estará disponible en: **http://localhost:8000**

Presiona `CTRL+C` para detener el servidor.

### Modo Servicio de Windows (Recomendado para Producción)

#### Instalar NSSM (Non-Sucking Service Manager)

1. Descargar desde: https://nssm.cc/download
2. Extraer el archivo ZIP
3. Copiar `nssm.exe` (carpeta win64) a `C:\nssm\`

#### Configurar como Servicio

1. **Abrir PowerShell como Administrador**

2. **Ejecutar el script de instalación del servicio:**
   ```powershell
   cd C:\java\PythonProjects\Inventarios
   .\install_service.ps1
   ```

#### Gestionar el Servicio

```powershell
# Iniciar servicio
nssm start DjangoInventarios

# Detener servicio
nssm stop DjangoInventarios

# Reiniciar servicio
nssm restart DjangoInventarios

# Ver estado
nssm status DjangoInventarios

# Eliminar servicio
nssm remove DjangoInventarios confirm
```

También puedes gestionar el servicio desde:
- **Panel de Control → Herramientas Administrativas → Servicios**
- O ejecutando `services.msc`

## 🔒 Configuración de Seguridad

### 1. Cambiar la Clave Secreta

**IMPORTANTE:** Antes de poner en producción, genera una nueva clave secreta:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Edita `core/settings_prod.py` y reemplaza la clave.

### 2. Configurar ALLOWED_HOSTS

Edita `core/settings_prod.py` y agrega las IPs o dominios permitidos:

```python
ALLOWED_HOSTS = ['tu-servidor.com', '192.168.1.100']
```

### 3. Configurar HTTPS (Recomendado)

Si usas un proxy inverso (Nginx/Apache) con SSL, descomenta estas líneas en `core/settings_prod.py`:

```python
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

## 🌐 Configuración de Firewall

Si necesitas acceder desde otras computadoras:

```powershell
# Permitir tráfico en el puerto 8000
New-NetFirewallRule -DisplayName "Django Inventarios" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
```

## 📊 Monitoreo y Logs

Los logs se guardan en la carpeta `logs/`:

- `django_error.log`: Errores de Django
- `service_output.log`: Salida estándar del servicio
- `service_error.log`: Errores del servicio

Para ver logs en tiempo real:
```powershell
Get-Content logs\django_error.log -Wait -Tail 50
```

## 🔄 Actualización de la Aplicación

1. **Detener el servicio:**
   ```powershell
   nssm stop DjangoInventarios
   ```

2. **Actualizar código y dependencias:**
   ```powershell
   git pull  # Si usas git
   pip install -r requirements.txt
   ```

3. **Aplicar migraciones:**
   ```powershell
   python manage.py migrate
   ```

4. **Recolectar archivos estáticos:**
   ```powershell
   python manage.py collectstatic --noinput
   ```

5. **Iniciar el servicio:**
   ```powershell
   nssm start DjangoInventarios
   ```

## 🛠️ Solución de Problemas

### El servicio no inicia

1. Verificar logs en `logs/service_error.log`
2. Verificar que Python esté en el PATH
3. Ejecutar manualmente para ver errores:
   ```powershell
   python run_production.py
   ```

### Archivos estáticos no se cargan

```powershell
python manage.py collectstatic --noinput --clear
```

### Error de conexión a Oracle

Verificar credenciales en `core/settings.py` o usar variables de entorno.

## 📞 Configuración Avanzada

### Cambiar Puerto

Edita `run_production.py` y cambia:
```python
port = 8000  # Cambiar a tu puerto deseado
```

### Aumentar Threads (para más tráfico)

Edita `run_production.py`:
```python
threads = 8  # Aumentar según necesidad
```

### Usar Proxy Inverso (Nginx/Apache)

Para mejor rendimiento, puedes poner Nginx o Apache delante de Waitress:

**Nginx** (recomendado):
- Descarga: https://nginx.org/en/download.html
- Configuración: proxy_pass a http://localhost:8000

**Apache**:
- Usar mod_proxy para redirigir a Waitress

## 🎯 Checklist de Producción

- [ ] DEBUG = False en settings_prod.py
- [ ] Cambiar SECRET_KEY
- [ ] Configurar ALLOWED_HOSTS
- [ ] Recolectar archivos estáticos
- [ ] Aplicar migraciones
- [ ] Configurar backups de base de datos
- [ ] Configurar logs
- [ ] Configurar firewall
- [ ] Probar acceso desde red local
- [ ] Documentar credenciales de base de datos
- [ ] Configurar SSL/HTTPS (recomendado)

## 📚 Recursos Adicionales

- **Django Deployment Checklist:** https://docs.djangoproject.com/en/stable/howto/deployment/checklist/
- **Waitress Documentation:** https://docs.pylonsproject.org/projects/waitress/
- **NSSM Documentation:** https://nssm.cc/usage

---

**Versión:** 1.0  
**Última actualización:** Enero 2026
