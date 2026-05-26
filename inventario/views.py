# inventario/views.py
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.db import connection, transaction
from django.utils import timezone
import requests
import json
from django.http import HttpResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.graphics.barcode import code128
from reportlab.lib.units import mm
from django.db import connection
import oracledb
import oracledb as cx_Oracle
import os
from datetime import datetime
import time


@csrf_exempt
def custom_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        # Verificar si es una petición AJAX
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        print(f"Intento de login: {username}")  # Debug

        # URL del servicio web
        url = 'https://ns.aseyco.com:444/MSWebServiceNomina/rest/service/wsNomina'

        # Datos para enviar al servicio
        payload = {
            "cedula": username,
            "password": password
        }

        # Headers requeridos
        headers = {
            'Content-Type': 'text/plain'
        }

        try:
            print("Intentando conectar con el web service...")  # Debug
            # Llamada al servicio web
            response = requests.post(
                url, headers=headers, data=json.dumps(payload), timeout=10)
            print(f"Respuesta recibida: {response.status_code}")  # Debug

            response_data = response.json()

            # --- IMPRIMIR ESTRUCTURA COMPLETA ---
            print("=" * 50)
            print("ESTRUCTURA COMPLETA DE LA RESPUESTA DEL WEB SERVICE:")
            print(json.dumps(response_data, indent=2, ensure_ascii=False))
            print("=" * 50)
            # --- FIN DE IMPRESIÓN ---

            # Verificar respuesta del servicio
            if response_data.get('resultado') == '1':  # Autenticación exitosa
                # Verificar si el usuario está activo
                estado_usuario = response_data.get(
                    'colaboradr', {}).get('ESTADO', '')
                usuario_activo = estado_usuario == '1'

                print(f"Valor del campo ESTADO: '{estado_usuario}'")  # Debug
                print(f"Usuario activo: {usuario_activo}")  # Debug

                if usuario_activo:
                    # Guardar datos del usuario en sesión - CORRECCIÓN IMPORTANTE
                    request.session['usuario'] = {
                        'cedula': username,
                        'identificacion': username,
                        'nombre': response_data.get('colaboradr', {}).get('COLABORADOR', ''),
                        'empresa': response_data.get('colaboradr', {}).get('EMPRESA', ''),
                        'cargo': response_data.get('colaboradr', {}).get('CARGO', ''),
                        'email': response_data.get('colaboradr', {}).get('CORREO_EMPRESARIAL', ''),
                        'region': response_data.get('colaboradr', {}).get('REGION', ''),
                        'activo': True
                    }

                    if is_ajax:
                        # Responder con JSON para AJAX
                        return JsonResponse({
                            'success': True,
                            'usuario_nombre': response_data.get('colaboradr', {}).get('COLABORADOR', ''),
                            'activo': True,
                            'message': 'Usuario autenticado correctamente'
                        })
                    else:
                        # Para peticiones normales, redirigir al dashboard
                        return redirect('dashboard')
                else:
                    # Usuario no activo
                    print("Usuario no activo")  # Debug
                    if is_ajax:
                        return JsonResponse({
                            'success': False,
                            'activo': False,
                            'message': 'Usuario no activo en el sistema'
                        })
                    else:
                        messages.error(
                            request, 'Usuario no activo en el sistema')
                        return render(request, 'inventario/login.html')

            else:
                # Autenticación fallida
                print("Autenticación fallida")  # Debug
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'activo': False,
                        'message': 'Credenciales incorrectas o usuario no registrado'
                    })
                else:
                    messages.error(
                        request, 'Credenciales incorrectas o usuario no registrado')
                    return render(request, 'inventario/login.html')

        except requests.exceptions.RequestException as e:
            # Error de conexión
            print(f"Error de conexión: {e}")  # Debug
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'activo': False,
                    'message': 'Error de conexión con el servicio de autenticación'
                })
            else:
                messages.error(
                    request, 'Error de conexión con el servicio de autenticación')
                return render(request, 'inventario/login.html')
        except KeyError as e:
            # Error en la estructura de la respuesta
            print(f"Error en estructura de respuesta: {e}")  # Debug
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'activo': False,
                    'message': 'Error en la respuesta del servicio de autenticación'
                })
            else:
                messages.error(
                    request, 'Error en la respuesta del servicio de autenticación')
                return render(request, 'inventario/login.html')
        except Exception as e:
            # Cualquier otro error
            print(f"Error inesperado: {e}")  # Debug
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'activo': False,
                    'message': 'Error inesperado en el servidor'
                })
            else:
                messages.error(request, 'Error inesperado en el servidor')
                return render(request, 'inventario/login.html')

    return render(request, 'inventario/login.html')


def seleccionar_perfil(request):
    # Verificar si el usuario está autenticado
    if 'usuario' not in request.session:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'error': 'No autenticado'}, status=401)
        return redirect('login')

    # URL del servicio web
    url = 'https://ns.aseyco.com:444/MSWebServiceNomina/rest/service/getPerfilesUsuario'

    # Obtener la identificación del usuario de la sesión
    usuario_sesion = request.session.get('usuario', {})
    identificacion = usuario_sesion.get(
        'identificacion', '') or usuario_sesion.get('cedula', '')

    if not identificacion:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'error': 'Identificación no encontrada'}, status=400)
        messages.error(request, 'Identificación no encontrada')
        return redirect('login')

    # Datos para la solicitud
    payload = {
        "id_sistema": 621,
        "identificacion": identificacion,
        "pais": "ECUADOR"
    }

    headers = {
        'Content-Type': 'application/json'
    }

    perfiles = []

    try:
        # Realizar la solicitud al servicio web
        response = requests.post(url, headers=headers,
                                 data=json.dumps(payload), timeout=10)
        response.raise_for_status()

        # Procesar la respuesta
        datos_perfiles = response.json()

        if datos_perfiles:
            for perfil in datos_perfiles:
                perfiles.append({
                    'id': perfil['id_perfil'],
                    'nombre': perfil['nombre_perfil'],
                    'codigo': f"PERFIL_{perfil['id_perfil']}",
                    'datos_completos': perfil  # Guardar todos los datos por si se necesitan
                })
        else:
            # Si no hay perfiles, mostrar mensaje
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'perfiles': [], 'message': 'No se encontraron perfiles'})
            else:
                messages.warning(
                    request, 'No se encontraron perfiles para tu usuario')

    except requests.exceptions.RequestException as e:
        error_msg = f'Error al conectar con el servicio de perfiles: {str(e)}'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'error': error_msg}, status=500)
        else:
            messages.error(request, error_msg)
        perfiles = []
    except json.JSONDecodeError as e:
        error_msg = 'Error al procesar la respuesta del servicio'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'error': error_msg}, status=500)
        else:
            messages.error(request, error_msg)
        perfiles = []

    # Si es una petición AJAX, retornar JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'perfiles': perfiles})

    # Para peticiones normales (POST) - desde el template antiguo
    if request.method == 'POST':
        perfil_seleccionado_id = request.POST.get('perfil')
        if perfil_seleccionado_id:
            # Buscar el perfil completo
            perfil_completo = next((p for p in perfiles if str(
                p['id']) == perfil_seleccionado_id), None)

            if perfil_completo:
                # Guardar el perfil COMPLETO en sesión
                request.session['perfil_seleccionado'] = perfil_completo
                messages.success(
                    request, f'Perfil {perfil_completo["nombre"]} seleccionado')
                return redirect('dashboard')
            else:
                messages.error(request, 'Perfil seleccionado no válido')

    # Para peticiones GET - renderizar template (si aún usas el template antiguo)
    return render(request, 'inventario/seleccionar_perfil.html', {
        'perfiles': perfiles
    })


def dashboard(request):
    # Verificar manualmente si el usuario está en sesión
    if 'usuario' not in request.session:
        return redirect('login')

    # Obtener el perfil seleccionado COMPLETO de la sesión
    perfil_completo = request.session.get('perfil_seleccionado', {})

    # Si viene de GET parameter (redirección desde JavaScript)
    perfil_id_get = request.GET.get('perfil')
    perfil_nombre_get = request.GET.get('nombre')

    if perfil_id_get and perfil_nombre_get:
        # Guardar el perfil completo desde los parámetros GET
        perfil_completo = {
            'id': perfil_id_get,
            'nombre': perfil_nombre_get
        }
        request.session['perfil_seleccionado'] = perfil_completo

    # Verificar si tiene perfil seleccionado
    if not perfil_completo:
        return redirect('seleccionar_perfil')

    # Obtener el NOMBRE del perfil para el template
    if isinstance(perfil_completo, dict):
        perfil_nombre = perfil_completo.get('nombre', 'Perfil no seleccionado')
    else:
        # Si es solo un string (ID), mapear manualmente
        perfil_map = {
            '761': 'ADMINISTRATIVO',
            '762': 'JEFE DE TIENDA',
            '763': 'SUPERVISOR',
            'ADMIN_INV': 'ADMINISTRADOR DE INVENTARIO',
            'USER_BODEGA': 'USUARIO DE BODEGA'
        }
        perfil_nombre = perfil_map.get(
            str(perfil_completo), f'Perfil {perfil_completo}')
        # Actualizar la sesión con el objeto completo
        perfil_completo = {'id': perfil_completo, 'nombre': perfil_nombre}
        request.session['perfil_seleccionado'] = perfil_completo

    usuario_context = dict(request.session.get('usuario', {}))
    if 'tienda' not in usuario_context:
        usuario_context['tienda'] = usuario_context.get('empresa', '')

    context = {
        'usuario': usuario_context,
        'perfil': perfil_nombre,
        'perfil_completo': perfil_completo
    }

    return render(request, 'inventario/dashboard.html', context)


@csrf_exempt
def administracion_conteo(request):
    # Verificar manualmente si el usuario está en sesión
    if 'usuario' not in request.session:
        return redirect('login')

    # Verificar si tiene perfil seleccionado
    perfil_completo = request.session.get('perfil_seleccionado', {})
    if not perfil_completo:
        return redirect('seleccionar_perfil')

    # Obtener el NOMBRE del perfil
    if isinstance(perfil_completo, dict):
        perfil_nombre = perfil_completo.get('nombre', 'Perfil no seleccionado')
    else:
        # Mapeo manual si es solo ID
        perfil_map = {
            '761': 'ADMINISTRATIVO',
            '762': 'JEFE DE TIENDA',
            '763': 'SUPERVISOR',
            'ADMIN_INV': 'ADMINISTRADOR DE INVENTARIO',
            'USER_BODEGA': 'USUARIO DE BODEGA'
        }
        perfil_nombre = perfil_map.get(
            str(perfil_completo), f'Perfil {perfil_completo}')

    # VERIFICAR PERMISOS - Solo permitir ADMINISTRATIVO
    if perfil_nombre != "ADMINISTRATIVO":
        messages.error(
            request, 'No tiene permisos para acceder a Administración de Conteo')
        return redirect('dashboard')

    # OBTENER FILTROS DE LA PETICIÓN
    filtros = {}
    if request.method == 'GET':
        filtros['estado'] = request.GET.get('estado', '').strip()
        filtros['centro'] = request.GET.get('centro', '').strip()
        filtros['almacen'] = request.GET.get('almacen', '').strip()
        filtros['fecha_inicio_desde'] = request.GET.get(
            'fecha_inicio_desde', '').strip()
        filtros['fecha_inicio_hasta'] = request.GET.get(
            'fecha_inicio_hasta', '').strip()
        filtros['fecha_fin_desde'] = request.GET.get(
            'fecha_fin_desde', '').strip()
        filtros['fecha_fin_hasta'] = request.GET.get(
            'fecha_fin_hasta', '').strip()

    # Si es petición AJAX para filtros
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' and request.method == 'POST':
        try:
            data = json.loads(request.body)
            filtros = data.get('filtros', {})
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Error en los datos de filtros'}, status=400)

    # CONSULTA REAL A LA BASE DE DATOS
    conteos_reales = []
    estadisticas = {
        'total': 0,
        'pendientes': 0,
        'en_proceso': 0,
        'completados': 0,
        'activos': 0
    }

    try:
        with connection.cursor() as cursor:
            # Consulta base con filtros dinámicos
            base_query = """
                SELECT 
                    pi.piqueo_id,
                    pi.numero_conteo,
                    pi.pais,
                    pi.centro,
                    pi.almacen,
                    TO_CHAR(pi.fecha_inicio, 'YYYY-MM-DD'),
                    TO_CHAR(pi.fecha_fin, 'YYYY-MM-DD'),
                    pi.estado,
                    pi.centro_costo,
                    pi.fecha_creacion,
                    pi.usuario_creacion,
                    pi.ap_responsable,
                    pi.nm_responsable,
                    pi.cargo_responsable
                FROM view_planificacion_inventario pi
                WHERE 1=1
            """

            params = []

            # APLICAR FILTROS DINÁMICAMENTE
            if filtros.get('estado'):
                base_query += " AND UPPER(pi.estado) = UPPER(%s)"
                params.append(filtros['estado'])

            if filtros.get('centro'):
                base_query += " AND pi.centro = %s"
                params.append(filtros['centro'])

            if filtros.get('almacen'):
                base_query += " AND pi.almacen = %s"
                params.append(filtros['almacen'])

            if filtros.get('fecha_inicio_desde'):
                base_query += " AND pi.fecha_inicio >= TO_DATE(%s, 'YYYY-MM-DD')"
                params.append(filtros['fecha_inicio_desde'])

            if filtros.get('fecha_inicio_hasta'):
                base_query += " AND pi.fecha_inicio <= TO_DATE(%s, 'YYYY-MM-DD')"
                params.append(filtros['fecha_inicio_hasta'])

            if filtros.get('fecha_fin_desde'):
                base_query += " AND pi.fecha_fin >= TO_DATE(%s, 'YYYY-MM-DD')"
                params.append(filtros['fecha_fin_desde'])

            if filtros.get('fecha_fin_hasta'):
                base_query += " AND pi.fecha_fin <= TO_DATE(%s, 'YYYY-MM-DD')"
                params.append(filtros['fecha_fin_hasta'])

            base_query += " ORDER BY pi.fecha_creacion DESC"

            cursor.execute(base_query, params)
            resultados = cursor.fetchall()

            print(f"🔍 Filtros aplicados: {filtros}")
            print(f"📊 Número de registros encontrados: {len(resultados)}")

            for row in resultados:
                try:
                    estado = row[7] if len(row) > 7 else 'PENDIENTE'

                    conteo = {
                        'id': row[0] if len(row) > 0 else 0,
                        'numero_conteo': row[1] if len(row) > 1 else 'N/A',
                        'pais': row[2] if len(row) > 2 else 'N/A',
                        'centro': row[3] if len(row) > 3 else 'N/A',
                        'almacen': row[4] if len(row) > 4 else 'N/A',
                        'fecha_inicio': row[5] if len(row) > 5 else 'N/A',
                        'fecha_fin': row[6] if len(row) > 6 else 'N/A',
                        'estado': estado,
                        'centro_costo': row[8] if len(row) > 8 else 'N/A',
                        'fecha_creacion': row[9] if len(row) > 9 else 'N/A',
                        'usuario_creacion': row[10] if len(row) > 10 else 'Sistema',
                        'ap_responsable': row[11] if len(row) > 11 else '',
                        'nm_responsable': row[12] if len(row) > 12 else 'No asignado',
                        'cargo_responsable': row[13] if len(row) > 13 else ''
                    }

                    conteos_reales.append(conteo)

                    # CALCULAR ESTADÍSTICAS
                    estadisticas['total'] += 1
                    estado_normalizado = estado.upper().strip()

                    if estado_normalizado == 'PENDIENTE':
                        estadisticas['pendientes'] += 1
                    elif estado_normalizado in ['EN_PROCESO', 'EN PROGRESO', 'PROCESANDO', 'ACTIVO']:
                        estadisticas['en_proceso'] += 1
                        estadisticas['activos'] += 1
                    elif estado_normalizado in ['COMPLETADO', 'FINALIZADO', 'TERMINADO']:
                        estadisticas['completados'] += 1

                except Exception as e:
                    print(f"❌ Error procesando fila: {e}")
                    continue

    except Exception as e:
        print(f"❌ Error al consultar conteos: {e}")
        messages.error(request, f'Error al cargar los conteos: {str(e)}')
        conteos_reales = []
        estadisticas = {'total': 0, 'pendientes': 0,
                        'en_proceso': 0, 'completados': 0}

    # Si es petición AJAX, devolver JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'conteos': conteos_reales,
            'estadisticas': estadisticas,
            'filtros_aplicados': filtros
        })

    # OBTENER OPCIONES PARA LOS FILTROS
    centros_disponibles = []
    almacenes_disponibles = []

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT DISTINCT centro FROM view_planificacion_inventario WHERE centro IS NOT NULL ORDER BY centro")
            centros_disponibles = [row[0] for row in cursor.fetchall()]

            cursor.execute(
                "SELECT DISTINCT almacen FROM view_planificacion_inventario WHERE almacen IS NOT NULL ORDER BY almacen")
            almacenes_disponibles = [row[0] for row in cursor.fetchall()]

    except Exception as e:
        print(f"❌ Error al obtener opciones de filtros: {e}")

    context = {
        'usuario': request.session['usuario'],
        'perfil': perfil_nombre,
        'conteos': conteos_reales,
        'estadisticas': estadisticas,
        'centros_disponibles': centros_disponibles,
        'almacenes_disponibles': almacenes_disponibles,
        'filtros_actuales': filtros
    }

    return render(request, 'inventario/administracion_conteo.html', context)


@csrf_exempt
def administracion_conteo_jefe(request):
    """
    Vista especial de Administración de Conteo para el perfil JEFE
    """
    # Verificar manualmente si el usuario está en sesión
    if 'usuario' not in request.session:
        return redirect('login')

    # Verificar si tiene perfil seleccionado
    perfil_completo = request.session.get('perfil_seleccionado', {})
    if not perfil_completo:
        return redirect('seleccionar_perfil')

    # Obtener el NOMBRE del perfil
    if isinstance(perfil_completo, dict):
        perfil_nombre = perfil_completo.get('nombre', 'Perfil no seleccionado')
    else:
        # Mapeo manual si es solo ID
        perfil_map = {
            '761': 'ADMINISTRATIVO',
            '762': 'JEFE DE TIENDA',
            '763': 'SUPERVISOR',
            'ADMIN_INV': 'ADMINISTRADOR DE INVENTARIO',
            'USER_BODEGA': 'USUARIO DE BODEGA'
        }
        perfil_nombre = perfil_map.get(
            str(perfil_completo), f'Perfil {perfil_completo}')

    # VERIFICAR PERMISOS - Solo permitir JEFE
    if perfil_nombre != "JEFE DE TIENDA":
        messages.error(
            request, 'No tiene permisos para acceder a Administración de Conteo - Jefe')
        return redirect('dashboard')

    # OBTENER USUARIO LOGUEADO
    usuario_sesion = request.session.get('usuario', {})
    usuario_nombre = usuario_sesion.get('nombre', '')
    usuario_cedula = usuario_sesion.get('cedula', '')

    print(
        f"👤 [JEFE] Usuario logueado: {usuario_nombre} (Cédula: {usuario_cedula})")

    # OBTENER DATOS DE LA TIENDA DEL JEFE DEL WEB SERVICE
    datos_tienda_jefe = []
    if usuario_cedula:
        try:
            # Consumir web service para obtener datos de la tienda del jefe
            url = 'https://ns.aseyco.com:444/MSWebServiceNomina/rest/service/getDatoTiendaColabroador'
            payload = {
                "cedula": usuario_cedula
            }
            headers = {
                'Content-Type': 'application/json'
            }

            response = requests.post(
                url, headers=headers, data=json.dumps(payload), timeout=10)
            response_data = response.json()

            print(
                f"🏪 [JEFE] Respuesta del web service de tienda: {response_data}")

            if response_data and isinstance(response_data, list):
                datos_tienda_jefe = response_data
                print(
                    f"✅ [JEFE] Datos de tienda encontrados: {len(datos_tienda_jefe)} registros")
            else:
                print("⚠️ [JEFE] No se encontraron datos de tienda para el jefe")
                messages.warning(
                    request, 'No se encontraron datos de tienda asignada para su usuario')

        except Exception as e:
            print(f"❌ [JEFE] Error al obtener datos de tienda: {e}")
            messages.error(
                request, f'Error al obtener datos de tienda: {str(e)}')
    else:
        print("❌ [JEFE] No se encontró cédula en la sesión")
        messages.error(request, 'No se pudo identificar su cédula de usuario')

    # EXTRAER CENTROS Y ALMACENES ASIGNADOS AL JEFE
    centros_asignados = []
    almacenes_asignados = []

    for tienda in datos_tienda_jefe:
        centro = tienda.get('centro', '')
        almacen = tienda.get('almacen', '')

        if centro and centro not in centros_asignados:
            centros_asignados.append(centro)

        if almacen and almacen not in almacenes_asignados:
            almacenes_asignados.append(almacen)

    print(f"📍 [JEFE] Centros asignados: {centros_asignados}")
    print(f"📍 [JEFE] Almacenes asignados: {almacenes_asignados}")

    # OBTENER FILTROS DE LA PETICIÓN
    filtros = {}
    if request.method == 'GET':
        filtros['estado'] = request.GET.get('estado', '').strip()
        filtros['centro'] = request.GET.get('centro', '').strip()
        filtros['almacen'] = request.GET.get('almacen', '').strip()
        filtros['fecha_inicio_desde'] = request.GET.get(
            'fecha_inicio_desde', '').strip()
        filtros['fecha_inicio_hasta'] = request.GET.get(
            'fecha_inicio_hasta', '').strip()

    # Si es petición AJAX para filtros
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' and request.method == 'POST':
        try:
            data = json.loads(request.body)
            filtros = data.get('filtros', {})
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Error en los datos de filtros'}, status=400)

    # CONSULTA ESPECIAL PARA JEFE - FILTRADO POR CENTROS/ALMACENES ASIGNADOS
    conteos_reales = []
    estadisticas = {
        'total': 0,
        'pendientes': 0,
        'en_proceso': 0,
        'completados': 0,
        'activos': 0
    }

    try:
        with connection.cursor() as cursor:
            # QUERY MODIFICADO - FILTRAR POR CENTROS/ALMACENES ASIGNADOS AL JEFE
            base_query = """
                SELECT 
                    pi.piqueo_id,
                    pi.numero_conteo,
                    pi.pais,
                    pi.centro,
                    pi.almacen,
                    TO_CHAR(pi.fecha_inicio, 'YYYY-MM-DD'),
                    TO_CHAR(pi.fecha_fin, 'YYYY-MM-DD'),
                    pi.estado,
                    pi.centro_costo,
                    pi.fecha_creacion,
                    pi.usuario_creacion,
                    pi.ap_responsable,
                    pi.nm_responsable,
                    pi.cargo_responsable
                FROM view_planificacion_inventario pi
                WHERE 1=1
            """

            params = []

            # FILTRAR POR CENTROS ASIGNADOS AL JEFE
            if centros_asignados:
                placeholders = ','.join(['%s'] * len(centros_asignados))
                base_query += f" AND pi.centro IN ({placeholders})"
                params.extend(centros_asignados)
            else:
                # Si no hay centros asignados, no mostrar ningún conteo
                base_query += " AND 1=0"

            base_query += " AND pi.usuario_responsable = %s"
            params.append(usuario_cedula)
            # APLICAR FILTROS ADICIONALES DINÁMICAMENTE
            if filtros.get('estado'):
                base_query += " AND UPPER(pi.estado) = UPPER(%s)"
                params.append(filtros['estado'])

            if filtros.get('centro') and centros_asignados and filtros['centro'] in centros_asignados:
                base_query += " AND pi.centro = %s"
                params.append(filtros['centro'])

            if filtros.get('almacen') and almacenes_asignados and filtros['almacen'] in almacenes_asignados:
                base_query += " AND pi.almacen = %s"
                params.append(filtros['almacen'])

            if filtros.get('fecha_inicio_desde'):
                base_query += " AND pi.fecha_inicio >= TO_DATE(%s, 'YYYY-MM-DD')"
                params.append(filtros['fecha_inicio_desde'])

            if filtros.get('fecha_inicio_hasta'):
                base_query += " AND pi.fecha_inicio <= TO_DATE(%s, 'YYYY-MM-DD')"
                params.append(filtros['fecha_inicio_hasta'])

            base_query += " ORDER BY pi.fecha_creacion DESC"

            print(f"🔍 [JEFE] Query ejecutado: {base_query}")
            print(f"🔍 [JEFE] Parámetros: {params}")

            cursor.execute(base_query, params)
            resultados = cursor.fetchall()

            print(f"🔍 [JEFE] Filtros aplicados: {filtros}")
            print(f"📊 [JEFE] Número de conteos encontrados: {len(resultados)}")

            for row in resultados:
                try:
                    estado = row[7] if len(row) > 7 else 'PENDIENTE'

                    conteo = {
                        'id': row[0] if len(row) > 0 else 0,
                        'numero_conteo': row[1] if len(row) > 1 else 'N/A',
                        'pais': row[2] if len(row) > 2 else 'N/A',
                        'centro': row[3] if len(row) > 3 else 'N/A',
                        'almacen': row[4] if len(row) > 4 else 'N/A',
                        'fecha_inicio': row[5] if len(row) > 5 else 'N/A',
                        'fecha_fin': row[6] if len(row) > 6 else 'N/A',
                        'estado': estado,
                        'centro_costo': row[8] if len(row) > 8 else 'N/A',
                        'fecha_creacion': row[9] if len(row) > 9 else 'N/A',
                        'usuario_creacion': row[10] if len(row) > 10 else 'Sistema',
                        'ap_responsable': row[11] if len(row) > 11 else '',
                        'nm_responsable': row[12] if len(row) > 12 else 'No asignado',
                        'cargo_responsable': row[13] if len(row) > 13 else ''
                    }

                    conteos_reales.append(conteo)

                    # CALCULAR ESTADÍSTICAS
                    estadisticas['total'] += 1
                    estado_normalizado = estado.upper().strip()

                    if estado_normalizado == 'PENDIENTE':
                        estadisticas['pendientes'] += 1
                    elif estado_normalizado in ['EN_PROCESO', 'EN PROGRESO', 'PROCESANDO', 'ACTIVO']:
                        estadisticas['en_proceso'] += 1
                        estadisticas['activos'] += 1
                    elif estado_normalizado in ['COMPLETADO', 'FINALIZADO', 'TERMINADO']:
                        estadisticas['completados'] += 1

                except Exception as e:
                    print(f"❌ [JEFE] Error procesando fila: {e}")
                    continue

    except Exception as e:
        print(f"❌ [JEFE] Error al consultar conteos: {e}")
        messages.error(request, f'Error al cargar los conteos: {str(e)}')
        conteos_reales = []
        estadisticas = {'total': 0, 'pendientes': 0,
                        'en_proceso': 0, 'completados': 0, 'activos': 0}

    # Si es petición AJAX, devolver JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'conteos': conteos_reales,
            'estadisticas': estadisticas,
            'filtros_aplicados': filtros,
            'centros_asignados': centros_asignados,
            'almacenes_asignados': almacenes_asignados
        })

    # OBTENER OPCIONES PARA LOS FILTROS (solo los centros/almacenes asignados al jefe)
    centros_disponibles = centros_asignados
    almacenes_disponibles = almacenes_asignados

    context = {
        'usuario': request.session['usuario'],
        'perfil': perfil_nombre,
        'conteos': conteos_reales,
        'estadisticas': estadisticas,
        'centros_disponibles': centros_disponibles,
        'almacenes_disponibles': almacenes_disponibles,
        'filtros_actuales': filtros,
        'datos_tienda_jefe': datos_tienda_jefe,
        'centros_asignados': centros_asignados,
        'almacenes_asignados': almacenes_asignados
    }

    return render(request, 'inventario/administracion_conteo_jefe.html', context)


@csrf_exempt
def aprobar_rechazar_conteo(request, piqueo_id):
    """
    Vista para que el jefe apruebe o rechace un conteo
    """
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'message': 'No autenticado'})

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'})

    try:
        data = json.loads(request.body)
        accion = data.get('accion')  # 'aprobar' o 'rechazar'
        observaciones = data.get('observaciones', '')

        if accion not in ['aprobar', 'rechazar']:
            return JsonResponse({'success': False, 'message': 'Acción no válida'})

        with connection.cursor() as cursor:
            # Actualizar el estado de aprobación
            nuevo_estado = 'APROBADO' if accion == 'aprobar' else 'RECHAZADO'

            cursor.execute("""
                UPDATE INV_PIQUEOS_INVENTARIO_TBL 
                SET estado_aprobacion = %s,
                    observaciones_aprobacion = %s,
                    fecha_aprobacion = SYSTIMESTAMP,
                    usuario_aprobacion = %s
                WHERE piqueo_id = %s
            """, [nuevo_estado, observaciones, request.session['usuario']['nombre'], piqueo_id])

        mensaje = f"Conteo {nuevo_estado.lower()} exitosamente"
        return JsonResponse({'success': True, 'message': mensaje})

    except Exception as e:
        print(f"❌ Error al {accion} conteo: {e}")
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})


def nuevo_conteo(request):
    # Verificar manualmente si el usuario está en sesión
    if 'usuario' not in request.session:
        return redirect('login')

    # Verificar si tiene perfil seleccionado
    perfil_completo = request.session.get('perfil_seleccionado', {})
    if not perfil_completo:
        return redirect('seleccionar_perfil')

    # Obtener el NOMBRE del perfil
    if isinstance(perfil_completo, dict):
        perfil_nombre = perfil_completo.get('nombre', 'Perfil no seleccionado')
    else:
        # Mapeo manual si es solo ID
        perfil_map = {
            '761': 'ADMINISTRATIVO',
            '762': 'JEFE DE TIENDA',
            '763': 'SUPERVISOR'
        }
        perfil_nombre = perfil_map.get(
            str(perfil_completo), f'Perfil {perfil_completo}')

    # VERIFICAR PERMISOS - Solo permitir ADMINISTRATIVO
    if perfil_nombre != "ADMINISTRATIVO":
        messages.error(request, 'No tiene permisos para crear nuevos conteos')
        return redirect('administracion_conteo')

    context = {
        'usuario': request.session['usuario'],
        'perfil': perfil_nombre,
    }

    return render(request, 'inventario/nuevo_conteo.html', context)

# AGREGAR ESTA VISTA DESPUÉS DE nuevo_conteo


