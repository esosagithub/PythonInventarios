from django.contrib import admin
from django.urls import path, include
from inventario import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.custom_login, name='login'),
    path('login/', views.custom_login, name='login'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('administracion-conteo/', views.administracion_conteo, name='administracion_conteo'),
    path('administracion-conteo-jefe/', views.administracion_conteo_jefe, name='administracion_conteo_jefe'),
    path('administracion-conteo/filtrar/', views.administracion_conteo, name='filtrar_conteos'),
    path('conteo/<int:piqueo_id>/detalle/', views.detalle_conteo, name='detalle_conteo'), 
    path('seleccionar-perfil/', views.seleccionar_perfil, name='seleccionar_perfil'), 
    path('nuevo-conteo/', views.nuevo_conteo, name='nuevo_conteo'),
    path('nuevo-conteo-jefe/', views.nuevo_conteo_jefe, name='nuevo_conteo_jefe'),
    path('guardar-conteo/', views.guardar_conteo, name='guardar_conteo'),
    path('guardar-conteo-jefe/', views.guardar_conteo_jefe, name='guardar_conteo_jefe'),
    path('conteo/<int:conteo_id>/eliminar/', views.eliminar_conteo, name='eliminar_conteo'),
    path('gestion-conteos/', views.gestion_conteos, name='gestion_conteos'),
    path('primer-conteo/', views.primer_conteo, name='primer_conteo'),
    
    path('asigna-conteo-colaborador/<int:piqueo_id>/', views.asigna_conteo_colaborador, name='asigna_conteo_colaborador'),
    path('obtener-colaboradores/', views.obtener_colaboradores, name='obtener_colaboradores'),
    path('guardar-colaboradores/', views.guardar_colaboradores, name='guardar_colaboradores'),
    path('obtener-colaboradores-piqueo/<int:piqueo_id>/', views.obtener_colaboradores_piqueo, name='obtener_colaboradores_piqueo'),
    path('eliminar-colaborador-piqueo/', views.eliminar_colaborador_piqueo, name='eliminar_colaborador_piqueo'),
    path('validar-colaborador-disponible/', views.validar_colaborador_disponible, name='validar_colaborador_disponible'),
    path('obtener-secuenciales/<int:detalle_piqueo_id>/', views.obtener_secuenciales, name='obtener_secuenciales'),
    path('guardar-secuenciales/', views.guardar_secuenciales, name='guardar_secuenciales'),
    path('eliminar-secuencial/', views.eliminar_secuencial, name='eliminar_secuencial'),
    path('imprimir-zonas/<int:detalle_piqueo_id>/', views.imprimir_zonas_print, name='imprimir_zonas_pdf'),
    path('imprimir-zonas/<int:detalle_piqueo_id>/', views.imprimir_zonas_print, name='imprimir_zonas'),
    path('imprimir-zonas-pdf/<int:detalle_piqueo_id>/', views.imprimir_zonas_pdf, name='imprimir_zonas_pdf_solo'),
    path('actualizar-secuencia/', views.actualizar_secuencia_hasta, name='actualizar_secuencia'),
    # Rutas específicas para Primer Conteo
    path('obtener-detalle-piqueo-primer-conteo/', views.obtener_detalle_piqueo_primer_conteo, name='obtener_detalle_piqueo_primer_conteo'),
    path('obtener-barcodes-escaneo-primer-conteo/', views.obtener_barcodes_escaneo_primer_conteo, name='obtener_barcodes_escaneo_primer_conteo'),
    path('eliminar-barcode-primer-conteo/', views.eliminar_barcode_primer_conteo, name='eliminar_barcode_primer_conteo'),
    path('eliminar-todos-barcodes-primer-conteo/', views.eliminar_todos_barcodes_primer_conteo, name='eliminar_todos_barcodes_primer_conteo'),
    path('eliminar-toma-primer-conteo/', views.eliminar_toma_primer_conteo, name='eliminar_toma_primer_conteo'),
    path('reprocesar-ean-primer-conteo/', views.reprocesar_ean_primer_conteo, name='reprocesar_ean_primer_conteo'),
    path('cerrar-conteo-primer-conteo/', views.cerrar_conteo_primer_conteo, name='cerrar_conteo_primer_conteo'),
    path('obtener-estadisticas-conteo/', views.obtener_estadisticas_conteo, name='obtener_estadisticas_conteo'),
    path('obtener-detalle-secuencias/<int:secuencial_id>/', views.obtener_detalle_secuencias, name='obtener_detalle_secuencias'),
    path('anular-secuencia-detalle/', views.anular_secuencia_detalle, name='anular_secuencia_detalle'),
    path('activar-secuencia-detalle/', views.activar_secuencia_detalle, name='activar_secuencia_detalle'),
    path('obtener-datos-tienda-piqueo-manual/', views.obtener_datos_tienda_piqueo_manual, name='obtener_datos_tienda_piqueo_manual'),
    path('validar-codigo-barras-piqueo-manual/', views.validar_codigo_barras_piqueo_manual, name='validar_codigo_barras_piqueo_manual'),
    path('guardar-piqueo-manual/', views.guardar_piqueo_manual, name='guardar_piqueo_manual'),
    # Reporte Primer Conteo
    path('reporte-primer-conteo/', views.reporte_primer_conteo, name='reporte_primer_conteo'),
    # Segundo Conteo
    path('segundo-conteo/', views.segundo_conteo, name='segundo_conteo'),
    path('finalizar-conteo/<int:piqueo_id>/', views.finalizar_conteo, name='finalizar_conteo'),
    path('diferencias-segundo-conteo/<int:piqueo_id>/', views.diferencias_segundo_conteo, name='diferencias_segundo_conteo'),
    path('asignar-colaborador-diferencia/', views.asignar_colaborador_diferencia, name='asignar_colaborador_diferencia'),
    path('obtener-colaboradores-conteo-redistribucion/', views.obtener_colaboradores_conteo_redistribucion, name='obtener_colaboradores_conteo_redistribucion'),
    path('redistribuir-diferencias-segundo-conteo/', views.redistribuir_diferencias_segundo_conteo, name='redistribuir_diferencias_segundo_conteo'),
    
    path('obtener-secuenciales-activos/<int:detalle_piqueo_id>/', views.obtener_secuenciales_activos, name='obtener_secuenciales_activos'),
    path('imprimir-zona-secuencia/<int:secuencial_deta_id>/', views.imprimir_zona_secuencia_print, name='imprimir_zona_secuencia'),
    path('imprimir-zonas-cola/', views.imprimir_zonas_cola, name='imprimir_zonas_cola'),
    
    # Tercer Conteo
    path('tercer-conteo/', views.tercer_conteo, name='tercer_conteo'),
    path('detalle-tercer-conteo/<str:numero_conteo>/', views.detalle_tercer_conteo, name='detalle_tercer_conteo'),
    path('guardar-detalle-tercer-conteo/', views.guardar_detalle_tercer_conteo, name='guardar_detalle_tercer_conteo'),
    path('actualizar-estado-tercer-conteo/', views.actualizar_estado_tercer_conteo, name='actualizar_estado_tercer_conteo'),
    path('acta-final/', views.acta_final, name='acta_final'),
    path('formulario-acta-final/', views.formulario_acta_final, name='formulario_acta_final'),
    path('guardar-acta-final/', views.guardar_acta_final, name='guardar_acta_final'),
    path('eliminar-acta-final/<int:acta_final_id>/', views.eliminar_acta_final, name='eliminar_acta_final'),
    path('imprimir-acta-final/<int:acta_final_id>/', views.imprimir_acta_final_pdf, name='imprimir_acta_final_pdf'),

    # Acta Preliminar
    path('acta-preliminar/', views.acta_preliminar, name='acta_preliminar'),
    path('formulario-acta-preliminar/<int:piqueo_id>/', views.formulario_acta_preliminar, name='formulario_acta_preliminar'),
    path('guardar-acta-preliminar/', views.guardar_acta_preliminar, name='guardar_acta_preliminar'),
    path('eliminar-acta-preliminar/<int:piqueo_id>/', views.eliminar_acta_preliminar, name='eliminar_acta_preliminar'),
    path('imprimir-acta-preliminar/<int:piqueo_id>/', views.imprimir_acta_preliminar_pdf, name='imprimir_acta_preliminar_pdf'),
    
    ]
