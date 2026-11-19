import re
from datetime import timedelta
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Max, Q, Sum, TextField, Value
from django.db.models.functions import Lower, Replace
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.views.decorators.http import require_POST
from openpyxl import Workbook
from openpyxl.styles import Font

from posApp.models import (Asistencia, Clientes, Grupo, Levels, Mensualidad, Sales, Sucursal, UserProfile,
                           salesItems)
from posApp.templatetags.whatsapp import whatsapp_adeudo

# Días antes del vencimiento en que se avisa "Por vencer"
DIAS_POR_VENCER = 5
# Solo se revisan pagos de este periodo hacia atrás para calcular la vigencia
VENTANA_PAGOS_DIAS = 400

# Acepta "URI123", "URI-123" (o con otro separador, por la distribución de teclado del lector) o solo "123"
CODIGO_RE = re.compile(r'^\s*(?:URI\W?)?(\d+)\s*$', re.IGNORECASE)

AL_CORRIENTE = 'Al corriente'
POR_VENCER = 'Por vencer'
VENCIDO = 'Vencido'
SIN_PAGOS = 'Sin pagos'


def _sucursal_de_request(request):
    """Regresa (sucursal, respuesta_error) siguiendo la misma regla que el resto de las vistas."""
    try:
        user_profile = UserProfile.objects.get(user=request.user)
    except UserProfile.DoesNotExist:
        return None, render(request, 'posApp/error.html', {'message': 'Este usuario no tiene un perfil asociado.'})

    if not user_profile.sucursal:
        return None, render(request, 'posApp/error.html', {'message': 'Este perfil no tiene una sucursal asignada.'})

    sucursal_a_usar = user_profile.sucursal
    if user_profile.is_manager and 'sucursal_id' in request.session:
        try:
            sucursal_a_usar = Sucursal.objects.get(id=request.session['sucursal_id'])
        except Sucursal.DoesNotExist:
            return None, render(request, 'posApp/error.html', {'message': 'Sucursal no válida en la sesión.'})
    return sucursal_a_usar, None


def _normalizar_horario(texto):
    return (texto or '').lower().replace(' ', '')


def buscar_clientes(clientes, query):
    """
    Búsqueda de clientes: cada palabra debe coincidir con el nombre, algún apellido o el celular
    ("ana perez" encuentra a Ana Pérez, no a todas las Anas). "URI123" busca por el código de la credencial.
    """
    query = (query or '').strip()
    if not query:
        return clientes
    codigo = re.match(r'^URI\W?(\d+)$', query, re.IGNORECASE)
    if codigo:
        return clientes.filter(id=codigo.group(1))

    clientes = clientes.annotate(
        celular_norm=Replace(Replace(Replace('celular', Value(' '), Value('')), Value('-'), Value('')),
                             Value('.'), Value(''), output_field=TextField())
    )
    for term in query.split():
        condicion = (Q(nombre__icontains=term) | Q(apellido_paterno__icontains=term) |
                     Q(apellido_materno__icontains=term))
        digitos = re.sub(r'\D', '', term)
        if len(digitos) >= 3:
            condicion |= Q(celular_norm__contains=digitos)
        clientes = clientes.filter(condicion)
    return clientes


def _filtrar_clientes(clientes, nivel_id, horario, query):
    if nivel_id:
        clientes = clientes.filter(nivel_id=nivel_id)
    if horario:
        # "5 pm", "5pm" y "5PM" se consideran el mismo horario
        clientes = clientes.annotate(
            horario_norm=Replace(Lower('horario'), Value(' '), Value(''), output_field=TextField())
        ).filter(horario_norm__contains=_normalizar_horario(horario))
    return buscar_clientes(clientes, query)


def horarios_de_sucursal(sucursal):
    """Lista de horarios capturados en los clientes activos, sin duplicados por mayúsculas/espacios."""
    horarios = {}
    for horario in (Clientes.objects.filter(sucursal=sucursal, status=1)
                    .exclude(horario='').values_list('horario', flat=True).distinct()):
        horarios.setdefault(_normalizar_horario(horario), horario.strip())
    return sorted(horarios.values(), key=str.lower)


def _registrar_pago(info, fecha_pago, vigente_hasta, concepto):
    if fecha_pago and (info['ultimo_pago'] is None or fecha_pago > info['ultimo_pago']):
        info['ultimo_pago'] = fecha_pago
        info['concepto'] = concepto
    if vigente_hasta and (info['vigente_hasta'] is None or vigente_hasta > info['vigente_hasta']):
        info['vigente_hasta'] = vigente_hasta


