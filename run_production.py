"""
Script para ejecutar Django con Waitress en producción
"""
import os
import sys

# Agregar el directorio del proyecto al path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# Configurar el módulo de settings de Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings_prod')

from waitress import serve
from core.wsgi import application

if __name__ == '__main__':
    # Configuración del servidor
    host = '0.0.0.0'  # Escucha en todas las interfaces
    port = 3004       # Puerto de la aplicación
    threads = 4       # Número de threads para manejar solicitudes
    
    print(f"Iniciando servidor Waitress en http://{host}:{port}")
    print(f"Usando {threads} threads")
    print("Presiona CTRL+C para detener el servidor")
    
    serve(
        application,
        host=host,
        port=port,
        threads=threads,
        url_scheme='http',
        channel_timeout=60,
        cleanup_interval=30,
        backlog=2048
    )
