import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from inventario import views


class ReprocesarEanPrimerConteoTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, codigo_barras='0198632912638'):
        request = self.factory.post(
            '/reprocesar-ean-primer-conteo/',
            data=json.dumps({
                'codigo_barras': codigo_barras,
                'section_name': 'SECCION-1',
                'numero_conteo': 'CONTEO-1',
            }),
            content_type='application/json'
        )
        request.session = {'usuario': {'cedula': '0912345678'}}
        return request

    def _cursor(self, estados):
        cursor = MagicMock()
        cursor.fetchall.return_value = [(estado,) for estado in estados]
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        cursor_context.__exit__.return_value = False
        return cursor, cursor_context

    @patch('inventario.views._puede_acceder_seccion', return_value=True)
    @patch(
        'inventario.views._obtener_estado_validacion_seccion',
        return_value='VALIDADO'
    )
    def test_informa_exito_solo_si_el_estado_persistido_es_validado(
        self,
        estado_seccion,
        puede_acceder
    ):
        cursor, cursor_context = self._cursor(['VALIDADO'])

        with patch('builtins.print'), patch(
            'inventario.views.connection'
        ) as database_connection:
            database_connection.cursor.return_value = cursor_context
            response = views.reprocesar_ean_primer_conteo(self._request())

        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['estado_ean'], 'VALIDADO')
        cursor.callproc.assert_called_once_with(
            'sp_actualiza_ean',
            ['0198632912638', 'CONTEO-1']
        )

    @patch('inventario.views._puede_acceder_seccion', return_value=True)
    @patch(
        'inventario.views._obtener_estado_validacion_seccion',
        return_value='ERROR'
    )
    def test_no_reporta_exito_si_el_sp_deja_el_ean_no_encontrado(
        self,
        estado_seccion,
        puede_acceder
    ):
        cursor, cursor_context = self._cursor(['NO_ENCONTRADO'])

        with patch('builtins.print'), patch(
            'inventario.views.connection'
        ) as database_connection:
            database_connection.cursor.return_value = cursor_context
            response = views.reprocesar_ean_primer_conteo(self._request())

        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertTrue(data['sp_ejecutado'])
        self.assertEqual(data['estado_ean'], 'NO_ENCONTRADO')


class ParseoNumericoFormularioTests(SimpleTestCase):
    def test_parsea_enteros_con_separadores_de_miles(self):
        self.assertEqual(
            views._parse_numero_formateado('6.088', entero=True),
            6088
        )
        self.assertEqual(
            views._parse_numero_formateado('6,088', entero=True),
            6088
        )

    def test_parsea_monedas_con_formato_local_y_us(self):
        self.assertEqual(
            views._parse_numero_formateado('$1.234,56'),
            1234.56
        )
        self.assertEqual(
            views._parse_numero_formateado('1,234.56'),
            1234.56
        )

    def test_parsea_porcentaje_decimal(self):
        self.assertEqual(
            views._parse_numero_formateado('74,90%'),
            74.9
        )


class AlcanceTiendaTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get('/')
        self.request.session = {
            'usuario': {'cedula': '0912345678'},
            'perfil_seleccionado': {'nombre': 'JEFE DE TIENDA'},
        }

    @patch('inventario.views.requests.post')
    def test_jefe_usa_parejas_exactas_centro_almacen(self, post):
        response = Mock()
        response.json.return_value = [
            {
                'centro': 'C001',
                'mcu': 'A001',
                'UNIDAD_NEGOCIO': 'TIENDA UNO',
            },
            {
                'centro': 'C002',
                'mcu': 'A002',
                'UNIDAD_NEGOCIO': 'TIENDA DOS',
            },
        ]
        post.return_value = response

        filtro, params = views._filtro_conteos_usuario(self.request, 'p')

        self.assertEqual(
            filtro,
            '((p.centro = %s AND p.almacen = %s) OR '
            '(p.centro = %s AND p.almacen = %s))'
        )
        self.assertEqual(params, ['C001', 'A001', 'C002', 'A002'])
        self.assertTrue(
            views._puede_acceder_tienda(self.request, 'C001', 'A001')
        )
        self.assertFalse(
            views._puede_acceder_tienda(self.request, 'C001', 'A002')
        )

    def test_normaliza_unidad_negocio_y_codigo_mcu(self):
        tiendas = views._normalizar_tiendas([{
            'centro': 'EC01',
            'mcu': 'NQN1',
            'UNIDAD_NEGOCIO': 'NIKE QUICENTRO SHOPPING',
            'ceco': '0001NQN1',
        }])

        self.assertEqual(tiendas[0]['unidad_negocio'], 'NIKE QUICENTRO SHOPPING')
        self.assertEqual(tiendas[0]['mcu'], 'NQN1')
        self.assertEqual(tiendas[0]['almacen'], 'NQN1')

    def test_normaliza_respuesta_de_tienda_con_claves_en_mayusculas(self):
        tiendas = views._normalizar_tiendas([{
            'CENTRO': 'EC01',
            'MCU': 'NQN1',
            'PAIS': 'ECUADOR',
            'CECO': '0001NQN1',
            'NOMINA_NOM': 'USUARIO',
            'NOMINA_APE': 'PRUEBA',
            'CEDULA': '1314743970',
        }])

        self.assertEqual(tiendas[0]['centro'], 'EC01')
        self.assertEqual(tiendas[0]['mcu'], 'NQN1')
        self.assertEqual(tiendas[0]['pais'], 'ECUADOR')
        self.assertEqual(tiendas[0]['ceco'], '0001NQN1')
        self.assertEqual(tiendas[0]['cedula'], '1314743970')
        self.assertEqual(tiendas[0]['nomina_nom'], 'USUARIO')
        self.assertEqual(tiendas[0]['nomina_ape'], 'PRUEBA')

    @patch('inventario.views.requests.post')
    def test_consulta_tienda_limpia_espacios_de_cedula(self, post):
        response = Mock()
        response.json.return_value = []
        response.raise_for_status.return_value = None
        post.return_value = response

        views._consultar_tiendas_colaborador('1314743970 ')

        self.assertEqual(
            json.loads(post.call_args.kwargs['data']),
            {'cedula': '1314743970'}
        )

    @patch('inventario.views.requests.post')
    def test_resuelve_tienda_desde_kostl_cuando_servicio_de_colaborador_viene_vacio(self, post):
        centros_response = Mock()
        centros_response.raise_for_status.return_value = None
        centros_response.json.return_value = [
            {'centro': 'TELESHOP', 'sociedad': 'E200'},
            {'centro': 'MARATHON', 'sociedad': 'E200'},
        ]
        tiendas_response = Mock()
        tiendas_response.raise_for_status.return_value = None
        tiendas_response.json.return_value = [
            {
                'ceco': 'E2001YTPA1',
                'mcu': 'TPA1',
                'nombre_tienda': 'TELESHOP MALL DEL PACÍFICO',
            },
        ]
        post.side_effect = [centros_response, tiendas_response]

        tiendas = views._consultar_tienda_desde_colaborador({
            'cedula': '1314743970',
            'nombre': 'MURILLO MOREIRA DIEGO ARMANDO',
            'unidad_negocio': 'TELESHOP MALL DEL PACIFICO',
            'kostl': 'E2001YTPA1',
            'cod_empresa': 'E200',
        })

        self.assertEqual(tiendas[0]['centro'], 'TELESHOP')
        self.assertEqual(tiendas[0]['mcu'], 'TPA1')
        self.assertEqual(tiendas[0]['ceco'], 'E2001YTPA1')
        self.assertEqual(tiendas[0]['pais'], 'ECUADOR')

    @patch('inventario.views.requests.post')
    def test_jefe_sin_tienda_no_ve_registros(self, post):
        response = Mock()
        response.json.return_value = []
        post.return_value = response

        filtro, params = views._filtro_conteos_usuario(self.request, 'p')

        self.assertEqual(filtro, '1=0')
        self.assertEqual(params, [])

    @patch(
        'inventario.views._consultar_tienda_desde_colaborador',
        return_value=[]
    )
    @patch(
        'inventario.views._consultar_tiendas_colaborador',
        return_value=[]
    )
    def test_nuevo_conteo_bloquea_si_no_se_resuelve_ceco(
        self,
        consultar_tiendas,
        consultar_fallback
    ):
        self.request.session['usuario'].update({
            'nombre': 'JEFE PRUEBA',
            'unidad_negocio': 'NIKE SAN MARINO',
            'kostl': 'E1001ZNSA1',
        })

        with patch('builtins.print'):
            response = views.nuevo_conteo_jefe(self.request)
        contenido = response.content.decode('utf-8')

        self.assertEqual(response.status_code, 422)
        self.assertContains(
            response,
            'No se encuentra CECO en JDE-GENERAL/TIENDASXCOCENPTOXPAIS_VIEW.',
            status_code=422
        )
        self.assertIn('/administracion-conteo-jefe/', contenido)
        consultar_tiendas.assert_called_once_with('0912345678')
        consultar_fallback.assert_called_once()

    def test_administrativo_conserva_filtro_de_listado_por_responsable(self):
        self.request.session['perfil_seleccionado'] = {
            'nombre': 'ADMINISTRATIVO'
        }

        filtro, params = views._filtro_conteos_usuario(self.request, 'p')

        self.assertEqual(filtro, 'p.usuario_responsable = %s')
        self.assertEqual(params, ['0912345678'])

    def test_administrativo_puede_validar_acciones_globales(self):
        self.request.session['perfil_seleccionado'] = {
            'nombre': 'ADMINISTRATIVO'
        }

        filtro, params = views._filtro_conteos_usuario(
            self.request, 'p', admin_global=True
        )

        self.assertEqual(filtro, '1=1')
        self.assertEqual(params, [])

    def test_otro_perfil_conserva_filtro_por_responsable(self):
        self.request.session['perfil_seleccionado'] = {
            'nombre': 'SUPERVISOR'
        }

        filtro, params = views._filtro_conteos_usuario(self.request, 'p')

        self.assertEqual(filtro, 'p.usuario_responsable = %s')
        self.assertEqual(params, ['0912345678'])


class ModificacionDiferenciaTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, perfil, payload):
        request = self.factory.post(
            '/modificar-diferencia-segundo-conteo/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        request.session = {
            'usuario': {
                'cedula': '0912345678',
                'nombre': 'JEFE PRUEBA',
            },
            'perfil_seleccionado': {'nombre': perfil},
        }
        return request

    def test_ruta_de_modificacion_existe(self):
        self.assertEqual(
            reverse('modificar_diferencia_segundo_conteo'),
            '/modificar-diferencia-segundo-conteo/'
        )

    def test_ruta_de_auditoria_existe(self):
        self.assertEqual(
            reverse(
                'auditoria_diferencias_segundo_conteo',
                args=['CONTEO-1']
            ),
            '/auditoria-diferencias-segundo-conteo/CONTEO-1/'
        )

    def test_solo_jefe_puede_modificar(self):
        request = self._request(
            'SUPERVISOR',
            {'diferencia_id': 1, 'nueva_diferencia': 2}
        )

        response = views.modificar_diferencia_segundo_conteo(request)

        self.assertEqual(response.status_code, 403)

    def test_rechaza_diferencia_no_numerica(self):
        request = self._request(
            'JEFE DE TIENDA',
            {'diferencia_id': 1, 'nueva_diferencia': 'abc'}
        )

        response = views.modificar_diferencia_segundo_conteo(request)

        self.assertEqual(response.status_code, 400)

    def test_script_log_contiene_campos_requeridos(self):
        sql_path = (
            Path(__file__).resolve().parent.parent
            / 'sql'
            / 'crear_log_modificacion_diferencia.sql'
        )
        sql = sql_path.read_text(encoding='utf-8').upper()

        for campo in (
            'NOMBRE_USUARIO',
            'CEDULA_USUARIO',
            'PROCESO',
            'CODIGO_SAP',
            'DIFERENCIA_ANTERIOR',
            'DIFERENCIA_NUEVA',
            'EAN',
            'FECHA_MODIFICACION',
        ):
            self.assertIn(campo, sql)


def _cursor_context(cursor):
    cursor_context = MagicMock()
    cursor_context.__enter__.return_value = cursor
    cursor_context.__exit__.return_value = False
    return cursor_context


def _llamada_sql(cursor, texto):
    """Devuelve (sql, params) de la última llamada a execute cuyo SQL contiene `texto`."""
    llamadas = [c.args for c in cursor.execute.call_args_list if texto in c.args[0].lower()]
    if not llamadas:
        raise AssertionError(f'No se ejecutó ninguna consulta con {texto!r}')
    return llamadas[-1]