def calcular_estados_pago(cliente_ids, hoy=None):
    """
    Calcula el estado de pago de cada cliente a partir de:
      - El "próximo pago" de cada venta (capturado en el POS o leído del comentario del ticket).
      - Si la venta no lo tiene: productos con `dias_vigencia` (fecha de venta + días de vigencia).
      - Mensualidades pagadas (cubren hasta su fecha de vencimiento).
    `vigente_hasta` es la fecha del próximo pago. Regresa
    {cliente_id: {'estado', 'ultimo_pago', 'concepto', 'vigente_hasta', 'dias'}}.
    """
    hoy = hoy or timezone.localdate()
    cliente_ids = list(cliente_ids)
    estados = {cid: {'ultimo_pago': None, 'concepto': '', 'vigente_hasta': None} for cid in cliente_ids}
    if not cliente_ids:
        return estados

    desde = hoy - timedelta(days=VENTANA_PAGOS_DIAS)

    # Por venta: fecha, próximo pago anotado y lo que cubren sus productos de clases
    ventas = {}
    for venta_id, cliente_id, fecha_venta, proximo_pago in (
            Sales.objects.filter(client_id__in=cliente_ids, proximo_pago__isnull=False,
                                 date_added__date__gte=desde, date_added__date__lte=hoy)
            .values_list('id', 'client_id', 'date_added', 'proximo_pago')):
        ventas[venta_id] = {'cliente': cliente_id, 'fecha': timezone.localdate(fecha_venta),
                            'proximo_pago': proximo_pago, 'cubre': None, 'concepto': ''}
    items = (salesItems.objects
             .filter(Q(sale_id__in=list(ventas)) |
                     Q(client_id__in=cliente_ids, product_id__dias_vigencia__gt=0,
                       sale_id__date_added__date__gte=desde, sale_id__date_added__date__lte=hoy))
             .values_list('sale_id', 'sale_id__client_id', 'sale_id__date_added', 'product_id__dias_vigencia',
                          'product_id__name', 'product_name'))
    for venta_id, cliente_id, fecha_venta, dias_vigencia, nombre, nombre_guardado in items:
        venta = ventas.setdefault(venta_id, {'cliente': cliente_id, 'fecha': timezone.localdate(fecha_venta),
                                             'proximo_pago': None, 'cubre': None, 'concepto': ''})
        if dias_vigencia:
            cubre = venta['fecha'] + timedelta(days=dias_vigencia)
            if venta['cubre'] is None or cubre > venta['cubre']:
                venta['cubre'], venta['concepto'] = cubre, nombre
        if not venta['concepto']:
            venta['concepto'] = nombre or nombre_guardado or ''

    for venta in ventas.values():
        if venta['cliente'] in estados:
            _registrar_pago(estados[venta['cliente']], venta['fecha'],
                            venta['proximo_pago'] or venta['cubre'], venta['concepto'] or 'Pago')

    mensualidades = (Mensualidad.objects
                     .filter(cliente_id__in=cliente_ids, pagado=True, fecha_vencimiento__gte=desde)
                     .values_list('cliente_id', 'fecha_pago', 'fecha_vencimiento', 'plan_inscripcion__nombre'))
    for cliente_id, fecha_pago, fecha_vencimiento, plan in mensualidades:
        _registrar_pago(estados[cliente_id], fecha_pago, fecha_vencimiento, f"Mensualidad {plan or ''}".strip())

    for info in estados.values():
        vigente_hasta = info['vigente_hasta']
        if vigente_hasta is None:
            info['estado'], info['dias'] = SIN_PAGOS, None
        elif vigente_hasta < hoy:
            info['estado'], info['dias'] = VENCIDO, (hoy - vigente_hasta).days
        elif (vigente_hasta - hoy).days <= DIAS_POR_VENCER:
            info['estado'], info['dias'] = POR_VENCER, (vigente_hasta - hoy).days
        else:
            info['estado'], info['dias'] = AL_CORRIENTE, (vigente_hasta - hoy).days
    return estados


# Una clase cuenta como "en curso" desde 45 min antes de empezar hasta 75 min después
MINUTOS_ANTES_DE_CLASE = 45
MINUTOS_DESPUES_DE_CLASE = 75


# Minutos de gracia: quien llega después de esto queda con retardo
TOLERANCIA_RETARDO = 10


