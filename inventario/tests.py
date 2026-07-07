import json
from pathlib import Path
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from inventario import views


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
