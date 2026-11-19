import re
from collections import OrderedDict
from urllib.parse import urlencode
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from posApp.horarios import NOMBRES_DIAS, describir_dias, leer_horario
from posApp.models import Clientes, Grupo, Levels, Products, salesItems
from posApp.views_asistencia import _sucursal_de_request, buscar_clientes

MINIMO_ALUMNOS_SUGERENCIA = 3
# Para inscribir a quienes ya compraron el producto de una clase
DIAS_COMPRA_RECIENTE = 40


def _nombre_sugerido(hora, dias, etiqueta):
    partes = []
    if etiqueta:
        partes.append(etiqueta.title())
    if dias:
        partes.append(describir_dias(dias))
    if hora:
        partes.append(hora.strftime('%H:%M'))
    return ' '.join(partes) or 'Sin nombre'


def proponer_grupos(sucursal):
    """Agrupa a los alumnos activos sin grupo según lo que dice su horario."""
    propuestas = OrderedDict()
    sin_grupo = Clientes.objects.filter(sucursal=sucursal, status=1, grupos__isnull=True).only('id', 'horario')
    for cliente in sin_grupo:
        hora, dias, etiqueta = leer_horario(cliente.horario)
        if not hora and not etiqueta:
            continue
        clave = f"{hora.strftime('%H:%M') if hora else ''}|{dias}|{etiqueta}"
        propuesta = propuestas.setdefault(clave, {
            'clave': clave, 'hora': hora, 'dias': dias, 'etiqueta': etiqueta,
            'nombre': _nombre_sugerido(hora, dias, etiqueta), 'clientes': [], 'ejemplos': set(),
        })
        propuesta['clientes'].append(cliente.id)
        propuesta['ejemplos'].add((cliente.horario or '').strip())
    lista = sorted(propuestas.values(), key=lambda p: (-len(p['clientes']), p['nombre']))
    for p in lista:
        p['ejemplos'] = sorted(p['ejemplos'])[:4]
    return lista


def _palabras(etiqueta):
    return {palabra.rstrip('S') for palabra in etiqueta.split() if len(palabra) > 2}


def grupo_para_producto(producto, grupos):
    """
    El grupo que mejor coincide con lo que dice el nombre de un producto sin grupo ligado
    ("Niños Lun Mie y Vie 5PM" -> el grupo de niños lunes, miércoles y viernes a las 17:00).
    Debe empezar a menos de 45 min; gana el de los mismos días y luego el que comparte palabras.
    """
    hora, dias, etiqueta = leer_horario(re.sub(r'\(.*?\)', ' ', producto.name))
    if not hora:
        return None
    palabras = _palabras(etiqueta)
    mejor, mejor_puntaje = None, None
    for grupo in grupos:
        if not grupo.hora_inicio:
            continue
        diferencia = abs((grupo.hora_inicio.hour * 60 + grupo.hora_inicio.minute) - (hora.hour * 60 + hora.minute))
        if diferencia >= 45:
            continue
        if dias and grupo.dias and not set(dias) & set(grupo.dias):
            continue
        _, _, etiqueta_grupo = leer_horario(grupo.nombre)
        puntaje = (grupo.dias == dias, len(palabras & _palabras(etiqueta_grupo)), -diferencia)
        if mejor_puntaje is None or puntaje > mejor_puntaje:
            mejor, mejor_puntaje = grupo, puntaje
    return mejor