def minutos_tarde(grupo, hora):
    """Cuántos minutos después del inicio de la clase llegó (0 si llegó a tiempo o el grupo no tiene hora)."""
    if not grupo or not grupo.hora_inicio or not hora:
        return 0
    return max(0, (hora.hour * 60 + hora.minute) - (grupo.hora_inicio.hour * 60 + grupo.hora_inicio.minute))


def grupo_mas_cercano(grupos, ahora):
    """Si le toca clase hoy pero pasó el QR fuera de la ventana, se va a la clase de hoy más cercana a esa hora."""
    con_hora = [g for g in grupos if g.hora_inicio]
    if not con_hora:
        return grupos[0] if len(grupos) == 1 else None
    minutos = ahora.hour * 60 + ahora.minute
    return min(con_hora, key=lambda g: abs(minutos - (g.hora_inicio.hour * 60 + g.hora_inicio.minute)))


def grupo_en_curso(grupos, ahora):
    """De los grupos que tocan hoy, el que está por empezar o empezó hace poco (el más cercano a la hora)."""
    mejor, distancia = None, None
    minutos_ahora = ahora.hour * 60 + ahora.minute
    for grupo in grupos:
        if not grupo.hora_inicio:
            continue
        diferencia = minutos_ahora - (grupo.hora_inicio.hour * 60 + grupo.hora_inicio.minute)
        if -MINUTOS_ANTES_DE_CLASE <= diferencia <= MINUTOS_DESPUES_DE_CLASE:
            if distancia is None or abs(diferencia) < distancia:
                mejor, distancia = grupo, abs(diferencia)
    return mejor


@login_required
def pase_lista(request):
    sucursal_a_usar, error = _sucursal_de_request(request)
    if error:
        return error

    hoy = timezone.localdate()
    fecha = parse_date(request.GET.get('fecha') or '') or hoy
    grupo_id = request.GET.get('grupo') or ''

    activos = Q(clientes__status=1)
    grupos_dia = [g for g in Grupo.objects.filter(sucursal=sucursal_a_usar, activo=True)
                  .annotate(alumnos=Count('clientes', filter=activos, distinct=True))
                  .order_by(F('hora_inicio').asc(nulls_last=True), 'nombre') if g.toca_el(fecha)]
    grupo = next((g for g in grupos_dia if str(g.id) == grupo_id), None)
    if grupo_id and not grupo:
        # Un grupo que no toca ese día también se puede abrir desde su enlace
        grupo = Grupo.objects.filter(id=grupo_id, sucursal=sucursal_a_usar).first()
    en_curso = grupo_en_curso(grupos_dia, timezone.localtime()) if fecha == hoy else None
    if not grupo_id and en_curso:
        grupo = en_curso

    llegaron_por_grupo = dict(
        Asistencia.objects.filter(sucursal=sucursal_a_usar, fecha=fecha, grupo__isnull=False,
                                  estado__in=[Asistencia.PRESENTE, Asistencia.RETARDO])
        .values_list('grupo').annotate(total=Count('id'))
    )
    for g in grupos_dia:
        g.llegaron = llegaron_por_grupo.get(g.id, 0)
        g.es_en_curso = en_curso is not None and g.id == en_curso.id

    filas = []
    if grupo:
        miembros = list(grupo.clientes.filter(status=1).select_related('nivel').order_by('nombre', 'apellido_paterno'))
        ids_miembros = {c.id for c in miembros}
        registros = {a.cliente_id: a for a in Asistencia.objects.filter(fecha=fecha, cliente_id__in=ids_miembros)}
        # Alumnos de otros grupos que vinieron a esta clase (reposiciones)
        invitados = list(Asistencia.objects.filter(fecha=fecha, grupo=grupo).exclude(cliente_id__in=ids_miembros)
                         .select_related('cliente', 'cliente__nivel'))
        estados_pago = calcular_estados_pago(list(ids_miembros) + [a.cliente_id for a in invitados], hoy=fecha)
        filas = [{'cliente': c, 'asistencia': registros.get(c.id), 'pago': estados_pago[c.id], 'invitado': False}
                 for c in miembros]
        filas += [{'cliente': a.cliente, 'asistencia': a, 'pago': estados_pago[a.cliente_id], 'invitado': True}
                  for a in invitados]
        for f in filas:
            a = f['asistencia']
            f['tarde'] = minutos_tarde(grupo, a.hora_llegada) if a and a.hora_llegada else 0
            f['es_tarde'] = f['tarde'] > TOLERANCIA_RETARDO

    # Llegaron (casi siempre por QR) un día en que no les tocaba clase: no salen en ninguna lista de grupo
    sin_clase = list(Asistencia.objects.filter(sucursal=sucursal_a_usar, fecha=fecha, grupo__isnull=True,
                                               estado__in=[Asistencia.PRESENTE, Asistencia.RETARDO])
                     .select_related('cliente').order_by('hora_llegada'))
    if sin_clase:
        pagos_sin_clase = calcular_estados_pago([a.cliente_id for a in sin_clase], hoy=fecha)
        for a in sin_clase:
            a.pago = pagos_sin_clase[a.cliente_id]

    conteo = {estado: 0 for estado, _ in Asistencia.ESTADO_CHOICES}
    for f in filas:
        if f['asistencia']:
            conteo[f['asistencia'].estado] += 1
    resumen = {
        'total': len(filas),
        'presentes': conteo[Asistencia.PRESENTE] + conteo[Asistencia.RETARDO],
        'sin_marcar': len(filas) - sum(conteo.values()),
        'con_adeudo': sum(1 for f in filas if f['pago']['estado'] in (VENCIDO, SIN_PAGOS)),
        'tarde': sum(1 for f in filas if f.get('es_tarde')),
        'barra': [(estado, conteo[estado] * 100 / len(filas)) for estado in conteo] if filas else [],
    }

    context = {
        'page_title': 'Pase de lista',
        'fecha': fecha,
        'dia_anterior': fecha - timedelta(days=1),
        'dia_siguiente': fecha + timedelta(days=1),
        'es_hoy': fecha == hoy,
        'grupos_dia': grupos_dia,
        'grupo': grupo,
        'hay_grupos': Grupo.objects.filter(sucursal=sucursal_a_usar).exists(),
        'filas': filas,
        'resumen': resumen,
        'estados_asistencia': Asistencia.ESTADO_CHOICES,
        'sin_clase': sin_clase,
        'tolerancia': TOLERANCIA_RETARDO,
    }
    return render(request, 'posApp/pase_lista.html', context)