@csrf_exempt
def nuevo_conteo_jefe(request):
    """
    Vista para crear nuevo conteo - Específica para JEFE DE TIENDA
    """
    # Verificar manualmente si el usuario está en sesión
    if 'usuario' not in request.session:
        return redirect('login')

    # Verificar si tiene perfil seleccionado
    perfil_completo = request.session.get('perfil_seleccionado', {})
    if not perfil_completo:
        return redirect('seleccionar_perfil')

    # Obtener el NOMBRE del perfil
    if isinstance(perfil_completo, dict):
        perfil_nombre = perfil_completo.get('nombre', 'Perfil no seleccionado')
    else:
        # Mapeo manual si es solo ID
        perfil_map = {
            '761': 'ADMINISTRATIVO',
            '762': 'JEFE DE TIENDA',
            '763': 'SUPERVISOR',
            'ADMIN_INV': 'ADMINISTRADOR DE INVENTARIO',
            'USER_BODEGA': 'USUARIO DE BODEGA'
        }
        perfil_nombre = perfil_map.get(
            str(perfil_completo), f'Perfil {perfil_completo}')

    # VERIFICAR PERMISOS - Solo permitir JEFE DE TIENDA
    if perfil_nombre != "JEFE DE TIENDA":
        messages.error(request, 'No tiene permisos para crear nuevos conteos')
        return redirect('administracion_conteo_jefe')

    # OBTENER DATOS DEL JEFE DEL WEB SERVICE
    datos_jefe = {}
    usuario_sesion = request.session.get('usuario', {})
    cedula_jefe = usuario_sesion.get('cedula', '')

    print(f"🔍 [NUEVO_CONTEO_JEFE] Cédula del jefe: {cedula_jefe}")

    if cedula_jefe:
        try:
            # Consumir web service para obtener datos del jefe
            url = 'https://ns.aseyco.com:444/MSWebServiceNomina/rest/service/getDatoTiendaColabroador'
            payload = {
                "cedula": cedula_jefe
            }
            headers = {
                'Content-Type': 'application/json'
            }

            response = requests.post(
                url, headers=headers, data=json.dumps(payload), timeout=10)
            response_data = response.json()

            print(
                f"📋 [NUEVO_CONTEO_JEFE] Respuesta completa del web service: {response_data}")

            if response_data and isinstance(response_data, list) and len(response_data) > 0:
                # Tomar el primer elemento del array
                datos_jefe = response_data[0]
                print(
                    f"✅ [NUEVO_CONTEO_JEFE] Datos del jefe encontrados: {datos_jefe}")

                # DEBUG: Imprimir todas las claves disponibles
                print("🔑 [NUEVO_CONTEO_JEFE] Claves disponibles en datos_jefe:")
                for key, value in datos_jefe.items():
                    print(f"   {key}: {value}")
            else:
                print(
                    "⚠️ [NUEVO_CONTEO_JEFE] No se encontraron datos del jefe en el web service")
                messages.warning(
                    request, 'No se encontraron datos de tienda asignada para su usuario')

        except Exception as e:
            print(
                f"❌ [NUEVO_CONTEO_JEFE] Error al obtener datos del jefe: {e}")
            messages.error(
                request, f'Error al obtener datos de tienda: {str(e)}')
    else:
        print("❌ [NUEVO_CONTEO_JEFE] No se encontró cédula en la sesión")

    context = {
        'usuario': request.session['usuario'],
        'perfil': perfil_nombre,
        'datos_jefe': datos_jefe,
        'cedula_jefe': cedula_jefe
    }

    return render(request, 'inventario/nuevo_conteo_jefe.html', context)
# AGREGAR ESTA FUNCIÓN PARA GUARDAR CONTEO DEL JEFE


@csrf_exempt
def guardar_conteo_jefe(request):
    """
    Vista para guardar conteo creado por JEFE DE TIENDA
    """
    # Verificar manualmente si el usuario está en sesión
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'message': 'No autenticado'})

    if request.method == 'POST':
        try:
            # Parsear los datos JSON del request
            data = json.loads(request.body)

            print("Datos recibidos para conteo jefe:", data)  # Debug

            # Validar que hay artículos
            detalles_data = data.get('detalles_articulos', [])
            if not detalles_data:
                return JsonResponse({
                    'success': False,
                    'message': 'Debe agregar al menos un artículo al conteo'
                })

            # Validar datos básicos del formulario
            form_data = {
                'pais': data.get('pais', '').strip(),
                'centro': data.get('centro', '').strip(),
                'almacen': data.get('almacen', '').strip(),
                'usuario_responsable': data.get('responsable', '').strip(),
                'fecha_inicio': data.get('fecha_inicio', '').strip(),
                'fecha_fin': data.get('fecha_fin', '').strip(),
                'centro_costo': data.get('centro_costo', '').strip(),
            }

            # Validaciones manuales
            errors = []
            if not form_data['pais']:
                errors.append('El campo PAÍS es obligatorio')
            if not form_data['centro']:
                errors.append('El campo CENTRO es obligatorio')
            if not form_data['almacen']:
                errors.append('El campo ALMACÉN es obligatorio')
            if not form_data['usuario_responsable']:
                errors.append('El campo RESPONSABLE es obligatorio')
            if not form_data['fecha_inicio']:
                errors.append('El campo FECHA INICIO es obligatorio')
            if not form_data['fecha_fin']:
                errors.append('El campo FECHA FIN es obligatorio')

            if errors:
                return JsonResponse({
                    'success': False,
                    'message': 'Errores de validación',
                    'errors': errors
                })

            # OBTENER USUARIO DE LA SESIÓN (JEFE)
            usuario_sesion = request.session.get('usuario', {})
            usuario_creacion = usuario_sesion.get(
                'nombre', 'Usuario no identificado')
            cedula_usuario = usuario_sesion.get('cedula', '')

            print(f"Jefe creando conteo: {usuario_creacion}")  # Debug

            # Usar transacción para asegurar consistencia
            with transaction.atomic():
                with connection.cursor() as cursor:
                    # Insertar en la tabla principal - MISMA ESTRUCTURA
                    cursor.execute("""
                        INSERT INTO INV_PIQUEOS_INVENTARIO_TBL (
                            centro, almacen, fecha_inicio, fecha_fin, usuario_responsable,
                            estado, centro_costo, nombre_conteo, fecha_creacion, usuario_creacion, pais
                        ) VALUES (
                            %s, %s, TO_DATE(%s, 'YYYY-MM-DD'), TO_DATE(%s, 'YYYY-MM-DD'), %s,
                            'PENDIENTE', %s, %s, SYSTIMESTAMP, %s, %s
                        )
                    """, [
                        form_data['centro'],
                        form_data['almacen'],
                        form_data['fecha_inicio'],
                        form_data['fecha_fin'],
                        form_data['usuario_responsable'],
                        form_data['centro_costo'],
                        f"Conteo {form_data['almacen']}-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                        usuario_creacion,
                        form_data['pais']
                    ])

                    # Obtener el ID del piqueo insertado
                    cursor.execute("SELECT sec_inv_piqueo.CURRVAL FROM DUAL")
                    piqueo_id = cursor.fetchone()[0]

                    # Debug
                    print(f"Piqueo guardado por jefe con ID: {piqueo_id}")

                    # Insertar los detalles - MISMA ESTRUCTURA
                    for detalle_data in detalles_data:
                        cursor.execute("""
                            INSERT INTO INV_DETALLE_PIQUEOS_INVENTARIOS_TBL (
                                piqueo_id, grupo_articulos, linea, marca, observaciones
                            ) VALUES (
                                %s, %s, %s, %s, %s
                            )
                        """, [
                            piqueo_id,
                            detalle_data.get('grupo_articulos', '') or '',
                            detalle_data.get('linea', '') or '',
                            detalle_data.get('marca', '') or '',
                            detalle_data.get('observaciones', '') or ''
                        ])
                        # Debug
                        print(f"Detalle guardado para piqueo {piqueo_id}")

            # Mensaje de éxito
            success_message = f'Conteo guardado exitosamente. ID: {piqueo_id}'
            print(success_message)

            return JsonResponse({
                'success': True,
                'message': success_message,
                'piqueo_id': piqueo_id,
                # URL para redirección a vista jefe
                'redirect_url': '/administracion-conteo-jefe/'
            })

        except Exception as e:
            print(f"Error general al guardar conteo jefe: {e}")  # Debug
            return JsonResponse({
                'success': False,
                'message': f'Error interno del servidor: {str(e)}'
            })

    return JsonResponse({
        'success': False,
        'message': 'Método no permitido'
    })


@csrf_exempt
def guardar_conteo(request):
    # Verificar manualmente si el usuario está en sesión
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'message': 'No autenticado'})

    if request.method == 'POST':
        try:
            # Parsear los datos JSON del request
            data = json.loads(request.body)

            print("Datos recibidos:", data)  # Debug

            # Validar que hay artículos
            detalles_data = data.get('detalles_articulos', [])
            if not detalles_data:
                return JsonResponse({
                    'success': False,
                    'message': 'Debe agregar al menos un artículo al conteo'
                })

            # Validar datos básicos del formulario
            form_data = {
                'pais': data.get('pais', '').strip(),
                'centro': data.get('centro', '').strip(),
                'almacen': data.get('almacen', '').strip(),
                'usuario_responsable': data.get('responsable', '').strip(),
                'fecha_inicio': data.get('fecha_inicio', '').strip(),
                'fecha_fin': data.get('fecha_fin', '').strip(),
                'centro_costo': data.get('centro_costo', '').strip(),
            }

            # Validaciones manuales
            errors = []
            if not form_data['pais']:
                errors.append('El campo PAÍS es obligatorio')
            if not form_data['centro']:
                errors.append('El campo CENTRO es obligatorio')
            if not form_data['almacen']:
                errors.append('El campo ALMACÉN es obligatorio')
            if not form_data['usuario_responsable']:
                errors.append('El campo RESPONSABLE es obligatorio')
            if not form_data['fecha_inicio']:
                errors.append('El campo FECHA INICIO es obligatorio')
            if not form_data['fecha_fin']:
                errors.append('El campo FECHA FIN es obligatorio')

            if errors:
                return JsonResponse({
                    'success': False,
                    'message': 'Errores de validación',
                    'errors': errors
                })

            # OBTENER USUARIO DE LA SESIÓN
            usuario_sesion = request.session.get('usuario', {})
            usuario_creacion = usuario_sesion.get(
                'nombre', 'Usuario no identificado')
            cedula_usuario = usuario_sesion.get('cedula', '')

            print(f"Usuario de sesión: {usuario_creacion}")  # Debug

            # Usar transacción para asegurar consistencia
            with transaction.atomic():
                with connection.cursor() as cursor:
                    # Insertar en la tabla principal
                    cursor.execute("""
                        INSERT INTO INV_PIQUEOS_INVENTARIO_TBL (
                            centro, almacen, fecha_inicio, fecha_fin, usuario_responsable,
                            estado, centro_costo, nombre_conteo, fecha_creacion, usuario_creacion, pais
                        ) VALUES (
                            %s, %s, TO_DATE(%s, 'YYYY-MM-DD'), TO_DATE(%s, 'YYYY-MM-DD'), %s,
                            'PENDIENTE', %s, %s, SYSTIMESTAMP, %s, %s
                        )
                    """, [
                        form_data['centro'],
                        form_data['almacen'],
                        form_data['fecha_inicio'],
                        form_data['fecha_fin'],
                        form_data['usuario_responsable'],
                        form_data['centro_costo'],
                        f"Conteo {form_data['almacen']}-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                        usuario_creacion,
                        form_data['pais']
                    ])

                    # Obtener el ID del piqueo insertado
                    cursor.execute("SELECT sec_inv_piqueo.CURRVAL FROM DUAL")
                    piqueo_id = cursor.fetchone()[0]

                    print(f"Piqueo guardado con ID: {piqueo_id}")  # Debug

                    # Insertar los detalles usando tu query específico
                    for detalle_data in detalles_data:
                        cursor.execute("""
                            INSERT INTO INV_DETALLE_PIQUEOS_INVENTARIOS_TBL (
                                piqueo_id, grupo_articulos, linea, marca, observaciones
                            ) VALUES (
                                %s, %s, %s, %s, %s
                            )
                        """, [
                            piqueo_id,
                            detalle_data.get('grupo_articulos', '') or '',
                            detalle_data.get('linea', '') or '',
                            detalle_data.get('marca', '') or '',
                            detalle_data.get('observaciones', '') or ''
                        ])
                        # Debug
                        print(f"Detalle guardado para piqueo {piqueo_id}")

            # Mensaje de éxito
            success_message = f'Conteo guardado exitosamente. ID: {piqueo_id}'
            print(success_message)

            return JsonResponse({
                'success': True,
                'message': success_message,
                'piqueo_id': piqueo_id,
                'redirect_url': '/administracion-conteo/'  # URL para redirección
            })

        except Exception as e:
            print(f"Error general al guardar conteo: {e}")  # Debug
            return JsonResponse({
                'success': False,
                'message': f'Error interno del servidor: {str(e)}'
            })

    return JsonResponse({
        'success': False,
        'message': 'Método no permitido'
    })

# AGREGAR ESTA FUNCIÓN AL FINAL DE views.py


@csrf_exempt
def detalle_conteo(request, piqueo_id):
    """
    Vista para obtener los detalles de un conteo específico
    """
    # Verificar autenticación
    if 'usuario' not in request.session:
        return JsonResponse({'error': 'No autenticado'}, status=401)

    # Solo permitir GET
    if request.method != 'GET':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    try:
        detalles = []
        info_conteo = {}
        colaboradores = []
        secuenciales = []

        with connection.cursor() as cursor:
            # Primero obtener información básica del conteo
            cursor.execute("""
                SELECT 
                    pi.piqueo_id,
                    pi.numero_conteo,
                    pi.pais,
                    pi.centro,
                    pi.almacen,
                    TO_CHAR(pi.fecha_inicio, 'YYYY-MM-DD'),
                    TO_CHAR(pi.fecha_fin, 'YYYY-MM-DD'),
                    pi.estado,
                    pi.usuario_creacion,
                    pi.ap_responsable,
                    pi.nm_responsable
                FROM view_planificacion_inventario pi
                WHERE pi.piqueo_id = %s
            """, [piqueo_id])

            conteo_info = cursor.fetchone()

            if not conteo_info:
                return JsonResponse({'error': 'Conteo no encontrado'}, status=404)

            info_conteo = {
                'id': conteo_info[0],
                'numero_conteo': conteo_info[1],
                'pais': conteo_info[2],
                'centro': conteo_info[3],
                'almacen': conteo_info[4],
                'fecha_inicio': conteo_info[5],
                'fecha_fin': conteo_info[6],
                'estado': conteo_info[7],
                'usuario_creacion': conteo_info[8],
                'responsable': f"{conteo_info[9]} {conteo_info[10]}".strip()
            }

            # Ahora obtener los detalles del conteo
            cursor.execute("""
                SELECT
                    detalle_piqueo_id,
                    piqueo_id,
                    grupo_articulos,
                    linea,
                    marca,
                    observaciones
                FROM
                    inv_detalle_piqueos_inventarios_tbl
                WHERE piqueo_id = %s
                ORDER BY detalle_piqueo_id
            """, [piqueo_id])

            resultados_detalle = cursor.fetchall()

            for row in resultados_detalle:
                detalle = {
                    'detalle_id': row[0] if row[0] else 0,
                    'piqueo_id': row[1] if row[1] else 0,
                    'grupo_articulos': row[2] if row[2] else 'N/A',
                    'linea': row[3] if row[3] else 'N/A',
                    'marca': row[4] if row[4] else 'N/A',
                    'observaciones': row[5] if row[5] else 'Sin observaciones'
                }
                detalles.append(detalle)

            print(
                f"✅ Detalles encontrados para piqueo {piqueo_id}: {len(detalles)} registros")
            # Colaboradores
            cursor.execute("""
                SELECT CEDULA, NOMBRES, CARGO, TIENDA
                FROM MS_INVENTARIOS.INV_PIQUEO_COLABORADORES_TBL
                WHERE PIQUEO_ID = %s
            """, [piqueo_id])
            colaboradores = [
                {
                    'cedula': row[0],
                    'nombre': row[1],
                    'cargo': row[2],
                    'tienda': row[3]
                }
                for row in cursor.fetchall()
            ]

            # Secuenciales (por cada detalle)
            cursor.execute("""
                SELECT s.DETALLE_PIQUEO_ID, s.SECUENCIAL_ID, s.UBICACION, s.SECUENCIA_HASTA, s.CODIGO
                FROM MS_INVENTARIOS.INV_PIQUEO_SECUENCIAL_TBL s
                WHERE s.DETALLE_PIQUEO_ID IN (
                    SELECT d.DETALLE_PIQUEO_ID 
                    FROM MS_INVENTARIOS.INV_DETALLE_PIQUEOS_INVENTARIOS_TBL d
                    WHERE d.PIQUEO_ID = %s
                )
                ORDER BY s.DETALLE_PIQUEO_ID, s.SECUENCIA_HASTA
            """, [piqueo_id])
            secuenciales = [
                {
                    'detalle_piqueo_id': row[0],
                    'secuencial_id': row[1],
                    'ubicacion': row[2],
                    'secuencia_hasta': row[3],
                    'codigo': row[4]
                }
                for row in cursor.fetchall()
            ]
        return JsonResponse({
            'success': True,
            'conteo': info_conteo,
            'detalles': detalles,
            'colaboradores': colaboradores,
            'secuenciales': secuenciales,
            'total_detalles': len(detalles)
        })

    except Exception as e:
        print(f"❌ Error al obtener detalles del conteo {piqueo_id}: {e}")
        return JsonResponse({
            'error': f'Error al obtener los detalles: {str(e)}'
        }, status=500)


@csrf_exempt
def eliminar_conteo(request, conteo_id):
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'message': 'No autenticado'}, status=401)
    perfil = request.session.get('perfil_seleccionado', {}).get('nombre', '')
    # Si usuario_creacion guarda el nombre
    usuario = request.session['usuario'].get('nombre', '')

    if perfil not in ["ADMINISTRATIVO", "JEFE DE TIENDA"]:
        return JsonResponse({'success': False, 'message': 'No tiene permisos'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)

    # Verificar permisos para jefe de tienda
    if perfil == "JEFE DE TIENDA":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT usuario_creacion FROM INV_PIQUEOS_INVENTARIO_TBL WHERE piqueo_id = %s", [conteo_id])
            row = cursor.fetchone()
            if not row or row[0] != usuario:
                return JsonResponse({'success': False, 'message': 'Solo puede eliminar sus propios conteos'}, status=403)

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM INV_PIQUEOS_INVENTARIO_TBL WHERE piqueo_id = %s", [conteo_id])
            cursor.execute(
                "DELETE FROM INV_DETALLE_PIQUEOS_INVENTARIOS_TBL WHERE piqueo_id = %s", [conteo_id])
        return JsonResponse({'success': True, 'message': 'Conteo eliminado correctamente'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'}, status=500)


@csrf_exempt
def gestion_conteos(request):
    if 'usuario' not in request.session:
        return redirect('login')

    perfil = request.session.get('perfil_seleccionado', {}).get('nombre', '')
    usuario_sesion = request.session.get('usuario', {})
    usuario_cedula = usuario_sesion.get('cedula', '')

    # OBTENER FILTROS (GET o POST/AJAX)
    filtros = {}
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            data = json.loads(request.body)
            filtros = data.get('filtros', {})
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Error en los datos de filtros'}, status=400)
    elif request.method == 'GET':
        filtros['estado'] = request.GET.get('estado', '').strip()
        filtros['centro'] = request.GET.get('centro', '').strip()
        filtros['almacen'] = request.GET.get('almacen', '').strip()

    with connection.cursor() as cursor:
        query = """
            SELECT piqueo_id, numero_conteo, estado, fecha_inicio, fecha_fin,
            nombre_empleado_func(usuario_responsable) as nm_responsable, 
            usuario_creacion, centro, almacen
            FROM INV_PIQUEOS_INVENTARIO_TBL
            WHERE usuario_responsable = %s
        """
        params = [usuario_cedula]

        # APLICAR FILTROS DINÁMICAMENTE
        if filtros.get('estado'):
            query += " AND UPPER(estado) = UPPER(%s)"
            params.append(filtros['estado'])

        if filtros.get('centro'):
            query += " AND centro = %s"
            params.append(filtros['centro'])

        if filtros.get('almacen'):
            query += " AND almacen = %s"
            params.append(filtros['almacen'])

        query += " ORDER BY fecha_inicio DESC"

        print(f"🔍 Query ejecutado: {query}")
        print(f"🔍 Parámetros: {params}")
        cursor.execute(query, params)
        rows = cursor.fetchall()

    conteos = [
        {
            'id': row[0],
            'numero_conteo': row[1],
            'estado': row[2],
            'fecha_inicio': row[3].strftime('%b. %d, %Y') if row[3] else '-',
            'fecha_fin': row[4].strftime('%b. %d, %Y') if row[4] else '-',
            'nm_responsable': row[5],
            'usuario_creacion': row[6],
            'centro': row[7],
            'almacen': row[8],
        }
        for row in rows
    ]

    estadisticas = {
        'total': len(conteos),
        'pendientes': sum(1 for c in conteos if c['estado'].upper() == 'PENDIENTE'),
        'en_proceso': sum(1 for c in conteos if c['estado'].upper() == 'EN_PROCESO'),
        'completados': sum(1 for c in conteos if c['estado'].upper() == 'COMPLETADO'),
    }

    # Si es petición AJAX, devolver JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'conteos': conteos,
            'estadisticas': estadisticas
        })

    context = {
        'usuario': request.session['usuario'],
        'perfil': perfil,
        'conteos': conteos,
        'estadisticas': estadisticas,
    }
    return render(request, 'inventario/gestion_conteos.html', context)


@csrf_exempt
def asigna_conteo_colaborador(request, piqueo_id):
    if 'usuario' not in request.session:
        return redirect('login')

    perfil = request.session.get('perfil_seleccionado', {}).get('nombre', '')
    usuario = request.session['usuario'].get('nombre', '')
    print(f"Buscando artículos para PIQUEO_ID: {piqueo_id}")
    # Procesa los artículos dentro del bloque 'with'
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT DETALLE_PIQUEO_ID, GRUPO_ARTICULOS, LINEA, MARCA, OBSERVACIONES
            FROM INV_DETALLE_PIQUEOS_INVENTARIOS_TBL
            WHERE PIQUEO_ID = %s
        """, [piqueo_id])
        articulos = [
            {
                'id': row[0],
                'grupo_articulos': row[1],
                'linea': row[2],
                'marca': row[3],
                'observaciones': row[4],
            }
            for row in cursor.fetchall()
        ]
        print(f"Artículos recuperados: {len(articulos)}")
        print(articulos)
    # Procesa el conteo principal dentro de otro bloque 'with'
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT numero_conteo, centro, almacen, fecha_inicio, fecha_fin
            FROM INV_PIQUEOS_INVENTARIO_TBL
            WHERE piqueo_id = %s
        """, [piqueo_id])
        conteo_row = cursor.fetchone()
        conteo = {}
        if conteo_row:
            conteo = {
                'numero_conteo': conteo_row[0],
                'centro': conteo_row[1],
                'almacen': conteo_row[2],
                'fecha_inicio': conteo_row[3],
                'fecha_fin': conteo_row[4],
            }

    context = {
        'usuario': request.session['usuario'],
        'perfil': perfil,
        'piqueo_id': piqueo_id,
        'conteo': conteo,
        'articulos': articulos,
    }
    return render(request, 'inventario/asigna_conteo_colaborador.html', context)


@csrf_exempt
def obtener_colaboradores(request):
    almacen = request.GET.get('almacen')
    if not almacen:
        return JsonResponse({'error': 'Falta el parámetro almacen'}, status=400)
    url = 'https://ns.aseyco.com:444/MSWebServiceNomina/rest/service/colaboradores'
    payload = {"mcu": almacen}
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.post(
            url, json=payload, headers=headers, verify=False)
        colaboradores = response.json()
        return JsonResponse(colaboradores, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def guardar_colaboradores(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            colaboradores = data.get('colaboradores', [])
            with connection.cursor() as cursor:
                for col in colaboradores:
                    print("Insertando colaborador:", [
                        col['idConteo'],
                        col['colaboradorId'],
                        col['nombre'],
                        col.get('cargo', ''),
                        col.get('tienda', '')
                    ])
                    cursor.execute("""
                        INSERT INTO MS_INVENTARIOS.INV_PIQUEO_COLABORADORES_TBL
                        (PIQUEO_ID, CEDULA, NOMBRES, CARGO, TIENDA)
                        VALUES (%s, %s, %s, %s, %s)
                    """, [
                        int(col['idConteo']),
                        col['colaboradorId'],
                        col['nombre'],
                        col.get('cargo', ''),
                        col.get('tienda', '')
                    ])
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': 'Método no permitido'})


@csrf_exempt
def validar_colaborador_disponible(request):
    if request.method == 'GET':
        cedula = request.GET.get('cedula')
        if not cedula:
            return JsonResponse({'error': 'Falta el parámetro cedula'}, status=400)
        
        try:
            with connection.cursor() as cursor:
                # Consulta proporcionada para verificar si el colaborador estÃ¡ en otro proceso activo
                cursor.execute("""
                    SELECT count(*) 
                    FROM inv_piqueos_inventario_tbl 
                    WHERE (estado = 'PENDIENTE' or estado = 'EN_PROCESO')
                    AND piqueo_id IN (
                        SELECT piqueo_id 
                        FROM MS_INVENTARIOS.inv_piqueo_colaboradores_tbl 
                        WHERE cedula = %s
                    )
                """, [cedula])
                
                count = cursor.fetchone()[0]
                
                if count > 0:
                    return JsonResponse({
                        'disponible': False, 
                        'message': 'El Colaborador se encuentra activo en otro proceso de inventario. Podrá ser asignado a este proceso una vez que el inventario anterior haya finalizado su primer conteo.'
                    })
                else:
                    return JsonResponse({'disponible': True})
                    
        except Exception as e:
            print(f"Error valdiando colaborador: {e}")
            return JsonResponse({'error': str(e)}, status=500)
            
    return JsonResponse({'error': 'Método no permitido'}, status=405)


def obtener_colaboradores_piqueo(request, piqueo_id):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT EMPLEADO_ID, CEDULA, NOMBRES, CARGO, TIENDA
            FROM MS_INVENTARIOS.INV_PIQUEO_COLABORADORES_TBL
            WHERE PIQUEO_ID = %s
        """, [piqueo_id])
        rows = cursor.fetchall()
        colaboradores = [
            {
                'empleado_id': row[0],
                'idConteo': piqueo_id,
                'colaboradorId': row[1],
                'nombre': row[2],
                'cargo': row[3],
                'tienda': row[4]
            }
            for row in rows
        ]
    return JsonResponse({'colaboradores': colaboradores})


@csrf_exempt
def eliminar_colaborador_piqueo(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            empleado_id = data.get('empleado_id')
            if not empleado_id:
                return JsonResponse({'success': False, 'message': 'ID no proporcionado'})
            with connection.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM MS_INVENTARIOS.INV_PIQUEO_COLABORADORES_TBL
                    WHERE EMPLEADO_ID = %s
                """, [empleado_id])
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': 'Método no permitido'})


def obtener_secuenciales(request, detalle_piqueo_id):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT SECUENCIAL_ID, UBICACION, SECUENCIA_HASTA, CODIGO
            FROM MS_INVENTARIOS.INV_PIQUEO_SECUENCIAL_TBL
            WHERE DETALLE_PIQUEO_ID = %s
        """, [detalle_piqueo_id])
        rows = cursor.fetchall()
        secuenciales = [
            {
                'secuencial_id': row[0],
                'ubicacion': row[1],
                'secuencia_hasta': row[2],
                'codigo': row[3]
            }
            for row in rows
        ]
    return JsonResponse({'secuenciales': secuenciales})

@csrf_exempt
def obtener_secuenciales_activos(request, detalle_piqueo_id):
    """Obtener solo los secuenciales ACTIVOS para un detalle específico"""
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT SECUENCIAL_DETA_ID, UBICACION, SECUENCIA, CODIGO, ESTADO
                FROM MS_INVENTARIOS.INV_PIQUEO_SECUENCIAL_DETA_TBL
                WHERE DETALLE_PIQUEO_ID = %s
                AND ESTADO = 'ACTIVO'
                ORDER BY SECUENCIA
            """, [detalle_piqueo_id])
            
            # Convertir resultados a lista de diccionarios
            columns = [col[0].lower() for col in cursor.description]
            rows = cursor.fetchall()
            secuenciales = [dict(zip(columns, row)) for row in rows]
        
        return JsonResponse({
            'success': True,
            'secuenciales': secuenciales,
            'total': len(secuenciales)
        })
        
    except Exception as e:
        return JsonResponse({
            'error': str(e),
            'success': False
        }, status=500)

@csrf_exempt
def guardar_secuenciales(request):
    if request.method == 'POST':
        import json
        try:
            data = json.loads(request.body)
            secuenciales = data.get('secuenciales', [])
            detalle_piqueo_id = None
            with connection.cursor() as cursor:
                for sec in secuenciales:
                    detalle_piqueo_id = int(sec['detalle_piqueo_id'])

                    cursor.execute("""
                        INSERT INTO MS_INVENTARIOS.INV_PIQUEO_SECUENCIAL_TBL
                        (DETALLE_PIQUEO_ID, UBICACION, SECUENCIA_HASTA)
                        VALUES (%s, %s, %s)
                    """, [
                        int(sec['detalle_piqueo_id']),
                        sec['ubicacion'],
                        int(sec['secuencia_hasta'])
                    ])

                # ✅ Llamar al procedimiento DENTRO del bloque with cursor
                if detalle_piqueo_id:
                    cursor.callproc('AGREGAR_NUEVOS_SECUENCIALES', [detalle_piqueo_id])

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': 'Método no permitido'})


@csrf_exempt
def actualizar_secuencia_hasta(request):
    """
    Vista para actualizar el campo secuencia_hasta en INV_PIQUEO_SECUENCIAL_TBL
    """
    # Verificar autenticación
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'message': 'No autenticado'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        secuencial_id = data.get('secuencial_id')
        nueva_secuencia = data.get('secuencia_hasta')

        print(
            f"🔧 Actualizando secuencia - Secuencial ID: {secuencial_id}, Nueva secuencia: {nueva_secuencia}")

        # Validar datos
        if not secuencial_id or nueva_secuencia is None:
            return JsonResponse({
                'success': False,
                'message': 'Datos incompletos: se requiere secuencial_id y secuencia_hasta'
            })

        # Validar que sea un número válido
        try:
            nueva_secuencia = int(nueva_secuencia)
            if nueva_secuencia < 0:
                raise ValueError("La secuencia no puede ser negativa")
        except ValueError:
            return JsonResponse({
                'success': False,
                'message': 'La secuencia debe ser un número válido'
            })

        with connection.cursor() as cursor:
            # OBTENER DATOS PARA VALIDACIÓN
            cursor.execute("""
                SELECT 
                    ips.SECUENCIA_HASTA,
                    ips.DETALLE_PIQUEO_ID,
                    (SELECT MAX(ips2.SECUENCIA_HASTA) 
                     FROM MS_INVENTARIOS.INV_PIQUEO_SECUENCIAL_TBL ips2 
                     WHERE ips2.DETALLE_PIQUEO_ID = ips.DETALLE_PIQUEO_ID 
                     AND ips2.SECUENCIA_HASTA < ips.SECUENCIA_HASTA) as SECUENCIA_ANTERIOR
                FROM MS_INVENTARIOS.INV_PIQUEO_SECUENCIAL_TBL ips
                WHERE ips.SECUENCIAL_ID = %s
            """, [secuencial_id])

            resultado = cursor.fetchone()

            if not resultado:
                return JsonResponse({
                    'success': False,
                    'message': 'No se encontró el secuencial especificado'
                })

            secuencia_actual, detalle_piqueo_id, secuencia_anterior = resultado
            secuencia_anterior = secuencia_anterior or 0  # Si es None, usar 0

            print(
                f"🔍 Datos validación - Actual: {secuencia_actual}, Anterior: {secuencia_anterior}, Nueva: {nueva_secuencia}")

            # VALIDACIÓN 1: No puede ser mayor al valor actual (solo disminuir)
            if nueva_secuencia > secuencia_actual:
                return JsonResponse({
                    'success': False,
                    'message': f'Error: El valor no puede ser mayor a {secuencia_actual} (solo se permite disminuir)'
                })

            # VALIDACIÓN 2: Debe ser mayor al registro anterior
            if nueva_secuencia <= secuencia_anterior:
                return JsonResponse({
                    'success': False,
                    'message': f'Error: El valor debe ser mayor a {secuencia_anterior}'
                })

            # Verificar si existe el registro específico
            cursor.execute("""
                SELECT COUNT(*) FROM MS_INVENTARIOS.INV_PIQUEO_SECUENCIAL_TBL 
                WHERE SECUENCIAL_ID = %s
            """, [secuencial_id])

            existe = cursor.fetchone()[0] > 0

            if not existe:
                return JsonResponse({
                    'success': False,
                    'message': 'No se encontró el secuencial especificado'
                })

            # Actualizar SOLO el registro específico usando SECUENCIAL_ID
            cursor.execute("""
                UPDATE MS_INVENTARIOS.INV_PIQUEO_SECUENCIAL_TBL 
                SET SECUENCIA_HASTA = %s
                WHERE SECUENCIAL_ID = %s
            """, [nueva_secuencia, secuencial_id])

            # Verificar si se actualizó correctamente
            if cursor.rowcount > 0:
                print(
                    f"✅ Secuencia actualizada exitosamente para secuencial_id: {secuencial_id}")

                if detalle_piqueo_id:
                    try:
                        cursor.callproc('AGREGAR_NUEVOS_SECUENCIALES', [
                                        detalle_piqueo_id])
                        print(
                            f"🔧 Procedimiento AGREGAR_NUEVOS_SECUENCIALES ejecutado para detalle: {detalle_piqueo_id}")
                    except Exception as proc_error:
                        print(
                            f"⚠️ Error al ejecutar procedimiento (puede ser normal): {proc_error}")

                return JsonResponse({
                    'success': True,
                    'message': 'Secuencia actualizada correctamente'
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'No se pudo actualizar la secuencia'
                })

    except Exception as e:
        print(f"❌ Error al actualizar secuencia: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error interno del servidor: {str(e)}'
        })


