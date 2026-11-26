import json
from datetime import date, datetime, time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from posApp.models import (Asistencia, Category, Clientes, FormaPago, Grupo, Levels, Mensualidad, Products, Sales,
                           Sucursal, UserProfile, salesItems)
from posApp.horarios import leer_horario
from posApp.proximo_pago import dia_de_pago, leer_proximo_pago
from posApp.templatetags.whatsapp import numero_whatsapp, whatsapp_adeudo
from posApp.views_asistencia import grupo_en_curso
from posApp.views_asistencia import AL_CORRIENTE, POR_VENCER, SIN_PAGOS, VENCIDO, calcular_estados_pago


def crear_cliente(sucursal, nombre, horario='5 pm', nivel=None, status=1):
    return Clientes.objects.create(
        nombre=nombre, apellido_paterno='Pérez', apellido_materno='López', direccion='x', suburbio='x',
        codigo_postal='97000', celular='9990000000', sangre='O+', contacto_emergencia='x', emergency_phone='x',
        pay_day='1 de cada mes', condicion_medica='', horario=horario, nivel=nivel, status=status, sucursal=sucursal,
    )


class AsistenciaTests(TestCase):
    def setUp(self):
        self.sucursal = Sucursal.objects.create(nombre='Acuatica Urioste Chuburna')
        self.otra_sucursal = Sucursal.objects.create(nombre='Otra')
        self.user = User.objects.create_user('recepcion', password='x')
        UserProfile.objects.create(user=self.user, sucursal=self.sucursal, is_seller=True)
        self.client.force_login(self.user)

        self.nivel = Levels.objects.create(level='Principiantes', sucursal=self.sucursal)
        self.ana = crear_cliente(self.sucursal, 'Ana', '5 pm', self.nivel)
        self.beto = crear_cliente(self.sucursal, 'Beto', '5PM', self.nivel)
        self.carla = crear_cliente(self.sucursal, 'Carla', '7am', self.nivel)
        self.baja = crear_cliente(self.sucursal, 'Inactivo', '5pm', self.nivel, status=4)
        self.ajeno = crear_cliente(self.otra_sucursal, 'Ajeno', '5pm')

        categoria = Category.objects.create(name='Clases', description='', sucursal=self.sucursal)
        self.mensualidad = Products.objects.create(code='1', category_id=categoria, name='3 CLA X SEM', description='',
                                                   price=1250, sucursal=self.sucursal, dias_vigencia=30)
        self.refresco = Products.objects.create(code='2', category_id=categoria, name='Coca cola', description='',
                                                price=25, sucursal=self.sucursal)
        self.forma_pago = FormaPago.objects.create(tipo='Efectivo')

    def vender(self, cliente, producto, hace_dias):
        venta = Sales.objects.create(code='V', client=cliente, tipoPago=self.forma_pago, sucursal=self.sucursal,
                                     date_added=timezone.now() - timedelta(days=hace_dias))
        salesItems.objects.create(sale_id=venta, product_id=producto, price=producto.price, qty=1,
                                  total=producto.price, client=cliente, sucursal=self.sucursal)

    def test_borrar_cliente_con_ventas_avisa_y_no_borra(self):
        self.vender(self.ana, self.mensualidad, hace_dias=3)
        resp = self.client.post(reverse('delete_cliente'), {'id': self.ana.id}).json()
        self.assertEqual(resp['status'], 'failed')
        self.assertIn('1 venta(s)', resp['msg'])
        self.assertTrue(Clientes.objects.filter(id=self.ana.id).exists())

        resp = self.client.post(reverse('delete_cliente'), {'id': self.beto.id}).json()
        self.assertEqual(resp['status'], 'success')
        self.assertFalse(Clientes.objects.filter(id=self.beto.id).exists())

    def test_estado_pago(self):
        self.vender(self.ana, self.mensualidad, hace_dias=3)     # al corriente
        self.vender(self.beto, self.mensualidad, hace_dias=27)   # vence en 3 días
        self.vender(self.carla, self.mensualidad, hace_dias=45)  # vencido hace 15
        self.vender(self.carla, self.refresco, hace_dias=1)      # no cuenta como pago de clases
        estados = calcular_estados_pago([self.ana.id, self.beto.id, self.carla.id, self.baja.id])
        self.assertEqual(estados[self.ana.id]['estado'], AL_CORRIENTE)
        self.assertEqual(estados[self.beto.id]['estado'], POR_VENCER)
        self.assertEqual(estados[self.carla.id]['estado'], VENCIDO)
        self.assertEqual(estados[self.carla.id]['dias'], 15)
        self.assertEqual(estados[self.carla.id]['concepto'], '3 CLA X SEM')
        self.assertEqual(estados[self.baja.id]['estado'], SIN_PAGOS)

    def test_proximo_pago_del_ticket_manda(self):
        hoy = timezone.localdate()
        # Ticket de hace 40 días que dice que el próximo pago es en 5 días: está por vencer, no vencido
        venta = Sales.objects.create(code='V', client=self.ana, tipoPago=self.forma_pago, sucursal=self.sucursal,
                                     date_added=timezone.now() - timedelta(days=40),
                                     proximo_pago=hoy + timedelta(days=5))
        salesItems.objects.create(sale_id=venta, product_id=self.mensualidad, price=1250, qty=1, total=1250,
                                  client=self.ana, sucursal=self.sucursal)
        estado = calcular_estados_pago([self.ana.id])[self.ana.id]
        self.assertEqual(estado['estado'], POR_VENCER)
        self.assertEqual(estado['vigente_hasta'], hoy + timedelta(days=5))
        self.assertEqual(estado['concepto'], '3 CLA X SEM')

        # También cuenta aunque la venta no sea de un producto marcado como mensualidad
        Sales.objects.create(code='V', client=self.beto, tipoPago=self.forma_pago, sucursal=self.sucursal,
                             proximo_pago=hoy - timedelta(days=2))
        self.assertEqual(calcular_estados_pago([self.beto.id])[self.beto.id]['estado'], VENCIDO)

    def test_pos_guarda_proximo_pago(self):
        base = {'client': self.ana.id, 'tipoPago': self.forma_pago.id, 'sub_total': 1250, 'tax': 0,
                'tax_amount': 0, 'grand_total': 1250, 'tendered_amount': 1250, 'tendered_amount_card': 0,
                'amount_change': 0, 'product_id[]': [self.mensualidad.id], 'qty[]': [1], 'price[]': [1250]}
        resp = self.client.post(reverse('save-pos'), {**base, 'comentario': '', 'proximo_pago': '2026-11-01'})
        self.assertEqual(Sales.objects.get(id=resp.json()['sale_id']).proximo_pago, date(2026, 11, 1))

        # Si lo escriben en el comentario como antes, también se guarda
        resp = self.client.post(reverse('save-pos'), {**base, 'comentario': 'Proxima fecha de pago 15 de noviembre'})
        venta = Sales.objects.get(id=resp.json()['sale_id'])
        self.assertEqual((venta.proximo_pago.month, venta.proximo_pago.day), (11, 15))

    def test_reporte_de_ventas(self):
        from posApp.models import Salida
        self.vender(self.ana, self.mensualidad, hace_dias=0)
        self.vender(self.beto, self.refresco, hace_dias=0)
        self.vender(self.carla, self.mensualidad, hace_dias=3)
        Sales.objects.filter(client=self.ana).update(grand_total=1250)
        Sales.objects.filter(client=self.beto).update(grand_total=25)
        Salida.objects.create(concepto='Cloro', monto=100, fecha=timezone.localdate(), sucursal=self.sucursal)

        resp = self.client.get(reverse('sales-page'))  # por defecto: hoy
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['dias']), 1)
        conceptos = sorted(c for v in resp.context['dias'][0]['ventas'] for c in v['conceptos'])
        self.assertEqual(conceptos, ['3 CLA X SEM', 'Coca cola'])
        self.assertEqual(float(resp.context['total_ventas']), 1275)
        self.assertEqual(float(resp.context['neto']), 1175)
        self.assertEqual(resp.context['por_forma_pago'][0]['forma'], 'Efectivo')

        # Con un cliente elegido sale todo su historial, sin importar la fecha
        resp = self.client.get(reverse('sales-page'), {'cliente_id': self.carla.id})
        self.assertEqual(resp.context['numero_ventas'], 1)
        self.assertContains(resp, f'<option value="{self.carla.id}" selected>')

    def test_mensualidad_registrada_cuenta_como_pago(self):
        hoy = timezone.localdate()
        Mensualidad.objects.create(cliente=self.ana, pagado=True, fecha_pago=hoy - timedelta(days=10),
                                   fecha_vencimiento=hoy + timedelta(days=20), sucursal=self.sucursal)
        self.assertEqual(calcular_estados_pago([self.ana.id])[self.ana.id]['estado'], AL_CORRIENTE)

    def crear_grupo(self, nombre='17:00', hora=time(17, 0), dias='', alumnos=()):
        grupo = Grupo.objects.create(nombre=nombre, sucursal=self.sucursal, hora_inicio=hora, dias=dias)
        grupo.clientes.add(*alumnos)
        return grupo

    def test_pase_lista_por_grupo(self):
        grupo = self.crear_grupo(alumnos=[self.ana, self.beto, self.baja])
        resp = self.client.get(reverse('pase-lista'), {'grupo': grupo.id})
        self.assertEqual([f['cliente'].nombre for f in resp.context['filas']], ['Ana', 'Beto'])  # sin bajas

        # Un alumno de otro grupo que vino a esta clase aparece como invitado
        Asistencia.objects.create(cliente=self.carla, fecha=timezone.localdate(), estado='P', grupo=grupo,
                                  sucursal=self.sucursal)
        resp = self.client.get(reverse('pase-lista'), {'grupo': grupo.id})
        self.assertEqual([(f['cliente'].nombre, f['invitado']) for f in resp.context['filas']][-1], ('Carla', True))

    def test_solo_muestra_grupos_que_tocan_ese_dia(self):
        hoy = timezone.localdate()
        otro_dia = str((hoy.weekday() + 1) % 7)
        toca = self.crear_grupo('Hoy', dias=str(hoy.weekday()))
        self.crear_grupo('Otro día', dias=otro_dia)
        todos = self.crear_grupo('Todos los días', dias='')
        resp = self.client.get(reverse('pase-lista'))
        self.assertEqual({g.id for g in resp.context['grupos_dia']}, {toca.id, todos.id})

    def test_grupo_en_curso(self):
        temprano = self.crear_grupo('7am', hora=time(7, 0))
        tarde = self.crear_grupo('5pm', hora=time(17, 0))
        grupos = [temprano, tarde]
        self.assertEqual(grupo_en_curso(grupos, datetime(2026, 1, 1, 16, 30)), tarde)  # media hora antes
        self.assertEqual(grupo_en_curso(grupos, datetime(2026, 1, 1, 17, 50)), tarde)  # ya empezada
        self.assertIsNone(grupo_en_curso(grupos, datetime(2026, 1, 1, 12, 0)))

    def test_pase_lista_se_guarda_al_tocar(self):
        grupo = self.crear_grupo(alumnos=[self.ana, self.beto])
        url, fecha = reverse('asistencia-marcar'), '2026-10-13'
        self.assertTrue(self.client.post(url, {'cliente': self.ana.id, 'fecha': fecha, 'estado': 'P', 'grupo': grupo.id}).json()['ok'])
        asistencia = Asistencia.objects.get(cliente=self.ana)
        self.assertEqual((asistencia.estado, asistencia.grupo), ('P', grupo))

        self.client.post(url, {'cliente': self.ana.id, 'fecha': fecha, 'estado': 'J', 'grupo': grupo.id})
        self.client.post(url, {'cliente': self.ana.id, 'fecha': fecha, 'comentario': 'Enferma'})
        asistencia.refresh_from_db()
        self.assertEqual((asistencia.estado, asistencia.comentario), ('J', 'Enferma'))

        self.client.post(url, {'cliente': self.ana.id, 'fecha': fecha, 'estado': ''})
        self.assertFalse(Asistencia.objects.exists())
        # Nota sin asistencia, o alumno de otra sucursal: no se guarda
        self.assertEqual(self.client.post(url, {'cliente': self.beto.id, 'fecha': fecha, 'comentario': 'x'}).status_code, 400)
        self.assertEqual(self.client.post(url, {'cliente': self.ajeno.id, 'fecha': fecha, 'estado': 'P'}).status_code, 404)

    def test_cerrar_lista_marca_falta_a_pendientes(self):
        grupo = self.crear_grupo(alumnos=[self.ana, self.beto, self.carla])
        fecha = timezone.localdate()
        Asistencia.objects.create(cliente=self.ana, fecha=fecha, estado='P', sucursal=self.sucursal)
        resp = self.client.post(reverse('asistencia-marcar-pendientes'),
                                {'fecha': fecha.isoformat(), 'grupo': grupo.id, 'estado': 'F'}).json()
        self.assertEqual(resp['marcados'], 2)
        self.assertEqual(dict(Asistencia.objects.values_list('cliente__nombre', 'estado')),
                         {'Ana': 'P', 'Beto': 'F', 'Carla': 'F'})

    def test_checkin_anota_la_clase_en_curso(self):
        ahora = timezone.localtime()
        grupo = self.crear_grupo('Ahora', hora=ahora.time().replace(second=0, microsecond=0), alumnos=[self.ana])
        resp = self.client.post(reverse('checkin-registrar'), {'codigo': self.ana.codigo_asistencia}).json()
        self.assertEqual(resp['clase'], 'Ahora')
        self.assertEqual(Asistencia.objects.get(cliente=self.ana).grupo, grupo)

        # Sin clase a esa hora: se registra igual y se avisa
        resp = self.client.post(reverse('checkin-registrar'), {'codigo': self.beto.codigo_asistencia}).json()
        self.assertTrue(resp['ok'])
        self.assertIsNone(resp['clase'])

    def test_checkin_lectura_guardada_sin_internet_conserva_su_hora(self):
        hace_rato = timezone.localtime() - timedelta(hours=2)
        self.client.post(reverse('checkin-registrar'), {'codigo': self.ana.codigo_asistencia, 'hora': hace_rato.isoformat()})
        llegada = Asistencia.objects.get(cliente=self.ana).hora_llegada
        self.assertEqual((llegada.hour, llegada.minute), (hace_rato.hour, hace_rato.minute))

    def test_checkin_otra_sucursal_y_sesion_cerrada(self):
        resp = self.client.post(reverse('checkin-registrar'), {'codigo': self.ajeno.codigo_asistencia}).json()
        self.assertFalse(resp['ok'])
        self.assertIn('Otra', resp['msg'])  # dice de qué sucursal es
        self.client.logout()
        resp = self.client.post(reverse('checkin-registrar'), {'codigo': self.ana.codigo_asistencia})
        self.assertEqual(resp.status_code, 401)
        self.assertTrue(resp.json()['sesion'])

    def test_crear_grupos_desde_horarios(self):
        # Ana "5 pm", Beto "5PM", Inactivo "5pm" (baja) y Carla "7am": "5 pm" y "5PM" van juntos
        tercero = crear_cliente(self.sucursal, 'Diego', '17:00', self.nivel)
        resp = self.client.get(reverse('grupos-importar'))
        propuesta = next(p for p in resp.context['propuestas'] if p['hora'] == time(17, 0))
        self.assertEqual(sorted(propuesta['clientes']), sorted([self.ana.id, self.beto.id, tercero.id]))

        self.client.post(reverse('grupos-importar'), {'clave': propuesta['clave'], f"nombre_{propuesta['clave']}": 'Tarde 5'})
        grupo = Grupo.objects.get(nombre='Tarde 5')
        self.assertEqual(grupo.hora_inicio, time(17, 0))
        self.assertEqual(grupo.clientes.count(), 3)

    def test_cobrar_producto_ligado_inscribe_al_grupo(self):
        grupo = self.crear_grupo()
        self.mensualidad.grupo = grupo
        self.mensualidad.save()
        self.client.post(reverse('save-pos'), {
            'client': self.carla.id, 'tipoPago': self.forma_pago.id, 'sub_total': 1250, 'tax': 0, 'tax_amount': 0,
            'grand_total': 1250, 'tendered_amount': 1250, 'tendered_amount_card': 0, 'amount_change': 0,
            'comentario': '', 'product_id[]': [self.mensualidad.id], 'qty[]': [1], 'price[]': [1250]})
        self.assertIn(self.carla, grupo.clientes.all())

    def test_grupos_desde_productos(self):
        producto = Products.objects.create(code='96', category_id=self.mensualidad.category_id, name='Niños Lun Mie y Vie 5PM',
                                           description='', price=1350, sucursal=self.sucursal, dias_vigencia=30)
        general = self.crear_grupo('17:00', alumnos=[self.ana, self.beto])
        self.vender(self.ana, producto, hace_dias=10)
        self.vender(self.carla, producto, hace_dias=90)  # compra vieja: no se inscribe

        resp = self.client.get(reverse('grupos-desde-productos'))
        propuesta = next(p for p in resp.context['propuestas'] if p['productos'] == [producto])
        self.assertEqual((propuesta['hora'], propuesta['dias'], propuesta['clientes']), (time(17, 0), '024', [self.ana.id]))

        self.client.post(reverse('grupos-desde-productos'), {'clave': propuesta['clave'], 'inscribir': '1'})
        nuevo = Grupo.objects.get(nombre='Niños Lun Mie y Vie 5PM')
        producto.refresh_from_db()
        self.assertEqual(producto.grupo, nuevo)
        self.assertEqual(list(nuevo.clientes.all()), [self.ana])
        # Ana sale del grupo general de las 17:00; Beto se queda ahí hasta que pague
        self.assertEqual(list(general.clientes.all()), [self.beto])

    def test_inscribir_solo_saca_de_clases_que_chocan(self):
        nueva = self.crear_grupo('Niños LMV 17:00', hora=time(17, 0), dias='024')
        mismo_horario = self.crear_grupo('17:00 general', hora=time(17, 0), dias='', alumnos=[self.ana])
        casi_igual = self.crear_grupo('17:15 LMV', hora=time(17, 15), dias='0', alumnos=[self.ana])
        otros_dias = self.crear_grupo('17:00 MJ', hora=time(17, 0), dias='13', alumnos=[self.ana])
        otra_hora = self.crear_grupo('Equipo 15:00', hora=time(15, 0), alumnos=[self.ana])
        sin_hora = self.crear_grupo('Aguas abiertas', hora=None, alumnos=[self.ana])

        salio = nueva.inscribir(self.ana)
        self.assertEqual({g.nombre for g in salio}, {'17:00 general', '17:15 LMV'})
        self.assertEqual({g.nombre for g in self.ana.grupos.all()},
                         {'Niños LMV 17:00', '17:00 MJ', 'Equipo 15:00', 'Aguas abiertas'})

    def test_grupos_ordenados_por_hora_y_sin_hora_al_final(self):
        self.crear_grupo('Equipo A', hora=None)
        self.crear_grupo('18:00', hora=time(18, 0))
        self.crear_grupo('07:00', hora=time(7, 0))
        nombres = [g.nombre for g in self.client.get(reverse('grupos')).context['grupos']]
        self.assertEqual(nombres, ['07:00', '18:00', 'Equipo A'])
        nombres = [g.nombre for g in self.client.get(reverse('pase-lista')).context['grupos_dia']]
        self.assertEqual(nombres, ['07:00', '18:00', 'Equipo A'])

    def test_pos_sugiere_grupo_por_nombre_del_producto(self):
        from posApp.views_grupos import grupo_para_producto
        general = self.crear_grupo('17:00', hora=time(17, 0), dias='')
        ninos_lmv = self.crear_grupo('Niños Lun Mie y Vie 5PM', hora=time(17, 0), dias='024')
        adultos_mj = self.crear_grupo('Adultos Martes y Jueves 5pm', hora=time(17, 0), dias='13')
        self.crear_grupo('Niños 7pm', hora=time(19, 0))
        grupos = list(Grupo.objects.all())
        nuevo = lambda nombre: Products(name=nombre, dias_vigencia=30)

        self.assertEqual(grupo_para_producto(nuevo('Niños Lun Mie y Vie 5 PM promo'), grupos), ninos_lmv)  # mismos días
        self.assertEqual(grupo_para_producto(nuevo('Adultos Mar y Jue 5pm'), grupos), adultos_mj)
        self.assertEqual(grupo_para_producto(nuevo('Clase libre 5pm'), grupos), general)
        self.assertIsNone(grupo_para_producto(nuevo('3 CLA X SEM'), grupos))     # sin hora: no adivina
        self.assertIsNone(grupo_para_producto(nuevo('Niños 9am'), grupos))       # nadie a esa hora

        # El POS manda la sugerencia solo para productos de clase sin grupo ligado
        self.mensualidad.name = 'Niños Lun Mie y Vie 5PM nuevo'
        self.mensualidad.save()
        productos = {p['id']: p for p in json.loads(self.client.get(reverse('pos-page')).context['product_json'])}
        self.assertEqual(productos[self.mensualidad.id]['grupo_sugerido'], ninos_lmv.id)
        self.assertIsNone(productos[self.refresco.id]['grupo_sugerido'])

    def test_sin_filtro_no_muestra_lista(self):
        resp = self.client.get(reverse('pase-lista'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['filas'], [])

    def test_reporte_y_excel(self):
        hoy = timezone.localdate()
        for dias, estado in [(1, 'P'), (2, 'R'), (3, 'F'), (4, 'J')]:
            Asistencia.objects.create(cliente=self.ana, fecha=hoy - timedelta(days=dias), estado=estado,
                                      sucursal=self.sucursal)
        Asistencia.objects.create(cliente=self.beto, fecha=hoy - timedelta(days=1), estado='P', sucursal=self.sucursal)
        self.vender(self.beto, self.mensualidad, hace_dias=1)
        params = {'fecha_inicio': (hoy - timedelta(days=10)).isoformat(), 'fecha_fin': hoy.isoformat()}
        url = reverse('reporte-asistencia')

        resp = self.client.get(url, params)
        filas = {f['cliente'].nombre: f for f in resp.context['filas']}
        self.assertEqual(set(filas), {'Ana', 'Beto'})
        self.assertEqual(filas['Ana']['dias'], 2)  # presente + retardo
        self.assertEqual(filas['Ana']['porcentaje'], 67)  # la justificada no cuenta en contra
        self.assertEqual(resp.context['resumen']['asistencias'], 3)
        self.assertEqual(resp.context['resumen']['deben'], 1)

        # Vinieron y deben: Ana no tiene pagos, Beto está al corriente
        resp = self.client.get(url, {**params, 'vista': 'deben'})
        self.assertEqual([f['cliente'].nombre for f in resp.context['filas']], ['Ana'])

        # No han venido: activos sin asistencias (no incluye bajas ni a quienes sí vinieron)
        resp = self.client.get(url, {**params, 'vista': 'ausentes'})
        self.assertEqual(sorted(f['cliente'].nombre for f in resp.context['filas']), ['Carla'])

        resp = self.client.get(reverse('exportar-asistencia-excel'), {**params, 'vista': 'deben'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('spreadsheetml', resp['Content-Type'])

    def test_historial_cliente(self):
        Asistencia.objects.create(cliente=self.ana, fecha=timezone.localdate(), estado='P', sucursal=self.sucursal)
        resp = self.client.get(reverse('cliente-asistencias', args=[self.ana.id]))
        self.assertEqual(resp.context['totales']['porcentaje'], 100)
        self.assertEqual(self.client.get(reverse('cliente-asistencias', args=[self.ajeno.id])).status_code, 404)

    def test_guardar_producto_con_dias_vigencia(self):
        resp = self.client.post(reverse('save-product-page'), {
            'id': self.refresco.id, 'code': '2', 'category_id': self.refresco.category_id_id, 'name': 'Coca cola',
            'description': '', 'price': '25', 'status': '1', 'dias_vigencia': '15', 'entrada_inventario': '0',
        })
        self.assertEqual(resp.json()['status'], 'success')
        self.refresco.refresh_from_db()
        self.assertEqual(self.refresco.dias_vigencia, 15)

    def test_checkin_qr(self):
        url = reverse('checkin-registrar')
        self.vender(self.ana, self.mensualidad, hace_dias=3)

        resp = self.client.post(url, {'codigo': self.ana.codigo_asistencia}).json()
        self.assertTrue(resp['ok'])
        self.assertFalse(resp['ya_registrado'])
        self.assertEqual(resp['pago']['estado'], AL_CORRIENTE)
        asistencia = Asistencia.objects.get(cliente=self.ana)
        self.assertEqual(asistencia.estado, Asistencia.PRESENTE)
        self.assertIsNotNone(asistencia.hora_llegada)

        # Segunda lectura el mismo día no duplica ni cambia la hora
        resp = self.client.post(url, {'codigo': f'uri-{self.ana.id}'}).json()
        self.assertTrue(resp['ya_registrado'])
        self.assertEqual(Asistencia.objects.filter(cliente=self.ana).count(), 1)

        # Solo el número (tecleado en recepción) también funciona y avisa adeudo
        resp = self.client.post(url, {'codigo': str(self.carla.id)}).json()
        self.assertEqual(resp['pago']['estado'], SIN_PAGOS)

        # Si se le había puesto falta y llega, cambia a presente
        Asistencia.objects.create(cliente=self.beto, fecha=timezone.localdate(), estado='F', sucursal=self.sucursal)
        self.client.post(url, {'codigo': self.beto.codigo_asistencia})
        self.assertEqual(Asistencia.objects.get(cliente=self.beto).estado, Asistencia.PRESENTE)

    def test_checkin_rechaza_codigos_invalidos_y_otra_sucursal(self):
        url = reverse('checkin-registrar')
        self.assertFalse(self.client.post(url, {'codigo': 'https://ejemplo.com'}).json()['ok'])
        self.assertFalse(self.client.post(url, {'codigo': self.ajeno.codigo_asistencia}).json()['ok'])
        self.assertFalse(self.client.post(url, {'codigo': '999999'}).json()['ok'])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertFalse(Asistencia.objects.exists())

    def test_pagina_checkin_y_credenciales(self):
        self.client.post(reverse('checkin-registrar'), {'codigo': self.ana.codigo_asistencia})
        resp = self.client.get(reverse('checkin'))
        self.assertEqual(len(resp.context['llegadas']), 1)

        resp = self.client.get(reverse('credenciales-qr'), {'horario': '5pm'})
        self.assertContains(resp, f'data-codigo="URI{self.ana.id}"')
        self.assertNotContains(resp, f'data-codigo="URI{self.baja.id}"')
        resp = self.client.get(reverse('cliente-credencial', args=[self.carla.id]))
        self.assertContains(resp, f'data-codigo="URI{self.carla.id}"')
        self.assertEqual(self.client.get(reverse('cliente-credencial', args=[self.ajeno.id])).status_code, 404)

    def nombres_en_clientes(self, **params):
        resp = self.client.get(reverse('client-page'), params)
        self.assertEqual(resp.status_code, 200)
        return [f['cliente'].nombre for f in resp.context['filas']]

    def test_busqueda_de_clientes(self):
        Clientes.objects.filter(id=self.beto.id).update(apellido_paterno='Gómez', celular='999 233 0181')
        # Todas las palabras deben coincidir (antes "ana pérez" traía a todos los Pérez)
        self.assertEqual(self.nombres_en_clientes(q='ana pérez'), ['Ana'])
        self.assertEqual(self.nombres_en_clientes(q='beto gómez'), ['Beto'])
        # Celular aunque esté capturado con espacios
        self.assertEqual(self.nombres_en_clientes(q='2330181'), ['Beto'])
        # Código de credencial
        self.assertEqual(self.nombres_en_clientes(q=f'URI{self.carla.id}'), ['Carla'])
        # Nunca muestra clientes de otra sucursal
        self.assertNotIn('Ajeno', self.nombres_en_clientes(q='ajeno'))

    def test_filtros_de_clientes(self):
        self.vender(self.ana, self.mensualidad, hace_dias=3)
        self.vender(self.carla, self.mensualidad, hace_dias=45)
        self.assertEqual(self.nombres_en_clientes(estado=AL_CORRIENTE), ['Ana'])
        self.assertEqual(self.nombres_en_clientes(estado=VENCIDO), ['Carla'])
        self.assertEqual(self.nombres_en_clientes(status='4'), ['Inactivo'])
        self.assertEqual(sorted(self.nombres_en_clientes(horario='5pm')), ['Ana', 'Beto', 'Inactivo'])

    def test_ficha_muestra_pagos(self):
        self.vender(self.ana, self.mensualidad, hace_dias=3)
        resp = self.client.get(reverse('cliente-ficha', args=[self.ana.id]))
        self.assertEqual(resp.context['numero_pagos'], 1)
        self.assertEqual(resp.context['pagos'][0]['conceptos'], ['3 CLA X SEM'])
        self.assertEqual(resp.context['pago']['estado'], AL_CORRIENTE)
        self.assertEqual(self.client.get(reverse('cliente-ficha', args=[self.ajeno.id])).status_code, 404)

    def test_iniciales_ignoran_espacios_y_puntos(self):
        cliente = crear_cliente(self.sucursal, '  Gerardo')
        self.assertEqual(cliente.iniciales, 'GP')
        cliente.nombre, cliente.apellido_paterno = '...', ''
        self.assertEqual(cliente.iniciales, '?')


    def test_modal_cliente_conserva_condicion_medica_y_horario(self):
        from posApp.models import Genero
        Genero.objects.create(genero='Femenino')
        self.ana.condicion_medica = 'Asma, trae inhalador'
        self.ana.horario = 'JUEVES Y VIERNES 6:00 AM'
        self.ana.save()
        r = self.client.get(reverse('manage_clients-page'), {'id': self.ana.id})
        self.assertContains(r, '>Asma, trae inhalador</textarea>')
        self.assertContains(r, 'value="JUEVES Y VIERNES 6:00 AM"')
        self.assertContains(r, '<option value="JUEVES Y VIERNES 6:00 AM">')  # sugerido en la lista

    def test_reporte_asistencia_por_grupo(self):
        grupo = Grupo.objects.create(nombre='Niños 5pm', sucursal=self.sucursal, hora_inicio=time(17), dias='024')
        grupo.clientes.add(self.ana, self.carla)
        hoy = timezone.localdate()
        Asistencia.objects.create(cliente=self.ana, fecha=hoy, estado='P', grupo=grupo, sucursal=self.sucursal)
        Asistencia.objects.create(cliente=self.beto, fecha=hoy, estado='P', grupo=grupo, sucursal=self.sucursal)  # invitado
        params = {'grupo': grupo.id, 'fecha_inicio': hoy.isoformat(), 'fecha_fin': hoy.isoformat()}

        r = self.client.get(reverse('reporte-asistencia'), params)
        self.assertEqual({f['cliente'].id for f in r.context['filas']}, {self.ana.id, self.beto.id})
        r = self.client.get(reverse('reporte-asistencia'), {**params, 'vista': 'ausentes'})
        self.assertEqual([f['cliente'].id for f in r.context['filas']], [self.carla.id])
        r = self.client.get(reverse('exportar-asistencia-excel'), params)
        self.assertEqual(r.status_code, 200)

    def test_reporte_anual(self):
        from decimal import Decimal

        def venta(cliente, dia, total):
            v = Sales.objects.create(code='V', client=cliente, tipoPago=self.forma_pago, sucursal=self.sucursal,
                                     grand_total=total, date_added=timezone.make_aware(datetime.combine(dia, time(17))))
            salesItems.objects.create(sale_id=v, product_id=self.mensualidad, price=total, qty=1, total=total,
                                      client=cliente, sucursal=self.sucursal)

        venta(self.ana, date(2024, 3, 5), 1000)
        venta(self.ana, date(2025, 3, 5), 1500)
        venta(self.beto, date(2025, 7, 9), 500)
        r = self.client.get(reverse('reporte-anual'), {'anio': 2025})
        self.assertEqual(r.status_code, 200)
        ctx = r.context
        self.assertEqual(ctx['ingresos'], Decimal('2000.00'))
        self.assertEqual(ctx['ingresos_cmp'], Decimal('1000.00'))
        self.assertEqual(ctx['cambios']['ingresos'], 100)
        self.assertEqual(ctx['alumnos'], 2)
        self.assertEqual(ctx['meses'][2]['ingresos'], Decimal('1500.00'))
        self.assertEqual(ctx['meses'][2]['cambio'], 50)
        self.assertEqual(ctx['mejor_mes']['nombre'], 'marzo')
        self.assertEqual([h['anio'] for h in ctx['historico']][:2], [2024, 2025])
        self.assertEqual(self.client.get(reverse('reporte-anual-excel'), {'anio': 2025}).status_code, 200)
        self.assertEqual(self.client.get(reverse('reporte-anual'), {'anio': 'abc'}).status_code, 200)

    def test_login_y_pagina_de_error(self):
        self.client.logout()
        self.assertContains(self.client.get(reverse('login')), 'Inicia sesión')
        r = self.client.post(reverse('login-user'), {'username': 'recepcion', 'password': 'mal'})
        self.assertEqual(r.json()['msg'], 'El usuario o la contraseña no coinciden.')
        # Un perfil sin sucursal ve el mensaje en lugar de un error 500
        sin_sucursal = User.objects.create_user('sin-sucursal', password='x')
        UserProfile.objects.create(user=sin_sucursal)
        self.client.force_login(sin_sucursal)
        self.assertContains(self.client.get(reverse('sales-page')), 'no tiene una sucursal asignada')

    def test_modal_cliente_inscribe_y_saca_de_grupos(self):
        from posApp.models import Genero
        genero = Genero.objects.create(genero='Femenino')
        manana = Grupo.objects.create(nombre='Niños 7am', sucursal=self.sucursal, hora_inicio=time(7), dias='024')
        tarde = Grupo.objects.create(nombre='Niños 5pm', sucursal=self.sucursal, hora_inicio=time(17), dias='024')
        choca = Grupo.objects.create(nombre='Adultos 5pm', sucursal=self.sucursal, hora_inicio=time(17, 15), dias='0')
        manana.clientes.add(self.ana)
        choca.clientes.add(self.ana)
        r = self.client.get(reverse('manage_clients-page'), {'id': self.ana.id})
        self.assertContains(r, 'name="quitar_grupo" value="%d"' % manana.id)

        datos = {'id': self.ana.id, 'nombre': 'Ana', 'apellido_paterno': 'Pérez', 'apellido_materno': 'López',
                 'genero_id': genero.id, 'celular': '', 'fecha_nacimiento': '', 'codigo_postal': '', 'email': '',
                 'contacto_emergencia': '', 'emergency_phone': '', 'sangre': '', 'pay_day': '', 'horario': '5 pm',
                 'suburbio': '', 'direccion': '', 'condicion_medica': '', 'status': 1,
                 'grupo_id': tarde.id, 'quitar_grupo': [manana.id]}
        r = self.client.post(reverse('save-client-page'), datos)
        self.assertEqual(r.json()['status'], 'success')
        # Entró a 5pm, salió de 7am porque se marcó y de "Adultos 5pm" porque chocaba
        self.assertEqual(list(self.ana.grupos.all()), [tarde])
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.horario, 'Niños 5pm')  # el horario queda igual al del grupo

    def test_grupos_lleva_a_pasar_lista(self):
        hoy = timezone.localdate()
        diario = Grupo.objects.create(nombre='Diario 5pm', sucursal=self.sucursal, hora_inicio=time(17), dias='')
        otro_dia = str((hoy.weekday() + 1) % 7)  # Le toca mañana, no hoy
        manana = Grupo.objects.create(nombre='Mañana 6pm', sucursal=self.sucursal, hora_inicio=time(18), dias=otro_dia)
        r = self.client.get(reverse('grupos'))
        self.assertContains(r, 'Grupos y horarios')
        self.assertContains(r, '?fecha=%s&grupo=%d' % (hoy.isoformat(), diario.id))
        # Si hoy no le toca, lleva al último día que tuvo clase
        self.assertContains(r, '?fecha=%s&grupo=%d' % ((hoy - timedelta(days=6)).isoformat(), manana.id))

        r = self.client.get(reverse('client-page'))
        self.assertContains(r, '/pos?cliente=%d' % self.ana.id)
        self.assertNotContains(r, '/mensualidades/pagar/')

    def _venta_clase(self, cliente, dia, total=1000):
        v = Sales.objects.create(code='V', client=cliente, tipoPago=self.forma_pago, sucursal=self.sucursal,
                                 grand_total=total, date_added=timezone.make_aware(datetime.combine(dia, time(17))))
        salesItems.objects.create(sale_id=v, product_id=self.mensualidad, price=total, qty=1, total=total,
                                  client=cliente, sucursal=self.sucursal)

    def test_comparar_meses_y_tipos_de_alumno(self):
        self._venta_clase(self.carla, date(2025, 5, 3))   # Carla ya era alumna, faltó en junio-julio
        self._venta_clase(self.ana, date(2025, 7, 3))
        self._venta_clase(self.beto, date(2025, 7, 4))
        self._venta_clase(self.ana, date(2025, 8, 3))     # Ana sigue
        self._venta_clase(self.carla, date(2025, 8, 5))   # Carla regresó
        self._venta_clase(self.baja, date(2025, 8, 6))    # primera vez: nuevo
        r = self.client.get(reverse('comparar-meses'), {'a': '2025-07', 'b': '2025-08'})
        self.assertEqual(r.status_code, 200)
        ctx = r.context
        self.assertEqual(ctx['retencion'], 50)
        self.assertEqual([f['id'] for f in ctx['volvieron']], [self.ana.id])
        self.assertEqual([f['id'] for f in ctx['no_volvieron']], [self.beto.id])
        self.assertEqual([f['id'] for f in ctx['nuevos']], [self.baja.id])
        self.assertEqual([f['id'] for f in ctx['de_antes']], [self.carla.id])
        self.assertEqual(ctx['cambios']['ventas'], 50)

        r = self.client.get(reverse('monthly_report'), {'mes': '2025-08'})
        self.assertEqual(r.context['composicion'], {'nuevo': 1, 'sigue': 1, 'regreso': 1})
        self.assertEqual(self.client.get(reverse('reporte-mensual-excel'), {'mes': '2025-08'}).status_code, 200)

    def test_llegada_sin_clase_se_ve_en_pase_de_lista(self):
        hoy = timezone.localdate()
        otro_dia = str((hoy.weekday() + 1) % 7)
        grupo = Grupo.objects.create(nombre='Mañana 6pm', sucursal=self.sucursal, hora_inicio=time(18), dias=otro_dia)
        grupo.clientes.add(self.ana)
        r = self.client.post(reverse('checkin-registrar'), {'codigo': self.ana.codigo_asistencia})
        self.assertEqual(r.json()['sin_clase_hoy'], ['Mañana 6pm (%s)' % grupo.dias_texto])
        r = self.client.get(reverse('pase-lista'), {'fecha': hoy.isoformat()})
        self.assertEqual([a.cliente_id for a in r.context['sin_clase']], [self.ana.id])
        self.assertContains(r, 'llegaron sin clase este día')

    def test_grupos_de_otro_dia_se_pueden_abrir_en_pase_de_lista(self):
        hoy = timezone.localdate()
        otro_dia = str((hoy.weekday() + 1) % 7)
        grupo = Grupo.objects.create(nombre='Niños B 4pm', sucursal=self.sucursal, hora_inicio=time(16), dias=otro_dia)
        grupo.clientes.add(self.ana)
        r = self.client.get(reverse('pase-lista'), {'fecha': hoy.isoformat()})
        self.assertNotIn(grupo, r.context['grupos_dia'])
        self.assertEqual(r.context['otros_dias'], [grupo])
        self.assertContains(r, 'Grupos que no tienen clase este día')
        r = self.client.get(reverse('pase-lista'), {'fecha': hoy.isoformat(), 'grupo': grupo.id})
        self.assertEqual([f['cliente'] for f in r.context['filas']], [self.ana])

    def test_checkin_tarde_queda_con_retardo_en_su_grupo(self):
        hoy = timezone.localdate()
        grupo = Grupo.objects.create(nombre='Niños 9am', sucursal=self.sucursal, hora_inicio=time(9), dias='')
        grupo.clientes.add(self.ana, self.beto)
        llegada = timezone.make_aware(datetime.combine(hoy, time(9, 25)))
        r = self.client.post(reverse('checkin-registrar'), {'codigo': self.ana.codigo_asistencia, 'hora': llegada.isoformat()})
        datos = r.json()
        self.assertEqual(datos['clase'], 'Niños 9am')
        self.assertEqual(datos['minutos_tarde'], 25)
        self.assertEqual(Asistencia.objects.get(cliente=self.ana, fecha=hoy).estado, Asistencia.RETARDO)
        # Muy fuera de la ventana de la clase, pero es su día: igual queda en la lista de su grupo
        llegada = timezone.make_aware(datetime.combine(hoy, time(13, 0)))
        r = self.client.post(reverse('checkin-registrar'), {'codigo': self.beto.codigo_asistencia, 'hora': llegada.isoformat()})
        self.assertEqual(r.json()['clase'], 'Niños 9am')
        r = self.client.get(reverse('pase-lista'), {'fecha': hoy.isoformat(), 'grupo': grupo.id})
        self.assertEqual(r.context['resumen']['tarde'], 2)
        self.assertContains(r, '25 min tarde')

    def test_reportes_comparan_contra_el_mes_o_anio_elegido(self):
        self._venta_clase(self.ana, date(2025, 3, 3), 900)
        self._venta_clase(self.ana, date(2025, 7, 3), 1000)
        self._venta_clase(self.ana, date(2025, 8, 3), 1200)
        self._venta_clase(self.beto, date(2025, 8, 4), 600)
        r = self.client.get(reverse('monthly_report'), {'mes': '2025-08', 'vs': '2025-03'})
        ctx = r.context
        self.assertEqual(ctx['mes_ant_nombre'], 'marzo')
        self.assertEqual(ctx['cambios']['ingresos'], 100)       # 1800 contra 900
        self.assertEqual(ctx['renovacion'], 100)                # Ana pagó en marzo y en agosto
        self.assertEqual(ctx['composicion']['sigue'], 1)        # "sigue" siempre es contra el mes anterior
        self.assertContains(r, 'Comparar con')
        r = self.client.get(reverse('monthly_report'), {'mes': '2025-08'})
        self.assertEqual(r.context['mes_ant_nombre'], 'julio')
        self._venta_clase(self.ana, date(2023, 8, 3), 500)
        r = self.client.get(reverse('reporte-anual'), {'anio': 2025, 'vs': 2023})
        self.assertEqual(r.context['anio_ant'], 2023)
        self.assertEqual(r.context['ingresos_cmp'], 500)
        self.assertContains(r, 'mes=2025-08&vs=2023-08')
        self.assertEqual(self.client.get(reverse('reporte-anual-excel'), {'anio': 2025, 'vs': 2023}).status_code, 200)

    def test_pase_de_lista_trae_guia_con_videos(self):
        r = self.client.get(reverse('pase-lista'))
        self.assertContains(r, 'data-guia-abrir')
        for paso in range(1, 7):
            self.assertContains(r, 'guia/pase_lista_%d.mp4' % paso)

    def test_grupos_trae_guia_con_videos(self):
        r = self.client.get(reverse('grupos'))
        self.assertContains(r, 'data-guia-abrir')
        for paso in range(1, 6):
            self.assertContains(r, 'guia/grupos_%d.mp4' % paso)

    def test_punto_de_venta_trae_guia_de_mensualidad(self):
        r = self.client.get(reverse('pos-page'))
        self.assertContains(r, 'data-guia-abrir')
        for paso in range(1, 7):
            self.assertContains(r, 'guia/cobrar_%d.mp4' % paso)

    def test_inicio_trae_los_tutoriales_de_flujo(self):
        sesion = self.client.session; sesion['sucursal_id'] = self.sucursal.id; sesion.save()
        r = self.client.get(reverse('home-page'))
        for guia, pasos in [('lista', 6), ('venta', 3), ('mensualidad', 6), ('estado', 4)]:
            self.assertContains(r, 'data-guia-abrir="%s"' % guia)
            self.assertContains(r, 'data-guia="%s"' % guia)
        self.assertContains(r, 'guia/venta_2.mp4')
        self.assertContains(r, 'guia/reporte_asistencia_2.mp4')
        self.assertContains(r, 'class="u-guia__paso', count=19)

    def test_pantallas_traen_su_guia_con_videos(self):
        for url, guia, pasos in [('checkin', 'checkin', 4), ('client-page', 'clientes', 4),
                                 ('monthly_report', 'reporte_mensual', 3), ('comparar-meses', 'comparar_meses', 2),
                                 ('reporte-anual', 'reporte_anual', 2), ('reporte-asistencia', 'reporte_asistencia', 2)]:
            with self.subTest(url=url):
                r = self.client.get(reverse(url))
                self.assertContains(r, 'data-guia-abrir')
                for paso in range(1, pasos + 1):
                    self.assertContains(r, 'guia/%s_%d.mp4' % (guia, paso))
                self.assertNotContains(r, 'guia/%s_%d.mp4' % (guia, pasos + 1))

    def test_asignar_sin_grupo_cambia_el_horario(self):
        grupo = Grupo.objects.create(nombre='Niños 5pm', sucursal=self.sucursal, hora_inicio=time(17))
        self.client.post(reverse('grupos-sin-asignar'), {'grupo': grupo.id, 'cliente': [self.carla.id]})
        self.carla.refresh_from_db()
        self.assertIn(self.carla, grupo.clientes.all())
        self.assertEqual(self.carla.horario, 'Niños 5pm')

    def test_reporte_mensual(self):
        from decimal import Decimal
        from posApp.models import Salida

        def venta(cliente, producto, dia, total):
            v = Sales.objects.create(code='V', client=cliente, tipoPago=self.forma_pago, sucursal=self.sucursal,
                                     grand_total=total, date_added=timezone.make_aware(datetime.combine(dia, time(17))))
            salesItems.objects.create(sale_id=v, product_id=producto, price=total, qty=1, total=total,
                                      client=cliente, sucursal=self.sucursal)

        venta(self.ana, self.mensualidad, date(2025, 8, 3), 1000)
        venta(self.beto, self.mensualidad, date(2025, 8, 5), 1000)
        venta(self.ana, self.mensualidad, date(2025, 9, 2), 1250)   # Ana renovó
        venta(self.carla, self.mensualidad, date(2025, 9, 4), 1250)  # Carla es nueva
        venta(self.carla, self.refresco, date(2025, 9, 4), 50)
        Salida.objects.create(concepto='Cloro', monto=Decimal('500'), fecha=date(2025, 9, 10), sucursal=self.sucursal)
        Salida.objects.create(concepto='Ajena', monto=Decimal('999'), fecha=date(2025, 9, 10), sucursal=self.otra_sucursal)

        r = self.client.get(reverse('monthly_report'), {'mes': '2025-09'})
        self.assertEqual(r.status_code, 200)
        ctx = r.context
        self.assertEqual(ctx['ingresos'], Decimal('2550.00'))
        self.assertEqual(ctx['total_salidas'], Decimal('500.00'))
        self.assertEqual(ctx['utilidad'], Decimal('2050.00'))
        self.assertEqual(ctx['cambios']['ingresos'], 28)
        self.assertEqual(ctx['alumnos_pagaron'], 2)
        self.assertEqual(ctx['alumnos_nuevos'], 1)
        self.assertEqual(ctx['renovacion'], 50)
        self.assertEqual([a['id'] for a in ctx['sin_renovar']], [self.beto.id])
        self.assertEqual(ctx['productos'][0]['nombre'], '3 CLA X SEM')
        self.assertEqual(ctx['grafica']['ingresos'][3], 1300)
        self.assertEqual(ctx['grafica']['salidas'][9], -500)
        self.assertEqual(ctx['grafica']['doce']['etiquetas'], ['Ago 25', 'Sep 25'])

        r = self.client.get(reverse('reporte-mensual-excel'), {'mes': '2025-09'})
        self.assertEqual(r.status_code, 200)
        from io import BytesIO
        from openpyxl import load_workbook
        libro = load_workbook(BytesIO(r.content))
        self.assertIn('Por cobrar', libro.sheetnames)
        self.assertEqual(libro['Resumen']['B6'].value, 2550)
        self.assertEqual(libro['Por cobrar']['A5'].value, 'Beto Pérez López')
        self.assertEqual(libro['Salidas']['B5'].value, 'Cloro')

        # Un mes inválido o futuro cae en el mes actual sin romperse
        self.assertEqual(self.client.get(reverse('monthly_report'), {'mes': 'abc'}).status_code, 200)
        self.assertEqual(self.client.get(reverse('monthly_report'), {'mes': '2999-01'}).status_code, 200)


class LeerProximoPagoTests(TestCase):
    def test_formatos_que_usa_recepcion(self):
        venta = date(2024, 8, 13)
        casos = {
            'Proxima fecha de pago 14 de septiembre': date(2024, 9, 14),
            'PRÓXIMA FECHA DE PAGO 6 DE SEPTIEMBRE.': date(2024, 9, 6),
            'proxima fecha de pago 14 de sep.': date(2024, 9, 14),
            'proximo pago 9 d ejunio': date(2025, 6, 9),
            'Proxima fecha de pago 23 de npoviembre': date(2024, 11, 23),
            'proxima fecha de pago 1 al 5 de septiembre para no generar recargo': date(2024, 9, 5),
            'Semestre. Proximo pago 1ro de febrero': date(2025, 2, 1),
            'proximo pago 10/9': date(2024, 9, 10),
            'Proxima fecha de pago 12 de enero de 2025': date(2025, 1, 12),
        }
        for texto, esperado in casos.items():
            self.assertEqual(leer_proximo_pago(texto, venta), esperado, texto)

    def test_no_inventa_fechas(self):
        venta = date(2024, 8, 13)
        for texto in ['TOMA CLASE 1', 'pago de paquete de 10 clases', 'Proxima fecha de pago pendiente',
                      'Proxima fecha de pago 9 DE CADA MES', 'Proxima fecha de pago 30 de febrero',
                      'FUE EN EFECTIVO SU PAGO. 16 AÑOS, 11AM', 'pago 1210', None, '']:
            self.assertIsNone(leer_proximo_pago(texto, venta), texto)

    def test_dia_de_pago(self):
        self.assertEqual(dia_de_pago('1 de cada mes '), 1)
        self.assertEqual(dia_de_pago('29 DE CADA MES'), 29)
        self.assertIsNone(dia_de_pago(''))
        self.assertIsNone(dia_de_pago('cada mes'))


class WhatsappAdeudoTests(TestCase):
    def test_numero_con_lada_de_mexico(self):
        self.assertEqual(numero_whatsapp('999 123-4567'), '529991234567')
        self.assertEqual(numero_whatsapp('+52 1 999 123 4567'), '5219991234567')
        self.assertIsNone(numero_whatsapp('12345'))
        self.assertIsNone(numero_whatsapp(''))

    def test_liga_solo_si_debe_y_tiene_celular(self):
        sucursal = Sucursal.objects.create(nombre='Centro')
        ana = crear_cliente(sucursal, 'Ana')
        vencido = {'estado': VENCIDO, 'dias': 3, 'vigente_hasta': date(2026, 10, 29)}
        liga = whatsapp_adeudo(ana, vencido)
        self.assertTrue(liga.startswith('https://web.whatsapp.com/send?phone=529990000000&text='))
        self.assertIn('Ana', liga)
        self.assertIn('29/10/2026', liga)
        self.assertIn('3%20d%C3%ADas', liga)
        self.assertEqual(whatsapp_adeudo(ana, {'estado': AL_CORRIENTE, 'dias': 0}), '')
        ana.celular = ''
        self.assertEqual(whatsapp_adeudo(ana, vencido), '')


class LeerHorarioTests(TestCase):
    def test_formatos_de_horario(self):
        casos = {
            '5 pm': (time(17, 0), '', ''),
            '17:00 PRINCIPIANTES': (time(17, 0), '', 'PRINCIPIANTES'),
            '7:00': (time(7, 0), '', ''),
            '11am sabados': (time(11, 0), '5', ''),
            'Niños Martes y Jueves 5pm': (time(17, 0), '13', 'NINOS'),
            'Adultos Lun Mie y Vie 7:15AM': (time(7, 15), '024', 'ADULTOS'),
            'Equipo de 3 a 6pm': (time(15, 0), '', 'EQUIPO'),
            'EQUIPO A': (None, '', 'EQUIPO A'),
            'Niños 5pm Lun-vie': (time(17, 0), '01234', 'NINOS'),
            '3 CLA X SEM': (None, '', 'CLA X SEM'),
        }
        for texto, esperado in casos.items():
            self.assertEqual(leer_horario(texto), esperado, texto)


class BorrarSalidaTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import Permission
        from posApp.models import Salida
        self.sucursal = Sucursal.objects.create(nombre='Acuatica Urioste Chuburna')
        self.salida = Salida.objects.create(concepto='Acido', monto=129, fecha=timezone.localdate(), sucursal=self.sucursal)
        self.otra = Salida.objects.create(concepto='Cloro', monto=500, fecha=timezone.localdate(),
                                          sucursal=Sucursal.objects.create(nombre='Otra'))
        self.dueno = User.objects.create_user('luisU', password='x')
        self.dueno.user_permissions.add(Permission.objects.get(codename='delete_salida'))
        self.jefe = User.objects.create_superuser('yuri', password='x')
        for u in (self.dueno, self.jefe):
            UserProfile.objects.create(user=u, sucursal=self.sucursal)

    def test_solo_quien_tiene_el_permiso_puede_borrar(self):
        from posApp.models import Salida
        # Ser superusuario no basta
        self.client.force_login(self.jefe)
        self.assertNotContains(self.client.get(reverse('sales-page')), 'data-salida-borrar="')
        self.assertEqual(self.client.post(reverse('delete_salida'), {'id': self.salida.id}).status_code, 403)
        self.assertTrue(Salida.objects.filter(id=self.salida.id).exists())

        self.client.force_login(self.dueno)
        self.assertContains(self.client.get(reverse('sales-page')), 'data-salida-borrar="')
        self.assertContains(self.client.get(reverse('monthly_report')), 'data-salida-borrar="')
        # No puede borrar la de otra sucursal
        self.assertEqual(self.client.post(reverse('delete_salida'), {'id': self.otra.id}).json()['status'], 'failed')
        self.assertEqual(self.client.post(reverse('delete_salida'), {'id': self.salida.id}).json()['status'], 'success')
        self.assertFalse(Salida.objects.filter(id=self.salida.id).exists())