def _json_login_required(vista):
    """Como login_required, pero responde JSON 401 para que la pantalla avise que la sesión se cerró."""
    def envuelta(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'ok': False, 'sesion': True,
                                 'msg': 'La sesión se cerró. Vuelve a entrar para seguir registrando.'}, status=401)
        return vista(request, *args, **kwargs)
    envuelta.__name__ = vista.__name__
    return envuelta


@_json_login_required
@require_POST
def asistencia_marcar(request):
    """Guarda al momento lo que se marca en el pase de lista (un alumno)."""
    sucursal_a_usar, error = _sucursal_de_request(request)
    if error:
        return JsonResponse({'ok': False, 'msg': 'Tu usuario no tiene una sucursal asignada.'}, status=403)
    cliente = Clientes.objects.filter(id=request.POST.get('cliente') or 0, sucursal=sucursal_a_usar).first()
    if not cliente:
        return JsonResponse({'ok': False, 'msg': 'No se encontró al alumno.'}, status=404)
    fecha = parse_date(request.POST.get('fecha') or '') or timezone.localdate()
    grupo = Grupo.objects.filter(id=request.POST.get('grupo') or 0, sucursal=sucursal_a_usar).first()

    if 'estado' in request.POST:
        estado = request.POST['estado']
        if estado == '':
            Asistencia.objects.filter(cliente=cliente, fecha=fecha).delete()
            return JsonResponse({'ok': True})
        if estado not in dict(Asistencia.ESTADO_CHOICES):
            return JsonResponse({'ok': False, 'msg': 'Estado no válido.'}, status=400)
        defaults = {'estado': estado, 'sucursal': sucursal_a_usar, 'registrado_por': request.user}
        if grupo:
            defaults['grupo'] = grupo
        Asistencia.objects.update_or_create(cliente=cliente, fecha=fecha, defaults=defaults)

    if 'comentario' in request.POST:
        actualizados = Asistencia.objects.filter(cliente=cliente, fecha=fecha).update(
            comentario=request.POST['comentario'].strip()[:200])
        if not actualizados:
            return JsonResponse({'ok': False, 'msg': 'Marca primero la asistencia y luego agrega la nota.'}, status=400)
    return JsonResponse({'ok': True})