@csrf_exempt
def eliminar_secuencial(request):
    if request.method == 'POST':
        import json
        try:
            data = json.loads(request.body)
            secuencial_id = data.get('secuencial_id')
            if not secuencial_id:
                return JsonResponse({'success': False, 'message': 'ID no proporcionado'})
            with connection.cursor() as cursor:
                # Obtener el detalle_piqueo_id antes de eliminar
                cursor.execute("""
                    SELECT DETALLE_PIQUEO_ID FROM MS_INVENTARIOS.INV_PIQUEO_SECUENCIAL_TBL
                    WHERE SECUENCIAL_ID = %s
                """, [secuencial_id])
                row = cursor.fetchone()
                detalle_piqueo_id = row[0] if row else None

                # Eliminar el secuencial
                cursor.execute("""
                    DELETE FROM MS_INVENTARIOS.INV_PIQUEO_SECUENCIAL_TBL
                    WHERE SECUENCIAL_ID = %s
                """, [secuencial_id])

                # Ejecutar el SP si se obtuvo el detalle_piqueo_id
                if detalle_piqueo_id:
                    cursor.callproc('REGENERAR_SECUENCIAS_DETALLE', [
                                    detalle_piqueo_id])

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': 'Método no permitido'})


def imprimir_zonas_pdf(request, detalle_piqueo_id):
    from io import BytesIO
    from reportlab.lib.units import mm
    buffer = BytesIO()

    # Configurar para ticket POS (80mm de ancho, alto variable)
    ticket_width = 80 * mm
    ticket_height = 120 * mm  # Alto estimado por etiqueta
    margin = 5 * mm
    content_width = ticket_width - (2 * margin)

    p = canvas.Canvas(buffer, pagesize=(ticket_width, ticket_height))

    # MODIFICADO: Consulta SOLO los secuenciales ACTIVOS
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT DETALLE_PIQUEO_ID, UBICACION, SECUENCIA, CODIGO, ESTADO
            FROM MS_INVENTARIOS.INV_PIQUEO_SECUENCIAL_DETA_TBL
            WHERE DETALLE_PIQUEO_ID = %s
            AND ESTADO = 'ACTIVO'  -- FILTRAR SOLO ACTIVOS
            ORDER BY SECUENCIA
        """, [detalle_piqueo_id])
        rows = cursor.fetchall()

    # VERIFICAR si hay secuenciales activos
    if not rows:
        p.setFont("Helvetica-Bold", 8)
        p.drawString(margin, ticket_height / 2, "No hay secuenciales ACTIVOS")
        p.showPage()
        p.save()
        buffer.seek(0)
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="etiquetas_{detalle_piqueo_id}.pdf"'
        return response

    for idx, row in enumerate(rows):
        detalle_piqueo_id = row[0]
        ubicacion = row[1]
        secuencia = row[2]
        codigo = row[3]
        estado = row[4]

        if estado != 'ACTIVO':
            continue

        y = ticket_height - margin

        # Ubicación y Secuencia en la misma línea
        p.setFont("Helvetica-Bold", 9)
        p.drawString(margin, y - 10, f"Ubicación: {ubicacion}")
        p.drawString(margin, y - 22, f"Secuencia: {secuencia}")

        # Líneas para llenar a mano
        p.setFont("Helvetica", 8)
        y_field = y - 38
        fields = ["Total conteo:", "Total recibidos:", "Responsable conteo:"]
        for field in fields:
            p.drawString(margin, y_field, field)
            label_w = p.stringWidth(field, "Helvetica", 8) + 3
            p.line(margin + label_w, y_field - 1, margin + content_width, y_field - 1)
            y_field -= 14

        # CÓDIGO DE BARRAS centrado
        try:
            from reportlab.graphics.barcode import code128

            bar_height = 25 * mm
            bar_width = 0.8

            barcode = code128.Code128(
                str(codigo), barHeight=bar_height, barWidth=bar_width)
            barcode_w = barcode.width

            # Ajustar si es más ancho que el ticket
            if barcode_w > content_width:
                bar_width = bar_width * (content_width / barcode_w) * 0.95
                barcode = code128.Code128(
                    str(codigo), barHeight=bar_height, barWidth=bar_width)
                barcode_w = barcode.width

            barcode_x = margin + (content_width - barcode_w) / 2
            barcode_y = y_field - bar_height - 4
            barcode.drawOn(p, barcode_x, barcode_y)

            # Texto del código centrado debajo
            p.setFont("Helvetica-Bold", 8)
            text_w = p.stringWidth(str(codigo), "Helvetica-Bold", 8)
            text_x = margin + (content_width - text_w) / 2
            p.drawString(text_x, barcode_y - 10, str(codigo))

        except Exception as e:
            print(f"Error generando código de barras: {e}")
            p.setFont("Helvetica-Bold", 10)
            p.drawString(margin, y_field - 20, f"COD: {str(codigo)}")

        p.showPage()

        # Actualizar estado
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE MS_INVENTARIOS.INV_PIQUEOS_INVENTARIO_TBL
                SET ESTADO = 'EN_PROCESO'
                WHERE PIQUEO_ID IN (
                    SELECT PIQUEO_ID
                    FROM MS_INVENTARIOS.INV_DETALLE_PIQUEOS_INVENTARIOS_TBL
                    WHERE DETALLE_PIQUEO_ID = %s
                )
            """, [detalle_piqueo_id])

    p.save()
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="etiquetas_{detalle_piqueo_id}.pdf"'
    return response


def _codigo_barras_svg(codigo):
    """Genera un SVG inline de un barcode CODE128 dimensionado para ticket POS (80mm).
    Las quiet zones (márgenes blancos) son OBLIGATORIAS para que el scanner pueda leer."""
    import re as _re
    from io import StringIO
    from reportlab.graphics.barcode import createBarcodeDrawing
    from reportlab.graphics import renderSVG
    from reportlab.lib.units import mm

    # barWidth=1.2 mínimo recomendado para impresoras térmicas TM-T20
    # quiet=True mantiene las quiet zones obligatorias para lectura de scanner
    drawing = createBarcodeDrawing('Code128', value=str(codigo),
                                   barHeight=22 * mm, barWidth=1.2,
                                   quiet=True)
    buf = StringIO()
    renderSVG.drawToFile(drawing, buf)
    svg_str = buf.getvalue()
    start = svg_str.find('<svg')
    svg_str = svg_str[start:] if start != -1 else svg_str

    # Extraer width/height originales y forzar viewBox para escalado proporcional
    w_match = _re.search(r'width="([^"]+)"', svg_str)
    h_match = _re.search(r'height="([^"]+)"', svg_str)
    if w_match and h_match:
        w_val = w_match.group(1)
        h_val = h_match.group(1)
        if 'viewBox' not in svg_str:
            svg_str = svg_str.replace('<svg ',
                f'<svg viewBox="0 0 {w_val} {h_val}" preserveAspectRatio="xMidYMid meet" ', 1)
        svg_str = _re.sub(r'width="[^"]+"', 'width="100%"', svg_str, count=1)
        svg_str = _re.sub(r'height="[^"]+"', 'height="auto"', svg_str, count=1)

    return svg_str


def imprimir_zonas_print(request, detalle_piqueo_id):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT DETALLE_PIQUEO_ID, UBICACION, SECUENCIA, CODIGO, ESTADO
            FROM MS_INVENTARIOS.INV_PIQUEO_SECUENCIAL_DETA_TBL
            WHERE DETALLE_PIQUEO_ID = %s
            AND ESTADO = 'ACTIVO'
            ORDER BY SECUENCIA
        """, [detalle_piqueo_id])
        rows = cursor.fetchall()

    if not rows:
        return HttpResponse("""<!DOCTYPE html><html><head><meta charset="UTF-8">
            <title>Sin secuenciales</title></head><body>
            <p style="font-family:Helvetica;font-size:14pt;padding:40px;">
              No hay secuenciales ACTIVOS para imprimir.
            </p>
            <script>setTimeout(function(){window.close();},3000);</script>
            </body></html>""")

    secuenciales = []
    for row in rows:
        if row[4] != 'ACTIVO':
            continue
        secuenciales.append({
            'ubicacion': str(row[1]),
            'secuencia': row[2],
            'codigo': str(row[3]),
            'barcode_svg': _codigo_barras_svg(str(row[3])),
        })

    with connection.cursor() as cursor:
        cursor.execute("""
            UPDATE MS_INVENTARIOS.INV_PIQUEOS_INVENTARIO_TBL
            SET ESTADO = 'EN_PROCESO'
            WHERE PIQUEO_ID IN (
                SELECT PIQUEO_ID
                FROM MS_INVENTARIOS.INV_DETALLE_PIQUEOS_INVENTARIOS_TBL
                WHERE DETALLE_PIQUEO_ID = %s
            )
        """, [detalle_piqueo_id])

    pdf_url = request.build_absolute_uri(
        '/imprimir-zonas-pdf/{}/'.format(detalle_piqueo_id)
    )

    context = {
        'secuenciales': secuenciales,
        'pdf_url': pdf_url,
        'queue_mode': request.GET.get('queue') == '1',
        'queue_next_url': '',
        'queue_progress_text': '',
    }
    return render(request, 'inventario/imprimir_zonas.html', context)


def imprimir_zona_secuencia_print(request, secuencial_deta_id):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT DETALLE_PIQUEO_ID, UBICACION, SECUENCIA, CODIGO, ESTADO
            FROM MS_INVENTARIOS.INV_PIQUEO_SECUENCIAL_DETA_TBL
            WHERE SECUENCIAL_DETA_ID = %s
            AND ESTADO = 'ACTIVO'
        """, [secuencial_deta_id])
        row = cursor.fetchone()

    if not row:
        return HttpResponse("""<!DOCTYPE html><html><head><meta charset="UTF-8">
            <title>Sin secuencia</title></head><body>
            <p style="font-family:Helvetica;font-size:14pt;padding:40px;">
              La secuencia solicitada no est\u00e1 activa o no existe.
            </p>
            <script>setTimeout(function(){window.close();},3000);</script>
            </body></html>""")

    detalle_piqueo_id = row[0]
    secuenciales = [{
        'ubicacion': str(row[1]),
        'secuencia': row[2],
        'codigo': str(row[3]),
        'barcode_svg': _codigo_barras_svg(str(row[3])),
    }]

    with connection.cursor() as cursor:
        cursor.execute("""
            UPDATE MS_INVENTARIOS.INV_PIQUEOS_INVENTARIO_TBL
            SET ESTADO = 'EN_PROCESO'
            WHERE PIQUEO_ID IN (
                SELECT PIQUEO_ID
                FROM MS_INVENTARIOS.INV_DETALLE_PIQUEOS_INVENTARIOS_TBL
                WHERE DETALLE_PIQUEO_ID = %s
            )
        """, [detalle_piqueo_id])

    queue_mode = request.GET.get('queue') == '1'
    queue_next_url = ''
    queue_progress_text = ''

    if queue_mode:
        ids_param = request.GET.get('ids', '')
        current_index = request.GET.get('index', '0')

        try:
            index_value = int(current_index)
        except ValueError:
            index_value = 0

        queue_ids = []
        for raw_id in ids_param.split(','):
            raw_id = raw_id.strip()
            if not raw_id:
                continue
            try:
                queue_ids.append(int(raw_id))
            except ValueError:
                continue

        total_queue = len(queue_ids)
        if total_queue > 0:
            queue_progress_text = f"Ticket {index_value + 1} de {total_queue}"

        next_index = index_value + 1
        if next_index < total_queue:
            next_id = queue_ids[next_index]
            queue_next_url = (
                f"/imprimir-zona-secuencia/{next_id}/?queue=1"
                f"&ids={ids_param}&index={next_index}"
            )

    context = {
        'secuenciales': secuenciales,
        'pdf_url': request.build_absolute_uri(
            '/imprimir-zonas-pdf/{}/'.format(detalle_piqueo_id)
        ),
        'queue_mode': queue_mode,
        'queue_next_url': queue_next_url,
        'queue_progress_text': queue_progress_text,
    }
    return render(request, 'inventario/imprimir_zonas.html', context)


def imprimir_zonas_cola(request):
    ids_param = request.GET.get('ids', '')
    secuencial_ids = []

    for raw_id in ids_param.split(','):
        raw_id = raw_id.strip()
        if not raw_id:
            continue
        try:
            secuencial_ids.append(int(raw_id))
        except ValueError:
            continue

    context = {
        'secuencial_ids_json': json.dumps(secuencial_ids),
        'total_secuencias': len(secuencial_ids),
    }
    return render(request, 'inventario/imprimir_zonas_cola.html', context)


@csrf_exempt
def primer_conteo(request):
    """
    Vista para la pantalla Primer Conteo - Igual acceso que Gestión de Conteos
    pero con funcionalidad específica para mostrar detalles de piqueo y códigos de barras
    """
    if 'usuario' not in request.session:
        return redirect('login')

    perfil = request.session.get('perfil_seleccionado', {}).get('nombre', '')
    usuario_sesion = request.session.get('usuario', {})
    usuario_cedula = usuario_sesion.get('cedula', '')

    # OBTENER FILTROS (GET o POST/AJAX)
    filtros = {}
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            data = json.loads(request.body)
            filtros = data.get('filtros', {})
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Error en los datos de filtros'}, status=400)
    elif request.method == 'GET':
        filtros['estado'] = request.GET.get('estado', '').strip()
        filtros['centro'] = request.GET.get('centro', '').strip()
        filtros['almacen'] = request.GET.get('almacen', '').strip()

    with connection.cursor() as cursor:
        query = """
            SELECT piqueo_id, numero_conteo, estado, fecha_inicio, fecha_fin,
            nombre_empleado_func(usuario_responsable) as nm_responsable, 
            usuario_creacion, centro, almacen
            FROM INV_PIQUEOS_INVENTARIO_TBL
            WHERE usuario_responsable = %s
        """
        params = [usuario_cedula]

        # APLICAR FILTROS DINÁMICAMENTE
        if filtros.get('estado'):
            query += " AND UPPER(estado) = UPPER(%s)"
            params.append(filtros['estado'])

        if filtros.get('centro'):
            query += " AND centro = %s"
            params.append(filtros['centro'])

        if filtros.get('almacen'):
            query += " AND almacen = %s"
            params.append(filtros['almacen'])

        query += " ORDER BY fecha_inicio DESC"

        print(f"🔍 Query ejecutado: {query}")
        print(f"🔍 Parámetros: {params}")
        cursor.execute(query, params)
        rows = cursor.fetchall()

    conteos = [
        {
            'id': row[0],
            'numero_conteo': row[1],
            'estado': row[2],
            'fecha_inicio': row[3].strftime('%b. %d, %Y') if row[3] else '-',
            'fecha_fin': row[4].strftime('%b. %d, %Y') if row[4] else '-',
            'nm_responsable': row[5],
            'usuario_creacion': row[6],
            'centro': row[7],
            'almacen': row[8],
        }
        for row in rows
    ]

    estadisticas = {
        'total': len(conteos),
        'pendientes': sum(1 for c in conteos if c['estado'].upper() == 'PENDIENTE'),
        'en_proceso': sum(1 for c in conteos if c['estado'].upper() == 'EN_PROCESO'),
        'completados': sum(1 for c in conteos if c['estado'].upper() == 'COMPLETADO'),
    }

    # Si es petición AJAX, devolver JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'conteos': conteos,
            'estadisticas': estadisticas
        })

    context = {
        'usuario': request.session['usuario'],
        'perfil': perfil,
        'conteos': conteos,
        'estadisticas': estadisticas,
    }
    return render(request, 'inventario/primer_conteo.html', context)


@csrf_exempt
def obtener_detalle_piqueo(request, piqueo_id):
    """
    Vista para obtener detalles de piqueo con información secuencial
    Consulta: select a.detalle_piqueo_id,a.grupo_articulos,a.linea,a.marca,a.observaciones, 
              b.ubicacion,b.codigo
              from inv_detalle_piqueos_inventarios_tbl a, inv_piqueo_secuencial_tbl b
              where a.detalle_piqueo_id = b.detalle_piqueo_id and a.piqueo_id = piqueo_id
    """
    if 'usuario' not in request.session:
        return JsonResponse({'error': 'No autenticado'}, status=401)

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT a.detalle_piqueo_id, a.grupo_articulos, a.linea, a.marca, 
                       a.observaciones, b.ubicacion, b.codigo
                FROM inv_detalle_piqueos_inventarios_tbl a, inv_piqueo_secuencial_tbl b
                WHERE a.detalle_piqueo_id = b.detalle_piqueo_id 
                AND a.piqueo_id = %s
                ORDER BY a.detalle_piqueo_id
            """, [piqueo_id])

            rows = cursor.fetchall()

            detalles = [
                {
                    'detalle_piqueo_id': row[0],
                    'grupo_articulos': row[1],
                    'linea': row[2],
                    'marca': row[3],
                    'observaciones': row[4],
                    'ubicacion': row[5],
                    'codigo': row[6]
                }
                for row in rows
            ]

        return JsonResponse({
            'success': True,
            'detalles': detalles,
            'total': len(detalles)
        })

    except Exception as e:
        print(f"❌ Error al obtener detalles de piqueo {piqueo_id}: {e}")
        return JsonResponse({
            'error': f'Error al obtener los detalles: {str(e)}'
        }, status=500)


@csrf_exempt
def obtener_codigos_barras(request, codigo):
    """
    Vista para obtener códigos de barras escaneados
    Consulta: select count(codigo_barras) as conteo,codigo_barras,codigo_sap,descripcion,estado as estado_EAN
              from barcodes_escaneo_tbl 
              where sesion_id in(select sesion_id 
                                 from sesiones_escaneo_tbl 
                                 where section_name = 'codigo_param'
                                 and proceso_id in (select proceso_id 
                                                   from procesos_escaneo_tbl 
                                                   where estado = 'RECIBIDO'))
              group by codigo_barras,codigo_sap,descripcion,estado
    """
    if 'usuario' not in request.session:
        return JsonResponse({'error': 'No autenticado'}, status=401)

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(codigo_barras) as conteo, codigo_barras, codigo_sap, 
                       descripcion, estado as estado_EAN
                FROM barcodes_escaneo_tbl 
                WHERE sesion_id IN (
                    SELECT sesion_id 
                    FROM sesiones_escaneo_tbl 
                    WHERE section_name = %s
                    AND proceso_id IN (
                        SELECT proceso_id 
                        FROM procesos_escaneo_tbl 
                        WHERE estado = 'RECIBIDO'
                    )
                )
                GROUP BY codigo_barras, codigo_sap, descripcion, estado
                ORDER BY codigo_barras
            """, [codigo])

            rows = cursor.fetchall()

            codigos = [
                {
                    'conteo': row[0],
                    'codigo_barras': row[1],
                    'codigo_sap': row[2],
                    'descripcion': row[3],
                    'estado_EAN': row[4]
                }
                for row in rows
            ]

        return JsonResponse({
            'success': True,
            'codigos': codigos,
            'total': len(codigos)
        })

    except Exception as e:
        print(f"❌ Error al obtener códigos de barras para {codigo}: {e}")
        return JsonResponse({
            'error': f'Error al obtener códigos de barras: {str(e)}'
        }, status=500)


@csrf_exempt
def eliminar_codigo_barras(request):
    """
    Vista para eliminar código de barras específico
    Query: delete from barcodes_escaneo_tbl where codigo_barras = codigo_param
    """
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'message': 'No autenticado'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        codigo_barras = data.get('codigo_barras')

        if not codigo_barras:
            return JsonResponse({
                'success': False,
                'message': 'Código de barras requerido'
            })

        with connection.cursor() as cursor:
            cursor.execute("""
                DELETE FROM barcodes_escaneo_tbl 
                WHERE codigo_barras = %s
            """, [codigo_barras])

            filas_afectadas = cursor.rowcount

        if filas_afectadas > 0:
            return JsonResponse({
                'success': True,
                'message': f'Código de barras {codigo_barras} eliminado correctamente',
                'filas_eliminadas': filas_afectadas
            })
        else:
            return JsonResponse({
                'success': False,
                'message': f'No se encontró el código de barras {codigo_barras}'
            })

    except Exception as e:
        print(f"❌ Error al eliminar código de barras: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error al eliminar código de barras: {str(e)}'
        }, status=500)