def proponer_grupos_de_productos(sucursal):
    """
    Un grupo por cada producto de clase cuyo nombre dice la hora (y a veces los días), por ejemplo
    "Niños Lun Mie y Vie 5PM". Solo productos marcados como mensualidad y aún sin grupo.
    Productos que dicen exactamente la misma clase van al mismo grupo.
    """
    propuestas = OrderedDict()
    for producto in Products.objects.filter(sucursal=sucursal, status=1, grupo__isnull=True,
                                            dias_vigencia__isnull=False).order_by('name'):
        # Lo que va entre paréntesis suele ser una promoción ("(Mantra)"), no otra clase
        hora, dias, etiqueta = leer_horario(re.sub(r'\(.*?\)', ' ', producto.name))
        if not hora:
            continue
        # "ADULTO" y "ADULTOS" son la misma clase; "GRUPO A" y "GRUPO B" no
        etiqueta_base = ' '.join(palabra.rstrip('S') for palabra in etiqueta.split())
        clave = f"{hora.strftime('%H:%M')}|{dias}|{etiqueta_base}"
        propuesta = propuestas.setdefault(clave, {
            'clave': clave, 'hora': hora, 'dias': dias, 'dias_texto': describir_dias(dias),
            'nombre': ' '.join(producto.name.split()), 'productos': [], 'clientes': [],
        })
        propuesta['productos'].append(producto)

    # Cada alumno activo va al grupo del último producto de clase que compró recientemente
    producto_a_clave = {p.id: clave for clave, prop in propuestas.items() for p in prop['productos']}
    ultimo_por_cliente = {}
    for cliente_id, producto_id in (salesItems.objects
                                    .filter(product_id__in=list(producto_a_clave), client__status=1,
                                            sale_id__date_added__gte=timezone.now() - timedelta(days=DIAS_COMPRA_RECIENTE))
                                    .order_by('sale_id__date_added')
                                    .values_list('client_id', 'product_id')):
        ultimo_por_cliente[cliente_id] = producto_a_clave[producto_id]
    for cliente_id, clave in ultimo_por_cliente.items():
        propuestas[clave]['clientes'].append(cliente_id)

    return sorted(propuestas.values(), key=lambda p: (p['hora'], p['nombre']))


@login_required
def grupos_desde_productos(request):
    sucursal, error = _sucursal_de_request(request)
    if error:
        return error

    propuestas = proponer_grupos_de_productos(sucursal)
    if request.method == 'POST':
        elegidas = set(request.POST.getlist('clave'))
        inscribir = request.POST.get('inscribir') == '1'
        creados = inscritos = movidos = 0
        with transaction.atomic():
            for p in propuestas:
                if p['clave'] not in elegidas:
                    continue
                nombre = (request.POST.get(f"nombre_{p['clave']}") or p['nombre']).strip()[:100]
                grupo = Grupo.objects.create(nombre=nombre, sucursal=sucursal, dias=p['dias'], hora_inicio=p['hora'])
                for producto in p['productos']:
                    producto.grupo = grupo
                    producto.save(update_fields=['grupo'])
                creados += 1
                if inscribir:
                    for cliente in Clientes.objects.filter(id__in=p['clientes']):
                        movidos += len(grupo.inscribir(cliente))
                        inscritos += 1
        mensaje = f'Se crearon {creados} grupos ligados a sus productos.'
        if inscribir:
            mensaje += f' Se inscribieron {inscritos} alumnos'
            mensaje += f' ({movidos} salieron de un grupo a la misma hora).' if movidos else '.'
        messages.success(request, mensaje)
        return redirect('grupos')

    return render(request, 'posApp/grupos_productos.html', {
        'page_title': 'Crear grupos desde productos',
        'propuestas': propuestas,
        'dias_compra': DIAS_COMPRA_RECIENTE,
        'total_alumnos': sum(len(p['clientes']) for p in propuestas),
    })


def _grupos_con_conteos(sucursal):
    return (Grupo.objects.filter(sucursal=sucursal)
            .select_related('nivel')
            .annotate(alumnos=Count('clientes', filter=Q(clientes__status=1), distinct=True))
            .prefetch_related('productos')
            .order_by(F('hora_inicio').asc(nulls_last=True), 'nombre'))