@_json_login_required
@require_POST
def asistencia_marcar_pendientes(request):
    """Marca de una vez a los alumnos que siguen sin registro (todos presentes o cerrar la lista con faltas)."""
    sucursal_a_usar, error = _sucursal_de_request(request)
    if error:
        return JsonResponse({'ok': False, 'msg': 'Tu usuario no tiene una sucursal asignada.'}, status=403)
    estado = request.POST.get('estado')
    if estado not in (Asistencia.PRESENTE, Asistencia.FALTA):
        return JsonResponse({'ok': False, 'msg': 'Estado no válido.'}, status=400)
    fecha = parse_date(request.POST.get('fecha') or '') or timezone.localdate()
    grupo = Grupo.objects.filter(id=request.POST.get('grupo') or 0, sucursal=sucursal_a_usar).first()
    if not grupo:
        return JsonResponse({'ok': False, 'msg': 'No se encontró el grupo.'}, status=404)
    con_registro = Asistencia.objects.filter(fecha=fecha).values('cliente_id')
    pendientes = grupo.clientes.filter(status=1).exclude(id__in=con_registro)
    nuevos = [Asistencia(cliente=c, fecha=fecha, estado=estado, grupo=grupo, sucursal=sucursal_a_usar,
                         registrado_por=request.user) for c in pendientes]
    Asistencia.objects.bulk_create(nuevos, ignore_conflicts=True)
    return JsonResponse({'ok': True, 'marcados': len(nuevos)})


VISTAS_REPORTE = {
    'vinieron': 'Vinieron',
    'deben': 'Vinieron y deben',
    'ausentes': 'No han venido',
}


def _periodos_rapidos(hoy):
    inicio_mes = hoy.replace(day=1)
    fin_mes_pasado = inicio_mes - timedelta(days=1)
    return [
        ('Hoy', hoy, hoy),
        ('Esta semana', hoy - timedelta(days=hoy.weekday()), hoy),
        ('Este mes', inicio_mes, hoy),
        ('Mes pasado', fin_mes_pasado.replace(day=1), fin_mes_pasado),
    ]


def _datos_reporte(request, sucursal_a_usar):
    hoy = timezone.localdate()
    fecha_inicio = parse_date(request.GET.get('fecha_inicio') or '') or hoy.replace(day=1)
    fecha_fin = parse_date(request.GET.get('fecha_fin') or '') or hoy
    if fecha_fin < fecha_inicio:
        fecha_inicio, fecha_fin = fecha_fin, fecha_inicio
    nivel_id = request.GET.get('nivel') or ''
    horario = (request.GET.get('horario') or '').strip()
    query = (request.GET.get('q') or '').strip()
    vista = request.GET.get('vista') if request.GET.get('vista') in VISTAS_REPORTE else 'vinieron'
    grupo_elegido = Grupo.objects.filter(id=request.GET.get('grupo') or 0, sucursal=sucursal_a_usar).first()

    en_rango = Q(asistencia__fecha__range=[fecha_inicio, fecha_fin])
    clientes = Clientes.objects.filter(sucursal=sucursal_a_usar)
    if grupo_elegido:
        # Los inscritos en el grupo y los que vinieron a esa clase como invitados
        clientes = clientes.filter(
            Q(grupos=grupo_elegido) |
            Q(id__in=Asistencia.objects.filter(grupo=grupo_elegido, fecha__range=[fecha_inicio, fecha_fin]).values('cliente_id'))
        ).distinct()
    clientes = _filtrar_clientes(
        clientes.select_related('nivel').prefetch_related('grupos'),
        nivel_id, horario, query,
    ).annotate(
        presentes=Count('asistencia', filter=en_rango & Q(asistencia__estado=Asistencia.PRESENTE)),
        retardos=Count('asistencia', filter=en_rango & Q(asistencia__estado=Asistencia.RETARDO)),
        faltas=Count('asistencia', filter=en_rango & Q(asistencia__estado=Asistencia.FALTA)),
        justificadas=Count('asistencia', filter=en_rango & Q(asistencia__estado=Asistencia.JUSTIFICADA)),
        ultima_asistencia=Max('asistencia__fecha', filter=Q(asistencia__estado__in=[Asistencia.PRESENTE, Asistencia.RETARDO])),
    ).filter(
        # Solo alumnos activos o que tengan registros en el periodo
        Q(status=1) | Q(presentes__gt=0) | Q(retardos__gt=0) | Q(faltas__gt=0) | Q(justificadas__gt=0)
    ).order_by('nombre', 'apellido_paterno')

    clientes = list(clientes)
    estados_pago = calcular_estados_pago([c.id for c in clientes])
    grupos = {'vinieron': [], 'deben': [], 'ausentes': []}
    total_dias = 0
    for c in clientes:
        dias = c.presentes + c.retardos
        contables = dias + c.faltas  # las justificadas no cuentan en contra
        fila = {
            'cliente': c,
            'pago': estados_pago[c.id],
            'dias': dias,
            'porcentaje': round(dias * 100 / contables) if contables else None,
        }
        if dias:
            total_dias += dias
            grupos['vinieron'].append(fila)
            if fila['pago']['estado'] in (VENCIDO, SIN_PAGOS):
                grupos['deben'].append(fila)
        elif c.status == 1:
            grupos['ausentes'].append(fila)

    # Quien más vino primero; los ausentes, los que llevan más tiempo sin venir primero
    for grupo in ('vinieron', 'deben'):
        grupos[grupo].sort(key=lambda f: -f['dias'])
    grupos['ausentes'].sort(key=lambda f: (f['cliente'].ultima_asistencia is not None, f['cliente'].ultima_asistencia or hoy))

    vinieron = len(grupos['vinieron'])
    return {
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        'nivel_id': nivel_id,
        'horario': horario,
        'grupo': grupo_elegido,
        'query': query,
        'vista': vista,
        'vistas': [(clave, nombre, len(grupos[clave])) for clave, nombre in VISTAS_REPORTE.items()],
        'filas': grupos[vista],
        'resumen': {
            'asistencias': total_dias,
            'vinieron': vinieron,
            'activos': sum(1 for c in clientes if c.status == 1),
            'promedio': round(total_dias / vinieron, 1) if vinieron else 0,
            'deben': len(grupos['deben']),
        },
        'periodos': [
            {'nombre': n, 'inicio': i, 'fin': f, 'activo': (i, f) == (fecha_inicio, fecha_fin)}
            for n, i, f in _periodos_rapidos(hoy)
        ],
    }