@csrf_exempt
def obtener_detalle_piqueo_primer_conteo(request):
    """
    Vista específica para Primer Conteo - Obtener detalle del piqueo
    """
    if 'usuario' not in request.session:
        return JsonResponse({'error': 'No autenticado'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        piqueo_id = data.get('piqueo_id')

        if not piqueo_id:
            return JsonResponse({'error': 'piqueo_id requerido'}, status=400)

        print(f"🔍 Buscando detalles para piqueo_id: {piqueo_id}")

        with connection.cursor() as cursor:
            # ⭐ MODIFICADO: Filtrar solo secuenciales con estado ACTIVO
            # Acepta filtros opcionales: ubicacion, codigo
            ubicacion = data.get('ubicacion', '')
            codigo = data.get('codigo', '')

            base_query = """
                SELECT DISTINCT
                    a.detalle_piqueo_id,
                    a.grupo_articulos,
                    a.linea,
                    a.marca,
                    a.observaciones,
                    b.ubicacion,
                    c.codigo,
                    c.secuencia,
                    verificar_escaneos_func(c.codigo) as errores
                FROM inv_detalle_piqueos_inventarios_tbl a
                LEFT JOIN inv_piqueo_secuencial_tbl b ON a.detalle_piqueo_id = b.detalle_piqueo_id
                LEFT JOIN inv_piqueo_secuencial_deta_tbl c ON b.secuencial_id = c.secuencial_id
                WHERE a.piqueo_id = %s
                AND (c.estado = 'ACTIVO' OR c.estado IS NULL)
            """

            params = [piqueo_id]

            if ubicacion:
                base_query += " AND UPPER(b.ubicacion) LIKE UPPER(%s)"
                params.append(f"%{ubicacion}%")

            if codigo:
                base_query += " AND UPPER(c.codigo) LIKE UPPER(%s)"
                params.append(f"%{codigo}%")

            base_query += " ORDER BY b.ubicacion NULLS LAST, c.secuencia NULLS LAST"

            print(f"📝 Query (con filtros): {base_query}")
            print(f"📝 Parámetros: {params}")

            cursor.execute(base_query, params)
            rows = cursor.fetchall()

            print(f"📊 Filas encontradas (con filtros): {len(rows)}")

            detalles = []
            if rows:
                print(f"✅ Primera fila: {rows[0]}")

                detalles = [
                    {
                        'detalle_piqueo_id': row[0],
                        'grupo_articulos': row[1] or 'N/A',
                        'linea': row[2] or 'N/A',
                        'marca': row[3] or 'N/A',
                        'observaciones': row[4] or 'Sin observaciones',
                        'ubicacion': row[5] or 'N/A',
                        'codigo': row[6] or 'N/A',
                        'secuencia': row[7] or 'N/A',
                        'estado_validacion': str(row[8]).upper() if row[8] else 'ERROR'
                    }
                    for row in rows
                ]

                print(f"📊 Detalles procesados (solo ACTIVOS): {len(detalles)}")

        return JsonResponse({
            'success': True,
            'detalles': detalles,
            'total': len(detalles)
        })

    except Exception as e:
        print(f"❌ Error al obtener detalles de piqueo {piqueo_id}: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': f'Error al obtener los detalles: {str(e)}'
        }, status=500)


@csrf_exempt
def obtener_barcodes_escaneo_primer_conteo(request):
    """
    Vista específica para Primer Conteo - Obtener códigos de barras escaneados
    """
    if 'usuario' not in request.session:
        return JsonResponse({'error': 'No autenticado'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        section_name = data.get('section_name', '464mostrador1')
        codigo_filter = (data.get('codigo_filter') or '').strip()

        print(
            f"🔍 Buscando códigos de barras para section_name: {section_name}")

        with connection.cursor() as cursor:
            # Primero verificamos si existen datos en las tablas
            cursor.execute("""
                SELECT COUNT(*) 
                FROM sesiones_escaneo_tbl 
                WHERE section_name = %s
            """, [section_name])

            count_sesiones = cursor.fetchone()[0]
            print(
                f"📊 Sesiones encontradas con section_name '{section_name}': {count_sesiones}")

            # Si no hay sesiones con ese nombre exacto, buscar LIKE (CORREGIDO PARA ORACLE)
            if count_sesiones == 0:
                cursor.execute("""
                    SELECT DISTINCT section_name 
                    FROM sesiones_escaneo_tbl 
                    WHERE section_name LIKE %s
                    AND ROWNUM <= 5
                """, [f'%{section_name}%'])

                similar_sections = cursor.fetchall()
                print(f"📋 Secciones similares encontradas: {similar_sections}")

            # Query principal (acepta filtro por código de barras)
            base_query = """
                SELECT 
                    COUNT(a.codigo_barras) as conteo,
                    a.codigo_barras,
                    a.codigo_sap,
                    a.descripcion,
                    a.estado as estado_EAN,
                    b.cedula
                FROM barcodes_escaneo_tbl a 
                INNER JOIN sesiones_escaneo_tbl b ON a.sesion_id = b.sesion_id 
                WHERE b.section_name = %s
                    AND b.proceso_id IN (
                        SELECT proceso_id 
                        FROM procesos_escaneo_tbl 
                        WHERE UPPER(estado) = 'RECIBIDO'
                    )
            """

            params = [section_name]

            if codigo_filter:
                base_query += " AND UPPER(a.codigo_barras) LIKE UPPER(%s)"
                params.append(f"%{codigo_filter}%")

            base_query += "\n                GROUP BY \n                    a.codigo_barras,\n                    a.codigo_sap,\n                    a.descripcion,\n                    a.estado, \n                    b.cedula\n                ORDER BY a.codigo_barras\n            "

            print(f"📝 Query: {base_query}")
            print(f"📝 Parámetros: {params}")

            cursor.execute(base_query, params)
            rows = cursor.fetchall()

            print(f"📊 Códigos de barras encontrados: {len(rows)}")

            if rows:
                print(f"✅ Primera fila: {rows[0]}")
            else:
                # Si no hay resultados, hacer debug adicional
                print("⚠️ No se encontraron códigos de barras")

                # Verificar si hay datos en barcodes_escaneo_tbl
                cursor.execute("SELECT COUNT(*) FROM barcodes_escaneo_tbl")
                total_barcodes = cursor.fetchone()[0]
                print(
                    f"📊 Total de códigos de barras en la tabla: {total_barcodes}")

                # Verificar procesos con estado RECIBIDO
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM procesos_escaneo_tbl 
                    WHERE UPPER(estado) = 'RECIBIDO'
                """)
                procesos_recibidos = cursor.fetchone()[0]
                print(f"📊 Procesos con estado RECIBIDO: {procesos_recibidos}")

                # Listar algunos section_name disponibles (CORREGIDO PARA ORACLE)
                cursor.execute("""
                    SELECT * FROM (
                        SELECT DISTINCT b.section_name, COUNT(a.codigo_barras) as cantidad
                        FROM barcodes_escaneo_tbl a 
                        INNER JOIN sesiones_escaneo_tbl b ON a.sesion_id = b.sesion_id 
                        GROUP BY b.section_name
                        ORDER BY cantidad DESC
                    ) WHERE ROWNUM <= 10
                """)
                sections_disponibles = cursor.fetchall()
                print(
                    f"📋 Secciones disponibles con códigos: {sections_disponibles}")

            barcodes = [
                {
                    'conteo': row[0],
                    'codigo_barras': row[1],
                    'codigo_sap': row[2] or 'N/A',
                    'descripcion': row[3] or 'N/A',
                    'estado_EAN': row[4] or 'N/A',
                    'cedula': row[5] or 'N/A'
                }
                for row in rows
            ]

        return JsonResponse({
            'success': True,
            'barcodes': barcodes,
            'total': len(barcodes),
            'section_name_usado': section_name
        })

    except Exception as e:
        print(f"❌ Error al obtener códigos de barras escaneados: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': f'Error al obtener códigos de barras: {str(e)}'
        }, status=500)


# ...existing code...

@csrf_exempt
def eliminar_barcode_primer_conteo(request):
    """
    Vista específica para Primer Conteo - Eliminar código de barras
    Query: delete from barcodes_escaneo_tbl where codigo_barras = codigo_param

    ⭐ ACTUALIZADO: Ahora recalcula el estado de validación del detalle del piqueo
    """
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'message': 'No autenticado'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        codigo_barras = data.get('codigo_barras')
        # ⭐ NUEVO: Recibir el código/section_name
        section_name = data.get('section_name')

        if not codigo_barras:
            return JsonResponse({
                'success': False,
                'message': 'Código de barras requerido'
            })

        print(f"🗑️ Eliminando código de barras: {codigo_barras}")
        print(f"📍 Section name (código): {section_name}")

        with connection.cursor() as cursor:
            # ⭐ PASO 1: Eliminar el código de barras
            cursor.execute("""
                DELETE FROM barcodes_escaneo_tbl 
                WHERE codigo_barras = %s
            """, [codigo_barras])

            filas_afectadas = cursor.rowcount

            if filas_afectadas > 0:
                print(
                    f"✅ Código eliminado exitosamente: {codigo_barras} ({filas_afectadas} filas)")

                # ⭐ PASO 2: Si se proporcionó el section_name, recalcular validación del detalle
                if section_name:
                    print(
                        f"🔄 Recalculando validación para código: {section_name}")

                    # Obtener el estado actualizado usando la función de validación
                    cursor.execute("""
                        SELECT verificar_escaneos_func(%s) FROM DUAL
                    """, [section_name])

                    nuevo_estado = cursor.fetchone()
                    estado_validacion = nuevo_estado[0] if nuevo_estado else 'ERROR'

                    print(f"📊 Nuevo estado de validación: {estado_validacion}")

                    return JsonResponse({
                        'success': True,
                        'message': f'Código de barras eliminado correctamente',
                        'codigo_eliminado': codigo_barras,
                        'filas_eliminadas': filas_afectadas,
                        'nuevo_estado_validacion': estado_validacion,
                        'section_name': section_name
                    })
                else:
                    return JsonResponse({
                        'success': True,
                        'message': f'Código de barras eliminado correctamente',
                        'codigo_eliminado': codigo_barras,
                        'filas_eliminadas': filas_afectadas
                    })
            else:
                print(f"⚠️ No se encontró el código: {codigo_barras}")
                return JsonResponse({
                    'success': False,
                    'message': f'No se encontró el código de barras especificado'
                })

    except Exception as e:
        print(f"❌ Error al eliminar código de barras: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': f'Error al eliminar código de barras: {str(e)}'
        }, status=500)


@csrf_exempt
def eliminar_todos_barcodes_primer_conteo(request):
    """
    Vista para eliminar todos los códigos de barras de una sección en Primer Conteo.
    Recalcula el estado de validación del detalle del piqueo después de eliminar.
    """
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'message': 'No autenticado'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        section_name = data.get('section_name')

        if not section_name:
            return JsonResponse({
                'success': False,
                'message': 'Section name requerido'
            })

        print(f"🗑️ Eliminando TODOS los barcodes para sección: {section_name}")


        with connection.cursor() as cursor:
            # Eliminar todos los códigos de barras de la sección usando sesion_id
            cursor.execute("""
                DELETE FROM barcodes_escaneo_tbl
                WHERE sesion_id IN (
                    SELECT sesion_id FROM sesiones_escaneo_tbl WHERE SECTION_NAME = %s
                )
            """, [section_name])

            filas_afectadas = cursor.rowcount
            print(f"✅ Registros eliminados: {filas_afectadas}")

            # Recalcular validación del detalle
            cursor.execute("""
                SELECT verificar_escaneos_func(%s) FROM DUAL
            """, [section_name])

            nuevo_estado = cursor.fetchone()
            estado_validacion = nuevo_estado[0] if nuevo_estado else 'ERROR'

            print(f"📊 Nuevo estado de validación: {estado_validacion}")

            return JsonResponse({
                'success': True,
                'message': f'Se eliminaron todos los registros correctamente',
                'registros_eliminados': filas_afectadas,
                'nuevo_estado_validacion': estado_validacion,
                'section_name': section_name
            })

    except Exception as e:
        print(f"❌ Error al eliminar todos los barcodes: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': f'Error al eliminar registros: {str(e)}'
        }, status=500)


@csrf_exempt
def eliminar_toma_primer_conteo(request):
    """
    Elimina una toma (detalle de piqueo) y sus secuencias asociadas.
    Espera POST JSON: { detalle_id: <int>, piqueo_id: <int> (opcional) }
    """
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'message': 'No autenticado'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        detalle_id = data.get('detalle_id')
        piqueo_id = data.get('piqueo_id')

        if not detalle_id:
            return JsonResponse({'success': False, 'message': 'detalle_id requerido'}, status=400)

        print(f"🗑️ Eliminando toma detalle_id={detalle_id} (piqueo_id={piqueo_id})")

        with connection.cursor() as cursor:
            # Eliminar filas detalle de secuenciales detalle
            cursor.execute("""
                DELETE FROM inv_piqueo_secuencial_deta_tbl
                WHERE detalle_piqueo_id = %s
            """, [detalle_id])
            deleted_deta = cursor.rowcount

            # Eliminar filas de secuencial (cabecera) asociadas
            cursor.execute("""
                DELETE FROM inv_piqueo_secuencial_tbl
                WHERE detalle_piqueo_id = %s
            """, [detalle_id])
            deleted_secuencial = cursor.rowcount

            # Finalmente eliminar el detalle (la toma)
            cursor.execute("""
                DELETE FROM inv_detalle_piqueos_inventarios_tbl
                WHERE detalle_piqueo_id = %s
            """, [detalle_id])
            deleted_detalle = cursor.rowcount

        message = f'Toma eliminada. detalle: {deleted_detalle}, secuencial: {deleted_secuencial}, deta_rows: {deleted_deta}'
        return JsonResponse({'success': True, 'message': message, 'deleted': {
            'detalle': deleted_detalle,
            'secuencial': deleted_secuencial,
            'secuencial_deta': deleted_deta
        }})

    except Exception as e:
        print(f"❌ Error al eliminar toma {detalle_id}: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'}, status=500)


@csrf_exempt
def reprocesar_ean_primer_conteo(request):
    """
    Vista para reprocesar EAN no validados - recalcula el estado de validación
    """
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'message': 'No autenticado'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        codigo_barras = data.get('codigo_barras')
        section_name = data.get('section_name')

        if not codigo_barras:
            return JsonResponse({'success': False, 'message': 'codigo_barras requerido'})

        # Eliminar ceros a la izquierda del código de barras
        codigo_barras_limpio = codigo_barras.lstrip('0') or '0'

        print(f"🔄 Reprocesando EAN para código de barras: {codigo_barras}")
        if codigo_barras != codigo_barras_limpio:
            print(f"🔄 Código limpio (sin ceros iniciales): {codigo_barras_limpio}")
        print(f"📍 Section name (código): {section_name}")


        with connection.cursor() as cursor:
            # Ejecutar el Store Procedure sp_actualiza_ean ANTES de actualizar el código
            print(f"▶️ Ejecutando SP sp_actualiza_ean({codigo_barras_limpio})")
            cursor.callproc('sp_actualiza_ean', [codigo_barras_limpio])

            # Si el código tenía ceros a la izquierda, actualizar en la BD
            if codigo_barras != codigo_barras_limpio:
                cursor.execute("""
                    UPDATE barcodes_escaneo_tbl 
                    SET codigo_barras = %s
                    WHERE codigo_barras = %s
                """, [codigo_barras_limpio, codigo_barras])
                filas_actualizadas = cursor.rowcount
                print(f"✅ Código actualizado en BD: {codigo_barras} -> {codigo_barras_limpio} ({filas_actualizadas} filas)")

            # Recalcular el estado de validación del EAN usando la función existente
            cursor.execute("""
                SELECT verificar_escaneos_func(%s) FROM DUAL
            """, [section_name or codigo_barras_limpio])
            resultado = cursor.fetchone()
            nuevo_estado_validacion = resultado[0] if resultado else None
            print(f"📊 Nuevo estado de validación: {nuevo_estado_validacion}")

        return JsonResponse({
            'success': True,
            'message': 'EAN reprocesado correctamente',
            'nuevo_estado_validacion': nuevo_estado_validacion,
            'section_name': section_name
        })

    except Exception as e:
        print(f"❌ Error al reprocesar EAN: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': f'Error al reprocesar EAN: {str(e)}'
        }, status=500)


@csrf_exempt
def obtener_estadisticas_conteo(request):
    """
    Vista para obtener estadísticas de un conteo específico
    """
    if 'usuario' not in request.session:
        return JsonResponse({'error': 'No autenticado'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        piqueo_id = data.get('piqueo_id')

        if not piqueo_id:
            return JsonResponse({'error': 'piqueo_id requerido'}, status=400)

        print(f"📊 Obteniendo estadísticas para piqueo_id: {piqueo_id}")

        with connection.cursor() as cursor:
            # Obtener información del conteo
            cursor.execute("""
                SELECT 
                    piqueo_id, 
                    numero_conteo, 
                    estado, 
                    TO_CHAR(fecha_inicio, 'DD/MM/YYYY') as fecha_inicio, 
                    TO_CHAR(fecha_fin, 'DD/MM/YYYY') as fecha_fin,
                    nombre_empleado_func(usuario_responsable) as nm_responsable, 
                    usuario_creacion, 
                    centro, 
                    almacen
                FROM INV_PIQUEOS_INVENTARIO_TBL
                WHERE piqueo_id = %s
            """, [piqueo_id])
            row = cursor.fetchone()

            if not row:
                return JsonResponse({'error': 'Conteo no encontrado'}, status=404)

            numero_conteo = row[1]
            
            # Contar solo secuenciales ACTIVOS
            cursor.execute("""
                SELECT COUNT(DISTINCT ipsd.codigo) 
                FROM inv_piqueo_secuencial_deta_tbl ipsd
                JOIN inv_piqueo_secuencial_tbl ips ON ipsd.secuencial_id = ips.secuencial_id
                JOIN inv_detalle_piqueos_inventarios_tbl idp ON ips.detalle_piqueo_id = idp.detalle_piqueo_id
                WHERE idp.piqueo_id = %s
                AND ipsd.estado = 'ACTIVO'
            """, [piqueo_id])
            total_codigos = cursor.fetchone()[0] or 0

            # Códigos cerrados (sin errores de validación) - solo ACTIVOS
            cursor.execute("""
                SELECT COUNT(DISTINCT ipsd.codigo)
                FROM inv_piqueo_secuencial_deta_tbl ipsd
                JOIN inv_piqueo_secuencial_tbl ips ON ipsd.secuencial_id = ips.secuencial_id
                JOIN inv_detalle_piqueos_inventarios_tbl idp ON ips.detalle_piqueo_id = idp.detalle_piqueo_id
                WHERE idp.piqueo_id = %s
                AND ipsd.estado = 'ACTIVO'
                AND verificar_escaneos_func(ipsd.codigo) = 'VALIDADO'
            """, [piqueo_id])
            codigos_cerrados = cursor.fetchone()[0] or 0

            # Códigos pendientes
            codigos_pendientes = total_codigos - codigos_cerrados

            # Calcular porcentaje
            porcentaje_avance = 0
            if total_codigos > 0:
                porcentaje_avance = round((codigos_cerrados / total_codigos) * 100, 2)

            estadisticas = {
                'piqueo_id': row[0],
                'numero_conteo': numero_conteo,
                'estado': row[2],
                'fecha_inicio': row[3],
                'fecha_fin': row[4],
                'nm_responsable': row[5],
                'usuario_creacion': row[6],
                'centro': row[7],
                'almacen': row[8],
                'total_ubicaciones': total_codigos,
                'total_ubicaciones_cerradas': codigos_cerrados,
                'total_ubicaciones_pendientes': codigos_pendientes,
                'porcentaje_avance': porcentaje_avance
            }

            print(f"✅ Estadísticas calculadas (solo ACTIVOS):")
            print(f"   - Total códigos ACTIVOS: {total_codigos}")
            print(f"   - Códigos ACTIVOS validados: {codigos_cerrados}")
            print(f"   - Códigos ACTIVOS pendientes: {codigos_pendientes}")
            print(f"   - Porcentaje avance: {porcentaje_avance}%")

            # Obtener colaboradores y sus escaneos
            # Usar tabla con schema explícito para evitar problemas de búsqueda de esquema
            query_colaboradores = """
                SELECT
                    pc.cedula,
                    pc.nombres,
                    obtener_total_escaneos_usuario(pit.numero_conteo, pc.cedula) AS cantidad_total
                FROM MS_INVENTARIOS.INV_PIQUEO_COLABORADORES_TBL pc
                LEFT JOIN (
                    SELECT DISTINCT se.cedula, be.codigo_barras
                    FROM sesiones_escaneo_tbl se
                    LEFT JOIN barcodes_escaneo_tbl be ON se.sesion_id = be.sesion_id
                ) escaneos ON pc.cedula = escaneos.cedula
                LEFT JOIN inv_piqueos_inventario_tbl pit ON pc.piqueo_id = pit.piqueo_id
                WHERE pc.piqueo_id = %s
                GROUP BY pc.cedula, pc.nombres, pit.numero_conteo
                ORDER BY pc.nombres
            """

            print(f"📝 Ejecutando query_colaboradores para piqueo_id={piqueo_id}")

            cursor.execute(query_colaboradores, [piqueo_id])
            colaboradores_rows = cursor.fetchall()

            colaboradores = []
            total_productos_escaneados = 0

            for col_row in colaboradores_rows:
                cantidad = col_row[2] or 0
                total_productos_escaneados += cantidad
                colaboradores.append({
                    'cedula': col_row[0],
                    'nombres': col_row[1],
                    'cantidad_total': cantidad
                })

            print(f"✅ Colaboradores encontrados: {len(colaboradores)}")
            print(f"📦 Total productos escaneados: {total_productos_escaneados}")

        return JsonResponse({
            'success': True,
            'estadisticas': estadisticas,
            'colaboradores': colaboradores,
            'total_productos_escaneados': total_productos_escaneados,
            'total_escaneado': total_productos_escaneados
        })

    except Exception as e:
        print(f"❌ Error al obtener estadísticas: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': f'Error al obtener estadísticas: {str(e)}'
        }, status=500)


@csrf_exempt
def cerrar_conteo_primer_conteo(request):
    """
    Vista para cerrar un conteo de primer inventario
    Ejecuta secuencialmente:
    1. sp_procesar_primer_conteo_inventario
    2. generar_toma_fisica_resumen
    3. distribuir_articulos_conteo
    """
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'error': 'No autenticado'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        piqueo_id = data.get('piqueo_id')

        if not piqueo_id:
            return JsonResponse({'success': False, 'message': 'piqueo_id requerido'}, status=400)

        usuario = request.session.get('usuario', {})
        cedula = usuario.get('cedula', '')

        print(f"🔒 Procesando cierre de conteo {piqueo_id} para usuario: {cedula}")

        # ========================================
        # PASO 1: VALIDACIONES PREVIAS
        # ========================================
        
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT numero_conteo, estado, usuario_responsable, almacen
                FROM INV_PIQUEOS_INVENTARIO_TBL
                WHERE piqueo_id = %s
            """, [piqueo_id])

            row = cursor.fetchone()

            if not row:
                return JsonResponse({'success': False, 'message': 'Conteo no encontrado'}, status=404)

            numero_conteo, estado_actual, usuario_responsable, almacen = row

            print(f"📋 Número de conteo: {numero_conteo}")
            print(f"📊 Estado actual: {estado_actual}")
            print(f"🏪 Almacén: {almacen}")

            # Verificar permisos
            if usuario_responsable != cedula:
                return JsonResponse({
                    'success': False,
                    'message': 'No tiene permisos para cerrar este conteo'
                }, status=403)

            if estado_actual.upper() == 'COMPLETADO':
                return JsonResponse({'success': False, 'message': 'El conteo ya está completado'})

            # Verificar errores en códigos de barras
            print(f"🔍 Verificando EAN con errores para: {numero_conteo}")
            cursor.execute("""
                SELECT obtener_conteos_erroneos_primer_conteo(%s) FROM DUAL
            """, [numero_conteo])

            result = cursor.fetchone()
            conteos_erroneos = result[0] if result else 0

            print(f"❌ Conteos erróneos encontrados: {conteos_erroneos}")

            if conteos_erroneos > 0:
                return JsonResponse({
                    'success': False,
                    'message': f'⚠️ Se encontraron {conteos_erroneos} EAN con errores.\n\nPor favor, verifique y corrija los códigos de barras antes de cerrar el conteo.',
                    'conteos_erroneos': conteos_erroneos
                })

            # NUEVA VALIDACIÓN: Verificar que TODOS los items estén VALIDADOS (Espejo del frontend)
            print(f"🔍 Verificando estados VALIDADO para piqueo: {piqueo_id}")
            cursor.execute("""
                SELECT COUNT(*)
                FROM inv_detalle_piqueos_inventarios_tbl a
                LEFT JOIN inv_piqueo_secuencial_tbl b ON a.detalle_piqueo_id = b.detalle_piqueo_id
                LEFT JOIN inv_piqueo_secuencial_deta_tbl c ON b.secuencial_id = c.secuencial_id
                WHERE a.piqueo_id = %s
                AND (c.estado = 'ACTIVO' OR c.estado IS NULL)
                AND (verificar_escaneos_func(c.codigo) IS NULL OR UPPER(verificar_escaneos_func(c.codigo)) != 'VALIDADO')
            """, [piqueo_id])
            
            items_no_validos = cursor.fetchone()[0]
            
            if items_no_validos > 0:
                 return JsonResponse({
                    'success': False,
                    'message': f'⚠️ NO SE PUEDE CERRAR.\n\nSe encontraron {items_no_validos} items que NO están en estado VALIDADO.\n\nPor favor, revise el detalle y asegúrese de que todos los códigos estén verificados correctamente.'
                })

        print(f"✅ Validaciones completadas. Procesando cierre del conteo...")

        # ========================================
        # PASO 2: LIMPIEZA PREVIA PARA EVITAR DUPLICADOS
        # ========================================

        with connection.cursor() as cursor:
            print(f"🧹 Ejecutando limpieza previa en inv_piqueo_toma_fisica_tbl para conteo: {numero_conteo}")
            cursor.execute("""
                DELETE FROM inv_piqueo_toma_fisica_tbl
                WHERE numero_conteo = %s
            """, [numero_conteo])
            print(f"✅ Limpieza completada. Filas eliminadas: {cursor.rowcount}")

        # ========================================
        # PASO 3: COMMIT EXPLÍCITO
        # ========================================
        
        connection.connection.commit()
        print("✅ Commit explícito realizado tras limpieza previa")

        # ========================================
        # PASO 4: EJECUTAR SP PRINCIPAL
        # ========================================
        
        with connection.cursor() as cursor:
            # Crear variables OUT
            v_resultado = cursor.var(str)
            v_mensaje = cursor.var(str)

            print(f"🔧 Ejecutando sp_procesar_primer_conteo_inventario para: {numero_conteo}")

            # Ejecutar el stored procedure principal
            cursor.execute("""
                BEGIN
                    sp_procesar_primer_conteo_inventario(
                        p_numero_conteo => :p_numero_conteo,
                        p_resultado => :p_resultado,
                        p_mensaje => :p_mensaje
                    );
                END;
            """, {
                'p_numero_conteo': numero_conteo,
                'p_resultado': v_resultado,
                'p_mensaje': v_mensaje
            })

            # Obtener los valores OUT
            resultado_str = v_resultado.getvalue()
            mensaje = v_mensaje.getvalue()

            print(f"📊 RESULTADO SP: {resultado_str}")
            print(f"💬 MENSAJE SP: {mensaje}")

            # Verificar si el SP fue exitoso
            if resultado_str and str(resultado_str).upper() == 'EXITOSO':
                print(f"✅ SP principal ejecutado exitosamente")

                # ========================================
                # PASO 5: EJECUTAR PROCEDIMIENTOS COMPLEMENTARIOS
                # ========================================
                
                advertencias = []
                
                # 4.1 - Ejecutar generar_toma_fisica_resumen
                try:
                    print(f"🔧 Ejecutando generar_toma_fisica_resumen...")
                    cursor.execute("""
                        BEGIN
                            generar_toma_fisica_resumen(
                                p_numero_conteo => :p_numero_conteo,
                                p_almacen => :p_almacen
                            );
                        END;
                    """, {
                        'p_numero_conteo': numero_conteo,
                        'p_almacen': almacen
                    })
                    connection.connection.commit()
                    print(f"✅ generar_toma_fisica_resumen ejecutado exitosamente")
                    
                except Exception as e:
                    error_msg = str(e)
                    if 'ORA-' in error_msg:
                        lines = error_msg.split('\n')
                        for line in lines:
                            if 'ORA-' in line:
                                error_msg = line.strip()
                                break
                    print(f"⚠️ Advertencia en generar_toma_fisica_resumen: {error_msg}")
                    advertencias.append(f"generar_toma_fisica_resumen: {error_msg}")
                
                # 4.2 - Ejecutar distribuir_articulos_conteo
                try:
                    print(f"🔧 Ejecutando distribuir_articulos_conteo...")
                    cursor.execute("""
                        BEGIN
                            distribuir_articulos_conteo(
                                p_numero_conteo => :p_numero_conteo,
                                p_almacen => :p_almacen
                            );
                        END;
                    """, {
                        'p_numero_conteo': numero_conteo,
                        'p_almacen': almacen
                    })
                    connection.connection.commit()
                    print(f"✅ distribuir_articulos_conteo ejecutado exitosamente")
                    
                except Exception as e:
                    error_msg = str(e)
                    if 'ORA-' in error_msg:
                        lines = error_msg.split('\n')
                        for line in lines:
                            if 'ORA-' in line:
                                error_msg = line.strip()
                                break
                    print(f"⚠️ Advertencia en distribuir_articulos_conteo: {error_msg}")
                    advertencias.append(f"distribuir_articulos_conteo: {error_msg}")

                # ========================================
                # PASO 6: ACTUALIZAR FECHA FIN
                # ========================================
                
                cursor.execute("""
                    UPDATE INV_PIQUEOS_INVENTARIO_TBL
                    SET fecha_fin = SYSDATE
                    WHERE piqueo_id = %s
                    AND fecha_fin IS NULL
                """, [piqueo_id])

                # Commit final
                connection.connection.commit()
                print(f"✅ Proceso completado exitosamente")

                # ========================================
                # PASO 7: CONSTRUIR RESPUESTA
                # ========================================
                
                mensaje_final = str(mensaje) or f'Conteo {numero_conteo} cerrado y procesado exitosamente'
                
                if advertencias:
                    mensaje_final += '\n\n⚠️ Advertencias:\n' + '\n'.join(f'• {adv}' for adv in advertencias)

                return JsonResponse({
                    'success': True,
                    'message': mensaje_final,
                    'resultado': str(resultado_str),
                    'advertencias': advertencias if advertencias else None
                })
                
            else:
                # El SP reportó error
                error_msg = str(mensaje) if mensaje else 'Error al procesar el conteo'
                print(f"❌ Error reportado por el SP: {error_msg}")
                
                connection.connection.rollback()
                
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                })

    except Exception as e:
        print(f"❌ Error al cerrar conteo: {e}")
        import traceback
        traceback.print_exc()
        
        # Rollback en caso de error
        try:
            connection.connection.rollback()
        except:
            pass
        
        error_message = str(e)
        if 'ORA-' in error_message:
            lines = error_message.split('\n')
            for line in lines:
                if 'ORA-' in line:
                    error_message = line.strip()
                    break
        
        return JsonResponse({
            'success': False,
            'message': f'Error al cerrar conteo: {error_message}'
        }, status=500)   

@csrf_exempt
def segundo_conteo(request):
    """
    Vista para la pantalla Segundo Conteo - Similar a Primer Conteo
    pero enfocada en asignación de colaboradores
    """
    if 'usuario' not in request.session:
        return redirect('login')

    perfil = request.session.get('perfil_seleccionado', {}).get('nombre', '')
    usuario_sesion = request.session.get('usuario', {})
    usuario_cedula = usuario_sesion.get('cedula', '')

    # OBTENER FILTROS (GET o POST/AJAX)
    filtros = {}
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            data = json.loads(request.body)
            filtros = data.get('filtros', {})
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Error en los datos de filtros'}, status=400)
    elif request.method == 'GET':
        filtros['estado'] = request.GET.get('estado', '').strip()
        filtros['centro'] = request.GET.get('centro', '').strip()
        filtros['almacen'] = request.GET.get('almacen', '').strip()

    with connection.cursor() as cursor:
        # Query para obtener conteos con estado PRIMER_CONTEO (listos para segundo conteo)
        query = """
            SELECT piqueo_id, numero_conteo, estado, fecha_inicio, fecha_fin,
            nombre_empleado_func(usuario_responsable) as nm_responsable, 
            usuario_creacion, centro, almacen
            FROM INV_PIQUEOS_INVENTARIO_TBL
            WHERE usuario_responsable = %s
            AND UPPER(estado) IN ('PRIMER_CONTEO', 'SEGUNDO_CONTEO')
        """
        params = [usuario_cedula]

        # APLICAR FILTROS DINÁMICAMENTE
        if filtros.get('estado'):
            query += " AND UPPER(estado) = UPPER(%s)"
            params.append(filtros['estado'])

        if filtros.get('centro'):
            query += " AND centro = %s"
            params.append(filtros['centro'])

        if filtros.get('almacen'):
            query += " AND almacen = %s"
            params.append(filtros['almacen'])

        query += " ORDER BY fecha_inicio DESC"

        print(f"🔍 [SEGUNDO_CONTEO] Query ejecutado: {query}")
        print(f"🔍 [SEGUNDO_CONTEO] Parámetros: {params}")
        cursor.execute(query, params)
        rows = cursor.fetchall()

    conteos = [
        {
            'id': row[0],
            'numero_conteo': row[1],
            'estado': row[2],
            'fecha_inicio': row[3].strftime('%b. %d, %Y') if row[3] else '-',
            'fecha_fin': row[4].strftime('%b. %d, %Y') if row[4] else '-',
            'nm_responsable': row[5],
            'usuario_creacion': row[6],
            'centro': row[7],
            'almacen': row[8],
        }
        for row in rows
    ]

    estadisticas = {
        'total': len(conteos),
        'pendientes': sum(1 for c in conteos if c['estado'].upper() == 'PENDIENTE'),
        'primer_conteo': sum(1 for c in conteos if c['estado'].upper() == 'PRIMER_CONTEO'),
        'segundo_conteo': sum(1 for c in conteos if c['estado'].upper() == 'SEGUNDO_CONTEO'),
        'completados': sum(1 for c in conteos if c['estado'].upper() == 'COMPLETADO'),
    }

    # Si es petición AJAX, devolver JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'conteos': conteos,
            'estadisticas': estadisticas
        })

    context = {
        'usuario': request.session['usuario'],
        'perfil': perfil,
        'conteos': conteos,
        'estadisticas': estadisticas,
    }
    return render(request, 'inventario/segundo_conteo.html', context)


@csrf_exempt
def finalizar_conteo(request, piqueo_id):
    """
    Vista para finalizar un conteo ejecutando el stored procedure y actualizando el estado a SEGUNDO_CONTEO
    """
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'message': 'No autenticado'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        numero_conteo = data.get('numero_conteo')
        almacen = data.get('almacen')

        if not numero_conteo or not almacen:
            return JsonResponse({
                'success': False,
                'message': 'Faltan parámetros: numero_conteo y almacen son requeridos'
            }, status=400)

        print(f"🏁 [FINALIZAR_CONTEO] Iniciando proceso para PIQUEO_ID: {piqueo_id}")
        print(f"📋 [FINALIZAR_CONTEO] Número de conteo: {numero_conteo}")
        print(f"🏪 [FINALIZAR_CONTEO] Almacén: {almacen}")

        with connection.cursor() as cursor:
            # Verificar que el estado actual sea PRIMER_CONTEO
            cursor.execute("""
                SELECT estado
                FROM INV_PIQUEOS_INVENTARIO_TBL
                WHERE piqueo_id = %s
            """, [piqueo_id])
            
            result = cursor.fetchone()
            if not result:
                return JsonResponse({
                    'success': False,
                    'message': f'No se encontró el conteo con ID {piqueo_id}'
                }, status=404)

            estado_actual = result[0]
            if estado_actual.upper() != 'PRIMER_CONTEO':
                return JsonResponse({
                    'success': False,
                    'message': f'El conteo debe estar en estado PRIMER_CONTEO. Estado actual: {estado_actual}'
                }, status=400)

            # Ejecutar el stored procedure
            print(f"🔧 [FINALIZAR_CONTEO] Ejecutando stored procedure generar_toma_fisica_resumen_2")
            
            cursor.callproc('generar_toma_fisica_resumen_2', [numero_conteo, almacen])
            
            print(f"✅ [FINALIZAR_CONTEO] Stored procedure ejecutado exitosamente")

            # Actualizar el estado a SEGUNDO_CONTEO
            print(f"🔄 [FINALIZAR_CONTEO] Actualizando estado a SEGUNDO_CONTEO")
            
            cursor.execute("""
                UPDATE INV_PIQUEOS_INVENTARIO_TBL
                SET estado = 'SEGUNDO_CONTEO'
                WHERE piqueo_id = %s
            """, [piqueo_id])
            
            connection.commit()
            
            print(f"✅ [FINALIZAR_CONTEO] Estado actualizado exitosamente")

        return JsonResponse({
            'success': True,
            'message': 'Conteo finalizado exitosamente',
            'piqueo_id': piqueo_id,
            'nuevo_estado': 'SEGUNDO_CONTEO'
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Error al procesar los datos JSON'
        }, status=400)
    except Exception as e:
        print(f"❌ [FINALIZAR_CONTEO] Error: {str(e)}")
        connection.rollback()
        return JsonResponse({
            'success': False,
            'message': f'Error al finalizar el conteo: {str(e)}'
        }, status=500)


@csrf_exempt
def diferencias_segundo_conteo(request, piqueo_id):
    """
    Vista para mostrar diferencias del segundo conteo y permitir asignación de colaboradores
    """
    if 'usuario' not in request.session:
        return redirect('login')

    perfil = request.session.get('perfil_seleccionado', {}).get('nombre', '')
    usuario = request.session['usuario'].get('nombre', '')

    # Obtener información del conteo
    conteo = {}
    diferencias = []

    with connection.cursor() as cursor:
        # Obtener datos básicos del conteo
        cursor.execute("""
            SELECT 
                piqueo_id,
                numero_conteo, 
                centro, 
                almacen, 
                estado, 
                fecha_inicio, 
                fecha_fin,
                usuario_responsable,
                nombre_empleado_func(usuario_responsable) as nm_responsable
            FROM INV_PIQUEOS_INVENTARIO_TBL
            WHERE piqueo_id = %s
        """, [piqueo_id])
        conteo_row = cursor.fetchone()

        if conteo_row:
            conteo = {
                'piqueo_id': conteo_row[0],
                'numero_conteo': conteo_row[1],
                'centro': conteo_row[2],
                'almacen': conteo_row[3],
                'estado': conteo_row[4],
                'fecha_inicio': conteo_row[5].strftime('%Y-%m-%d') if conteo_row[5] else 'N/A',
                'fecha_fin': conteo_row[6].strftime('%Y-%m-%d') if conteo_row[6] else 'N/A',
                'usuario_responsable': conteo_row[7],
                'nm_responsable': conteo_row[8] or 'N/A'
            }

        # Obtener diferencias usando NUMERO_CONTEO y ALMACEN
        cursor.execute("""
            SELECT
                id,
                codigo_barras,
                codigo_sap,
                descripcion,
                marca,
                talla,
                ena,
                grupo_articulos,
                groes,
                ubicacion_fisica,
                conteo_fisico,
                stock_sistema,
                diferencia,
                diferencia_rpro,
                estado_comparacion,
                nombre_colaborador,
                proceso_segundo_conteo,
                observaciones_segundo_conteo
            FROM inv_inventario_fisico_vs_sistema
            WHERE numero_conteo = %s
              AND almacen_sistema = %s
              AND estado_comparacion = 'DIFERENCIA'
            ORDER BY codigo_barras, descripcion
        """, [conteo['numero_conteo'], conteo['almacen']])

        diferencias_rows = cursor.fetchall()
        for row in diferencias_rows:
            diferencias.append({
                'id': row[0],
                'codigo_barras': row[1] or 'N/A',
                'codigo_sap': row[2] or 'N/A',
                'descripcion': row[3] or 'N/A',
                'marca': row[4] or 'N/A',
                'talla': row[5] or 'N/A',
                'ena': row[6] or 'N/A',
                'grupo_articulos': row[7] or 'N/A',
                'groes': row[8] or 'N/A',
                'ubicacion_fisica': row[9] or 'N/A',
                'conteo_fisico': int(row[10]) if row[10] is not None else 0,
                'stock_sistema': int(row[11]) if row[11] is not None else 0,
                'diferencia': int(row[12]) if row[12] is not None else 0,
                'diferencia_rpro': int(row[13]) if row[13] is not None else 0,
                'estado_comparacion': row[14] or 'N/A',
                'nombre_colaborador': row[15] or 'Sin asignar',
                'proceso_segundo_conteo': row[16] or 'Pendiente',
                'observaciones_segundo_conteo': row[17] or 'N/A',
            })

    # Estadísticas rápidas
    estadisticas = {
        'total': len(diferencias),
        'pendientes': sum(1 for d in diferencias if d['proceso_segundo_conteo'] == 'Pendiente'),
        'aceptados': sum(1 for d in diferencias if d['proceso_segundo_conteo'] == 'Aceptado'),
        'rechazados': sum(1 for d in diferencias if d['proceso_segundo_conteo'] == 'Rechazado'),
    }

    context = {
        'usuario': request.session['usuario'],
        'perfil': perfil,
        'piqueo_id': piqueo_id,
        'conteo': conteo,
        'diferencias': diferencias,
        'estadisticas': estadisticas,
    }
    return render(request, 'inventario/diferencias_segundo_conteo.html', context)