@login_required
def grupos(request):
    sucursal, error = _sucursal_de_request(request)
    if error:
        return error

    propuestas = [p for p in proponer_grupos(sucursal) if len(p['clientes']) >= MINIMO_ALUMNOS_SUGERENCIA]
    hoy = timezone.localdate()
    lista = list(_grupos_con_conteos(sucursal))
    for grupo in lista:
        # "Pasar lista" abre el pase de hoy; si hoy no le toca, el último día que tuvo clase (para ponerse al día)
        grupo.pase_fecha = next((hoy - timedelta(days=d) for d in range(7) if grupo.toca_el(hoy - timedelta(days=d))), None)
        grupo.pase_hoy = grupo.pase_fecha == hoy
    return render(request, 'posApp/grupos.html', {
        'page_title': 'Grupos y horarios',
        'grupos': lista,
        'sugeridos': len(propuestas),
        'sugeridos_productos': len(proponer_grupos_de_productos(sucursal)),
        'sin_grupo': Clientes.objects.filter(sucursal=sucursal, status=1, grupos__isnull=True).count(),
    })


@login_required
def grupos_importar(request):
    """Crea grupos a partir de los horarios que ya tienen capturados los alumnos."""
    sucursal, error = _sucursal_de_request(request)
    if error:
        return error

    propuestas = [p for p in proponer_grupos(sucursal) if len(p['clientes']) >= MINIMO_ALUMNOS_SUGERENCIA]

    if request.method == 'POST':
        elegidas = set(request.POST.getlist('clave'))
        creados = inscritos = 0
        with transaction.atomic():
            for p in propuestas:
                if p['clave'] not in elegidas:
                    continue
                nombre = (request.POST.get(f"nombre_{p['clave']}") or p['nombre']).strip()[:100]
                grupo = Grupo.objects.create(nombre=nombre, sucursal=sucursal, dias=p['dias'], hora_inicio=p['hora'])
                grupo.clientes.add(*p['clientes'])
                creados += 1
                inscritos += len(p['clientes'])
        messages.success(request, f'Se crearon {creados} grupos con {inscritos} alumnos.')
        return redirect('grupos')

    return render(request, 'posApp/grupos_importar.html', {
        'page_title': 'Crear grupos desde horarios',
        'propuestas': propuestas,
        'minimo': MINIMO_ALUMNOS_SUGERENCIA,
    })


def _leer_hora(texto):
    try:
        return datetime.strptime(texto, '%H:%M').time() if texto else None
    except ValueError:
        return None


@login_required
def grupo_editar(request, grupo_id=None):
    sucursal, error = _sucursal_de_request(request)
    if error:
        return error

    grupo = get_object_or_404(Grupo, id=grupo_id, sucursal=sucursal) if grupo_id else Grupo(sucursal=sucursal)
    productos = Products.objects.filter(sucursal=sucursal, status=1).order_by('name')

    if request.method == 'POST':
        nombre = (request.POST.get('nombre') or '').strip()
        if not nombre:
            messages.error(request, 'Escribe un nombre para el grupo.')
        else:
            with transaction.atomic():
                grupo.nombre = nombre[:100]
                grupo.hora_inicio = _leer_hora(request.POST.get('hora_inicio'))
                grupo.dias = ''.join(sorted(d for d in request.POST.getlist('dias') if d in '0123456'))
                grupo.nivel = Levels.objects.filter(id=request.POST.get('nivel') or 0, sucursal=sucursal).first()
                grupo.activo = request.POST.get('activo') == '1'
                grupo.save()
                elegidos = set(request.POST.getlist('productos'))
                for producto in productos:
                    if str(producto.id) in elegidos and producto.grupo_id != grupo.id:
                        producto.grupo = grupo
                        producto.save(update_fields=['grupo'])
                    elif str(producto.id) not in elegidos and producto.grupo_id == grupo.id:
                        producto.grupo = None
                        producto.save(update_fields=['grupo'])
            messages.success(request, f'Grupo "{grupo.nombre}" guardado.')
            return redirect('grupo-editar', grupo_id=grupo.id)

    miembros = (grupo.clientes.filter(status=1).order_by('nombre', 'apellido_paterno') if grupo.pk else [])
    return render(request, 'posApp/grupo_editar.html', {
        'page_title': grupo.nombre or 'Nuevo grupo',
        'grupo': grupo,
        'miembros': miembros,
        'niveles': Levels.objects.filter(sucursal=sucursal),
        'productos': productos,
        'dias_semana': list(enumerate(NOMBRES_DIAS)),
    })