@login_required
def reporte_asistencia(request):
    sucursal_a_usar, error = _sucursal_de_request(request)
    if error:
        return error

    context = _datos_reporte(request, sucursal_a_usar)
    base = {k: v for k, v in request.GET.items() if v and k not in ('vista', 'fecha_inicio', 'fecha_fin')}
    fechas = {'fecha_inicio': context['fecha_inicio'].isoformat(), 'fecha_fin': context['fecha_fin'].isoformat()}
    context.update({
        'page_title': 'Reporte de asistencia',
        'niveles': Levels.objects.filter(sucursal=sucursal_a_usar),
        'horarios': horarios_de_sucursal(sucursal_a_usar),
        'grupos': Grupo.objects.filter(sucursal=sucursal_a_usar, activo=True)
                  .order_by(F('hora_inicio').asc(nulls_last=True), 'nombre'),
        # Enlaces que cambian una sola cosa y conservan el resto de los filtros
        'qs_sin_vista': urlencode({**base, **fechas}),
        'qs_sin_fechas': urlencode({**base, 'vista': context['vista']}),
        'qs_excel': urlencode({**base, **fechas, 'vista': context['vista']}),
    })
    return render(request, 'posApp/reporte_asistencia.html', context)


@login_required
def exportar_asistencia_excel(request):
    sucursal_a_usar, error = _sucursal_de_request(request)
    if error:
        return error

    datos = _datos_reporte(request, sucursal_a_usar)

    wb = Workbook()
    ws = wb.active
    ws.title = "Asistencia"
    nombre_vista = VISTAS_REPORTE[datos['vista']] + (f" ({datos['grupo'].nombre})" if datos['grupo'] else '')
    ws.append([f"{nombre_vista}: del {datos['fecha_inicio']:%d/%m/%Y} al {datos['fecha_fin']:%d/%m/%Y} - {sucursal_a_usar}"])
    ws['A1'].font = Font(bold=True)
    headers = ['Alumno', 'Grupo', 'Nivel', 'Horario', 'Días que vino', 'Retardos', 'Faltas', 'Justificadas',
               'Última vez que vino', 'Estado de pago', 'Último pago', 'Concepto', 'Próximo pago']
    ws.append(headers)
    for cell in ws[2]:
        cell.font = Font(bold=True)

    for fila in datos['filas']:
        c, pago = fila['cliente'], fila['pago']
        ws.append([
            f"{c.nombre} {c.apellido_paterno} {c.apellido_materno}",
            ', '.join(g.nombre for g in c.grupos.all()),
            str(c.nivel) if c.nivel else '',
            c.horario,
            fila['dias'], c.retardos, c.faltas, c.justificadas,
            c.ultima_asistencia,
            pago['estado'],
            pago['ultimo_pago'],
            pago['concepto'],
            pago['vigente_hasta'],
        ])

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = (
        f'attachment; filename="asistencia_{datos["fecha_inicio"]:%Y%m%d}_{datos["fecha_fin"]:%Y%m%d}.xlsx"'
    )
    wb.save(response)
    return response


