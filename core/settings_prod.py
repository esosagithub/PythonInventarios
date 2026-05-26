"""
Configuración de producción para Django
"""
from .settings import *

# Seguridad
DEBUG = False

# Configurar ALLOWED_HOSTS con tu servidor de producción
ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', ['localhost', '127.0.0.1'])

# Clave secreta - IMPORTANTE: Cambiar en producción
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', SECRET_KEY)

# Configuración de seguridad
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True

# Si usas HTTPS (recomendado):
# SECURE_SSL_REDIRECT = True
# SESSION_COOKIE_SECURE = True
# CSRF_COOKIE_SECURE = True

# Whitenoise para servir archivos estáticos
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

# Configuración de almacenamiento estático
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'django_error.log'),
            'formatter': 'verbose',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