@csrf_exempt
def asignar_colaborador_diferencia(request):
    """
    Vista para asignar colaborador a una diferencia específica del segundo conteo
    """
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'message': 'No autenticado'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        # ⭐ USAR ID EN LUGAR DE CODIGO_BARRAS + NUMERO_CONTEO
        diferencia_id = data.get('diferencia_id')
        cedula_colaborador = data.get('cedula_colaborador')
        nombre_colaborador = data.get('nombre_colaborador')

        print(f"🔄 Asignando colaborador a diferencia:")
        print(f"   ID diferencia: {diferencia_id}")
        print(f"   Cédula: {cedula_colaborador}")
        print(f"   Nombre: {nombre_colaborador}")

        if not all([diferencia_id, cedula_colaborador, nombre_colaborador]):
            return JsonResponse({
                'success': False,
                'message': 'Todos los campos son requeridos'
            })

        with connection.cursor() as cursor:
            # Verificar que existe la diferencia antes de actualizar
            cursor.execute("""
                SELECT id, codigo_barras, numero_conteo
                FROM inv_inventario_fisico_vs_sistema
                WHERE id = %s
                AND estado_comparacion = 'DIFERENCIA'
            """, [diferencia_id])

            resultado = cursor.fetchone()

            if not resultado:
                print(
                    f"⚠️ No se encontró la diferencia con ID: {diferencia_id}")
                return JsonResponse({
                    'success': False,
                    'message': f'No se encontró la diferencia especificada'
                })

            id_encontrado, codigo_barras, numero_conteo = resultado
            print(
                f"✅ Diferencia encontrada - ID: {id_encontrado}, Código: {codigo_barras}, Conteo: {numero_conteo}")

            # ⭐ ACTUALIZAR USANDO EL ID ÚNICO
            cursor.execute("""
                UPDATE inv_inventario_fisico_vs_sistema
                SET cedula_colaborador = %s,
                    nombre_colaborador = %s
                WHERE id = %s
            """, [cedula_colaborador, nombre_colaborador, diferencia_id])

            filas_actualizadas = cursor.rowcount

            if filas_actualizadas > 0:
                print(
                    f"✅ Colaborador asignado exitosamente. Filas actualizadas: {filas_actualizadas}")
                return JsonResponse({
                    'success': True,
                    'message': f'Colaborador {nombre_colaborador} asignado exitosamente',
                    'filas_actualizadas': filas_actualizadas,
                    'codigo_barras': codigo_barras,
                    'nombre_colaborador': nombre_colaborador
                })
            else:
                print(f"⚠️ No se pudo actualizar la diferencia")
                return JsonResponse({
                    'success': False,
                    'message': 'No se pudo realizar la asignación. Intente nuevamente.'
                })

    except Exception as e:
        print(f"❌ Error al asignar colaborador: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': f'Error al asignar colaborador: {str(e)}'
        }, status=500)


def obtener_colaboradores_conteo_redistribucion(request):
    """
    Obtiene colaboradores asignados a un conteo (por numero_conteo) para
    mostrar el listado inicial del dialogo de redistribucion.
    """
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'message': 'No autenticado'}, status=401)

    if request.method != 'GET':
        return JsonResponse({'success': False, 'message': 'Metodo no permitido'}, status=405)

    numero_conteo = request.GET.get('numero_conteo', '').strip()
    if not numero_conteo:
        return JsonResponse({'success': False, 'message': 'Falta numero_conteo'}, status=400)

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT
                    c.CEDULA,
                    c.NOMBRES,
                    c.CARGO,
                    c.TIENDA
                FROM MS_INVENTARIOS.INV_PIQUEO_COLABORADORES_TBL c
                INNER JOIN MS_INVENTARIOS.INV_PIQUEOS_INVENTARIO_TBL p
                    ON p.PIQUEO_ID = c.PIQUEO_ID
                WHERE p.NUMERO_CONTEO = %s
                ORDER BY c.NOMBRES
            """, [numero_conteo])

            rows = cursor.fetchall()

        colaboradores = [
            {
                'cedula': row[0] or '',
                'nombre': row[1] or 'Sin nombre',
                'cargo': row[2] or '',
                'tienda': row[3] or ''
            }
            for row in rows
        ]

        return JsonResponse({
            'success': True,
            'numero_conteo': numero_conteo,
            'colaboradores': colaboradores,
            'total': len(colaboradores)
        })
    except Exception as e:
        print(f"❌ Error obteniendo colaboradores para redistribucion: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error al obtener colaboradores: {str(e)}'
        }, status=500)


@csrf_exempt
def redistribuir_diferencias_segundo_conteo(request):
    """
    Redistribuye en forma equitativa (round-robin) los registros pendientes de
    segundo conteo entre los colaboradores seleccionados.
    """
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'message': 'No autenticado'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Metodo no permitido'}, status=405)

    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Payload invalido'}, status=400)

    numero_conteo = (data.get('numero_conteo') or '').strip()
    almacen = (data.get('almacen') or '').strip()
    colaboradores = data.get('colaboradores') or []

    if not numero_conteo:
        return JsonResponse({'success': False, 'message': 'Falta numero_conteo'}, status=400)

    if not almacen:
        return JsonResponse({'success': False, 'message': 'Falta almacen'}, status=400)

    colaboradores_validos = []
    for col in colaboradores:
        cedula = str(col.get('cedula') or '').strip()
        nombre = str(col.get('nombre') or '').strip()
        if cedula and nombre:
            colaboradores_validos.append({'cedula': cedula, 'nombre': nombre})

    if not colaboradores_validos:
        return JsonResponse({'success': False, 'message': 'Seleccione al menos un colaborador valido'}, status=400)

    started_at = time.perf_counter()

    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id
                    FROM inv_inventario_fisico_vs_sistema
                    WHERE numero_conteo = %s
                      AND almacen_sistema = %s
                        AND estado_comparacion = 'DIFERENCIA'
                      AND (
                            proceso_segundo_conteo IS NULL
                            OR (
                                                                UPPER(proceso_segundo_conteo) NOT LIKE %s
                                                                AND UPPER(proceso_segundo_conteo) NOT LIKE %s
                            )
                      )
                    ORDER BY id
                                """, [numero_conteo, almacen, '%ACEPT%', '%COMPLET%'])

                pendientes = [row[0] for row in cursor.fetchall()]
                total_pendientes = len(pendientes)

                if not pendientes:
                    return JsonResponse({
                        'success': True,
                        'message': 'No hay diferencias pendientes para redistribuir',
                        'total_pendientes': 0,
                        'total_actualizados': 0,
                        'tiempo_ms': round((time.perf_counter() - started_at) * 1000, 2)
                    })

                resumen = {}
                total_colaboradores = len(colaboradores_validos)
                actualizaciones = []

                for idx, diferencia_id in enumerate(pendientes):
                    colaborador = colaboradores_validos[idx % total_colaboradores]
                    actualizaciones.append((colaborador['cedula'], colaborador['nombre'], diferencia_id))
                    resumen_key = f"{colaborador['nombre']} ({colaborador['cedula']})"
                    resumen[resumen_key] = resumen.get(resumen_key, 0) + 1

                cursor.executemany("""
                    UPDATE inv_inventario_fisico_vs_sistema
                    SET cedula_colaborador = %s,
                        nombre_colaborador = %s
                    WHERE id = %s
                """, actualizaciones)

                return JsonResponse({
                    'success': True,
                    'message': 'Redistribucion realizada correctamente',
                    'total_pendientes': total_pendientes,
                    'total_actualizados': len(actualizaciones),
                    'colaboradores_usados': total_colaboradores,
                    'resumen': resumen,
                    'tiempo_ms': round((time.perf_counter() - started_at) * 1000, 2)
                })
    except Exception as e:
        print(f"❌ Error en redistribucion: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error al redistribuir diferencias: {str(e)}'
        }, status=500)


@csrf_exempt
def reporte_primer_conteo(request):
    """
    Vista para generar el reporte del primer conteo con filtros y exportación a Excel.
    """
    if 'usuario' not in request.session:
        return redirect('login')

    perfil = request.session.get('perfil_seleccionado', {}).get('nombre', '')
    usuario_responsable = request.session['usuario'].get('cedula', '')

    # Obtener opciones para los dropdowns
    opciones_centro = []
    opciones_almacen = []
    opciones_numero_conteo = []

    with connection.cursor() as cursor:
        # Obtener centros únicos
        cursor.execute("""
            SELECT DISTINCT a.centro
            FROM inv_piqueos_inventario_tbl a
            WHERE a.usuario_responsable = %s
            AND a.centro IS NOT NULL
            ORDER BY a.centro
        """, [usuario_responsable])
        opciones_centro = [row[0] for row in cursor.fetchall()]

        # Obtener almacenes únicos
        cursor.execute("""
            SELECT DISTINCT a.almacen
            FROM inv_piqueos_inventario_tbl a
            WHERE a.usuario_responsable = %s
            AND a.almacen IS NOT NULL
            ORDER BY a.almacen
        """, [usuario_responsable])
        opciones_almacen = [row[0] for row in cursor.fetchall()]

        # Obtener números de conteo únicos
        cursor.execute("""
            SELECT DISTINCT a.numero_conteo
            FROM inv_piqueos_inventario_tbl a
            WHERE a.usuario_responsable = %s
            AND a.numero_conteo IS NOT NULL
            ORDER BY a.numero_conteo DESC
        """, [usuario_responsable])
        opciones_numero_conteo = [row[0] for row in cursor.fetchall()]

    # OBTENER FILTROS
    filtros = {}
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            data = json.loads(request.body)
            filtros = data.get('filtros', {})
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Error en los datos de filtros'}, status=400)
    elif request.method == 'GET':
        filtros['centro'] = request.GET.get('centro', '').strip()
        filtros['almacen'] = request.GET.get('almacen', '').strip()
        filtros['numero_conteo'] = request.GET.get('numero_conteo', '').strip()

    # ⭐ SOLO OBTENER DATOS SI HAY AL MENOS UN FILTRO APLICADO
    resultados = []
    if any(filtros.values()):
        # Consulta SQL
        query = """
            SELECT 
                a.numero_conteo,
                a.centro,
                a.almacen,
                b.codigo_barras,
                b.codigo_sap,
                b.descripcion,
                b.marca,
                b.talla,
                b.ENA as ean,
                b.grupo_articulos,
                b.groes,
                b.ubicacion_fisica,
                b.conteo_fisico,
                b.stock_sistema,
                b.diferencia,
                b.diferencia_rpro
            FROM inv_piqueos_inventario_tbl a
            JOIN inv_inventario_fisico_vs_sistema b
            ON a.numero_conteo = b.numero_conteo
            AND a.almacen = b.almacen_sistema
            WHERE a.usuario_responsable = %s
        """
        params = [usuario_responsable]

        # Aplicar filtros
        if filtros.get('centro'):
            query += " AND a.centro = %s"
            params.append(filtros['centro'])
        if filtros.get('almacen'):
            query += " AND a.almacen = %s"
            params.append(filtros['almacen'])
        if filtros.get('numero_conteo'):
            query += " AND a.numero_conteo = %s"
            params.append(filtros['numero_conteo'])

        query += " ORDER BY a.numero_conteo, b.codigo_barras"

        print(f"🔍 [REPORTE] Query: {query}")
        print(f"🔍 [REPORTE] Parámetros: {params}")

        # Obtener datos
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            for row in rows:
                resultados.append({
                    'numero_conteo': row[0],
                    'centro': row[1],
                    'almacen': row[2],
                    'codigo_barras': row[3],
                    'codigo_sap': row[4],
                    'descripcion': row[5],
                    'marca': row[6],
                    'talla': row[7],
                    'ean': row[8],
                    'grupo_articulos': row[9],
                    'groes': row[10],
                    'ubicacion_fisica': row[11],
                    'conteo_fisico': row[12],
                    'stock_sistema': row[13],
                    'diferencia': row[14],
                    'diferencia_rpro': row[15],
                })

    # Exportar a Excel
    if request.GET.get('exportar') == 'excel':
        if not resultados:
            return JsonResponse({
                'success': False,
                'message': 'No hay datos para exportar. Por favor aplique filtros primero.'
            })

        import pandas as pd
        df = pd.DataFrame(resultados)
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="reporte_primer_conteo.xlsx"'
        df.to_excel(response, index=False)
        return response

    # Si es petición AJAX, devolver JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'resultados': resultados,
            'total': len(resultados)
        })

    # Renderizar la página
    context = {
        'usuario': request.session['usuario'],
        'perfil': perfil,
        'resultados': resultados,
        'filtros': filtros,
        'opciones_centro': opciones_centro,
        'opciones_almacen': opciones_almacen,
        'opciones_numero_conteo': opciones_numero_conteo,
    }
    return render(request, 'inventario/reporte_primer_conteo.html', context)

@csrf_exempt
def obtener_detalle_secuencias(request, secuencial_id):
    """
    Vista para obtener el detalle de secuencias de un secuencial específico
    Query: SELECT SECUENCIAL_DETA_ID, SECUENCIAL_ID, DETALLE_PIQUEO_ID, 
           UBICACION, SECUENCIA, CODIGO, ESTADO 
           FROM inv_piqueo_secuencial_deta_tbl
           WHERE SECUENCIAL_ID = secuencial_id
    """
    if 'usuario' not in request.session:
        return JsonResponse({'error': 'No autenticado'}, status=401)

    if request.method != 'GET':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    try:
        print(f"🔍 Obteniendo detalle de secuencias para secuencial_id: {secuencial_id}")

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    SECUENCIAL_DETA_ID,
                    SECUENCIAL_ID,
                    DETALLE_PIQUEO_ID,
                    UBICACION,
                    SECUENCIA,
                    CODIGO,
                    ESTADO
                FROM inv_piqueo_secuencial_deta_tbl
                WHERE SECUENCIAL_ID = %s
                ORDER BY SECUENCIA
            """, [secuencial_id])

            rows = cursor.fetchall()

            secuencias = [
                {
                    'secuencial_deta_id': row[0],
                    'secuencial_id': row[1],
                    'detalle_piqueo_id': row[2],
                    'ubicacion': row[3] or 'N/A',
                    'secuencia': row[4] or 0,
                    'codigo': row[5] or 'N/A',
                    'estado': row[6] or 'ACTIVO'
                }
                for row in rows
            ]

            print(f"✅ Secuencias encontradas: {len(secuencias)}")

        return JsonResponse({
            'success': True,
            'secuencias': secuencias,
            'total': len(secuencias)
        })

    except Exception as e:
        print(f"❌ Error al obtener detalle de secuencias: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': f'Error al obtener detalle de secuencias: {str(e)}'
        }, status=500)


@csrf_exempt
def anular_secuencia_detalle(request):
    """
    Vista para anular una secuencia específica
    UPDATE inv_piqueo_secuencial_deta_tbl 
    SET ESTADO = 'ANULADO' 
    WHERE SECUENCIAL_DETA_ID = secuencial_deta_id
    """
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'message': 'No autenticado'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        secuencial_deta_id = data.get('secuencial_deta_id')

        if not secuencial_deta_id:
            return JsonResponse({
                'success': False,
                'message': 'secuencial_deta_id requerido'
            })

        print(f"🚫 Anulando secuencia detalle ID: {secuencial_deta_id}")

        with connection.cursor() as cursor:
            # Verificar que la secuencia existe y no está ya anulada
            cursor.execute("""
                SELECT ESTADO FROM inv_piqueo_secuencial_deta_tbl
                WHERE SECUENCIAL_DETA_ID = %s
            """, [secuencial_deta_id])

            row = cursor.fetchone()

            if not row:
                return JsonResponse({
                    'success': False,
                    'message': 'Secuencia no encontrada'
                })

            estado_actual = row[0]

            if estado_actual == 'ANULADO':
                return JsonResponse({
                    'success': False,
                    'message': 'La secuencia ya está anulada'
                })

            # Actualizar el estado a ANULADO
            cursor.execute("""
                UPDATE inv_piqueo_secuencial_deta_tbl
                SET ESTADO = 'ANULADO'
                WHERE SECUENCIAL_DETA_ID = %s
            """, [secuencial_deta_id])

            filas_actualizadas = cursor.rowcount

            if filas_actualizadas > 0:
                print(f"✅ Secuencia anulada exitosamente. Filas actualizadas: {filas_actualizadas}")
                return JsonResponse({
                    'success': True,
                    'message': 'Secuencia anulada correctamente',
                    'filas_actualizadas': filas_actualizadas
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'No se pudo anular la secuencia'
                })

    except Exception as e:
        print(f"❌ Error al anular secuencia: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': f'Error al anular secuencia: {str(e)}'
        }, status=500)
    
@csrf_exempt
def activar_secuencia_detalle(request):
    """
    Vista para activar una secuencia específica
    UPDATE inv_piqueo_secuencial_deta_tbl 
    SET ESTADO = 'ACTIVO' 
    WHERE SECUENCIAL_DETA_ID = secuencial_deta_id
    """
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'message': 'No autenticado'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        secuencial_deta_id = data.get('secuencial_deta_id')

        if not secuencial_deta_id:
            return JsonResponse({
                'success': False,
                'message': 'secuencial_deta_id requerido'
            })

        print(f"✅ Activando secuencia detalle ID: {secuencial_deta_id}")

        with connection.cursor() as cursor:
            # Verificar que existe
            cursor.execute("""
                SELECT ESTADO FROM inv_piqueo_secuencial_deta_tbl
                WHERE SECUENCIAL_DETA_ID = %s
            """, [secuencial_deta_id])

            row = cursor.fetchone()

            if not row:
                return JsonResponse({
                    'success': False,
                    'message': 'Secuencia no encontrada'
                })

            estado_actual = row[0]

            if estado_actual == 'ACTIVO':
                return JsonResponse({
                    'success': False,
                    'message': 'La secuencia ya está activa'
                })

            # Actualizar a ACTIVO
            cursor.execute("""
                UPDATE inv_piqueo_secuencial_deta_tbl
                SET ESTADO = 'ACTIVO'
                WHERE SECUENCIAL_DETA_ID = %s
            """, [secuencial_deta_id])

            filas_actualizadas = cursor.rowcount

            if filas_actualizadas > 0:
                print(f"✅ Secuencia activada exitosamente")
                return JsonResponse({
                    'success': True,
                    'message': 'Secuencia activada correctamente',
                    'filas_actualizadas': filas_actualizadas
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'No se pudo activar la secuencia'
                })

    except Exception as e:
        print(f"❌ Error al activar secuencia: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': f'Error al activar secuencia: {str(e)}'
        }, status=500)

@csrf_exempt
def obtener_datos_tienda_piqueo_manual(request):
    """
    Vista para obtener sbs_no y store_no antes de abrir el modal de piqueo manual
    Query: SELECT sbs_no, store_no FROM jde_general 
           WHERE sap_werks = (SELECT SUBSTR(kostl, -4) FROM sap_hcm.ms_colaboradores WHERE cedide_mf = cedula)
    """
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'message': 'No autenticado'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)

    try:
        usuario = request.session.get('usuario', {})
        cedula = usuario.get('cedula', '')

        if not cedula:
            return JsonResponse({
                'success': False,
                'message': 'No se encontró la cédula del usuario'
            })

        print(f"🔍 Obteniendo datos de tienda para cédula: {cedula}")

        with connection.cursor() as cursor:
            # Ejecutar el query para obtener sbs_no y store_no
            cursor.execute("""
                SELECT sbs_no, store_no  
                FROM jde_general@DBL_CLOUDFRIDTMAN.REDBDD.REDPROD.ORACLEVCN.COM 
                WHERE sap_werks = (
                    SELECT SUBSTR(kostl, -4)  
                    FROM sap_hcm.ms_colaboradores 
                    WHERE cedide_mf = :cedula
                )
            """, {'cedula': cedula})

            row = cursor.fetchone()

            if not row:
                print(f"⚠️ No se encontraron datos de tienda para la cédula: {cedula}")
                return JsonResponse({
                    'success': False,
                    'message': 'No se encontraron datos de tienda para el usuario'
                })

            sbs_no, store_no = row

            print(f"✅ Datos de tienda obtenidos - SBS_NO: {sbs_no}, STORE_NO: {store_no}")

            return JsonResponse({
                'success': True,
                'sbs_no': sbs_no,
                'store_no': store_no,
                'cedula': cedula
            })

    except Exception as e:
        print(f"❌ Error al obtener datos de tienda: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': f'Error al obtener datos de tienda: {str(e)}'
        }, status=500)
    
@csrf_exempt
def validar_codigo_barras_piqueo_manual(request):
    """
    Vista para validar código de barras antes de agregarlo al piqueo manual
    Query: SELECT nvl(count(*),0)
           FROM INVN_SBS@DBL_MCO1.RPRODS a, invn_sbs_qty@DBL_MCO1.RPRODS b 
           WHERE a.item_sid=b.item_sid
           AND B.sbs_no=? AND B.store_no=?
           AND local_upc = ?
           AND B.qty<>0
           AND LENGTH(local_upc)>12
    """
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'message': 'No autenticado'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        codigo_barras = data.get('codigo_barras')
        sbs_no = data.get('sbs_no')
        store_no = data.get('store_no')

        if not codigo_barras or not sbs_no or not store_no:
            return JsonResponse({
                'success': False,
                'message': 'Faltan parámetros requeridos'
            })

        print(f"🔍 Validando código de barras: {codigo_barras}")
        print(f"   - SBS_NO: {sbs_no}")
        print(f"   - STORE_NO: {store_no}")

        # COMENTADO: Validación temporalmente deshabilitada para permitir cualquier ingreso
        # with connection.cursor() as cursor:
        #     # Ejecutar query de validación
        #     cursor.execute("""
        #         SELECT nvl(count(*),0)
        #         FROM INVN_SBS@DBL_MCO1.RPRODS a, 
        #              invn_sbs_qty@DBL_MCO1.RPRODS b 
        #         WHERE a.item_sid = b.item_sid
        #         AND b.sbs_no = :sbs_no
        #         AND b.store_no = :store_no
        #         AND a.local_upc = :local_upc
        #         AND b.qty <> 0
        #         AND LENGTH(a.local_upc) > 12
        #     """, {
        #         'sbs_no': sbs_no,
        #         'store_no': store_no,
        #         'local_upc': codigo_barras
        #     })

        #     resultado = cursor.fetchone()
        #     count = resultado[0] if resultado else 0

        #     print(f"📊 Resultado validación: {count}")

        #     if count > 0:
        #         # Código de barras válido
        #         print(f"✅ Código de barras válido: {codigo_barras}")
        #         return JsonResponse({
        #             'success': True,
        #             'valido': True,
        #             'message': 'Código de barras válido',
        #             'count': count
        #         })
        #     else:
        #         # Código de barras no encontrado o sin stock
        #         print(f"⚠️ Código de barras no válido: {codigo_barras}")
        #         return JsonResponse({
        #             'success': True,
        #             'valido': False,
        #             'message': 'El código de barras no se encuentra registrado en la base de datos',
        #             'count': 0
        #         })
        
        # SIEMPRE RETORNAR VÁLIDO (VALIDACIÓN DESHABILITADA)
        print(f"✅ Validación deshabilitada. Aceptando código: {codigo_barras}")
        return JsonResponse({
            'success': True,
            'valido': True,
            'message': 'Código de barras aceptado (Validación Deshabilitada)',
            'count': 1  # Retornar 1 para simular que existe
        })

    except Exception as e:
        print(f"❌ Error al validar código de barras: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': f'Error al validar código de barras: {str(e)}'
        }, status=500)
    