@login_required
def cliente_asistencias(request, cliente_id):
    """Ficha del cliente: estado de pago, historial de pagos, asistencias y datos de contacto."""
    sucursal_a_usar, error = _sucursal_de_request(request)
    if error:
        return error

    cliente = get_object_or_404(Clientes.objects.select_related('nivel', 'plan_inscripcion', 'genero'),
                                id=cliente_id, sucursal=sucursal_a_usar)
    asistencias = Asistencia.objects.filter(cliente=cliente).select_related('registrado_por').order_by('-fecha')
    totales = dict(asistencias.values_list('estado').annotate(total=Count('id')))
    asistio = totales.get(Asistencia.PRESENTE, 0) + totales.get(Asistencia.RETARDO, 0)
    contables = asistio + totales.get(Asistencia.FALTA, 0)

    ventas = (Sales.objects.filter(client=cliente, sucursal=sucursal_a_usar)
              .select_related('tipoPago', 'usuario')
              .prefetch_related('salesitems_set__product_id')
              .order_by('-date_added'))
    resumen_ventas = ventas.aggregate(total=Sum('grand_total'), cantidad=Count('id'))
    pagos = []
    for venta in ventas[:60]:
        conceptos = [i.product_name or (i.product_id.name if i.product_id else 'Producto eliminado')
                     for i in venta.salesitems_set.all()]
        pagos.append({'venta': venta, 'conceptos': conceptos})

    context = {
        'page_title': f'{cliente.nombre} {cliente.apellido_paterno}',
        'cliente': cliente,
        'asistencias': asistencias[:120],
        'totales': {
            'presentes': totales.get(Asistencia.PRESENTE, 0),
            'retardos': totales.get(Asistencia.RETARDO, 0),
            'faltas': totales.get(Asistencia.FALTA, 0),
            'justificadas': totales.get(Asistencia.JUSTIFICADA, 0),
            'porcentaje': round(asistio * 100 / contables) if contables else None,
        },
        'pago': calcular_estados_pago([cliente.id])[cliente.id],
        'pagos': pagos,
        'grupos_cliente': cliente.grupos.all(),
        'grupos_disponibles': Grupo.objects.filter(sucursal=sucursal_a_usar, activo=True).exclude(clientes=cliente),
        'total_pagado': resumen_ventas['total'] or 0,
        'numero_pagos': resumen_ventas['cantidad'],
    }
    return render(request, 'posApp/cliente_ficha.html', context)

def _pago_json(pago):
    return {
        'estado': pago['estado'],
        'dias': pago['dias'],
        'ultimo_pago': pago['ultimo_pago'].strftime('%d/%m/%Y') if pago['ultimo_pago'] else None,
        'concepto': pago['concepto'],
        'vigente_hasta': pago['vigente_hasta'].strftime('%d/%m/%Y') if pago['vigente_hasta'] else None,
    }


@login_required
def checkin(request):
    sucursal_a_usar, error = _sucursal_de_request(request)
    if error:
        return error

    hoy = timezone.localdate()
    llegadas = list(Asistencia.objects
                    .filter(sucursal=sucursal_a_usar, fecha=hoy, hora_llegada__isnull=False)
                    .select_related('cliente', 'cliente__nivel', 'grupo')
                    .order_by('-hora_llegada'))
    estados_pago = calcular_estados_pago([a.cliente_id for a in llegadas])
    context = {
        'page_title': 'Check-in QR',
        'hoy': hoy,
        'llegadas': [{'asistencia': a, 'pago': estados_pago[a.cliente_id]} for a in llegadas],
    }
    return render(request, 'posApp/checkin.html', context)


def _hora_de_lectura(texto, ahora):
    """Hora en que se escaneó; las lecturas guardadas sin internet llegan después con su hora original."""
    momento = parse_datetime(texto or '')
    if not momento:
        return ahora
    if timezone.is_naive(momento):
        momento = timezone.make_aware(momento)
    momento = timezone.localtime(momento)
    if ahora - timedelta(hours=36) <= momento <= ahora + timedelta(minutes=5):
        return momento
    return ahora