class ActaFinalPdfConteosTests(SimpleTestCase):
    # COUNT(*) + 12 cargos (6 personal ejecutando + 6 personal administrativo)
    SIN_PRELIMINARES = (0,) + (None,) * 12
    # COUNT(*) + 6 valores de caja
    SIN_CAJA = (0,) + (None,) * 6

    def _generar_pdf(self, row, fechas_prelim, fechas_inv=None, fila_promedio=SIN_PRELIMINARES,
                     fila_codigo=None, grupos=None, tiendas=None, fila_anterior=None,
                     fila_caja=SIN_CAJA, fila_documentos=None):
        cursor = MagicMock()
        # fetchone / fetchall responden según la última consulta ejecutada
        ultima_sql = {}
        cursor.execute.side_effect = lambda sql, params=None: ultima_sql.update(sql=sql.lower())

        def fetchone():
            sql = ultima_sql.get('sql', '')
            if 'ultima_fact_caja1' in sql and 'from acta_preliminar_tbl' in sql:
                return fila_documentos
            if 'round(avg(nvl(valor_efectivo' in sql:
                return fila_caja
            if 'round(avg(' in sql:
                return fila_promedio
            if 'order by piqueo_id desc' in sql:
                return fila_codigo
            return tuple(row)

        # fila_anterior: None (sin actas anteriores), una tupla (una acta anterior) o una lista
        if fila_anterior is None:
            previas = []
        elif isinstance(fila_anterior, list):
            previas = fila_anterior
        else:
            previas = [fila_anterior]

        def fetchall():
            sql = ultima_sql.get('sql', '')
            if 'distinct centro_costo' in sql:
                return tiendas if tiendas is not None else [('CC1',)]
            if 'order by af.fecha_creacion desc' in sql:
                return previas
            if 'grupo_articulos' in sql:
                return grupos or []
            if 'fecha_conteo_2' in sql:
                return fechas_inv or []
            return fechas_prelim

        cursor.fetchone.side_effect = fetchone
        cursor.fetchall.side_effect = fetchall
        pdf = MagicMock()
        pdf.stringWidth.return_value = 10
        request = RequestFactory().get('/imprimir-acta-final/61/')
        request.session = {'usuario': {'cedula': '0912345678'}}

        with patch('inventario.views.connection') as database_connection, \
                patch('inventario.views.canvas.Canvas', return_value=pdf):
            database_connection.cursor.return_value = _cursor_context(cursor)
            response = views.imprimir_acta_final_pdf(request, 61)
        return response, cursor, pdf

    @staticmethod
    def _textos(pdf):
        return [c.args[2] for c in pdf.drawString.call_args_list]

    def test_fecha_corta_con_distintos_tipos(self):
        from datetime import date, datetime

        self.assertEqual(views._fecha_corta(datetime(2026, 11, 10, 12, 8)), '10/11/2026')
        self.assertEqual(views._fecha_corta(date(2026, 3, 1)), '01/03/2026')
        self.assertEqual(views._fecha_corta('2026-11-10 12:08:00'), '10/11/2026')
        self.assertEqual(views._fecha_corta(None), '')
        self.assertEqual(views._fecha_corta(''), '')

    def test_pdf_muestra_tabla_de_conteos_con_fecha_segundo_conteo(self):
        from datetime import datetime

        row = [None] * 82
        row[0] = 61
        row[1] = 'E2001YBSA1TP000009,E2001YBSA1TP000008,E2001YBSA1TP000006'
        row[8] = datetime(2026, 10, 2)
        row[9] = datetime(2026, 10, 7)
        row[80] = datetime(2026, 10, 7)
        row[81] = datetime(2026, 11, 10, 12, 8)
        fechas_prelim = [
            ('E2001YBSA1TP000006', datetime(2026, 10, 2, 15, 45)),
            ('E2001YBSA1TP000008', datetime(2026, 10, 6, 14, 38)),
            ('E2001YBSA1TP000009', datetime(2026, 10, 7, 12, 10)),
        ]

        response, cursor, pdf = self._generar_pdf(row, fechas_prelim)
        textos = self._textos(pdf)

        self.assertEqual(response.status_code, 200)
        llamadas = cursor.execute.call_args_list
        self.assertEqual(len(llamadas), 9)
        self.assertIn('fecha_creacion', llamadas[0].args[0].lower())
        self.assertIn('acta_preliminar_tbl', llamadas[1].args[0].lower())
        self.assertIn('round(avg(nvl(jefe_tienda', llamadas[2].args[0].lower())
        self.assertIn('round(avg(nvl(valor_efectivo', llamadas[3].args[0].lower())
        self.assertIn('ultima_fact_caja1', llamadas[4].args[0].lower())
        self.assertIn('inv_piqueos_inventario_tbl', llamadas[5].args[0].lower())
        self.assertIn('distinct d.grupo_articulos', llamadas[6].args[0].lower())
        self.assertIn('distinct centro_costo', llamadas[7].args[0].lower())
        self.assertIn('order by af.fecha_creacion desc', llamadas[8].args[0].lower())

        inicio = textos.index('Fecha Generación Acta:')
        self.assertEqual(textos[inicio:inicio + 10], [
            'Fecha Generación Acta:', '10/11/2026',
            'CONTEOS', 'Fecha Segundo Conteo',
            'E2001YBSA1TP000009', '07/10/2026',
            'E2001YBSA1TP000008', '06/10/2026',
            'E2001YBSA1TP000006', '02/10/2026',
        ])
        for texto_eliminado in ('Fecha Primer Conteo:', 'Fecha Segundo Conteo:', 'Fecha Tercer Conteo:'):
            self.assertNotIn(texto_eliminado, textos)
        self.assertFalse(any(t.startswith('Conteos:') for t in textos))

    def test_pdf_usa_fecha_de_inventario_si_no_esta_en_acta_preliminar(self):
        from datetime import datetime

        row = [None] * 82
        row[1] = 'C1,C2'
        row[81] = datetime(2026, 11, 10)
        fechas_prelim = [('C1', datetime(2026, 10, 2))]
        fechas_inv = [('C2', datetime(2026, 10, 6))]

        _, cursor, pdf = self._generar_pdf(row, fechas_prelim, fechas_inv)
        textos = self._textos(pdf)

        sql_respaldo, params_respaldo = _llamada_sql(cursor, 'fecha_conteo_2')
        self.assertIn('inv_inventario_fisico_vs_sistema', sql_respaldo.lower())
        self.assertEqual(params_respaldo, ['C2'])
        inicio = textos.index('C1')
        self.assertEqual(textos[inicio:inicio + 4], ['C1', '02/10/2026', 'C2', '06/10/2026'])

    def test_cinco_conteos_no_mueven_el_resto_del_pdf(self):
        from datetime import datetime

        def posicion_personal(numeros):
            row = [None] * 82
            row[1] = ','.join(numeros)
            row[81] = datetime(2026, 11, 10)
            _, _, pdf = self._generar_pdf(row, [])
            return next(
                c.args[1] for c in pdf.drawString.call_args_list
                if c.args[2] == 'Personal ejecutando Toma Física'
            )

        self.assertEqual(
            posicion_personal(['C1']),
            posicion_personal(['C1', 'C2', 'C3', 'C4', 'C5'])
        )

    @staticmethod
    def _seccion_dibujada(pdf, titulo):
        textos = [c.args[2] for c in pdf.drawString.call_args_list]
        inicio = textos.index(titulo)
        pares = textos[inicio + 1:inicio + 13]
        return dict(zip(pares[0::2], pares[1::2]))

    def _personal_dibujado(self, pdf):
        return self._seccion_dibujada(pdf, 'Personal ejecutando Toma Física')

    def _administrativo_dibujado(self, pdf):
        return self._seccion_dibujada(pdf, 'Personal Administrativo presente')

    def test_pdf_personal_usa_promedio_de_actas_preliminares(self):
        from datetime import datetime

        row = [None] * 82
        row[1] = 'C1,C2,C3'
        row[10:22] = [5] * 12  # valores guardados distintos al promedio
        row[81] = datetime(2026, 11, 10)

        _, cursor, pdf = self._generar_pdf(
            row, [], fila_promedio=(3, 1, 0, 8, 0, 1, 0, 1, 0, 1, 0, 0, 2)
        )

        sql_promedio, params_promedio = _llamada_sql(cursor, 'round(avg(nvl(jefe_tienda')
        self.assertIn('from acta_preliminar_tbl', sql_promedio.lower())
        self.assertIn('round(avg(nvl(auxiliar_ventas, 0)))', sql_promedio.lower())
        self.assertIn('round(avg(nvl(supervisor_comercial, 0)))', sql_promedio.lower())
        self.assertEqual(params_promedio, ['C1', 'C2', 'C3'])
        self.assertEqual(self._personal_dibujado(pdf), {
            'Jefe de Tienda': '1',
            'Subjefe de Tienda': '0',
            'Auxiliar de Ventas': '8',
            'Auxiliar de Caja': '0',
            'Auxiliar de Bodega': '1',
            'Auxiliar Operativo': '0',
        })
        self.assertEqual(self._administrativo_dibujado(pdf), {
            'Asistente Operativo Inventarios': '1',
            'Jefe de Inventarios': '0',
            'Auditor Interno': '1',
            'Contado': '0',
            'Gerente Regional': '0',
            'Supervisor Comercial': '2',
        })

    def test_pdf_sin_actas_preliminares_usa_personal_guardado(self):
        from datetime import datetime

        row = [None] * 82
        row[1] = 'C1'
        row[10:16] = [1, 0, 3, 0, 0, 0]
        row[16:22] = [0, 0, 0, 0, 0, 4]
        row[81] = datetime(2026, 11, 10)

        _, _, pdf = self._generar_pdf(row, [])

        self.assertEqual(self._personal_dibujado(pdf)['Auxiliar de Ventas'], '3')
        self.assertEqual(self._personal_dibujado(pdf)['Jefe de Tienda'], '1')
        self.assertEqual(self._administrativo_dibujado(pdf)['Supervisor Comercial'], '4')

    @staticmethod
    def _codigo_dibujado(pdf):
        textos = [c.args[2] for c in pdf.drawString.call_args_list]
        return textos[textos.index('Código de inventario:') + 1]

    def test_pdf_codigo_inventario_es_el_ultimo_conteo(self):
        from datetime import datetime

        row = [None] * 82
        row[1] = 'C1,C3,C2'
        row[40] = 'VIEJO'  # código guardado distinto
        row[81] = datetime(2026, 11, 10)

        _, cursor, pdf = self._generar_pdf(row, [], fila_codigo=('C3',))

        sql_codigo, params_codigo = _llamada_sql(cursor, 'order by piqueo_id desc')
        self.assertIn('inv_piqueos_inventario_tbl', sql_codigo.lower())
        self.assertIn('order by piqueo_id desc', sql_codigo.lower())
        self.assertIn('rownum = 1', sql_codigo.lower())
        self.assertEqual(params_codigo, ['C1', 'C3', 'C2'])
        self.assertEqual(self._codigo_dibujado(pdf), 'C3')

    def test_pdf_sin_conteos_encontrados_usa_codigo_guardado(self):
        from datetime import datetime

        row = [None] * 82
        row[1] = 'C1'
        row[40] = 'GUARDADO'
        row[81] = datetime(2026, 11, 10)

        _, _, pdf = self._generar_pdf(row, [], fila_codigo=None)

        self.assertEqual(self._codigo_dibujado(pdf), 'GUARDADO')

    @staticmethod
    def _grupo_dibujado(pdf):
        textos = [c.args[2] for c in pdf.drawString.call_args_list]
        return textos[textos.index('Toma Física grupo:') + 1]

    def test_pdf_toma_fisica_grupo_consolida_grupos_sin_repetir(self):
        from datetime import datetime

        row = [None] * 82
        row[1] = 'C1,C2,C3'
        row[43] = 'Ropa (R)'  # grupo guardado distinto
        row[81] = datetime(2026, 11, 10)

        _, cursor, pdf = self._generar_pdf(
            row, [], grupos=[('Accesorios (A)',), ('Zapatos (C)',)]
        )

        sql_grupos, params_grupos = _llamada_sql(cursor, 'grupo_articulos')
        self.assertIn('select distinct d.grupo_articulos', sql_grupos.lower())
        self.assertIn('inv_detalle_piqueos_inventarios_tbl', sql_grupos.lower())
        self.assertIn('order by d.grupo_articulos', sql_grupos.lower())
        self.assertEqual(params_grupos, ['C1', 'C2', 'C3'])
        self.assertEqual(self._grupo_dibujado(pdf), 'Accesorios (A), Zapatos (C)')

    def test_pdf_sin_grupos_planificados_usa_grupo_guardado(self):
        from datetime import datetime

        row = [None] * 82
        row[1] = 'C1'
        row[43] = 'Ropa (R)'
        row[81] = datetime(2026, 11, 10)

        _, _, pdf = self._generar_pdf(row, [], grupos=[])

        self.assertEqual(self._grupo_dibujado(pdf), 'Ropa (R)')

    def test_grupos_toma_fisica_sin_repetir_y_recortado_al_tamano_de_la_columna(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [('Accesorios (A)',), ('Accesorios (A)',), ('Zapatos (C)',)]
        self.assertEqual(
            views._grupos_toma_fisica(cursor, ['C1', 'C2', 'C1']),
            'Accesorios (A), Zapatos (C)'
        )
        self.assertEqual(cursor.execute.call_args.args[1], ['C1', 'C2'])

        cursor.fetchall.return_value = [(f'Grupo largo numero {i:02d}',) for i in range(10)]
        resultado = views._grupos_toma_fisica(cursor, ['C1'])
        self.assertEqual(len(resultado), views.TOMA_FISICA_GRUPO_MAX_LEN)

        cursor.fetchall.return_value = []
        self.assertIsNone(views._grupos_toma_fisica(cursor, ['C1']))
        self.assertIsNone(views._grupos_toma_fisica(cursor, []))


class LimiteConteosActaFinalTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.seis = ['C1', 'C2', 'C3', 'C4', 'C5', 'C6']

    @staticmethod
    def _session():
        return {
            'usuario': {'cedula': '0912345678'},
            'perfil_seleccionado': {'nombre': 'ADMINISTRATIVO'},
        }

    def _post_generar(self, numeros):
        request = self.factory.post(
            '/acta-final/',
            data=json.dumps({'action': 'generar_acta_final', 'numeros_conteo': numeros}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        request.session = self._session()
        return request

    def test_generar_acta_final_rechaza_mas_de_cinco_conteos(self):
        with patch('inventario.views.connection') as database_connection:
            response = views.acta_final(self._post_generar(self.seis))

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('Excedió el número máximo de conteos', data['message'])
        self.assertIn('seleccionó 6', data['message'])
        database_connection.cursor.assert_not_called()

    def test_generar_acta_final_acepta_cinco_conteos(self):
        cinco = self.seis[:5]
        cursor = MagicMock()
        cursor.fetchall.return_value = [(n, 'C', 'A', 'TERCER_CONTEO') for n in cinco]

        with patch('inventario.views.connection') as database_connection:
            database_connection.cursor.return_value = _cursor_context(cursor)
            response = views.acta_final(self._post_generar(cinco))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(json.loads(response.content)['success'])

    def test_guardar_acta_final_rechaza_mas_de_cinco_conteos(self):
        request = self.factory.post(
            '/guardar-acta-final/',
            data=json.dumps({
                'numeros_conteo': ','.join(self.seis),
                'centro': 'C',
                'almacen': 'A',
            }),
            content_type='application/json',
        )
        request.session = self._session()

        with patch('inventario.views.connection') as database_connection:
            response = views.guardar_acta_final(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            'Excedió el número máximo de conteos',
            json.loads(response.content)['message']
        )
        database_connection.cursor.assert_not_called()


class GuardarActaFinalPersonalTests(SimpleTestCase):
    def test_guardar_ignora_personal_enviado_y_usa_promedio_de_preliminares(self):
        from datetime import datetime

        cursor = MagicMock()
        # fetchone / fetchall responden según la última consulta ejecutada
        ultima_sql = {}
        cursor.execute.side_effect = lambda sql, params=None: ultima_sql.update(sql=sql.lower())

        def fetchone():
            sql = ultima_sql.get('sql', '')
            if 'ultima_fact_caja1' in sql and 'from acta_preliminar_tbl' in sql:
                # acta preliminar del último conteo: caja1..caja5, guía remisión, nota crédito
                return ('035030000083052', '035031000145459', None, None, None,
                        '035030000001030', '035031000003551')
            if 'round(avg(nvl(valor_efectivo' in sql:
                # COUNT, efectivo, facturas, cheques, fondo caja, fondo sueltos, total (promedios)
                return (3, 85.83, 66.83, 0, 25, 72.33, 250)
            if 'round(avg(' in sql:
                return (3, 1, 0, 8, 0, 1, 0, 1, 0, 1, 0, 0, 2)
            if 'order by piqueo_id desc' in sql:
                return ('C3',)
            if 'currval' in sql:
                return (99,)
            return None  # no existe acta final con estos conteos

        def fetchall():
            sql = ultima_sql.get('sql', '')
            if 'distinct centro_costo' in sql:
                return [('E2001YBSA1',)]
            if 'order by af.fecha_creacion desc' in sql:
                # actas finales anteriores de la tienda: (fecha_creacion, cantidad_items)
                return [(datetime(2026, 6, 24, 17, 31), Decimal('2.385'))]
            if 'grupo_articulos' in sql:
                return [('Accesorios (A)',), ('Zapatos (C)',)]
            return []

        cursor.fetchone.side_effect = fetchone
        cursor.fetchall.side_effect = fetchall
        request = RequestFactory().post(
            '/guardar-acta-final/',
            data=json.dumps({
                'numeros_conteo': 'C1,C2,C3',
                'centro': 'C',
                'almacen': 'A',
                'jefe_tienda': 7,
                'auxiliar_ventas': 99,
                'auditor_interno': 30,
                'supervisor_comercial': 50,
                'codigo_inventario': 'MANIPULADO',
                'toma_fisica_grupo': 'GRUPO MANIPULADO',
                'fecha_toma_fisica_anterior': '2000-01-01',
                'cantidad_items': '9.676',
                'cantidad_item_ultimo_inv': '999',
                'numero_toma_fisica_anterior': '77',
                'cantidad_item_acumula_anual': '5',
                'valor_efectivo': '999',
                'total': '5000',
                'ultima_fact_caja1': 'FACTURA MANIPULADA',
                'ultimo_doc_nota_credit': 'NOTA MANIPULADA',
            }),
            content_type='application/json',
        )
        request.session = {'usuario': {'cedula': '0912345678'}}

        with patch('inventario.views.connection') as database_connection:
            database_connection.cursor.return_value = _cursor_context(cursor)
            response = views.guardar_acta_final(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(json.loads(response.content)['success'])

        _, params_promedio = _llamada_sql(cursor, 'round(avg(nvl(jefe_tienda')
        self.assertEqual(params_promedio, ['C1', 'C2', 'C3'])

        _, params_caja = _llamada_sql(cursor, 'round(avg(nvl(valor_efectivo')
        self.assertEqual(params_caja, ['C1', 'C2', 'C3'])

        _, params_codigo = _llamada_sql(cursor, 'order by piqueo_id desc')
        self.assertEqual(params_codigo, ['C1', 'C2', 'C3'])

        _, params_grupos = _llamada_sql(cursor, 'distinct d.grupo_articulos')
        self.assertEqual(params_grupos, ['C1', 'C2', 'C3'])

        # Acta nueva: se buscan actas finales anteriores a SYSDATE, sin excluir ninguna (-1)
        sql_anterior, params_anterior = _llamada_sql(cursor, 'order by af.fecha_creacion desc')
        self.assertIn('af.fecha_creacion < sysdate', sql_anterior.lower())
        self.assertEqual(params_anterior, [-1, 'E2001YBSA1'])

        _, params_insert = _llamada_sql(cursor, 'insert into acta_final_tbl')
        # params: numeros, centro, almacen, empresa, pais, concepto, tienda, fecha1, fecha_ultimo,
        #         personal ejecutando x6, personal administrativo x6
        self.assertEqual(params_insert[9:15], [1, 0, 8, 0, 1, 0])
        self.assertEqual(params_insert[15:21], [1, 0, 1, 0, 0, 2])
        # Lo que sigue (stock SAP) no se desplaza
        self.assertEqual(params_insert[21], 'CALZADO')
        # [32..38] items/valores, [39] código de inventario = último conteo, no lo enviado
        self.assertEqual(params_insert[39], 'C3')
        self.assertNotIn('MANIPULADO', params_insert)
        # [40] líneas de diferencias, [41] toma física grupo = grupos consolidados, no lo enviado
        self.assertEqual(params_insert[41], 'Accesorios (A), Zapatos (C)')
        self.assertNotIn('GRUPO MANIPULADO', params_insert)
        # [42] confirmó encerado, [43] fecha toma física anterior = creación del acta final anterior
        self.assertEqual(params_insert[43], '2026-06-24')
        self.assertNotIn('2000-01-01', params_insert)
        # [44] cantidad items último inventario = la del acta final anterior (2.385 → 2385)
        self.assertEqual(params_insert[44], 2385)
        self.assertNotIn(999, params_insert[44:45])
        # [45] número de tomas físicas anteriores = actas anteriores de la tienda en ese año
        self.assertEqual(params_insert[45], '1')
        self.assertNotIn('77', params_insert)
        # [46] acumulativo anual = esta acta (9.676) + anteriores de la tienda en el año de esta acta
        #      (acta nueva → año actual; la anterior es de 2026)
        from datetime import date
        esperado_acumulado = 9676 + (2385 if date.today().year == 2026 else 0)
        self.assertEqual(params_insert[46], esperado_acumulado)
        self.assertNotIn(5, params_insert[46:47])
        # [47..52] valores de caja = promedio de las actas preliminares, no lo enviado
        self.assertEqual(params_insert[47:53], [85.83, 66.83, 0.0, 25.0, 72.33, 250.0])
        self.assertNotIn(999, params_insert[47:53])
        self.assertNotIn(5000, params_insert[47:53])
        # [53] sucursal, [54..60] últimas facturas y documentos = acta preliminar del último conteo
        #      (vacíos → NULL), no lo enviado
        self.assertEqual(params_insert[54:61], [
            '035030000083052', '035031000145459', None, None, None,
            '035030000001030', '035031000003551',
        ])
        self.assertNotIn('FACTURA MANIPULADA', params_insert)
        self.assertNotIn('NOTA MANIPULADA', params_insert)


class DocumentosUltimoConteoTests(SimpleTestCase):
    def test_toma_los_documentos_del_acta_preliminar_del_ultimo_conteo(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = (
            '035030000083052', ' 035031000145459 ', None, None, None,
            '035030000001030', '035031000003551',
        )

        resultado = views._documentos_ultimo_conteo(cursor, ['C9', 'C8', 'C6'])

        self.assertEqual(resultado, {
            'ultima_fact_caja1': '035030000083052', 'ultima_fact_caja2': '035031000145459',
            'ultima_fact_caja3': '', 'ultima_fact_caja4': '', 'ultima_fact_caja5': '',
            'ultimo_doc_guia_remision': '035030000001030', 'ultimo_doc_nota_credit': '035031000003551',
        })
        sql, params = cursor.execute.call_args.args
        self.assertIn('from acta_preliminar_tbl', sql.lower())
        self.assertIn('order by piqueo_id desc', sql.lower())
        self.assertIn('rownum = 1', sql.lower())
        self.assertEqual(params, ['C9', 'C8', 'C6'])

    def test_recorta_al_tamano_de_la_columna_y_sin_acta_devuelve_none(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = ('9' * 80, None, None, None, None, None, None)
        resultado = views._documentos_ultimo_conteo(cursor, ['C1'])
        self.assertEqual(len(resultado['ultima_fact_caja1']), views.DOCUMENTOS_MAX_LEN)

        cursor.fetchone.return_value = None
        self.assertIsNone(views._documentos_ultimo_conteo(cursor, ['C1']))
        self.assertIsNone(views._documentos_ultimo_conteo(cursor, []))

    def _pdf_documentos(self, fila_documentos):
        from datetime import datetime

        row = [None] * 82
        row[0] = 61
        row[1] = 'C1,C2,C3'
        row[56:63] = [None, None, None, None, None, 'GUIA GUARDADA', 'NOTA GUARDADA']
        row[81] = datetime(2026, 11, 10, 12, 8)
        _, _, pdf = ActaFinalPdfConteosTests()._generar_pdf(
            row, [], fila_documentos=fila_documentos
        )
        return [c.args[2] for c in pdf.drawString.call_args_list]

    def test_pdf_muestra_documentos_del_ultimo_conteo(self):
        textos = self._pdf_documentos((
            '035030000083052', '035031000145459', None, None, None,
            '035030000001030', '035031000003551',
        ))
        i = textos.index('Última factura de venta Número:')
        self.assertEqual(textos[i + 1:i + 5], ['035030000083052', 'caja1', '035031000145459', 'caja2'])
        j = textos.index('Último número documento:')
        self.assertEqual(textos[j + 1:j + 5],
                         ['035030000001030', 'Guía Remisión', '035031000003551', 'Nota Crédito'])

    def test_pdf_sin_acta_preliminar_usa_lo_guardado(self):
        textos = self._pdf_documentos(None)
        j = textos.index('Último número documento:')
        self.assertEqual(textos[j + 1:j + 5],
                         ['GUIA GUARDADA', 'Guía Remisión', 'NOTA GUARDADA', 'Nota Crédito'])


class ValoresCajaPromedioTests(SimpleTestCase):
    def test_promedio_de_valores_de_caja_de_las_actas_preliminares(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = (3, 85.83, 66.83, 0, 25, 72.33, 250)

        resultado = views._promedio_valores_caja(cursor, ['C1', 'C2', 'C3', 'C1'])

        self.assertEqual(resultado, {
            'valor_efectivo': 85.83, 'valor_facturas': 66.83, 'valor_cheques': 0.0,
            'fondo_caja': 25.0, 'fondo_sueltos': 72.33, 'total': 250.0,
        })
        sql, params = cursor.execute.call_args.args
        self.assertIn('from acta_preliminar_tbl', sql.lower())
        for campo in ('valor_efectivo', 'valor_facturas', 'valor_cheques',
                      'fondo_caja', 'fondo_sueltos', 'total'):
            self.assertIn(f'round(avg(nvl({campo}, 0)), 2)', sql.lower())
        self.assertNotIn('sum(', sql.lower())
        self.assertEqual(params, ['C1', 'C2', 'C3'])

    def test_sin_actas_preliminares_devuelve_none(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = (0, None, None, None, None, None, None)
        self.assertIsNone(views._promedio_valores_caja(cursor, ['C1']))
        self.assertIsNone(views._promedio_valores_caja(cursor, []))

    def _pdf_caja(self, fila_caja):
        from datetime import datetime

        row = [None] * 82
        row[0] = 61
        row[1] = 'C1,C2,C3'
        row[49:55] = [257.5, 200.5, 0, 75, 217, 750]  # suma guardada (se reemplaza)
        row[81] = datetime(2026, 11, 10, 12, 8)
        _, _, pdf = ActaFinalPdfConteosTests()._generar_pdf(row, [], fila_caja=fila_caja)
        textos = [c.args[2] for c in pdf.drawString.call_args_list]
        inicio = textos.index('VALORES DE CAJA')
        pares = textos[inicio + 1:inicio + 13]
        return dict(zip(pares[0::2], pares[1::2]))

    def test_pdf_muestra_el_promedio_de_caja(self):
        self.assertEqual(self._pdf_caja((3, 85.83, 66.83, 0, 25, 72.33, 250)), {
            'Efectivo': '$86', 'Facturas': '$67', 'Cheques': '$0',
            'Fondo de Caja': '$25', 'Fondo de Sueltos': '$72', 'TOTAL': '$250',
        })

    def test_pdf_sin_preliminares_usa_lo_guardado(self):
        caja = self._pdf_caja(ActaFinalPdfConteosTests.SIN_CAJA)
        self.assertEqual(caja['Efectivo'], '$258')
        self.assertEqual(caja['TOTAL'], '$750')


class InventarioAnteriorTests(SimpleTestCase):
    def _cursor(self, tiendas, previas):
        """previas: None, una tupla (fecha, cantidad) o una lista de tuplas (más reciente primero)."""
        if previas is None:
            previas = []
        elif not isinstance(previas, list):
            previas = [previas]
        cursor = MagicMock()
        cursor.fetchall.side_effect = [tiendas, previas]
        return cursor

    def test_usa_datos_del_acta_final_anterior_de_la_misma_tienda(self):
        from datetime import date, datetime

        cursor = self._cursor([('E2001YBSA1',)], (datetime(2026, 6, 24, 17, 31), 8754))
        resultado = views._inventario_anterior(
            cursor, ['C9', 'C8'], acta_final_id=61,
            fecha_creacion=datetime(2026, 11, 10, 12, 8), cantidad_items_propia=9676
        )

        self.assertEqual(resultado, {
            'fecha': date(2026, 6, 24), 'cantidad_items': 8754, 'anio': 2026,
            'numero_tomas_anteriores': 1, 'acumulado_anual': 9676 + 8754,
        })
        sql_tiendas, params_tiendas = cursor.execute.call_args_list[0].args
        self.assertIn('distinct centro_costo', sql_tiendas.lower())
        self.assertEqual(params_tiendas, ['C9', 'C8'])
        sql, params = cursor.execute.call_args_list[1].args
        self.assertIn('select af.fecha_creacion, af.cantidad_items', sql.lower())
        self.assertIn('af.acta_final_id <> %s', sql.lower())
        self.assertIn('af.fecha_creacion < %s', sql.lower())
        self.assertIn('p.centro_costo in (%s)', sql.lower())
        self.assertIn('order by af.fecha_creacion desc', sql.lower())
        self.assertEqual(params, [61, datetime(2026, 11, 10, 12, 8), 'E2001YBSA1'])

    def test_numero_tomas_y_acumulado_por_anio(self):
        from datetime import date, datetime

        previas = [
            (datetime(2027, 2, 1), 100),   # más reciente: define fecha, cantidad y año
            (datetime(2027, 1, 10), 50),
            (datetime(2026, 12, 1), 70),   # otro año: no cuenta ni suma
        ]
        cursor = self._cursor([('E2001YBSA1',)], previas)
        resultado = views._inventario_anterior(
            cursor, ['C9'], 90, datetime(2027, 6, 1), cantidad_items_propia=30
        )
        self.assertEqual(resultado['fecha'], date(2027, 2, 1))
        self.assertEqual(resultado['cantidad_items'], 100)
        self.assertEqual(resultado['anio'], 2027)
        self.assertEqual(resultado['numero_tomas_anteriores'], 2)
        self.assertEqual(resultado['acumulado_anual'], 30 + 100 + 50)

    def test_acumulado_solo_del_anio_de_esta_acta(self):
        from datetime import datetime

        # La anterior es de 2026 y esta acta de 2027: el acumulado de 2027 es solo la propia
        cursor = self._cursor([('E2001YBSA1',)], (datetime(2026, 12, 1), 500))
        resultado = views._inventario_anterior(
            cursor, ['C9'], 90, datetime(2027, 3, 1), cantidad_items_propia=40
        )
        self.assertEqual(resultado['anio'], 2026)
        self.assertEqual(resultado['numero_tomas_anteriores'], 1)
        self.assertEqual(resultado['acumulado_anual'], 40)

    def test_cantidad_guardada_con_decimal_se_interpreta_como_entero(self):
        from datetime import datetime

        cursor = self._cursor([('E2001YBSA1',)], (datetime(2026, 6, 24), Decimal('2.385')))
        resultado = views._inventario_anterior(
            cursor, ['C9'], 61, datetime(2026, 11, 10), cantidad_items_propia=9676
        )
        self.assertEqual(resultado['cantidad_items'], 2385)
        self.assertEqual(resultado['acumulado_anual'], 2385 + 9676)

    def test_sin_acta_anterior_usa_datos_propios(self):
        from datetime import date, datetime

        cursor = self._cursor([('E2001YBSA1',)], None)
        resultado = views._inventario_anterior(
            cursor, ['C1'], acta_final_id=23,
            fecha_creacion=datetime(2026, 6, 24, 17, 31), cantidad_items_propia=Decimal('2.385')
        )
        self.assertEqual(resultado, {
            'fecha': date(2026, 6, 24), 'cantidad_items': 2385, 'anio': 2026,
            'numero_tomas_anteriores': 0, 'acumulado_anual': 2385,
        })

    def test_acta_nueva_sin_anterior_usa_hoy_y_su_cantidad(self):
        from datetime import date

        cursor = self._cursor([('E2001YBSA1',)], None)
        resultado = views._inventario_anterior(cursor, ['C1'], cantidad_items_propia=500)
        self.assertEqual(resultado['fecha'], date.today())
        self.assertEqual(resultado['cantidad_items'], 500)
        self.assertEqual(resultado['anio'], date.today().year)
        self.assertEqual(resultado['numero_tomas_anteriores'], 0)
        self.assertEqual(resultado['acumulado_anual'], 500)
        self.assertIn('< sysdate', cursor.execute.call_args_list[1].args[0].lower())

    def test_sin_tienda_identificada_usa_datos_propios(self):
        from datetime import date, datetime

        cursor = self._cursor([], None)
        resultado = views._inventario_anterior(
            cursor, ['C1'], acta_final_id=5,
            fecha_creacion=datetime(2026, 10, 26, 11, 5), cantidad_items_propia=8754
        )
        self.assertEqual(resultado, {
            'fecha': date(2026, 10, 26), 'cantidad_items': 8754, 'anio': 2026,
            'numero_tomas_anteriores': 0, 'acumulado_anual': 8754,
        })
        self.assertEqual(cursor.execute.call_count, 1)

    def _pdf(self, fila_anterior, cantidad_propia=9676):
        from datetime import date, datetime

        row = [None] * 82
        row[0] = 61
        row[1] = 'C1'
        row[35] = cantidad_propia
        row[45] = date(2026, 10, 7)  # fecha guardada (se ignora)
        row[46] = 0                  # cantidad guardada (se ignora)
        row[48] = 0                  # acumulado guardado (se ignora)
        row[81] = datetime(2026, 11, 10, 12, 8)
        _, cursor, pdf = ActaFinalPdfConteosTests()._generar_pdf(
            row, [], tiendas=[('E2001YBSA1',)], fila_anterior=fila_anterior
        )
        return cursor, [c.args[2] for c in pdf.drawString.call_args_list]

    def test_pdf_muestra_datos_del_acta_anterior_y_acumulado(self):
        from datetime import datetime

        cursor, textos = self._pdf((datetime(2026, 6, 24, 17, 31), Decimal('2.385')))

        fecha_etq = 'Fecha de la toma física de inventario anterior:'
        self.assertEqual(textos[textos.index(fecha_etq) + 1], '24/06/2026')
        cant_etq = 'Cantidad Items toma física parcial último inventario 2026:'
        self.assertEqual(textos[textos.index(cant_etq) + 1], '2.385')
        tomas_etq = 'Número de tomas Físicas anteriores en el año 2026:'
        self.assertEqual(textos[textos.index(tomas_etq) + 1], '1')
        acum_etq = 'Cantidad Items toma física ACUMULATIVO ANUAL:'
        self.assertEqual(textos[textos.index(acum_etq) + 1], '12.061')
        _, params = _llamada_sql(cursor, 'order by af.fecha_creacion desc')
        self.assertEqual(params, [61, datetime(2026, 11, 10, 12, 8), 'E2001YBSA1'])

    def test_pdf_sin_acta_anterior_muestra_sus_propios_datos(self):
        cursor, textos = self._pdf(None, cantidad_propia=9676)

        cant_etq = 'Cantidad Items toma física parcial último inventario 2026:'
        self.assertEqual(textos[textos.index(cant_etq) + 1], '9.676')
        fecha_etq = 'Fecha de la toma física de inventario anterior:'
        self.assertEqual(textos[textos.index(fecha_etq) + 1], '10/11/2026')
        tomas_etq = 'Número de tomas Físicas anteriores en el año 2026:'
        self.assertEqual(textos[textos.index(tomas_etq) + 1], '0')
        acum_etq = 'Cantidad Items toma física ACUMULATIVO ANUAL:'
        self.assertEqual(textos[textos.index(acum_etq) + 1], '9.676')


def _mapear_insert(sql, params):
    """Asocia cada columna de un INSERT ... VALUES (...) con su parámetro (o literal)."""
    import re

    m = re.search(r'INSERT\s+INTO\s+\w+\s*\((.*?)\)\s*VALUES\s*\((.*)\)', sql, re.S | re.I)
    columnas = [c.strip().upper() for c in m.group(1).split(',')]
    valores = [v.strip() for v in m.group(2).split(',')]
    if len(columnas) != len(valores):
        raise AssertionError(f'{len(columnas)} columnas vs {len(valores)} valores en el INSERT')
    placeholders = sum(1 for v in valores if v == '%s')
    if placeholders != len(params):
        raise AssertionError(f'{placeholders} placeholders vs {len(params)} parámetros')
    parametros = iter(params)
    return {
        col: (next(parametros) if val == '%s' else val)
        for col, val in zip(columnas, valores)
    }


class GuardarActaPreliminarPersonalAdministrativoTests(SimpleTestCase):
    COLUMNAS_ADMINISTRATIVO = {
        'ASISTENTE_OPERTAIVO_INVENTARIO': 'asistente_opertaivo_inventario',
        'JEFE_INVENTARIOS': 'jefe_inventarios',
        'AUDITOR_INTERNO': 'auditor_interno',
        'CONTADO': 'contado',
        'GERENTE_REGIONAL': 'gerente_regional',
        'SUPERVISOR_COMERCIAL': 'supervisor_comercial',
    }

    def _guardar(self, extra):
        cursor = MagicMock()
        ultima_sql = {}
        cursor.execute.side_effect = lambda sql, params=None: ultima_sql.update(sql=sql.lower())

        def fetchone():
            sql = ultima_sql.get('sql', '')
            if 'from inv_piqueos_inventario_tbl' in sql:
                return ('E2001YBSA1TP000099', 'C001', 'A001')
            if 'inv_inventario_fisico_vs_sistema' in sql:
                return (0, 0, 0, 0, 0, 0)
            if 'select sucursal, pais' in sql:
                return ('S', 'P')
            return None

        cursor.fetchone.side_effect = fetchone

        # Payload como lo arma FormData en el formulario: todo en texto
        payload = {
            'piqueo_id': '999',
            'numero_conteo': 'E2001YBSA1TP000099',
            'centro': 'C001',
            'almacen': 'A001',
            'sucursal': 'SUC1',  # evita las consultas a JDE
            'pais': 'ECUADOR',
            'jefe_tienda': '1',
            'auxiliar_ventas': '8',
        }
        payload.update(extra)
        request = RequestFactory().post(
            '/guardar-acta-preliminar/',
            data=json.dumps(payload),
            content_type='application/json',
        )
        request.session = {'usuario': {'cedula': '0912345678'}}

        # La vista imprime emojis de depuración; se silencia print para que la prueba
        # no dependa de la codificación de la consola (cp1252 en Windows).
        with patch('inventario.views._puede_acceder_piqueo', return_value=True), \
                patch('inventario.views.print', create=True), \
                patch('inventario.views.connection') as database_connection:
            database_connection.cursor.return_value = _cursor_context(cursor)
            response = views.guardar_acta_preliminar(request)

        llamadas = [c.args for c in cursor.execute.call_args_list]
        insert = next(a for a in llamadas if 'insert into acta_preliminar_tbl' in a[0].lower())
        return response, llamadas, _mapear_insert(*insert)

    def test_personal_administrativo_se_guarda_en_su_columna(self):
        enviados = {
            'asistente_opertaivo_inventario': '1',
            'jefe_inventarios': '2',
            'auditor_interno': '3',
            'contado': '4',
            'gerente_regional': '5',
            'supervisor_comercial': '6',
        }

        response, llamadas, fila = self._guardar(enviados)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(json.loads(response.content)['success'])
        for columna, campo in self.COLUMNAS_ADMINISTRATIVO.items():
            self.assertEqual(fila[columna], int(enviados[campo]), columna)
            self.assertIsInstance(fila[columna], int, columna)
        # El personal ejecutando también queda en su columna
        self.assertEqual(fila['JEFE_TIENDA'], 1)
        self.assertEqual(fila['AUXILIAR_VENTAS'], 8)
        self.assertEqual(fila['ESTADO'], "'ACTIVO'")
        self.assertTrue(any(
            "set estado = 'acta_preliminar'" in a[0].lower() for a in llamadas
        ))

    def test_personal_administrativo_no_enviado_se_guarda_en_cero(self):
        _, _, fila = self._guardar({})

        for columna in self.COLUMNAS_ADMINISTRATIVO:
            self.assertEqual(fila[columna], 0, columna)