@csrf_exempt
def guardar_piqueo_manual(request):
    """
    Vista para guardar el piqueo manual completo
    Realiza los siguientes INSERT en orden:
    1. inv_piqueo_secuencial_tbl
    2. INV_PIQUEO_SECUENCIAL_DETA_TBL
    3. PROCESOS_ESCANEO_TBL
    4. SESIONES_ESCANEO_TBL
    5. barcodes_escaneo_tbl (múltiples según SCAN_COUNT)
    """
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'message': 'No autenticado'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        conteo_id = data.get('conteo_id')
        items = data.get('items', [])
        sbs_no = data.get('sbs_no')
        store_no = data.get('store_no')
        cedula = data.get('cedula')

        # Validaciones
        if not conteo_id or not items or not sbs_no or not store_no or not cedula:
            return JsonResponse({
                'success': False,
                'message': 'Faltan parámetros requeridos'
            })

        if len(items) == 0:
            return JsonResponse({
                'success': False,
                'message': 'No hay items para guardar'
            })

        print(f"💾 Guardando piqueo manual...")
        print(f"   - Conteo ID: {conteo_id}")
        print(f"   - Total items: {len(items)}")
        print(f"   - SBS_NO: {sbs_no}")
        print(f"   - STORE_NO: {store_no}")
        print(f"   - Cédula: {cedula}")

        # Obtener DETALLE_PIQUEO_ID del conteo
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT MIN(dp.DETALLE_PIQUEO_ID)
                FROM INV_DETALLE_PIQUEOS_INVENTARIOS_TBL dp
                WHERE dp.PIQUEO_ID = :conteo_id
            """, {'conteo_id': conteo_id})
            
            result = cursor.fetchone()
            detalle_piqueo_id = result[0] if result and result[0] else None

            if not detalle_piqueo_id:
                return JsonResponse({
                    'success': False,
                    'message': 'No se encontró DETALLE_PIQUEO_ID para este conteo'
                })

            print(f"✅ DETALLE_PIQUEO_ID obtenido: {detalle_piqueo_id}")

            # ========== 1. Calcular siguiente secuencia de cabecera ==========
            cursor.execute("""
                SELECT NVL(MAX(NVL(secuencia_hasta, 0)), 0)
                FROM inv_piqueo_secuencial_tbl
                WHERE ubicacion = 'ST'
                  AND detalle_piqueo_id = :detalle_piqueo_id
            """, {'detalle_piqueo_id': detalle_piqueo_id})

            result = cursor.fetchone()
            max_secuencia_hasta = result[0] if result else 0
            secuencia_inicio = 1 if not max_secuencia_hasta else int(max_secuencia_hasta) + 1
            fecha_codigo = datetime.now().strftime('%Y%m%d')

            print(f"✅ MAX(secuencia_hasta): {max_secuencia_hasta}")
            print(f"✅ SECUENCIA_INICIO asignada: {secuencia_inicio}")

            # ========== 2. Crear UNA cabecera por guardado ==========
            secuencial_id_var = cursor.var(int)

            cursor.execute("""
                INSERT INTO inv_piqueo_secuencial_tbl (
                    DETALLE_PIQUEO_ID, UBICACION, ESTADO, SECUENCIA_INICIO, SECUENCIA_HASTA
                ) VALUES (
                    :detalle_piqueo_id, 'ST', 'ABIERTO', :secuencia_inicio, :secuencia_hasta
                ) RETURNING SECUENCIAL_ID INTO :secuencial_id
            """, {
                'detalle_piqueo_id': detalle_piqueo_id,
                'secuencia_inicio': secuencia_inicio,
                'secuencia_hasta': secuencia_inicio,
                'secuencial_id': secuencial_id_var
            })

            secuencial_id = secuencial_id_var.getvalue()[0]
            print(f"✅ Cabecera creada. SECUENCIAL_ID: {secuencial_id}")

            # Normalizar items y consolidar TODO el guardado en un solo detalle
            items_normalizados = []
            total_scan_count = 0

            for item in items:
                codigo_barras = item.get('codigoBarras')
                scan_count = int(item.get('conteo', 1) or 1)

                if scan_count < 1:
                    scan_count = 1
                if not codigo_barras:
                    raise ValueError('Se recibió un item sin código de barras')

                items_normalizados.append((codigo_barras, scan_count))
                total_scan_count += scan_count

            items_procesados = len(items_normalizados)

            # ========== 3. Crear UN detalle para la cabecera ==========
            secuencia_detalle = secuencia_inicio
            section_name = f"{fecha_codigo}{secuencial_id}{detalle_piqueo_id}ST{secuencia_detalle}"

            cursor.execute("""
                INSERT INTO INV_PIQUEO_SECUENCIAL_DETA_TBL (
                    SECUENCIAL_ID, DETALLE_PIQUEO_ID, UBICACION, SECUENCIA, CODIGO
                ) VALUES (
                    :secuencial_id, :detalle_piqueo_id, 'ST', :secuencia_detalle, :codigo
                )
            """, {
                'secuencial_id': secuencial_id,
                'detalle_piqueo_id': detalle_piqueo_id,
                'secuencia_detalle': secuencia_detalle,
                'codigo': section_name
            })
            print(f"✅ 3. Detalle único insertado. SECTION_NAME: {section_name}")

            # ========== 4. Crear UN proceso consolidado ==========
            proceso_id_var = cursor.var(int)

            cursor.execute("""
                INSERT INTO PROCESOS_ESCANEO_TBL (
                    TIMESTAMP_PROCESO, DEVICE_ID, PLATFORM,
                    TOTAL_SESSIONS, TOTAL_SCANS, START_TIME,
                    END_TIME, ESTADO
                ) VALUES (
                    SYSDATE, '000000001', 'HTML',
                    1, :total_scans, SYSDATE,
                    SYSDATE, 'RECIBIDO'
                ) RETURNING PROCESO_ID INTO :proceso_id
            """, {
                'total_scans': total_scan_count,
                'proceso_id': proceso_id_var
            })

            proceso_id = proceso_id_var.getvalue()[0]
            print(f"✅ 4. PROCESO_ID insertado: {proceso_id}")

            # ========== 5. Crear UNA sesión consolidada ==========
            sesion_id_var = cursor.var(int)

            cursor.execute("""
                INSERT INTO SESIONES_ESCANEO_TBL (
                    PROCESO_ID, SECTION_NAME, START_TIME,
                    END_TIME, SCAN_COUNT, CEDULA
                ) VALUES (
                    :proceso_id, :section_name, SYSDATE,
                    SYSDATE, :scan_count, :cedula
                ) RETURNING SESION_ID INTO :sesion_id
            """, {
                'proceso_id': proceso_id,
                'section_name': section_name,
                'scan_count': total_scan_count,
                'cedula': cedula,
                'sesion_id': sesion_id_var
            })

            sesion_id = sesion_id_var.getvalue()[0]
            print(f"✅ 5. SESION_ID insertado: {sesion_id}")

            # ========== 6. Insertar barcodes detallados en la sesión única ==========
            orden_global = 1
            for codigo_barras, scan_count in items_normalizados:
                print(f"📦 Insertando barcode: {codigo_barras} x {scan_count}")
                for _ in range(scan_count):
                    cursor.execute("""
                        INSERT INTO barcodes_escaneo_tbl (
                            SESION_ID, PROCESO_ID, CODIGO_BARRAS,
                            ORDEN_ESCANEO, FECHA_CREACION
                        ) VALUES (
                            :sesion_id, :proceso_id, :codigo_barras,
                            :orden_escaneo, SYSDATE
                        )
                    """, {
                        'sesion_id': sesion_id,
                        'proceso_id': proceso_id,
                        'codigo_barras': codigo_barras,
                        'orden_escaneo': orden_global
                    })
                    orden_global += 1

            print(f"✅ 6. Registros en barcodes_escaneo_tbl insertados: {total_scan_count}")

            # En modelo de detalle único, secuencia_hasta se fija igual a secuencia_inicio.
            # Se establece en el INSERT de cabecera para evitar conflictos del trigger al actualizar.
            secuencia_hasta = secuencia_inicio
            print(f"✅ secuencia_hasta definida en cabecera: {secuencia_hasta}")

            # Commit de la transacción
            connection.commit()

            print(f"\n🎉 PIQUEO MANUAL GUARDADO EXITOSAMENTE")
            print(f"   - Items procesados: {items_procesados}")
            print(f"   - Total scan_count: {total_scan_count}")

            return JsonResponse({
                'success': True,
                'message': f'Piqueo manual guardado exitosamente',
                'items_procesados': items_procesados,
                'total_scan_count': total_scan_count,
                'detalle_piqueo_id': detalle_piqueo_id,
                'secuencial_id': secuencial_id,
                'secuencia_inicio': secuencia_inicio,
                'secuencia_hasta': secuencia_hasta
            })

    except Exception as e:
        # Rollback en caso de error
        connection.rollback()
        
        print(f"❌ Error al guardar piqueo manual: {e}")
        import traceback
        traceback.print_exc()
        
        return JsonResponse({
            'success': False,
            'message': f'Error al guardar piqueo manual: {str(e)}'
        }, status=500)


def imprimir_acta_preliminar_pdf(request, piqueo_id):
    """
    Vista para generar PDF del acta preliminar
    """
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'message': 'No autenticado'}, status=401)

    try:
        print(f"🖨️ [IMPRIMIR_ACTA] Generando PDF para piqueo_id: {piqueo_id}")
        
        with connection.cursor() as cursor:
            # Obtener datos del acta preliminar: intentar primero con PAIS/CONCEPTO
            try:
                cursor.execute("""
                    SELECT 
                        p.piqueo_id, p.centro, p.almacen, p.numero_conteo, p.empresa, p.pais, p.concepto,
                        p.tienda, p.fecha_primer_conteo, p.fecha_segundo_conteo,
                        p.jefe_tienda, p.subjefe_tienda, p.auxiliar_ventas, p.auxiliar_caja,
                        p.auxiliar_bodega, p.auxiliar_operativo, p.asistente_opertaivo_inventario,
                        p.jefe_inventarios, p.auditor_interno, p.contado, p.gerente_regional,
                        p.supervisor_comercial, 
                        p.stock_sap_descripcion_calzado, p.stock_sap_valor_calzado,
                        p.stock_sap_descripcion_ropa, p.stock_sap_valor_ropa, 
                        p.stock_sap_descripcion_accesorio, p.stock_sap_valor_accesorio,
                        p.stock_sap_descripcion_fundas, p.stock_sap_valor_fundas, 
                        p.stock_sap_descripcion_otros, p.stock_sap_valor_otros,
                        p.stock_sap_total,
                        p.cantidad_marcas, p.cantidad_lineas, p.cantidad_items,
                        p.cantidad_items_faltantes, p.cantidad_items_sobrantes,
                        p.valor_items_faltantes, p.valor_items_sobrantes,
                        p.codigo_inventario, p.lineas_diferencias, p.hora_genero_informe_inven_sap,
                        p.toma_fisica_grupo, p.confirmo_encerado_guia_remi,
                        p.fecha_toma_fisica_anterior, p.cantidad_item_ultimo_inv,
                        p.numero_toma_fisica_anterior, p.cantidad_item_acumula_anual, 
                        p.valor_efectivo, p.valor_facturas,
                        p.valor_cheques, p.fondo_caja, p.fondo_sueltos, p.total,
                        p.sucursal, p.ultima_fact_caja1, p.ultima_fact_caja2,
                        p.ultima_fact_caja3, p.ultima_fact_caja4, p.ultima_fact_caja5,
                        p.ultimo_doc_guia_remision, p.ultimo_doc_nota_credit,
                        p.cargo_1, p.nombre_cargo_1, p.cargo_2, p.nombre_cargo_2,
                        p.cargo_3, p.nombre_cargo_3, p.cargo_4, p.nombre_cargo_4,
                        p.cargo_5, p.nombre_cargo_5, p.cargo_6, p.nombre_cargo_6,
                        p.cargo_7, p.nombre_cargo_7, p.cargo_8, p.nombre_cargo_8
                    FROM acta_preliminar_tbl p
                    WHERE p.piqueo_id = %s
                """, [piqueo_id])
                row = cursor.fetchone()
                if not row:
                    return JsonResponse({
                        'success': False, 
                        'message': 'No se encontró el acta preliminar para este conteo'
                    }, status=404)

                datos = {
                    'piqueo_id': row[0], 'centro': row[1], 'almacen': row[2], 'numero_conteo': row[3], 'empresa': row[4],
                    'pais': row[5], 'concepto': row[6], 'tienda': row[7], 'fecha_primer_conteo': row[8], 'fecha_segundo_conteo': row[9],
                    'jefe_tienda': row[10], 'subjefe_tienda': row[11], 'auxiliar_ventas': row[12], 'auxiliar_caja': row[13],
                    'auxiliar_bodega': row[14], 'auxiliar_operativo': row[15], 'asistente_opertaivo_inventario': row[16],
                    'jefe_inventarios': row[17], 'auditor_interno': row[18], 'contado': row[19], 'gerente_regional': row[20],
                    'supervisor_comercial': row[21], 
                    'stock_sap_descripcion_calzado': row[22], 'stock_sap_valor_calzado': row[23],
                    'stock_sap_descripcion_ropa': row[24], 'stock_sap_valor_ropa': row[25], 
                    'stock_sap_descripcion_accesorio': row[26], 'stock_sap_valor_accesorio': row[27],
                    'stock_sap_descripcion_fundas': row[28], 'stock_sap_valor_fundas': row[29], 
                    'stock_sap_descripcion_otros': row[30], 'stock_sap_valor_otros': row[31],
                    'stock_sap_total': row[32],
                    'cantidad_marcas': row[33], 'cantidad_lineas': row[34], 'cantidad_items': row[35],
                    'cantidad_items_faltantes': row[36], 'cantidad_items_sobrantes': row[37],
                    'valor_items_faltantes': row[38], 'valor_items_sobrantes': row[39],
                    'codigo_inventario': row[40], 'lineas_diferencias': row[41], 'hora_genero_informe_inven_sap': row[42],
                    'toma_fisica_grupo': row[43], 'confirmo_encerado_guia_remi': row[44],
                    'fecha_toma_fisica_anterior': row[45], 'cantidad_item_ultimo_inv': row[46],
                    'numero_toma_fisica_anterior': row[47], 'cantidad_item_acumula_anual': row[48], 
                    'valor_efectivo': row[49], 'valor_facturas': row[50],
                    'valor_cheques': row[51], 'fondo_caja': row[52], 'fondo_sueltos': row[53], 'total': row[54],
                    'sucursal': row[55], 'ultima_fact_caja1': row[56], 'ultima_fact_caja2': row[57],
                    'ultima_fact_caja3': row[58], 'ultima_fact_caja4': row[59], 'ultima_fact_caja5': row[60],
                    'ultimo_doc_guia_remision': row[61], 'ultimo_doc_nota_credit': row[62],
                    'cargo_1': row[63], 'nombre_cargo_1': row[64], 'cargo_2': row[65], 'nombre_cargo_2': row[66],
                    'cargo_3': row[67], 'nombre_cargo_3': row[68], 'cargo_4': row[69], 'nombre_cargo_4': row[70],
                    'cargo_5': row[71], 'nombre_cargo_5': row[72], 'cargo_6': row[73], 'nombre_cargo_6': row[74],
                    'cargo_7': row[75], 'nombre_cargo_7': row[76], 'cargo_8': row[77], 'nombre_cargo_8': row[78]
                }

            except Exception as e:
                # Si la DB no tiene las columnas PAIS/CONCEPTO, intentar consulta alternativa sin ellas
                print(f"⚠️ Error fetching with PAIS/CONCEPTO: {e}")
                cursor.execute("""
                    SELECT 
                        p.piqueo_id, p.centro, p.almacen, p.numero_conteo, p.empresa,
                        p.tienda, p.fecha_primer_conteo, p.fecha_segundo_conteo,
                        p.jefe_tienda, p.subjefe_tienda, p.auxiliar_ventas, p.auxiliar_caja,
                        p.auxiliar_bodega, p.auxiliar_operativo, p.asistente_opertaivo_inventario,
                        p.jefe_inventarios, p.auditor_interno, p.contado, p.gerente_regional,
                        p.supervisor_comercial, 
                        p.stock_sap_descripcion_calzado, p.stock_sap_valor_calzado,
                        p.stock_sap_descripcion_ropa, p.stock_sap_valor_ropa, 
                        p.stock_sap_descripcion_accesorio, p.stock_sap_valor_accesorio,
                        p.stock_sap_descripcion_fundas, p.stock_sap_valor_fundas, 
                        p.stock_sap_descripcion_otros, p.stock_sap_valor_otros,
                        p.stock_sap_total,
                        p.cantidad_marcas, p.cantidad_lineas, p.cantidad_items,
                        p.cantidad_items_faltantes, p.cantidad_items_sobrantes,
                        p.valor_items_faltantes, p.valor_items_sobrantes,
                        p.codigo_inventario, p.lineas_diferencias, p.hora_genero_informe_inven_sap,
                        p.toma_fisica_grupo, p.confirmo_encerado_guia_remi,
                        p.fecha_toma_fisica_anterior, p.cantidad_item_ultimo_inv,
                        p.numero_toma_fisica_anterior, p.cantidad_item_acumula_anual, 
                        p.valor_efectivo, p.valor_facturas,
                        p.valor_cheques, p.fondo_caja, p.fondo_sueltos, p.total,
                        p.sucursal, p.ultima_fact_caja1, p.ultima_fact_caja2,
                        p.ultima_fact_caja3, p.ultima_fact_caja4, p.ultima_fact_caja5,
                        p.ultimo_doc_guia_remision, p.ultimo_doc_nota_credit,
                        p.cargo_1, p.nombre_cargo_1, p.cargo_2, p.nombre_cargo_2,
                        p.cargo_3, p.nombre_cargo_3, p.cargo_4, p.nombre_cargo_4,
                        p.cargo_5, p.nombre_cargo_5, p.cargo_6, p.nombre_cargo_6,
                        p.cargo_7, p.nombre_cargo_7, p.cargo_8, p.nombre_cargo_8
                    FROM acta_preliminar_tbl p
                    WHERE p.piqueo_id = %s
                """, [piqueo_id])
                row = cursor.fetchone()
                if not row:
                    return JsonResponse({
                        'success': False, 
                        'message': 'No se encontró el acta preliminar para este conteo (fallback)'
                    }, status=404)

                datos = {
                    'piqueo_id': row[0], 'centro': row[1], 'almacen': row[2], 'numero_conteo': row[3], 'empresa': row[4],
                    'pais': '', 'concepto': '', 'tienda': row[5], 'fecha_primer_conteo': row[6], 'fecha_segundo_conteo': row[7],
                    'jefe_tienda': row[8], 'subjefe_tienda': row[9], 'auxiliar_ventas': row[10], 'auxiliar_caja': row[11],
                    'auxiliar_bodega': row[12], 'auxiliar_operativo': row[13], 'asistente_opertaivo_inventario': row[14],
                    'jefe_inventarios': row[15], 'auditor_interno': row[16], 'contado': row[17], 'gerente_regional': row[18],
                    'supervisor_comercial': row[19], 
                    'stock_sap_descripcion_calzado': row[20], 'stock_sap_valor_calzado': row[21],
                    'stock_sap_descripcion_ropa': row[22], 'stock_sap_valor_ropa': row[23], 
                    'stock_sap_descripcion_accesorio': row[24], 'stock_sap_valor_accesorio': row[25],
                    'stock_sap_descripcion_fundas': row[26], 'stock_sap_valor_fundas': row[27], 
                    'stock_sap_descripcion_otros': row[28], 'stock_sap_valor_otros': row[29],
                    'stock_sap_total': row[30],
                    'cantidad_marcas': row[31], 'cantidad_lineas': row[32], 'cantidad_items': row[33],
                    'cantidad_items_faltantes': row[34], 'cantidad_items_sobrantes': row[35],
                    'valor_items_faltantes': row[36], 'valor_items_sobrantes': row[37],
                    'codigo_inventario': row[38], 'lineas_diferencias': row[39], 'hora_genero_informe_inven_sap': row[40],
                    'toma_fisica_grupo': row[41], 'confirmo_encerado_guia_remi': row[42],
                    'fecha_toma_fisica_anterior': row[43], 'cantidad_item_ultimo_inv': row[44],
                    'numero_toma_fisica_anterior': row[45], 'cantidad_item_acumula_anual': row[46], 
                    'valor_efectivo': row[47], 'valor_facturas': row[48],
                    'valor_cheques': row[49], 'fondo_caja': row[50], 'fondo_sueltos': row[51], 'total': row[52],
                    'sucursal': row[53], 'ultima_fact_caja1': row[54], 'ultima_fact_caja2': row[55],
                    'ultima_fact_caja3': row[56], 'ultima_fact_caja4': row[57], 'ultima_fact_caja5': row[58],
                    'ultimo_doc_guia_remision': row[59], 'ultimo_doc_nota_credit': row[60],
                    'cargo_1': row[61], 'nombre_cargo_1': row[62], 'cargo_2': row[63], 'nombre_cargo_2': row[64],
                    'cargo_3': row[65], 'nombre_cargo_3': row[66], 'cargo_4': row[67], 'nombre_cargo_4': row[68],
                    'cargo_5': row[69], 'nombre_cargo_5': row[70], 'cargo_6': row[71], 'nombre_cargo_6': row[72],
                    'cargo_7': row[73], 'nombre_cargo_7': row[74], 'cargo_8': row[75], 'nombre_cargo_8': row[76]
                }
        
        # Generar PDF
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="acta_preliminar_{datos["numero_conteo"]}.pdf"'
        
        # Crear PDF
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib.colors import black, yellow, lightgrey
        from datetime import datetime
        from decimal import Decimal, InvalidOperation
        
        # Crear canvas
        p = canvas.Canvas(response, pagesize=A4)
        width, height = A4
        
        # Configuración de márgenes y espacios compactos
        margin = 30
        row_height = 11
        section_gap = 8
        
        # Función helper para dibujar celdas compactas
        def draw_cell(x, y, w, h, text, font_size=7, bold=False, center=False, bg_color=None):
            # Dibujar fondo si se especifica
            if bg_color:
                p.setFillColor(bg_color)
                p.rect(x, y, w, h, fill=1)
                p.setFillColor(black)
            
            # Dibujar borde
            p.setStrokeColor(black)
            p.rect(x, y, w, h)
            
            # Escribir texto
            font = "Helvetica-Bold" if bold else "Helvetica"
            p.setFont(font, font_size)
            
            if center:
                text_width = p.stringWidth(str(text), font, font_size)
                text_x = x + (w - text_width) / 2
            else:
                text_x = x + 3
            
            text_y = y + h/2 - font_size/3
            p.drawString(text_x, text_y, str(text))
        
        # ENCABEZADO COMPACTO
        y = height - 40
        
        # Título principal
        title_h = 20
        draw_cell(margin, y, width - 2*margin, title_h, "ACTA DE INVENTARIO FÍSICO", 
                 14, True, True)
        
        y -= title_h + section_gap
        
        # DOS RECUADROS LADO A LADO
        info_h = 12
        recuadro_w = (width - 2*margin - 20) / 2  # Dos recuadros con separación
        
        # RECUADRO IZQUIERDO - INFORMACIÓN EMPRESA/PADRON
        x_izq = margin
        y_recuadros = y

        # País
        draw_cell(x_izq, y_recuadros, recuadro_w - 80, info_h, "PAÍS:", 7, True)
        draw_cell(x_izq + recuadro_w - 80, y_recuadros, 80, info_h, datos.get('pais') or '', 7, center=True)
        y_recuadros -= info_h

        # Empresa
        draw_cell(x_izq, y_recuadros, recuadro_w - 80, info_h, "EMPRESA:", 7, True)
        draw_cell(x_izq + recuadro_w - 80, y_recuadros, 80, info_h, datos.get('empresa') or 'SUPERDEPORTE', 7, center=True)
        y_recuadros -= info_h

        # Concepto
        concepto_texto = datos.get('concepto') or ''
        draw_cell(x_izq, y_recuadros, recuadro_w - 80, info_h, "CONCEPTO:", 7, True)
        draw_cell(x_izq + recuadro_w - 80, y_recuadros, 80, info_h, concepto_texto, 7, center=True)
        y_recuadros -= info_h

        # Centro
        draw_cell(x_izq, y_recuadros, recuadro_w - 80, info_h, "CENTRO:", 7, True)
        draw_cell(x_izq + recuadro_w - 80, y_recuadros, 80, info_h, datos.get('centro') or '', 7, center=True)
        y_recuadros -= info_h

        # Almacén
        draw_cell(x_izq, y_recuadros, recuadro_w - 80, info_h, "ALMACÉN:", 7, True)
        draw_cell(x_izq + recuadro_w - 80, y_recuadros, 80, info_h, datos.get('almacen') or '', 7, center=True)
        y_recuadros -= info_h

        # (TIENDA eliminado — usamos SUCURSAL/ALMACÉN arriba para evitar duplicados)
        # RECUADRO DERECHO - HORARIOS
        x_der = margin + recuadro_w + 20
        y_horarios = y
        
        # Fecha del conteo
        if datos['fecha_primer_conteo']:
            try:
                fecha_conteo = datos['fecha_primer_conteo'].strftime("%A, %d de %B de %Y")
            except:
                fecha_conteo = datetime.now().strftime("%A, %d de %B de %Y")
        else:
            fecha_conteo = datetime.now().strftime("%A, %d de %B de %Y")
        
        draw_cell(x_der, y_horarios, recuadro_w, info_h, fecha_conteo, 7, True, True)
        y_horarios -= info_h

        # Ajustar y al menor espacio usado por los recuadros izquierdo/derecho
        y = min(y_recuadros, y_horarios) - section_gap

        # Hora de inicio
        hora_inicio = "7:00 AM"
        if datos['fecha_primer_conteo']:
            try:
                hora_inicio = datos['fecha_primer_conteo'].strftime("%I:%M %p")
            except:
                pass
        
        draw_cell(x_der, y_horarios, recuadro_w - 60, info_h, "Hora de inicio:", 7)
        draw_cell(x_der + recuadro_w - 60, y_horarios, 60, info_h, hora_inicio, 7, center=True)
        y_horarios -= info_h
        
        # Hora de finalización
        hora_fin = "9:00 PM"
        if datos['fecha_segundo_conteo']:
            try:
                hora_fin = datos['fecha_segundo_conteo'].strftime("%I:%M %p")
            except:
                pass
        
        draw_cell(x_der, y_horarios, recuadro_w - 60, info_h, "Hora de finalización:", 7)
        draw_cell(x_der + recuadro_w - 60, y_horarios, 60, info_h, hora_fin, 7, center=True)
        
        y -= 3 * info_h + section_gap
        
        # DOS TABLAS DE PERSONAL LADO A LADO
        tabla_w = (width - 2*margin - 20) / 2  # Dos tablas con separación
        
        # TABLA IZQUIERDA - PERSONAL EJECUTANDO TOMA FÍSICA
        x_izq = margin
        y_tablas = y
        
        # Título tabla izquierda
        draw_cell(x_izq, y_tablas, tabla_w, info_h, "Personal ejecutando Toma Física", 7, True, True)
        y_personal = y_tablas - info_h
        
        personal_data = [
            ("Jefe de Tienda", datos['jefe_tienda'] or 0),
            ("Subjefe de Tienda", datos['subjefe_tienda'] or 0),
            ("Auxiliar de Ventas", datos['auxiliar_ventas'] or 0),
            ("Auxiliar de Caja", datos['auxiliar_caja'] or 0),
            ("Auxiliar de Bodega", datos['auxiliar_bodega'] or 0),
            ("Auxiliar Operativo", datos['auxiliar_operativo'] or 0)
        ]
        
        for cargo, cant in personal_data:
            draw_cell(x_izq, y_personal - row_height, tabla_w - 25, row_height, cargo, 6)
            draw_cell(x_izq + tabla_w - 25, y_personal - row_height, 25, row_height, str(cant), 6, center=True)
            y_personal -= row_height
        
        # TABLA DERECHA - PERSONAL ADMINISTRATIVO PRESENTE
        x_der = margin + tabla_w + 20
        y_admin = y_tablas
        
        # Título tabla derecha
        draw_cell(x_der, y_admin, tabla_w, info_h, "Personal Administrativo presente", 7, True, True)
        y_admin -= info_h
        
        admin_data = [
            ("Asistente Operativo Inventarios", datos['asistente_opertaivo_inventario'] or 0),
            ("Jefe de Inventarios", datos['jefe_inventarios'] or 0),
            ("Auditor Interno", datos['auditor_interno'] or 0),
            ("Contado", datos['contado'] or 0),
            ("Gerente Regional", datos['gerente_regional'] or 0),
            ("Supervisor Comercial", datos['supervisor_comercial'] or 0)
        ]
        
        for item, valor in admin_data:
            draw_cell(x_der, y_admin - row_height, tabla_w - 25, row_height, item, 6)
            draw_cell(x_der + tabla_w - 25, y_admin - row_height, 25, row_height, str(valor), 6, center=True)
            y_admin -= row_height
        
        y = min(y_personal, y_admin) - section_gap
        
        # DOS TABLAS DE STOCK E INVENTARIO
        tabla_w = (width - 2*margin - 20) / 2  # Dos tablas con separación
        y_min = y - 15  # Definir y_min antes de usar
        
        # TABLA IZQUIERDA - STOCK SAP
        x_izq = margin
        y_stock = y_min
        
        # Título tabla stock
        draw_cell(x_izq, y_stock, tabla_w, info_h, "Stock SAP", 7, True, True)
        y_stock -= info_h
        
        # Construir datos de stock desde los campos separados
        stock_data = []
        stock_total = datos.get('stock_sap_total', 0)
        
        # Procesar los campos de stock SAP por categoría
        categorias = [
            ('calzado', 'CALZADO'),
            ('ropa', 'ROPA'), 
            ('accesorio', 'ACCESORIOS'),
            ('fundas', 'FUNDAS'),
            ('otros', 'OTROS')
        ]
        
        # Siempre incluir todas las categorías, mostrar 0 si no hay valor
        suma_categorias = 0
        for key, label in categorias:
            descripcion = datos.get(f'stock_sap_descripcion_{key}')
            raw_val = datos.get(f'stock_sap_valor_{key}')
            # Normalizar: eliminar espacios y separadores de miles (coma/espacio)
            if raw_val in (None, ''):
                valor = Decimal(0)
            else:
                s = str(raw_val).strip().replace(' ', '')
                # Asumir que la coma es separador de miles => eliminarla
                s = s.replace(',', '')
                # Si hay múltiples puntos, probablemente son separadores de miles
                if s.count('.') > 1:
                    s = s.replace('.', '')
                try:
                    valor = Decimal(s)
                except (InvalidOperation, Exception):
                    # Fallback: intentar eliminar cualquier separador y parsear
                    try:
                        valor = Decimal(s.replace('.', '').replace(',', ''))
                    except Exception:
                        valor = Decimal(0)

            stock_data.append((label, valor))
            suma_categorias += valor

        # Si no viene stock_sap_total, calcularlo como la suma de categorías
        if not stock_total:
            stock_total = suma_categorias

        # Agregar total al final (mostrar 0 si corresponde)
        stock_data.append(("Total:", Decimal(int(stock_total))))

        for item, valor in stock_data:
            is_total = item == "Total:"
            # Formatear mostrando separador de miles; mantener decimales si existen
            try:
                if isinstance(valor, Decimal):
                    if valor == valor.to_integral_value():
                        display_val = f"{int(valor):,}"
                    else:
                        display_val = f"{valor:,.2f}"
                else:
                    # valor puede ser int/float
                    if float(valor).is_integer():
                        display_val = f"{int(valor):,}"
                    else:
                        display_val = f"{float(valor):,.2f}"
            except Exception:
                display_val = str(valor)

            draw_cell(x_izq, y_stock - row_height, tabla_w - 60, row_height, item, 6, is_total)
            draw_cell(x_izq + tabla_w - 60, y_stock - row_height, 60, row_height, display_val, 6, is_total, True)
            y_stock -= row_height
        
        # TABLA DERECHA - ITEMS INVENTARIADOS
        x_der = margin + tabla_w + 20
        y_items = y_min
        
        # Título tabla items
        draw_cell(x_der, y_items, tabla_w, info_h, "Items inventariados", 7, True, True)
        y_items -= info_h
        
        items_data = [
            ("Cantidad MARCAS:", datos['cantidad_marcas'] or 31, False),
            ("Cantidad LÍNEAS:", datos['cantidad_lineas'] or 35, False),
            ("Cantidad ITEMS:", datos['cantidad_items'] or 16253, False),
            ("Cantidad Items faltantes:", datos['cantidad_items_faltantes'] or -218, False),
            ("Cantidad Items sobrantes:", datos['cantidad_items_sobrantes'] or 40, False),
            ("Valor Items faltantes:", f"-${abs(datos['valor_items_faltantes'] or 6376):,.2f}", False),
            ("Valor Items sobrantes:", f"${datos['valor_items_sobrantes'] or 1114:,.2f}", False),
            ("Código de inventario:", datos['codigo_inventario'] or '25519MQN1TO', False),
            ("Líneas de diferencias:", datos['lineas_diferencias'] or '', False)
        ]
        
        for item, valor, resaltar in items_data:
            bg_color = None  # Sin fondo de color
            # Ajustar ancho según el contenido
            if "Código" in item:
                label_width = tabla_w - 80  # Más espacio para el código
                value_width = 80
            else:
                label_width = tabla_w - 60
                value_width = 60
                
            draw_cell(x_der, y_items - row_height, label_width, row_height, item, 6, bg_color=bg_color)
            draw_cell(x_der + label_width, y_items - row_height, value_width, row_height, str(valor), 6, center=True, bg_color=bg_color)
            y_items -= row_height
        
        # Información adicional en tabla derecha
        if datos['hora_genero_informe_inven_sap']:
            try:
                hora_informe = datos['hora_genero_informe_inven_sap'].strftime("%I:%M %p")
            except:
                hora_informe = "2:00 PM"
        else:
            hora_informe = "2:00 PM"
            
        draw_cell(x_der, y_items - row_height, tabla_w - 60, row_height, "Hora: generó Informe Invensap", 6)
        draw_cell(x_der + tabla_w - 60, y_items - row_height, 60, row_height, hora_informe, 6, center=True)
        y_items -= row_height
        
        draw_cell(x_der, y_items - row_height, tabla_w - 60, row_height, "Toma Física grupo:", 6)
        draw_cell(x_der + tabla_w - 60, y_items - row_height, 60, row_height, datos['toma_fisica_grupo'] or 'Ropa', 6, center=True)
        y_items -= row_height
        
        y_min = min(y_stock, y_items) - 15
        
        # TABLA COMPLETA - INFORMACIÓN ADICIONAL DEL INVENTARIO
        tabla_completa_w = width - 2*margin
        
        # Año anterior dinámico (ej. si hoy es 2026, mostrar 2025)
        año_anterior = timezone.now().year - 1
        info_adicional_data = [
            ("Se confirmó encerado de guías de remisión:", datos['confirmo_encerado_guia_remi'] or 'NO'),
            ("Fecha de la toma física de inventario anterior:", 
             datos['fecha_toma_fisica_anterior'].strftime("%A, %d de %B de %Y") if datos['fecha_toma_fisica_anterior'] else 'miércoles, 19 de febrero de 2025'),
            (f"Cantidad Items por toma física parcial del último inventario en {año_anterior}:", datos['cantidad_item_ultimo_inv'] or ''),
            (f"Número de tomas Físicas anteriores a la presente en el año {año_anterior}:", datos['numero_toma_fisica_anterior'] or 0),
            ("Número de toma Física actual:", datos['numero_conteo'] or 1),
            ("Cantidad Items por toma física parcial ACUMULATIVO ANUAL:", f"{datos['cantidad_item_acumula_anual'] }")
        ]
        
        for item, valor in info_adicional_data:
            draw_cell(margin, y_min - row_height, tabla_completa_w - 100, row_height, item, 6)
            draw_cell(margin + tabla_completa_w - 100, y_min - row_height, 100, row_height, str(valor), 6, center=True)
            y_min -= row_height
        
        y_min -= 25  # Más espacio entre la tabla adicional y la siguiente sección
        
        # SECCIÓN INFERIOR - CAJA Y DOCUMENTOS (POSICIÓN CORREGIDA)
        seccion_w = (width - 2*margin - 20) / 2
        y_seccion_inferior = y_min  # Usar la posición actual correcta
        
        # VALORES DE CAJA CHICA (IZQUIERDA)
        x_caja = margin
        draw_cell(x_caja, y_seccion_inferior, seccion_w, 10, "VALORES DE CAJA", 6, True, True)
        y_caja = y_seccion_inferior - 10
        
        caja_data = [
            ("Efectivo", f"${datos['valor_efectivo'] or 100:.0f}"),
            ("Facturas", f"${datos['valor_facturas'] or 100:.0f}"),
            ("Cheques", f"${datos['valor_cheques'] or 0:.0f}"),
            ("Fondo de Caja", f"${datos['fondo_caja'] or 100:.0f}"),
            ("Fondo de Sueltos", f"${datos['fondo_sueltos'] or 100:.0f}"),
            ("TOTAL", f"${datos['total'] or 400:.0f}")
        ]
        
        for item, valor in caja_data:
            is_total = item == "TOTAL"
            draw_cell(x_caja, y_caja - 9, seccion_w - 50, 9, item, 5, is_total)
            draw_cell(x_caja + seccion_w - 50, y_caja - 9, 50, 9, valor, 5, is_total, True)
            y_caja -= 9
        
        # CENTRO SAP después del TOTAL de caja con más espacio
        y_caja -= 15  # Más espacio después del total
        centro_sap_w = seccion_w // 2
        draw_cell(x_caja, y_caja, centro_sap_w, 12, "CENTRO SAP", 6, True, True)
        draw_cell(x_caja + centro_sap_w, y_caja, centro_sap_w, 12, datos['almacen'] or 'MQN1', 6, True, True)
        
        # DOCUMENTOS SUCURSAL (DERECHA)  
        x_docs = margin + seccion_w + 20
        y_docs = y_seccion_inferior
        # Evitar duplicar 'S.A.' si ya viene en empresa
        empresa = datos.get('empresa') or 'SUPERDEPORTE'
        empresa_label = empresa if empresa.strip().upper().endswith('S.A.') else f"{empresa} S.A."
        pais_label = datos.get('pais') or ''
        draw_cell(x_docs, y_docs, seccion_w - 30, 10, f"Sucursal {empresa_label} - {pais_label}", 6, True)

        # Mostrar sucursal y opcionalmente sap_hcm_mcu separado por ' / ' sólo si sap_hcm_mcu existe
        sucursal_label = datos.get('sucursal') or '009'
        sap_mcu = datos.get('sap_hcm_mcu')
        if sap_mcu:
            sucursal_line = f"{sucursal_label} / {sap_mcu}"
        else:
            sucursal_line = f"{sucursal_label}"

        draw_cell(x_docs + seccion_w - 30, y_docs, 30, 10, sucursal_line, 6, True, True)
        
        y_docs -= 10
        draw_cell(x_docs, y_docs, seccion_w, 8, "Última factura de venta Número:", 5, True)
        y_docs -= 8
        
        # Mostrar las 5 facturas completas
        facturas_data = [
            (datos['ultima_fact_caja1'] or '009-032-000021579', 'caja1'),
            (datos['ultima_fact_caja2'] or '009-033-000001004', 'caja2'), 
            (datos['ultima_fact_caja3'] or '009-031-000047444', 'caja3'),
            (datos['ultima_fact_caja4'] or '', 'caja4'),
            (datos['ultima_fact_caja5'] or '', 'caja5')
        ]
        
        for factura, caja in facturas_data:
            draw_cell(x_docs, y_docs - 7, seccion_w - 30, 7, factura, 4)  # Más compacto
            draw_cell(x_docs + seccion_w - 30, y_docs - 7, 30, 7, caja, 4, center=True)
            y_docs -= 7
        
        y_docs -= 12  # Más espacio después de la caja 5
        draw_cell(x_docs, y_docs, seccion_w, 8, "Último número documento:", 5, True)
        y_docs -= 8
        
        documentos_data = [
            (datos['ultimo_doc_guia_remision'] or '009-040-000010312', 'Guía Remisión'),
            (datos['ultimo_doc_nota_credit'] or '047-030-000191413', 'Nota Crédito')
        ]
        
        for doc, tipo in documentos_data:
            draw_cell(x_docs, y_docs - 8, seccion_w - 45, 8, doc, 5)
            draw_cell(x_docs + seccion_w - 45, y_docs - 8, 45, 8, tipo, 5, center=True)
            y_docs -= 8
        
        # Calcular posición para firmas (sin centro SAP aquí)
        y_bottom = min(y_caja, y_docs) - 15
        
        # FIRMAS DINÁMICAS BASADAS EN BASE DE DATOS
        draw_cell(margin, y_bottom, width - 2*margin, 12, "FIRMAS DE RESPONSABILIDAD", 7, True, True)
        y_bottom -= 25  # Más espacio después del título
        
        # Construir lista de firmas válidas desde la base de datos
        firmas_validas = []
        for i in range(1, 9):  # CARGO_1 hasta CARGO_8
            cargo = datos.get(f'cargo_{i}', '').strip() if datos.get(f'cargo_{i}') else ''
            nombre = datos.get(f'nombre_cargo_{i}', '').strip() if datos.get(f'nombre_cargo_{i}') else ''
            
            # Solo agregar si ambos campos tienen contenido
            if cargo and nombre:
                firmas_validas.append({
                    'cargo': cargo,
                    'nombre': nombre
                })
        
        # Si no hay firmas en base de datos, usar firmas por defecto
        if not firmas_validas:
            firmas_validas = [
                {'cargo': 'Gerente Operaciones', 'nombre': ''},
                {'cargo': 'Jefe Inventarios', 'nombre': ''},
                {'cargo': 'Supervisor Comercial', 'nombre': ''},
                {'cargo': 'Auditor Interno', 'nombre': ''}
            ]
        
        # Calcular layout dinámico basado en cantidad de firmas
        total_firmas = len(firmas_validas)
        firmas_por_fila = 4 if total_firmas > 4 else total_firmas
        firma_w = (width - 2*margin - 30) / firmas_por_fila
        
        for i, firma_data in enumerate(firmas_validas):
            fila = i // firmas_por_fila
            col = i % firmas_por_fila
            x = margin + col * (firma_w + 10)
            y = y_bottom - fila * 60  # Máximo espacio entre filas (60px)
            
            # Línea para firma bien separada
            p.line(x, y - 18, x + firma_w, y - 18)
            
            # Mostrar nombre si existe, sino solo cargo
            if firma_data['nombre']:
                # Nombre en línea superior
                p.setFont("Helvetica-Bold", 6)
                text_width = p.stringWidth(firma_data['nombre'], "Helvetica-Bold", 6)
                p.drawString(x + (firma_w - text_width) / 2, y - 27, firma_data['nombre'])
                
                # Cargo en línea inferior
                p.setFont("Helvetica", 5)
                text_width = p.stringWidth(firma_data['cargo'], "Helvetica", 5)
                p.drawString(x + (firma_w - text_width) / 2, y - 35, firma_data['cargo'])
            else:
                # Solo cargo si no hay nombre
                p.setFont("Helvetica", 5)
                text_width = p.stringWidth(firma_data['cargo'], "Helvetica", 5)
                p.drawString(x + (firma_w - text_width) / 2, y - 30, firma_data['cargo'])
        
        # Finalizar PDF
        p.showPage()
        p.save()
        
        print(f"✅ PDF generado exitosamente para conteo: {datos['numero_conteo']}")
        return response
        
    except Exception as e:
        print(f"❌ Error al generar PDF: {e}")
        import traceback
        traceback.print_exc()
        
        return JsonResponse({
            'success': False,
            'message': f'Error al generar PDF: {str(e)}'
        }, status=500)


@csrf_exempt
def acta_preliminar(request):
    """
    Vista para mostrar conteos en estado SEGUNDO_CONTEO y permitir 
    imprimir actas y generar nuevas actas preliminares
    """
    if 'usuario' not in request.session:
        return redirect('login')

    perfil = request.session.get('perfil_seleccionado', {}).get('nombre', '')
    usuario_sesion = request.session.get('usuario', {})
    usuario_cedula = usuario_sesion.get('cedula', '')

    # OBTENER FILTROS (GET o POST/AJAX)
    filtros = {}
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            data = json.loads(request.body)
            filtros = data.get('filtros', {})
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Error en los datos de filtros'}, status=400)
    elif request.method == 'GET':
        filtros['estado'] = request.GET.get('estado', '').strip()
        filtros['centro'] = request.GET.get('centro', '').strip()
        filtros['almacen'] = request.GET.get('almacen', '').strip()

    with connection.cursor() as cursor:
        # Query para obtener conteos con estado SEGUNDO_CONTEO o ACTA_PRELIMINAR
        query = """
            SELECT piqueo_id, numero_conteo, estado, fecha_inicio, fecha_fin,
            nombre_empleado_func(usuario_responsable) as nm_responsable, 
            usuario_creacion, centro, almacen
            FROM INV_PIQUEOS_INVENTARIO_TBL
            WHERE usuario_responsable = %s
            AND UPPER(estado) IN ('SEGUNDO_CONTEO', 'ACTA_PRELIMINAR')
        """
        params = [usuario_cedula]

        # APLICAR FILTROS ADICIONALES SI SE PROPORCIONAN
        if filtros.get('centro'):
            query += " AND centro = %s"
            params.append(filtros['centro'])

        if filtros.get('almacen'):
            query += " AND almacen = %s"
            params.append(filtros['almacen'])

        query += " ORDER BY fecha_inicio DESC"

        print(f"🔍 [ACTA_PRELIMINAR] Query ejecutado: {query}")
        print(f"🔍 [ACTA_PRELIMINAR] Parámetros: {params}")
        cursor.execute(query, params)
        rows = cursor.fetchall()

    conteos = [
        {
            'piqueo_id': row[0],
            'numero_conteo': row[1],
            'estado': row[2],
            'fecha_inicio': row[3].strftime('%b. %d, %Y') if row[3] else '-',
            'fecha_fin': row[4].strftime('%b. %d, %Y') if row[4] else '-',
            'nm_responsable': row[5],
            'usuario_creacion': row[6],
            'centro': row[7],
            'almacen': row[8],
        }
        for row in rows
    ]

    # Calcular estadísticas por estado
    segundo_conteo_count = sum(1 for c in conteos if c['estado'].upper() == 'SEGUNDO_CONTEO')
    acta_preliminar_count = sum(1 for c in conteos if c['estado'].upper() == 'ACTA_PRELIMINAR')
    
    estadisticas = {
        'total': len(conteos),
        'segundo_conteo': segundo_conteo_count,
        'acta_preliminar': acta_preliminar_count,
    }

    # Si es petición AJAX, devolver JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'conteos': conteos,
            'estadisticas': estadisticas
        })

    context = {
        'usuario': request.session['usuario'],
        'perfil': perfil,
        'conteos': conteos,
        'estadisticas': estadisticas,
    }
    return render(request, 'inventario/acta_preliminar.html', context)


@csrf_exempt
def formulario_acta_preliminar(request, piqueo_id):
    """
    Vista para mostrar el formulario de acta preliminar con datos prellenados
    """
    if 'usuario' not in request.session:
        return redirect('login')

    perfil = request.session.get('perfil_seleccionado', {}).get('nombre', '')
    usuario_sesion = request.session.get('usuario', {})

    print(f"📋 [FORMULARIO_ACTA] Cargando formulario para PIQUEO_ID: {piqueo_id}")

    # Obtener datos del conteo
    datos_conteo = {}
    
    try:
        with connection.cursor() as cursor:
            # 1. Obtener datos básicos del conteo
            cursor.execute("""
                SELECT 
                    piqueo_id,
                    numero_conteo,
                    almacen,
                    centro,
                    estado
                FROM INV_PIQUEOS_INVENTARIO_TBL
                WHERE piqueo_id = %s
            """, [piqueo_id])
            
            row = cursor.fetchone()
            
            if not row:
                messages.error(request, 'No se encontró el conteo especificado')
                return redirect('acta_preliminar')
            
            datos_conteo = {
                'piqueo_id': row[0],
                'numero_conteo': row[1],
                'centro': row[3],
                'almacen': row[2],
                'empresa': usuario_sesion.get('empresa', 'SUPERDEPORTE'),
                'estado': row[4],
                'fecha_primer_conteo': None,
                'fecha_segundo_conteo': None,
                'jefe_tienda': 0,
                'subjefe_tienda': 0,
                'auxiliar_ventas': 0,
                'auxiliar_caja': 0,
                'auxiliar_bodega': 0,
                'auxiliar_operativo': 0
                , 'cantidad_item_acumula_anual': 0,
                'anio_anterior': timezone.now().year - 1
            }
            
            # Asignar numero_conteo a variable local para usar en queries posteriores
            numero_conteo = datos_conteo['numero_conteo']
            
            print(f"✅ Datos básicos del conteo obtenidos: {datos_conteo}")
            
            # 2. Obtener fecha_primer_conteo usando la función JDE fecha_primerPickeo_func
            try:
                cursor.execute("""
                    SELECT fecha_primerPickeo_func(%s) FROM dual
                """, [numero_conteo])

                fecha_func = cursor.fetchone()
                if fecha_func and fecha_func[0]:
                    try:
                        datos_conteo['fecha_primer_conteo'] = fecha_func[0].strftime('%Y-%m-%d %H:%M:%S')
                    except Exception:
                        datos_conteo['fecha_primer_conteo'] = str(fecha_func[0])
                    print(f"✅ Fecha Primer Conteo (func): {datos_conteo['fecha_primer_conteo']}")
                else:
                    # Fallback: consulta anterior si la función no retorna valor
                    cursor.execute("""
                        SELECT MAX(fecha) AS fecha_maxima
                        FROM INV_INVENTARIO_FISICO_VS_SISTEMA 
                        WHERE NUMERO_CONTEO = %s
                    """, [datos_conteo['numero_conteo']])
                    fecha_primer = cursor.fetchone()
                    if fecha_primer and fecha_primer[0]:
                        datos_conteo['fecha_primer_conteo'] = fecha_primer[0].strftime('%Y-%m-%d %H:%M:%S')
                        print(f"✅ Fecha Primer Conteo (fallback): {datos_conteo['fecha_primer_conteo']}")
                    else:
                        print(f"⚠️ No se encontró fecha_primer_conteo")
            except Exception as e:
                print(f"⚠️ Error ejecutando fecha_primerPickeo_func: {e}")
                # Intentar fallback si la función falla
                try:
                    cursor.execute("""
                        SELECT MAX(fecha) AS fecha_maxima
                        FROM INV_INVENTARIO_FISICO_VS_SISTEMA 
                        WHERE NUMERO_CONTEO = %s
                    """, [datos_conteo['numero_conteo']])
                    fecha_primer = cursor.fetchone()
                    if fecha_primer and fecha_primer[0]:
                        datos_conteo['fecha_primer_conteo'] = fecha_primer[0].strftime('%Y-%m-%d %H:%M:%S')
                        print(f"✅ Fecha Primer Conteo (fallback after error): {datos_conteo['fecha_primer_conteo']}")
                    else:
                        print(f"⚠️ No se encontró fecha_primer_conteo tras error en función")
                except Exception as e2:
                    print(f"⚠️ Error en fallback fecha_primer_conteo: {e2}")
            
            # 3. Obtener fecha_segundo_conteo
            cursor.execute("""
                SELECT DISTINCT MAX(fecha_conteo_2) 
                FROM INV_INVENTARIO_FISICO_VS_SISTEMA 
                WHERE NUMERO_CONTEO = %s
            """, [datos_conteo['numero_conteo']])
            
            fecha_segundo = cursor.fetchone()
            if fecha_segundo and fecha_segundo[0]:
                datos_conteo['fecha_segundo_conteo'] = fecha_segundo[0].strftime('%Y-%m-%d %H:%M:%S')
                print(f"✅ Fecha Segundo Conteo: {datos_conteo['fecha_segundo_conteo']}")
            else:
                print(f"⚠️ No se encontró fecha_segundo_conteo")
            
            # 4. Obtener conteo de JEFE_TIENDA
            cursor.execute("""
                SELECT COUNT(*) AS jefe_tienda 
                FROM INV_PIQUEO_COLABORADORES_TBL 
                WHERE cargo LIKE 'JEFE%%' 
                AND piqueo_id = %s
            """, [piqueo_id])
            
            jefe = cursor.fetchone()
            datos_conteo['jefe_tienda'] = jefe[0] if jefe else 0
            print(f"✅ Jefe Tienda: {datos_conteo['jefe_tienda']}")
            
            # 5. Obtener conteo de SUBJEFE_TIENDA
            cursor.execute("""
                SELECT COUNT(*) AS subjefe_tienda 
                FROM INV_PIQUEO_COLABORADORES_TBL 
                WHERE cargo LIKE 'SUB JEFE%%' 
                AND piqueo_id = %s
            """, [piqueo_id])
            
            subjefe = cursor.fetchone()
            datos_conteo['subjefe_tienda'] = subjefe[0] if subjefe else 0
            print(f"✅ Subjefe Tienda: {datos_conteo['subjefe_tienda']}")
            
            # 6. Obtener conteo de AUXILIAR_VENTAS
            cursor.execute("""
                SELECT COUNT(*) AS auxiliar_ventas 
                FROM INV_PIQUEO_COLABORADORES_TBL 
                WHERE cargo LIKE '%%VENTAS%%' 
                AND piqueo_id = %s
            """, [piqueo_id])
            
            aux_ventas = cursor.fetchone()
            datos_conteo['auxiliar_ventas'] = aux_ventas[0] if aux_ventas else 0
            print(f"✅ Auxiliar Ventas: {datos_conteo['auxiliar_ventas']}")
            
            # 7. Obtener conteo de AUXILIAR_CAJA
            cursor.execute("""
                SELECT COUNT(*) AS auxiliar_caja 
                FROM INV_PIQUEO_COLABORADORES_TBL 
                WHERE cargo LIKE '%%CAJ%%' 
                AND piqueo_id = %s
            """, [piqueo_id])
            
            aux_caja = cursor.fetchone()
            datos_conteo['auxiliar_caja'] = aux_caja[0] if aux_caja else 0
            print(f"✅ Auxiliar Caja: {datos_conteo['auxiliar_caja']}")
            
            # 8. Obtener conteo de AUXILIAR_BODEGA
            cursor.execute("""
                SELECT COUNT(*) AS auxiliar_bodega 
                FROM INV_PIQUEO_COLABORADORES_TBL 
                WHERE cargo LIKE '%%BODEGA%%' 
                AND piqueo_id = %s
            """, [piqueo_id])
            
            aux_bodega = cursor.fetchone()
            datos_conteo['auxiliar_bodega'] = aux_bodega[0] if aux_bodega else 0
            print(f"✅ Auxiliar Bodega: {datos_conteo['auxiliar_bodega']}")
            
            # 9. Obtener conteo de AUXILIAR_OPERATIVO
            cursor.execute("""
                SELECT COUNT(*) AS auxiliar_operativo 
                FROM INV_PIQUEO_COLABORADORES_TBL 
                WHERE cargo LIKE '%%OPERATIVO%%' 
                AND piqueo_id = %s
            """, [piqueo_id])
            
            aux_operativo = cursor.fetchone()
            datos_conteo['auxiliar_operativo'] = aux_operativo[0] if aux_operativo else 0
            print(f"✅ Auxiliar Operativo: {datos_conteo['auxiliar_operativo']}")
            
            # 10. Obtener cantidad de marcas
            cursor.execute("""
                SELECT COUNT(DISTINCT a.marca) as cantidad_marcas
                FROM inv_inventario_fisico_vs_sistema a
                WHERE numero_conteo = %s
            """, [numero_conteo])
            
            marcas = cursor.fetchone()
            datos_conteo['cantidad_marcas'] = marcas[0] if marcas and marcas[0] else 0
            print(f"✅ Cantidad Marcas: {datos_conteo['cantidad_marcas']}")
            
            # 11. Obtener cantidad de líneas
            cursor.execute("""
                SELECT COUNT(DISTINCT substr(grupo_articulos,7,3)) as cantidad_linea
                FROM inv_inventario_fisico_vs_sistema a
                WHERE numero_conteo = %s
            """, [numero_conteo])
            
            lineas = cursor.fetchone()
            datos_conteo['cantidad_lineas'] = lineas[0] if lineas and lineas[0] else 0
            print(f"✅ Cantidad Líneas: {datos_conteo['cantidad_lineas']}")
            
            # 12. Obtener cantidad de items

            cursor.execute("""
                SELECT sum( conteo_3) as cantidad_items
                FROM inv_inventario_fisico_vs_sistema a
                WHERE numero_conteo = %s
            """, [numero_conteo])
            items = cursor.fetchone()
            datos_conteo['cantidad_items'] = items[0] if items and items[0] else 0
            print(f"✅ Cantidad Items: {datos_conteo['cantidad_items']}")
            # Inicializar cantidad de toma revisada con la misma cantidad de items
            cursor.execute("""
                SELECT count(*)
                FROM inv_piqueo_secuencial_deta_tbl
                WHERE estado = 'ACTIVO'
                AND secuencial_id IN (
                    SELECT secuencial_id FROM inv_piqueo_secuencial_tbl
                    WHERE detalle_piqueo_id IN (
                        SELECT detalle_piqueo_id FROM inv_detalle_piqueos_inventarios_tbl
                        WHERE piqueo_id IN (
                            SELECT piqueo_id FROM inv_piqueos_inventario_tbl
                            WHERE numero_conteo = %s
                        )
                    )
                )
            """, [numero_conteo])
            toma_revisada = cursor.fetchone()
            datos_conteo['cantidad_toma_revisada'] = toma_revisada[0] if toma_revisada and toma_revisada[0] else 0
            print(f"✅ Cantidad Toma Revisada: {datos_conteo['cantidad_toma_revisada']}")
            
            # 13. Obtener cantidad de items faltantes (usar campo DIFERENCIA_3 y estado_comparacion_3)
            cursor.execute("""
                SELECT sum(DIFERENCIA_3) as cantidad_items_faltantes
                FROM inv_inventario_fisico_vs_sistema a
                WHERE numero_conteo = %s
                AND estado_comparacion_3 = 'FALTANTE'
            """, [numero_conteo])

            items_faltantes = cursor.fetchone()
            datos_conteo['cantidad_items_faltantes'] = items_faltantes[0] if items_faltantes and items_faltantes[0] else 0
            print(f"✅ Cantidad Items Faltantes: {datos_conteo['cantidad_items_faltantes']}")
            
            # 14. Obtener cantidad de items sobrantes (usar campo DIFERENCIA_3 y estado_comparacion_3)
            cursor.execute("""
                SELECT ABS(sum(DIFERENCIA_3)) as cantidad_items_sobrantes
                FROM inv_inventario_fisico_vs_sistema a
                WHERE numero_conteo = %s
                AND estado_comparacion_3 = 'SOBRANTE'
            """, [numero_conteo])

            items_sobrantes = cursor.fetchone()
            datos_conteo['cantidad_items_sobrantes'] = items_sobrantes[0] if items_sobrantes and items_sobrantes[0] else 0
            print(f"✅ Cantidad Items Sobrantes: {datos_conteo['cantidad_items_sobrantes']}")

            # Calcular líneas de diferencias = cantidad faltantes + cantidad sobrantes
            datos_conteo['lineas_diferencias'] = (
                int(datos_conteo.get('cantidad_items_faltantes', 0)) +
                int(datos_conteo.get('cantidad_items_sobrantes', 0))
            )
            print(f"✅ Líneas de Diferencias: {datos_conteo['lineas_diferencias']}")
            
            # 15. Obtener valor de items faltantes
            cursor.execute("""
                SELECT sum(diferencia_3*pvp) as valor_items_faltantes
                FROM inv_inventario_fisico_vs_sistema a
                WHERE numero_conteo = %s
                AND estado_comparacion_3='FALTANTE'
            """, [numero_conteo])
            
            valor_faltantes = cursor.fetchone()
            datos_conteo['valor_items_faltantes'] = abs(float(valor_faltantes[0])) if valor_faltantes and valor_faltantes[0] else 0.00
            print(f"✅ Valor Items Faltantes: ${datos_conteo['valor_items_faltantes']:.2f}")
            
            # 16. Obtener valor de items sobrantes
            cursor.execute("""
                SELECT sum(diferencia_3*pvp) as valor_items_sobrantes
                FROM inv_inventario_fisico_vs_sistema a
                WHERE numero_conteo = %s
                AND estado_comparacion_3='SOBRANTE'
            """, [numero_conteo])
            
            valor_sobrantes = cursor.fetchone()
            datos_conteo['valor_items_sobrantes'] = float(valor_sobrantes[0]) if valor_sobrantes and valor_sobrantes[0] else 0.00
            print(f"✅ Valor Items Sobrantes: ${datos_conteo['valor_items_sobrantes']:.2f}")
            
            # 17. Asignar código de inventario (es el mismo numero_conteo)
            datos_conteo['codigo_inventario'] = numero_conteo
            print(f"✅ Código Inventario: {datos_conteo['codigo_inventario']}")
            
            # 18. Obtener hora generó informe inventario SAP
            cursor.execute("""
                SELECT max(fecha_precio)
                FROM inv_inventario_fisico_vs_sistema a
                WHERE numero_conteo = %s
            """, [numero_conteo])
            
            hora_informe = cursor.fetchone()
            if hora_informe and hora_informe[0]:
                datos_conteo['hora_genero_informe_inven_sap'] = hora_informe[0].strftime('%Y-%m-%dT%H:%M')
                print(f"✅ Hora Generó Informe SAP: {datos_conteo['hora_genero_informe_inven_sap']}")
            else:
                datos_conteo['hora_genero_informe_inven_sap'] = ''
                print(f"⚠️ No se encontró hora_genero_informe_inven_sap")
            
            # 19. Obtener Stock SAP por tipo desde tabla SAP_S032 (remote) y vincular por número de conteo
            cursor.execute("""
                SELECT 
                    CASE
                        WHEN substr(s.letztver,1,1)='C' THEN 'CALZADO'
                        WHEN substr(s.letztver,1,1)='R' THEN 'ROPA'
                        WHEN substr(s.letztver,1,1)='A' THEN 'ACCESORIO'
                        WHEN substr(s.letztver,1,1)='B' THEN 'FUNDAS'
                        ELSE 'OTROS'
                    END TIPO,
                    SUM(s.mbwbest) AS stock_total
                FROM SAP_S032@DBL_CLOUDFRIDTMAN1.REDBDD.REDPROD.ORACLEVCN.COM s,
                     INV_PIQUEOS_INVENTARIO_TBL p
                WHERE s.werks = p.almacen
                  AND s.lgort = 'PR01'
                  AND p.numero_conteo = %s
                GROUP BY CASE
                    WHEN substr(s.letztver,1,1)='C' THEN 'CALZADO'
                    WHEN substr(s.letztver,1,1)='R' THEN 'ROPA'
                    WHEN substr(s.letztver,1,1)='A' THEN 'ACCESORIO'
                    WHEN substr(s.letztver,1,1)='B' THEN 'FUNDAS'
                    ELSE 'OTROS'
                END
            """, [numero_conteo])

            stock_sap_rows = cursor.fetchall()

            # Inicializar valores (mantener las claves existentes; agregar FUNDAS/OTROS por si acaso)
            datos_conteo['stock_sap_descripcion_calzado'] = 'CALZADO'
            datos_conteo['stock_sap_valor_calzado'] = 0
            datos_conteo['stock_sap_descripcion_ropa'] = 'ROPA'
            datos_conteo['stock_sap_valor_ropa'] = 0
            datos_conteo['stock_sap_descripcion'] = 'ACCESORIO'
            datos_conteo['stock_sap_valor'] = 0
            datos_conteo['stock_sap_descripcion_fundas'] = 'FUNDAS'
            datos_conteo['stock_sap_valor_fundas'] = 0
            datos_conteo['stock_sap_descripcion_otros'] = 'OTROS'
            datos_conteo['stock_sap_valor_otros'] = 0

            # Procesar resultados: recoger en un dict por tipo
            stock_map = {}
            for row in stock_sap_rows:
                tipo = row[0]
                valor = int(row[1]) if row[1] else 0
                stock_map[tipo] = valor

            # Orden y tipos que queremos mostrar (mantener consistencia en UI)
            tipos_orden = ['CALZADO', 'ROPA', 'ACCESORIO', 'FUNDAS', 'OTROS']

            # Construir lista de items para la plantilla y también mantener claves individuales para compatibilidad
            stock_items = []
            for t in tipos_orden:
                v = stock_map.get(t, 0)
                stock_items.append({'tipo': t, 'valor': v})
                # asignar claves antiguas para compatibilidad con otras partes del código
                if t == 'CALZADO':
                    datos_conteo['stock_sap_valor_calzado'] = v
                    datos_conteo['stock_sap_descripcion_calzado'] = t
                elif t == 'ROPA':
                    datos_conteo['stock_sap_valor_ropa'] = v
                    datos_conteo['stock_sap_descripcion_ropa'] = t
                elif t == 'ACCESORIO':
                    datos_conteo['stock_sap_valor'] = v
                    datos_conteo['stock_sap_descripcion'] = t
                elif t == 'FUNDAS':
                    datos_conteo['stock_sap_valor_fundas'] = v
                    datos_conteo['stock_sap_descripcion_fundas'] = t
                elif t == 'OTROS':
                    datos_conteo['stock_sap_valor_otros'] = v
                    datos_conteo['stock_sap_descripcion_otros'] = t

            # Añadir la lista ordenada al contexto de datos
            datos_conteo['stock_sap_items'] = stock_items

            # Calcular total de Stock SAP (sumar todas las categorías)
            datos_conteo['stock_sap_total'] = sum(item['valor'] for item in stock_items)
            print(f"✅ Stock SAP TOTAL: {datos_conteo['stock_sap_total']}")
            # ------------- Porcentaje inventariado hoy -------------
            # Ahora 100% corresponde a `stock_sap_total` y la cantidad realizada es `cantidad_items`.
            try:
                cantidad_items_val = int(datos_conteo.get('cantidad_items', 0))
            except (TypeError, ValueError):
                cantidad_items_val = 0

            stock_total_val = datos_conteo.get('stock_sap_total') or 0

            if stock_total_val > 0:
                porcentaje = (cantidad_items_val / float(stock_total_val)) * 100
            else:
                porcentaje = 0.0

            datos_conteo['porcentaje_inventariado_hoy'] = f"{porcentaje:.2f}%"
            print(f"✅ % Inventariado hoy: {datos_conteo['porcentaje_inventariado_hoy']}")
            # ------------------------------------------------------
            # ------------- Total de ítems por inventariar -------------
            try:
                cantidad_items_val = int(datos_conteo.get('cantidad_items', 0))
            except (TypeError, ValueError):
                cantidad_items_val = 0

            try:
                stock_total_val = int(datos_conteo.get('stock_sap_total', 0))
            except (TypeError, ValueError):
                stock_total_val = 0

            # Restar: Total Stock SAP - Cantidad Items (no negativo)
            total_por_inventariar = stock_total_val - cantidad_items_val
            if total_por_inventariar < 0:
                total_por_inventariar = 0

            datos_conteo['total_items_por_inventariar'] = total_por_inventariar
            print(f"✅ Total Items por inventariar: {datos_conteo['total_items_por_inventariar']}")
            # -----------------------------------------------------------
            
            # 20. Obtener punto_emision (sucursal), PAIS y sap_hcm_mcu desde JDE
            # Preferimos usar el segmento extraído del numero_conteo (pos 7-10), p.ej. 'ECP1'
            segmento = None
            try:
                if numero_conteo and len(str(numero_conteo)) >= 10:
                    segmento = str(numero_conteo)[6:10]
            except Exception:
                segmento = None

            datos_conteo['sucursal'] = ''
            datos_conteo['pais'] = ''
            datos_conteo['sap_hcm_mcu'] = None

            if segmento:
                try:
                    jde_sql = """
                        SELECT punto_emision, PAIS, sap_hcm_mcu
                        FROM jde_general@DBL_CLOUDFRIDTMAN.REDBDD.REDPROD.ORACLEVCN.COM
                        WHERE SAP_WERKS = %s
                    """
                    # Exponer la consulta y parámetros en el contexto para depuración en la página
                    try:
                        datos_conteo['jde_sql'] = jde_sql.strip()
                        datos_conteo['jde_params'] = [segmento]
                    except Exception:
                        datos_conteo['jde_sql'] = None
                        datos_conteo['jde_params'] = None
                    print("🔁 Ejecutando JDE SQL:")
                    print(jde_sql)
                    print(f"🔁 Parámetros: [{segmento}]")
                    cursor.execute(jde_sql, [segmento])
                    jde_row = cursor.fetchone()
                    print(f"🔎 Resultado JDE (punto_emision,PAIS,sap_hcm_mcu): {jde_row!r}")
                    # Registrar en archivo de debug para entornos donde stdout no se vea
                    try:
                        os.makedirs('logs', exist_ok=True)
                        with open(os.path.join('logs', 'jde_debug.log'), 'a', encoding='utf-8') as f:
                            f.write(f"[{datetime.now().isoformat()}] PIQUEO_ID={piqueo_id} - Ejecutando JDE SQL:\n")
                            f.write(jde_sql.strip() + "\n")
                            f.write(f"Params: [{segmento}]\n")
                            f.write(f"Resultado: {jde_row!r}\n\n")
                    except Exception as _e:
                        print(f"⚠️ No se pudo escribir el log JDE: {_e}")
                    if jde_row:
                        punto_emision_val = jde_row[0]
                        pais_val = jde_row[1] if len(jde_row) > 1 else None
                        sap_hcm_mcu_val = jde_row[2] if len(jde_row) > 2 else None

                        if punto_emision_val:
                            datos_conteo['sucursal'] = punto_emision_val
                        if pais_val:
                            datos_conteo['pais'] = pais_val
                        if sap_hcm_mcu_val:
                            datos_conteo['sap_hcm_mcu'] = sap_hcm_mcu_val
                            # Según especificación: 'almacen' debe ser sap_hcm_mcu y
                            # 'centro' debe ser el segmento (p.ej. 'ECP1')
                            datos_conteo['almacen'] = sap_hcm_mcu_val
                            if segmento:
                                datos_conteo['centro'] = segmento
                            print(f"ℹ️ Almacén sobrescrito en formulario por sap_hcm_mcu: {sap_hcm_mcu_val}")
                            print(f"ℹ️ Centro establecido como segmento: {segmento}")

                        # Intentar obtener la razón social (FE_RAZON_SOCIAL) desde JDE para usarla como empresa
                        try:
                            cursor.execute("""
                                SELECT FE_RAZON_SOCIAL
                                FROM jde_general@DBL_CLOUDFRIDTMAN.REDBDD.REDPROD.ORACLEVCN.COM
                                WHERE SAP_WERKS = %s
                            """, [segmento])
                            empresa_row = cursor.fetchone()
                            if empresa_row and empresa_row[0]:
                                datos_conteo['empresa'] = empresa_row[0]
                                print(f"✅ Empresa (FE_RAZON_SOCIAL) obtenida desde JDE: {datos_conteo['empresa']}")
                            else:
                                # Mantener valor por defecto desde sesión si no hay resultado
                                datos_conteo['empresa'] = usuario_sesion.get('empresa', 'SUPERDEPORTE')
                        except Exception as e:
                            print(f"⚠️ Error consultando FE_RAZON_SOCIAL en JDE: {e}")
                            datos_conteo['empresa'] = usuario_sesion.get('empresa', 'SUPERDEPORTE')
                        # Obtener tipo_cen desde JDE para llenar el campo 'concepto'
                        try:
                            cursor.execute("""
                                SELECT tipo_cen
                                FROM jde_general@DBL_CLOUDFRIDTMAN.REDBDD.REDPROD.ORACLEVCN.COM
                                WHERE SAP_WERKS = %s
                            """, [segmento])
                            tipo_row = cursor.fetchone()
                            if tipo_row and tipo_row[0]:
                                datos_conteo['concepto'] = tipo_row[0]
                                print(f"✅ Concepto (tipo_cen) obtenido desde JDE: {datos_conteo['concepto']}")
                            else:
                                datos_conteo['concepto'] = ''
                        except Exception as e:
                            print(f"⚠️ Error consultando tipo_cen en JDE: {e}")
                            datos_conteo['concepto'] = ''
                    else:
                        print(f"⚠️ JDE no devolvió filas para SAP_WERKS={segmento}")
                except Exception as e:
                    print(f"⚠️ Error consultando JDE para punto_emision/PAIS/sap_hcm_mcu: {e}")
                    datos_conteo['jde_sql'] = None
                    datos_conteo['jde_params'] = None
            else:
                print(f"⚠️ No se pudo extraer el segmento desde numero_conteo={numero_conteo}")
                datos_conteo['jde_sql'] = None
                datos_conteo['jde_params'] = None

            # 21. Obtener Toma Física Grupo
            # Query: select grupo_articulos from inv_detalle_piqueos_inventarios_tbl where piqueo_id = ...
            cursor.execute("""
                SELECT DISTINCT grupo_articulos
                FROM inv_detalle_piqueos_inventarios_tbl
                WHERE piqueo_id = %s
                AND ROWNUM = 1
            """, [piqueo_id])
            
            grupo_articulos = cursor.fetchone()
            if grupo_articulos and grupo_articulos[0]:
                datos_conteo['toma_fisica_grupo'] = grupo_articulos[0]
                print(f"✅ Toma Física Grupo: {datos_conteo['toma_fisica_grupo']}")
            else:
                datos_conteo['toma_fisica_grupo'] = ''
                print(f"⚠️ No se encontró grupo_articulos para piqueo_id: {piqueo_id}")

            # 22. Obtener la última Fecha Toma Física Anterior desde acta_preliminar_tbl
            try:
                cursor.execute("""
                    SELECT MAX(fecha_toma_fisica_anterior)
                    FROM acta_preliminar_tbl
                    WHERE empresa = %s AND centro = %s AND tienda = %s
                """, [datos_conteo.get('empresa', 'SUPERDEPORTE'), datos_conteo.get('centro'), datos_conteo.get('almacen')])

                fecha_anterior_row = cursor.fetchone()
                if fecha_anterior_row and fecha_anterior_row[0]:
                    # Formatear para input type=date (YYYY-MM-DD)
                    datos_conteo['fecha_toma_fisica_anterior'] = fecha_anterior_row[0].strftime('%Y-%m-%d')
                    print(f"✅ Fecha Toma Física Anterior encontrada: {datos_conteo['fecha_toma_fisica_anterior']}")
                else:
                    # Si no existe, usar la fecha de hoy
                    hoy = timezone.now().strftime('%Y-%m-%d')
                    datos_conteo['fecha_toma_fisica_anterior'] = hoy
                    print(f"⚠️ No se encontró fecha anterior. Usando hoy: {hoy}")

                # 23. Calcular número de toma física anterior (count de actas existentes)
                try:
                    # Calcular número de tomas físicas del año anterior filtrando por segmento dinámico
                    numero_conteo_val = datos_conteo.get('numero_conteo', '') or ''
                    segmento = ''
                    if len(numero_conteo_val) >= 10:
                        segmento = numero_conteo_val[6:10]

                    if not segmento:
                        datos_conteo['numero_toma_fisica_anterior'] = 0
                        datos_conteo['numero_toma_fisica_actual'] = datos_conteo.get('numero_conteo', '')
                        print(f"⚠️ No se pudo determinar el segmento del número de conteo para calcular tomas anteriores: '{numero_conteo_val}'")
                    else:
                        cursor.execute("""
                            SELECT COUNT(*)
                            FROM inv_piqueos_inventario_tbl
                            WHERE TO_CHAR(fecha_inicio,'YYYY') = TO_CHAR(ADD_MONTHS(SYSDATE, -12),'YYYY')
                              AND SUBSTR(numero_conteo,7,4) = %s
                        """, [segmento])

                        cnt_row = cursor.fetchone()
                        cnt = cnt_row[0] if cnt_row and cnt_row[0] is not None else 0
                        datos_conteo['numero_toma_fisica_anterior'] = int(cnt)
                        datos_conteo['numero_toma_fisica_actual'] = datos_conteo.get('numero_conteo', '')
                        print(f"✅ Número de tomas físicas en el año anterior (segmento={segmento}): {datos_conteo['numero_toma_fisica_anterior']}")
                except Exception as e:
                    print(f"⚠️ Error calculando número toma física anterior: {e}")
                    datos_conteo['numero_toma_fisica_anterior'] = 0
                    datos_conteo['numero_toma_fisica_actual'] = 1

                # 24. Obtener cantidad de items del último inventario (toma física parcial del año anterior)
                try:
                    numero_conteo_val = datos_conteo.get('numero_conteo', '') or ''
                    segmento = ''
                    if len(numero_conteo_val) >= 10:
                        segmento = numero_conteo_val[6:10]

                    if not segmento:
                        datos_conteo['cantidad_item_ultimo_inv'] = 0
                        print(f"⚠️ No se pudo determinar el segmento del número de conteo para último inventario: '{numero_conteo_val}'")
                    else:
                        cursor.execute("""
                            SELECT SUM(CONTEO_3)
                            FROM inv_inventario_fisico_vs_sistema
                            WHERE TO_CHAR(fecha,'YYYY') = TO_CHAR(ADD_MONTHS(SYSDATE, -12),'YYYY')
                              AND SUBSTR(numero_conteo,7,4) = %s
                        """, [segmento])

                        suma_row = cursor.fetchone()
                        suma_val = suma_row[0] if suma_row and suma_row[0] is not None else 0
                        datos_conteo['cantidad_item_ultimo_inv'] = int(suma_val)
                        print(f"✅ Cantidad Item último inventario (año anterior, segmento={segmento}): {datos_conteo['cantidad_item_ultimo_inv']}")
                except Exception as e:
                    print(f"⚠️ Error obteniendo cantidad_item_ultimo_inv: {e}")
                    datos_conteo['cantidad_item_ultimo_inv'] = 0
                
                    # 25. Calcular cantidad acumulada anual usando CONTEO_3 y el segmento del número de conteo
                    try:
                        numero_conteo_val = datos_conteo.get('numero_conteo', '') or ''
                        # Extraer el segmento que identifica la toma (SUBSTR(numero_conteo,7,4) en Oracle)
                        segmento = ''
                        if len(numero_conteo_val) >= 10:
                            segmento = numero_conteo_val[6:10]

                        if not segmento:
                            datos_conteo['cantidad_item_acumula_anual'] = 0
                            print(f"⚠️ No se pudo determinar el segmento del número de conteo para acumulado anual: '{numero_conteo_val}'")
                        else:
                            cursor.execute("""
                                SELECT SUM(CONTEO_3)
                                FROM inv_inventario_fisico_vs_sistema a
                                WHERE to_char(fecha,'yyyy') = to_char(sysdate,'yyyy')
                                  AND SUBSTR(numero_conteo,7,4) = %s
                            """, [segmento])

                            suma_row = cursor.fetchone()
                            suma_val = suma_row[0] if suma_row and suma_row[0] is not None else 0
                            datos_conteo['cantidad_item_acumula_anual'] = int(suma_val)
                            print(f"✅ Cantidad Item Acumulado Anual (segmento={segmento}): {datos_conteo['cantidad_item_acumula_anual']}")
                    except Exception as e:
                        print(f"⚠️ Error calculando cantidad_item_acumula_anual: {e}")
                        datos_conteo['cantidad_item_acumula_anual'] = 0
            except Exception as e:
                print(f"⚠️ Error obteniendo fecha_toma_fisica_anterior: {e}")
                datos_conteo['fecha_toma_fisica_anterior'] = timezone.now().strftime('%Y-%m-%d')

            # 23. Asegurar que PAÍS y CONCEPTO estén presentes: si no, intentar obtenerlos desde JDE (por segmento)
            try:
                segmento = None
                numero_conteo_val = datos_conteo.get('numero_conteo', '') or ''
                if len(numero_conteo_val) >= 10:
                    segmento = numero_conteo_val[6:10]
                if segmento:
                    # Intentar PAIS
                    try:
                        cursor.execute("""
                            SELECT PAIS
                            FROM jde_general@DBL_CLOUDFRIDTMAN.REDBDD.REDPROD.ORACLEVCN.COM
                            WHERE SAP_WERKS = %s
                        """, [segmento])
                        pais_row = cursor.fetchone()
                        if pais_row and pais_row[0] and not datos_conteo.get('pais'):
                            datos_conteo['pais'] = pais_row[0]
                            print(f"✅ PAIS completado desde JDE en formulario: {datos_conteo['pais']}")
                    except Exception as e:
                        print(f"⚠️ Error obteniendo PAIS desde JDE (falló fallback): {e}")

                    # Intentar CONCEPTO (tipo_cen)
                    try:
                        cursor.execute("""
                            SELECT tipo_cen
                            FROM jde_general@DBL_CLOUDFRIDTMAN.REDBDD.REDPROD.ORACLEVCN.COM
                            WHERE SAP_WERKS = %s
                        """, [segmento])
                        tipo_row = cursor.fetchone()
                        if tipo_row and tipo_row[0] and not datos_conteo.get('concepto'):
                            datos_conteo['concepto'] = tipo_row[0]
                            print(f"✅ CONCEPTO completado desde JDE en formulario: {datos_conteo['concepto']}")
                    except Exception as e:
                        print(f"⚠️ Error obteniendo tipo_cen desde JDE (falló fallback): {e}")
            except Exception as _e:
                print(f"⚠️ Error en fallback JDE para PAIS/CONCEPTO: {_e}")
    
    except Exception as e:
        print(f"❌ Error al obtener datos del conteo: {e}")
        import traceback
        traceback.print_exc()
        messages.error(request, f'Error al cargar los datos del conteo: {str(e)}')
        return redirect('acta_preliminar')
    
    context = {
        'usuario': request.session['usuario'],
        'perfil': perfil,
        'datos_conteo': datos_conteo,
    }
    
    return render(request, 'inventario/formulario_acta_preliminar.html', context)


@csrf_exempt
def guardar_acta_preliminar(request):
    """
    Vista para guardar el acta preliminar en la base de datos
    """
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'message': 'No autenticado'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        
        print(f"💾 [GUARDAR_ACTA] Recibiendo datos del acta preliminar")
        print(f"📊 Datos recibidos: {data}")
        
        # Validar campos obligatorios
        campos_obligatorios = ['piqueo_id', 'numero_conteo', 'centro', 'almacen']
        for campo in campos_obligatorios:
            if not data.get(campo):
                return JsonResponse({
                    'success': False,
                    'message': f'El campo {campo} es obligatorio'
                })
        
        with connection.cursor() as cursor:
            # Preparar valores, convirtiendo strings vacíos a NULL
            def get_value(key, default=None):
                val = data.get(key, default)
                return val if val != '' else default
            
            # Función para convertir a número de forma segura
            def get_number(key, default=0):
                val = get_value(key, default)
                if val is None or val == '':
                    return default
                try:
                    return float(val) if '.' in str(val) else int(val)
                except (ValueError, TypeError):
                    return default
            
            # Extraer valores necesarios
            piqueo_id_val = get_value('piqueo_id')
            numero_conteo_val = get_value('numero_conteo')
            centro_val = get_value('centro')
            almacen_val = get_value('almacen')
            empresa_val = get_value('empresa', 'SUPERDEPORTE')
            concepto_val = get_value('concepto', '')
            # Obtener valor de sucursal si viene en payload (se puede sobrescribir más abajo consultando JDE)
            sucursal_val = get_value('sucursal')
            # Preferir tienda enviada desde formulario; si no viene, usar sucursal (payload o JDE) o almacen
            tienda_val = get_value('tienda', sucursal_val or almacen_val)
            
            fecha_primer_conteo = get_value('fecha_primer_conteo')
            fecha_segundo_conteo = get_value('fecha_segundo_conteo')
            hora_genero_informe = get_value('hora_genero_informe_inven_sap')
            fecha_toma_anterior = get_value('fecha_toma_fisica_anterior')
            
            # Parse helper: parsear enteros desde cadenas que usan coma como separador de miles
            def parse_int_value(key, default=0):
                val = get_value(key, None)
                if val is None or val == '':
                    return default
                s = str(val).strip()
                # Eliminar separadores de miles comunes (punto, coma y espacio)
                s = s.replace(' ', '').replace(',', '').replace('.', '')
                if s == '':
                    return default
                try:
                    if '.' in s:
                        f = float(s)
                        return int(f) if f.is_integer() else int(round(f))
                    return int(s)
                except Exception:
                    try:
                        return int(float(s))
                    except Exception:
                        return default

            # Mapear nombres del formulario a los valores correctos
            # El formulario envía stock_sap_descripcion_1, stock_sap_valor_1, etc.
            stock_sap_descripcion_calzado = get_value('stock_sap_descripcion_1', 'CALZADO')
            stock_sap_valor_calzado = parse_int_value('stock_sap_valor_1', 0)
            stock_sap_descripcion_ropa = get_value('stock_sap_descripcion_2', 'ROPA')
            stock_sap_valor_ropa = parse_int_value('stock_sap_valor_2', 0)
            stock_sap_descripcion_accesorio = get_value('stock_sap_descripcion_3', 'ACCESORIO')
            stock_sap_valor_accesorio = parse_int_value('stock_sap_valor_3', 0)
            stock_sap_descripcion_fundas = get_value('stock_sap_descripcion_4', 'FUNDAS')
            stock_sap_valor_fundas = parse_int_value('stock_sap_valor_4', 0)
            stock_sap_descripcion_otros = get_value('stock_sap_descripcion_5', 'OTROS')
            stock_sap_valor_otros = parse_int_value('stock_sap_valor_5', 0)
            stock_sap_total = parse_int_value('stock_sap_total', 0)
            
            # Formatear fechas para Oracle
            def format_date_oracle(fecha_str, include_time=True):
                if not fecha_str:
                    return None
                # Reemplazar T por espacio si viene en formato ISO
                fecha_str = fecha_str.replace('T', ' ')
                # Si solo tiene fecha sin hora, agregar 00:00:00
                if include_time and len(fecha_str) == 10:
                    fecha_str += ' 00:00:00'
                # Si tiene hora pero sin segundos (HH:MM), agregar :00
                if include_time and len(fecha_str) == 16:
                    fecha_str += ':00'
                return fecha_str
            
            fecha_primer_conteo_fmt = format_date_oracle(fecha_primer_conteo)
            fecha_segundo_conteo_fmt = format_date_oracle(fecha_segundo_conteo)
            hora_genero_informe_fmt = format_date_oracle(hora_genero_informe)
            fecha_toma_anterior_fmt = format_date_oracle(fecha_toma_anterior, include_time=False)
            
            sql = """
                INSERT INTO acta_preliminar_tbl (
                    PIQUEO_ID, CENTRO, ALMACEN, NUMERO_CONTEO, EMPRESA, PAIS, CONCEPTO,
                    TIENDA, FECHA_PRIMER_CONTEO, FECHA_SEGUNDO_CONTEO,
                    JEFE_TIENDA, SUBJEFE_TIENDA, AUXILIAR_VENTAS, AUXILIAR_CAJA,
                    AUXILIAR_BODEGA, AUXILIAR_OPERATIVO, ASISTENTE_OPERTAIVO_INVENTARIO,
                    JEFE_INVENTARIOS, AUDITOR_INTERNO, CONTADO, GERENTE_REGIONAL,
                    SUPERVISOR_COMERCIAL,
                    STOCK_SAP_DESCRIPCION_CALZADO, STOCK_SAP_VALOR_CALZADO,
                    STOCK_SAP_DESCRIPCION_ROPA, STOCK_SAP_VALOR_ROPA,
                    STOCK_SAP_DESCRIPCION_ACCESORIO, STOCK_SAP_VALOR_ACCESORIO,
                    STOCK_SAP_DESCRIPCION_FUNDAS, STOCK_SAP_VALOR_FUNDAS,
                    STOCK_SAP_DESCRIPCION_OTROS, STOCK_SAP_VALOR_OTROS,
                    STOCK_SAP_TOTAL,
                    CANTIDAD_MARCAS, CANTIDAD_LINEAS, CANTIDAD_ITEMS,
                    CANTIDAD_ITEMS_FALTANTES, CANTIDAD_ITEMS_SOBRANTES,
                    VALOR_ITEMS_FALTANTES, VALOR_ITEMS_SOBRANTES,
                    CODIGO_INVENTARIO, LINEAS_DIFERENCIAS, HORA_GENERO_INFORME_INVEN_SAP,
                    TOMA_FISICA_GRUPO, CONFIRMO_ENCERADO_GUIA_REMI,
                    FECHA_TOMA_FISICA_ANTERIOR, CANTIDAD_ITEM_ULTIMO_INV,
                    NUMERO_TOMA_FISICA_ANTERIOR, CANTIDAD_ITEM_ACUMULA_ANUAL,
                    VALOR_EFECTIVO, VALOR_FACTURAS, VALOR_CHEQUES, FONDO_CAJA, FONDO_SUELTOS, TOTAL,
                    SUCURSAL, ULTIMA_FACT_CAJA1, ULTIMA_FACT_CAJA2,
                    ULTIMA_FACT_CAJA3, ULTIMA_FACT_CAJA4, ULTIMA_FACT_CAJA5,
                    ULTIMO_DOC_GUIA_REMISION, ULTIMO_DOC_NOTA_CREDIT, ESTADO,
                    CANTIDAD_TOMA_REVISADA, PORCENTAJE_INVENTARIO, TOTAL_ITEMS_POR_INVENTARIAR,
                    HORAS_SUSPENDIDAS_ATENCION_CLIENTE, TOTAL_GASTOS_EJECUCION_TOMA_FISICA,
                    CARGO_1, NOMBRE_CARGO_1,
                    CARGO_2, NOMBRE_CARGO_2,
                    CARGO_3, NOMBRE_CARGO_3,
                    CARGO_4, NOMBRE_CARGO_4,
                    CARGO_5, NOMBRE_CARGO_5,
                    CARGO_6, NOMBRE_CARGO_6,
                    CARGO_7, NOMBRE_CARGO_7,
                    CARGO_8, NOMBRE_CARGO_8
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, TO_DATE(%s, 'YYYY-MM-DD HH24:MI:SS'), TO_DATE(%s, 'YYYY-MM-DD HH24:MI:SS'),
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, TO_DATE(%s, 'YYYY-MM-DD HH24:MI:SS'),
                    %s, %s,
                    TO_DATE(%s, 'YYYY-MM-DD'), %s,
                    %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, 'ACTIVO',
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s
                )
            """
            
            # Intentar obtener segmento desde numero_conteo para lookup remoto JDE
            segmento = None
            try:
                if numero_conteo_val and len(str(numero_conteo_val)) >= 10:
                    segmento = str(numero_conteo_val)[6:10]
                else:
                    segmento = None
            except Exception:
                segmento = None

            # Intentar obtener sucursal desde payload; si no viene, consultar JDE remoto
            sucursal_val = get_value('sucursal')
            if (not sucursal_val or sucursal_val == '') and segmento:
                try:
                    # Obtener punto_emision
                    print(f"🔁 Ejecutando JDE punto_emision para SAP_WERKS={segmento}")
                    cursor.execute("""
                        SELECT punto_emision
                        FROM jde_general@DBL_CLOUDFRIDTMAN.REDBDD.REDPROD.ORACLEVCN.COM
                        WHERE SAP_WERKS = %s
                    """, [segmento])
                    row = cursor.fetchone()
                    print(f"🔎 Resultado JDE punto_emision: {row!r}")
                    if row and row[0] is not None:
                        sucursal_val = row[0]
                        print(f"🔎 Sucursal obtenida desde JDE (segmento={segmento}): {sucursal_val}")
                    else:
                        print(f"⚠️ No se encontró punto_emision en JDE para SAP_WERKS={segmento}")

                    # Obtener PAIS desde JDE
                    pais_val = None
                    try:
                        print(f"🔁 Ejecutando JDE PAIS para SAP_WERKS={segmento}")
                        cursor.execute("""
                            SELECT PAIS
                            FROM jde_general@DBL_CLOUDFRIDTMAN.REDBDD.REDPROD.ORACLEVCN.COM
                            WHERE SAP_WERKS = %s
                        """, [segmento])
                        rowp = cursor.fetchone()
                        print(f"🔎 Resultado JDE PAIS: {rowp!r}")
                        if rowp and rowp[0] is not None:
                            pais_val = rowp[0]
                            print(f"🔎 PAIS obtenido desde JDE (segmento={segmento}): {pais_val}")
                    except Exception as e:
                        print(f"⚠️ Error consultando JDE para PAIS: {e}")
                        pais_val = get_value('pais')

                    # Obtener sap_hcm_mcu desde JDE (para centro)
                    sap_hcm_mcu_val = None
                    try:
                        print(f"🔁 Ejecutando JDE sap_hcm_mcu para SAP_WERKS={segmento}")
                        cursor.execute("""
                            SELECT sap_hcm_mcu
                            FROM jde_general@DBL_CLOUDFRIDTMAN.REDBDD.REDPROD.ORACLEVCN.COM
                            WHERE SAP_WERKS = %s
                        """, [segmento])
                        rowm = cursor.fetchone()
                        print(f"🔎 Resultado JDE sap_hcm_mcu: {rowm!r}")
                        if rowm and rowm[0] is not None:
                            sap_hcm_mcu_val = rowm[0]
                            print(f"🔎 sap_hcm_mcu obtenido desde JDE (segmento={segmento}): {sap_hcm_mcu_val}")
                    except Exception as e:
                        print(f"⚠️ Error consultando JDE para sap_hcm_mcu: {e}")
                        sap_hcm_mcu_val = None

                    # Si obtuvimos sap_hcm_mcu, usarlo para sobreescribir centro
                    if sap_hcm_mcu_val:
                        centro_val = sap_hcm_mcu_val
                        print(f"ℹ️ Centro sobrescrito por sap_hcm_mcu: {centro_val}")

                except Exception as e:
                    print(f"⚠️ Error consultando JDE para sucursal/pais/centro: {e}")
                    sucursal_val = get_value('sucursal')
                    pais_val = get_value('pais')
                    sap_hcm_mcu_val = None
            else:
                pais_val = get_value('pais')
                sap_hcm_mcu_val = None

            # Mostrar valores importantes antes del INSERT para depuración
            print(f"🛠️ Preparando INSERT: segmento={segmento}, sucursal_val={sucursal_val!r}, pais_val={pais_val!r}, sap_hcm_mcu_val={sap_hcm_mcu_val!r}, centro_val={centro_val!r}")

            # Mostrar claves recibidas y valores de stock para depuración
            try:
                print(f"🔔 Claves recibidas en payload: {list(data.keys())}")
            except Exception:
                pass

            # Preparar parámetros
            print(f"🔔 Valores Stock antes de INSERT: calzado=({stock_sap_descripcion_calzado},{stock_sap_valor_calzado}), ropa=({stock_sap_descripcion_ropa},{stock_sap_valor_ropa}), accesorio=({stock_sap_descripcion_accesorio},{stock_sap_valor_accesorio}), fundas=({stock_sap_descripcion_fundas},{stock_sap_valor_fundas}), otros=({stock_sap_descripcion_otros},{stock_sap_valor_otros}), total={stock_sap_total}")
            params = [
                piqueo_id_val, centro_val, almacen_val, numero_conteo_val, empresa_val,
                pais_val, concepto_val,
                tienda_val, fecha_primer_conteo_fmt, fecha_segundo_conteo_fmt,
                get_number('jefe_tienda', 0),
                get_number('subjefe_tienda', 0),
                get_number('auxiliar_ventas', 0),
                get_number('auxiliar_caja', 0),
                get_number('auxiliar_bodega', 0),
                get_number('auxiliar_operativo', 0),
                get_number('asistente_opertaivo_inventario', 0),
                get_number('jefe_inventarios', 0),
                get_number('auditor_interno', 0),
                get_number('contado', 0),
                get_number('gerente_regional', 0),
                get_number('supervisor_comercial', 0),
                stock_sap_descripcion_calzado,
                stock_sap_valor_calzado,
                stock_sap_descripcion_ropa,
                stock_sap_valor_ropa,
                stock_sap_descripcion_accesorio,
                stock_sap_valor_accesorio,
                stock_sap_descripcion_fundas,
                stock_sap_valor_fundas,
                stock_sap_descripcion_otros,
                stock_sap_valor_otros,
                stock_sap_total,
                get_number('cantidad_marcas', 0),
                get_number('cantidad_lineas', 0),
                get_number('cantidad_items', 0),
                get_number('cantidad_items_faltantes', 0),
                get_number('cantidad_items_sobrantes', 0),
                get_number('valor_items_faltantes', 0),
                get_number('valor_items_sobrantes', 0),
                get_value('codigo_inventario'),
                get_value('lineas_diferencias'),
                hora_genero_informe_fmt,
                get_value('toma_fisica_grupo'),
                get_value('confirmo_encerado_guia_remi'),
                fecha_toma_anterior_fmt,
                get_number('cantidad_item_ultimo_inv', 0),
                get_value('numero_toma_fisica_anterior', ''),
                get_number('cantidad_item_acumula_anual', 0),
                get_number('valor_efectivo', 0),
                get_number('valor_facturas', 0),
                get_number('valor_cheques', 0),
                get_number('fondo_caja', 0),
                get_number('fondo_sueltos', 0),
                get_number('total', 0),
                sucursal_val,
                get_value('ultima_fact_caja1'),
                get_value('ultima_fact_caja2'),
                get_value('ultima_fact_caja3'),
                get_value('ultima_fact_caja4'),
                get_value('ultima_fact_caja5'),
                get_value('ultimo_doc_guia_remision'),
                get_value('ultimo_doc_nota_credit'),
                get_number('cantidad_toma_revisada', 0),
                get_number('porcentaje_inventariado_hoy', 0),
                get_number('total_items_por_inventariar', 0),
                get_number('horas_suspendidas_atencion', 0),
                get_number('total_gastos_ejecucion', 0),
                get_value('gerente_operaciones_cargo', '').upper(),
                get_value('gerente_operaciones_firma', '').upper(),
                get_value('jefe_inventarios_cargo', '').upper(),
                get_value('jefe_inventarios_firma', '').upper(),
                get_value('supervisor_comercial_cargo', '').upper(),
                get_value('supervisor_comercial_firma', '').upper(),
                get_value('asistente_control_inventarios_cargo', '').upper(),
                get_value('asistente_control_inventarios_firma', '').upper(),
                get_value('jefe_tienda_cargo', '').upper(),
                get_value('jefe_tienda_firma', '').upper(),
                get_value('sub_jefe_tienda_cargo', '').upper(),
                get_value('sub_jefe_tienda_firma', '').upper(),
                get_value('contador_general_cargo', '').upper(),
                get_value('contador_general_firma', '').upper(),
                get_value('auditor_interno_cargo', '').upper(),
                get_value('auditor_interno_firma', '').upper()
            ]
            
            cursor.execute(sql, params)

            # Guardar PAIS y SAP_HCM_MCU si los obtuvimos (UPDATE posterior al INSERT)
            try:
                if (pais_val is not None) or (sap_hcm_mcu_val is not None):
                    cursor.execute("""
                        UPDATE acta_preliminar_tbl
                        SET PAIS = %s,
                            SAP_HCM_MCU = %s
                        WHERE PIQUEO_ID = %s
                    """, [pais_val, sap_hcm_mcu_val, piqueo_id_val])
                    print(f"✅ PAIS/SAP_HCM_MCU actualizados en acta_preliminar_tbl para piqueo_id={piqueo_id_val}")
            except Exception as e:
                print(f"⚠️ Error actualizando PAIS/SAP_HCM_MCU en acta_preliminar_tbl: {e}")

            # Actualizar estado del piqueo a ACTA_PRELIMINAR
            cursor.execute("""
                UPDATE INV_PIQUEOS_INVENTARIO_TBL
                SET estado = 'ACTA_PRELIMINAR'
                WHERE piqueo_id = %s
            """, [get_value('piqueo_id')])
            
            connection.commit()
            
            print(f"✅ Acta preliminar guardada exitosamente para conteo: {get_value('numero_conteo')}")
            print(f"✅ Estado del piqueo actualizado a ACTA_PRELIMINAR")
            try:
                # Verificar qué se insertó en la tabla para SUCURSAL
                cursor.execute("SELECT SUCURSAL, PAIS, SAP_HCM_MCU FROM acta_preliminar_tbl WHERE PIQUEO_ID = %s", [piqueo_id_val])
                suc_row = cursor.fetchone()
                if suc_row:
                    print(f"🔍 Valores en acta_preliminar_tbl para piqueo_id={piqueo_id_val}: SUCURSAL={suc_row[0]!r}, PAIS={suc_row[1]!r}, SAP_HCM_MCU={suc_row[2]!r}")
                else:
                    print(f"⚠️ No se encontró registro en acta_preliminar_tbl para piqueo_id={piqueo_id_val} al verificar SUCURSAL/PAIS/SAP_HCM_MCU")
            except Exception as e:
                print(f"⚠️ Error verificando SUCURSAL insertada: {e}")
        
        return JsonResponse({
            'success': True,
            'message': 'Acta preliminar guardada exitosamente. El estado del conteo ha sido actualizado.'
        })
    
    except Exception as e:
        print(f"❌ Error al guardar acta preliminar: {e}")
        import traceback
        traceback.print_exc()
        
        try:
            connection.rollback()
        except:
            pass
        
        return JsonResponse({
            'success': False,
            'message': f'Error al guardar acta preliminar: {str(e)}'
        }, status=500)


@require_http_methods(["POST"])
def eliminar_acta_preliminar(request, piqueo_id):
    """
    Vista para eliminar el acta preliminar y volver el estado a SEGUNDO_CONTEO
    """
    if 'usuario' not in request.session:
        return JsonResponse({'success': False, 'message': 'No autenticado'}, status=401)

    try:
        print(f"🗑️ [ELIMINAR_ACTA] Iniciando eliminación para piqueo_id: {piqueo_id}")
        
        with connection.cursor() as cursor:
            # Verificar que el piqueo existe y está en estado ACTA_PRELIMINAR
            cursor.execute("""
                SELECT numero_conteo, estado
                FROM INV_PIQUEOS_INVENTARIO_TBL
                WHERE piqueo_id = %s
            """, [piqueo_id])
            
            row = cursor.fetchone()
            if not row:
                return JsonResponse({
                    'success': False,
                    'message': 'Conteo no encontrado'
                }, status=404)
            
            numero_conteo, estado_actual = row
            
            if estado_actual.upper() != 'ACTA_PRELIMINAR':
                return JsonResponse({
                    'success': False,
                    'message': f'El conteo no tiene un acta preliminar generada. Estado actual: {estado_actual}'
                })
            
            # Eliminar el acta de la tabla acta_preliminar_tbl
            cursor.execute("""
                DELETE FROM acta_preliminar_tbl
                WHERE piqueo_id = %s
            """, [piqueo_id])
            
            registros_eliminados = cursor.rowcount
            print(f"📊 Registros eliminados de acta_preliminar_tbl: {registros_eliminados}")
            
            # Actualizar el estado del piqueo a SEGUNDO_CONTEO
            cursor.execute("""
                UPDATE INV_PIQUEOS_INVENTARIO_TBL
                SET estado = 'SEGUNDO_CONTEO'
                WHERE piqueo_id = %s
            """, [piqueo_id])
            
            connection.commit()
            
            print(f"✅ Acta preliminar eliminada exitosamente para conteo: {numero_conteo}")
            print(f"✅ Estado del piqueo actualizado a SEGUNDO_CONTEO")
        
        return JsonResponse({
            'success': True,
            'message': f'Acta preliminar eliminada exitosamente. El conteo {numero_conteo} volvió al estado SEGUNDO_CONTEO.'
        })
    
    except Exception as e:
        print(f"❌ Error al eliminar acta preliminar: {e}")
        import traceback
        traceback.print_exc()
        
        try:
            connection.rollback()
        except:
            pass
        
        return JsonResponse({
            'success': False,
            'message': f'Error al eliminar acta preliminar: {str(e)}'
        }, status=500)