@_json_login_required
@require_POST
def checkin_registrar(request):
    sucursal_a_usar, error = _sucursal_de_request(request)
    if error:
        return JsonResponse({'ok': False, 'msg': 'Tu usuario no tiene una sucursal asignada.'}, status=403)

    codigo = request.POST.get('codigo', '')
    match = CODIGO_RE.match(codigo)
    if not match:
        return JsonResponse({'ok': False, 'msg': f'Código no reconocido: {codigo[:40]}'})
    cliente = Clientes.objects.filter(id=match.group(1)).select_related('nivel', 'sucursal').first()
    if not cliente:
        return JsonResponse({'ok': False, 'msg': 'No hay ningún alumno con ese código.'})
    if cliente.sucursal_id != sucursal_a_usar.id:
        return JsonResponse({'ok': False, 'msg': f'{cliente.nombre} {cliente.apellido_paterno} es alumno de '
                                                 f'{cliente.sucursal or "otra sucursal"}. No se registró aquí.'})

    momento = _hora_de_lectura(request.POST.get('hora'), timezone.localtime())
    grupos_hoy = [g for g in cliente.grupos.filter(activo=True) if g.toca_el(momento.date())]
    # En su día de clase siempre queda en la lista de su grupo, aunque llegue fuera de la ventana de la clase
    grupo = grupo_en_curso(grupos_hoy, momento) or grupo_mas_cercano(grupos_hoy, momento)
    tarde = minutos_tarde(grupo, momento.time())

    asistencia, creada = Asistencia.objects.get_or_create(
        cliente=cliente, fecha=momento.date(),
        defaults={'estado': Asistencia.RETARDO if tarde > TOLERANCIA_RETARDO else Asistencia.PRESENTE,
                  'hora_llegada': momento.time(), 'grupo': grupo,
                  'sucursal': sucursal_a_usar, 'registrado_por': request.user},
    )
    ya_registrado = not creada and asistencia.hora_llegada is not None
    if not creada and asistencia.hora_llegada is None:
        # Ya tenía un registro manual del día (ej. se le puso falta) y sí llegó
        asistencia.hora_llegada = momento.time()
        if asistencia.estado == Asistencia.FALTA:
            asistencia.estado = Asistencia.RETARDO if tarde > TOLERANCIA_RETARDO else Asistencia.PRESENTE
        asistencia.grupo = asistencia.grupo or grupo
        asistencia.registrado_por = request.user
        asistencia.save()

    pago = calcular_estados_pago([cliente.id])[cliente.id]
    return JsonResponse({
        'ok': True,
        'ya_registrado': ya_registrado,
        'cliente': {
            'id': cliente.id,
            'nombre': f"{cliente.nombre} {cliente.apellido_paterno} {cliente.apellido_materno}",
            'iniciales': cliente.iniciales,
            'grupo': ", ".join(x for x in [str(cliente.nivel) if cliente.nivel else '', cliente.horario] if x),
            'activo': cliente.status == 1,
            'url': reverse('cliente-ficha', args=[cliente.id]),
        },
        'clase': asistencia.grupo.nombre if asistencia.grupo else None,
        'tiene_grupos': bool(grupos_hoy) or cliente.grupos.exists(),
        # Tiene grupo pero hoy no le toca: se registra igual, pero recepción debe saberlo
        'sin_clase_hoy': [f"{g.nombre} ({g.dias_texto})" for g in cliente.grupos.filter(activo=True)] if not grupos_hoy else [],
        'hora': asistencia.hora_llegada.strftime('%H:%M'),
        'estado_asistencia': asistencia.get_estado_display(),
        'minutos_tarde': minutos_tarde(asistencia.grupo, asistencia.hora_llegada) if asistencia.grupo else 0,
        'tolerancia': TOLERANCIA_RETARDO,
        'pago': _pago_json(pago),
        'whatsapp': whatsapp_adeudo(cliente, pago),
    })


@login_required
def credenciales_qr(request, cliente_id=None):
    """Credenciales con QR para imprimir: de un alumno, o de todos los que coincidan con los filtros."""
    sucursal_a_usar, error = _sucursal_de_request(request)
    if error:
        return error

    if cliente_id:
        clientes = [get_object_or_404(Clientes, id=cliente_id, sucursal=sucursal_a_usar)]
    else:
        nivel_id = request.GET.get('nivel') or ''
        horario = (request.GET.get('horario') or '').strip()
        query = (request.GET.get('q') or '').strip()
        clientes = list(_filtrar_clientes(
            Clientes.objects.filter(sucursal=sucursal_a_usar, status=1).select_related('nivel'),
            nivel_id, horario, query,
        ).order_by('nombre', 'apellido_paterno'))

    return render(request, 'posApp/credenciales_qr.html', {
        'clientes': clientes,
        'sucursal': sucursal_a_usar,
        'individual': cliente_id is not None,
    })