@login_required
def grupos_sin_asignar(request):
    """Alumnos activos sin grupo, para acomodarlos en bloque."""
    sucursal, error = _sucursal_de_request(request)
    if error:
        return error

    if request.method == 'POST':
        grupo = Grupo.objects.filter(id=request.POST.get('grupo') or 0, sucursal=sucursal).first()
        alumnos = list(Clientes.objects.filter(sucursal=sucursal, id__in=request.POST.getlist('cliente')))
        if grupo and alumnos:
            for cliente in alumnos:
                grupo.inscribir(cliente, actualizar_horario=True)
            n = len(alumnos)
            messages.success(request, f'{n} alumno{"s" if n != 1 else ""} agregado{"s" if n != 1 else ""} a "{grupo.nombre}".')
        else:
            messages.error(request, 'Elige al menos un alumno y el grupo al que van.')
        return redirect(request.get_full_path())

    query = (request.GET.get('q') or '').strip()
    clientes = buscar_clientes(
        Clientes.objects.filter(sucursal=sucursal, status=1, grupos__isnull=True), query
    ).order_by('horario', 'nombre')
    pagina = Paginator(clientes, 50).get_page(request.GET.get('page'))
    return render(request, 'posApp/grupos_sin_asignar.html', {
        'page_title': 'Alumnos sin grupo',
        'clientes': pagina,
        'page_obj': pagina,
        'paginas': list(pagina.paginator.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1)),
        'elipsis': pagina.paginator.ELLIPSIS,
        'query_params': urlencode({'q': query}) if query else '',
        'query': query,
        'grupos': Grupo.objects.filter(sucursal=sucursal, activo=True),
    })


@login_required
@require_POST
def grupo_miembro(request):
    """Agrega o quita a un alumno de un grupo (JSON)."""
    sucursal, error = _sucursal_de_request(request)
    if error:
        return JsonResponse({'ok': False, 'msg': 'Tu usuario no tiene una sucursal asignada.'}, status=403)
    grupo = Grupo.objects.filter(id=request.POST.get('grupo') or 0, sucursal=sucursal).first()
    cliente = Clientes.objects.filter(id=request.POST.get('cliente') or 0, sucursal=sucursal).first()
    if not grupo or not cliente:
        return JsonResponse({'ok': False, 'msg': 'No se encontró el grupo o el alumno.'}, status=404)
    if request.POST.get('accion') == 'quitar':
        grupo.clientes.remove(cliente)
    else:
        grupo.clientes.add(cliente)
        # Su horario pasa a ser el del grupo, para que coincida en filtros y reportes
        Clientes.objects.filter(id=cliente.id).update(horario=grupo.nombre)
    return JsonResponse({'ok': True})


@login_required
def buscar_alumnos_json(request):
    """Búsqueda rápida de alumnos por nombre, celular o código, para el pase de lista y el check-in."""
    sucursal, error = _sucursal_de_request(request)
    if error:
        return JsonResponse({'resultados': []}, status=403)
    query = (request.GET.get('q') or '').strip()
    if len(query) < 2:
        return JsonResponse({'resultados': []})
    clientes = (buscar_clientes(Clientes.objects.filter(sucursal=sucursal), query)
                .prefetch_related('grupos').order_by('-status', 'nombre')[:8])
    return JsonResponse({'resultados': [{
        'id': c.id,
        'nombre': f'{c.nombre} {c.apellido_paterno} {c.apellido_materno}'.strip(),
        'iniciales': c.iniciales,
        'grupos': ', '.join(g.nombre for g in c.grupos.all()) or (c.horario or '').strip(),
        'activo': c.status == 1,
    } for c in clientes]})
