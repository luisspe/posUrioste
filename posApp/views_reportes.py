"""
Reporte mensual para gerencia: ingresos, salidas, utilidad, ritmo contra el mes pasado, alumnos que pagaron,
los que no han renovado, productos, formas de pago y a qué hora se cobra.
"""
import calendar
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Min, Q, Sum, TextField
from django.db.models.functions import Coalesce, ExtractHour, ExtractWeekDay, TruncDate, TruncMonth
from django.shortcuts import render
from django.utils import timezone

from posApp.models import Asistencia, Clientes, Salida, Sales, salesItems
from posApp.views_asistencia import _sucursal_de_request

MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
         'noviembre', 'diciembre']
MESES_CORTOS = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
DIAS_SEMANA = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']


def dinero(valor):
    return Decimal(valor or 0).quantize(Decimal('0.00'), rounding=ROUND_HALF_UP)


def _sumar_meses(dia, meses):
    total = dia.year * 12 + dia.month - 1 + meses
    return date(total // 12, total % 12 + 1, 1)


def _fin_de_mes(inicio):
    return inicio.replace(day=calendar.monthrange(inicio.year, inicio.month)[1])


def _cambio(actual, anterior):
    """Porcentaje de cambio contra el periodo anterior; None si antes no hubo nada con qué comparar."""
    if not anterior:
        return None
    return round((float(actual) - float(anterior)) / float(anterior) * 100)


def _pagos_de_clases(ventas):
    """Ventas que pagan clases: traen fecha de próximo pago o un producto con días de vigencia."""
    return ventas.filter(Q(proximo_pago__isnull=False) | Q(salesitems__product_id__dias_vigencia__gt=0)).distinct()


def alumnos_que_pagaron(ventas_suc, inicio, fin):
    """Ids de los alumnos que pagaron clases entre esas fechas."""
    return set(_pagos_de_clases(ventas_suc.filter(date_added__date__range=[inicio, fin]))
               .values_list('client_id', flat=True))


def clasificar_alumnos(ventas_suc, ids, inicio):
    """
    Separa a los alumnos que pagaron en un mes que empieza en `inicio`:
    nuevos (nunca habían pagado clases), siguen (pagaron también el mes anterior) y
    regresaron (ya habían pagado antes, pero no el mes anterior). Regresa {id: tipo} y {id: último pago previo}.
    """
    inicio_ant = _sumar_meses(inicio, -1)
    previos = {
        p['client_id']: timezone.localtime(p['ultimo']).date()
        for p in _pagos_de_clases(ventas_suc.filter(client_id__in=ids, date_added__date__lt=inicio))
        .values('client_id').annotate(ultimo=Max('date_added'))
    }
    tipos = {}
    for cid in ids:
        if cid not in previos:
            tipos[cid] = 'nuevo'
        elif previos[cid] >= inicio_ant:
            tipos[cid] = 'sigue'
        else:
            tipos[cid] = 'regreso'
    return tipos, previos


TIPOS_ALUMNO = {'nuevo': 'Nuevo', 'sigue': 'Sigue', 'regreso': 'Volvió después de faltar'}


def _datos_reporte_mensual(request, sucursal):
    """Todo lo que muestra el reporte mensual; lo usan la página y el Excel."""
    hoy = timezone.localdate()
    try:
        anio, mes = (int(x) for x in request.GET.get('mes', '').split('-'))
        inicio = date(anio, mes, 1)
    except ValueError:
        inicio = hoy.replace(day=1)
    if inicio > hoy:
        inicio = hoy.replace(day=1)
    fin = _fin_de_mes(inicio)
    en_curso = inicio <= hoy <= fin
    corte = hoy if en_curso else fin  # Último día con datos del mes elegido

    # Mes contra el que se compara: el anterior, o el que elija gerencia (ej. agosto contra marzo)
    inicio_previo = _sumar_meses(inicio, -1)
    inicio_ant = _leer_mes(request.GET.get('vs'), inicio_previo)
    if inicio_ant > hoy.replace(day=1) or inicio_ant == inicio:
        inicio_ant = inicio_previo
    vs_elegido = inicio_ant != inicio_previo
    fin_ant = _fin_de_mes(inicio_ant)
    # Para comparar parejo: el otro mes hasta el mismo día del mes
    corte_ant = inicio_ant.replace(day=min(corte.day, fin_ant.day))

    ventas_suc = Sales.objects.filter(sucursal=sucursal)
    salidas_suc = Salida.objects.filter(sucursal=sucursal)
    ventas = ventas_suc.filter(date_added__date__range=[inicio, fin])
    ventas_ant = ventas_suc.filter(date_added__date__range=[inicio_ant, fin_ant])
    salidas = salidas_suc.filter(fecha__range=[inicio, fin])
    salidas_ant = salidas_suc.filter(fecha__range=[inicio_ant, fin_ant])

    # Mientras el mes va en curso, las cifras se comparan contra el mes pasado hasta el mismo día
    ventas_cmp = ventas_ant.filter(date_added__date__lte=corte_ant) if en_curso else ventas_ant
    salidas_cmp = salidas_ant.filter(fecha__lte=corte_ant) if en_curso else salidas_ant

    resumen = ventas.aggregate(total=Sum('grand_total'), numero=Count('id'), clientes=Count('client', distinct=True))
    resumen_ant = ventas_cmp.aggregate(total=Sum('grand_total'), numero=Count('id'))
    ingresos, ingresos_ant = dinero(resumen['total']), dinero(resumen_ant['total'])
    ingresos_mes_ant = dinero(ventas_ant.aggregate(t=Sum('grand_total'))['t'])
    total_salidas = dinero(salidas.aggregate(t=Sum('monto'))['t'])
    total_salidas_ant = dinero(salidas_cmp.aggregate(t=Sum('monto'))['t'])
    utilidad, utilidad_ant = ingresos - total_salidas, ingresos_ant - total_salidas_ant
    numero_ventas = resumen['numero']
    ticket = dinero(ingresos / numero_ventas) if numero_ventas else dinero(0)
    ticket_ant = dinero(ingresos_ant / resumen_ant['numero']) if resumen_ant['numero'] else dinero(0)

    # ---- Ritmo: acumulado día por día contra el mes pasado ----
    por_dia = {d['dia']: float(d['total'] or 0) for d in
               ventas.annotate(dia=TruncDate('date_added')).values('dia').annotate(total=Sum('grand_total'))}
    por_dia_ant = {d['dia']: float(d['total'] or 0) for d in
                   ventas_ant.annotate(dia=TruncDate('date_added')).values('dia').annotate(total=Sum('grand_total'))}
    salidas_dia = {s['fecha']: float(s['total'] or 0) for s in salidas.values('fecha').annotate(total=Sum('monto'))}

    dias, ingresos_dia, salidas_por_dia, acumulado, acumulado_ant = [], [], [], [], []
    suma = suma_ant = 0
    for numero in range(1, fin.day + 1):
        dia = inicio.replace(day=numero)
        dias.append(numero)
        futuro = dia > corte
        ingresos_dia.append(None if futuro else round(por_dia.get(dia, 0), 2))
        salidas_por_dia.append(None if futuro else -round(salidas_dia.get(dia, 0), 2))
        suma += por_dia.get(dia, 0)
        acumulado.append(None if futuro else round(suma, 2))
        if numero <= fin_ant.day:
            suma_ant += por_dia_ant.get(inicio_ant.replace(day=numero), 0)
            acumulado_ant.append(round(suma_ant, 2))
        else:
            acumulado_ant.append(None)

    al_corte = Decimal(str(round(suma, 2)))
    al_corte_ant = dinero(ventas_ant.filter(date_added__date__lte=corte_ant).aggregate(t=Sum('grand_total'))['t'])
    proyeccion = dinero(al_corte / corte.day * fin.day) if en_curso and corte.day < fin.day else None
    mayor_carril = max(al_corte, al_corte_ant, Decimal(1))
    mejor_dia = max(por_dia.items(), key=lambda d: d[1]) if por_dia else None

    # ---- Últimos 12 meses (desde que hay ventas registradas) ----
    primera_venta = ventas_suc.aggregate(p=Min('date_added'))['p']
    primer_mes = timezone.localtime(primera_venta).date().replace(day=1) if primera_venta else inicio
    inicio_doce = max(_sumar_meses(inicio, -11), min(primer_mes, inicio))
    meses_grafica = (inicio.year - inicio_doce.year) * 12 + inicio.month - inicio_doce.month + 1
    meses_ventas = {m['mes'].date() if hasattr(m['mes'], 'date') else m['mes']: float(m['total'] or 0) for m in
                    ventas_suc.filter(date_added__date__range=[inicio_doce, fin])
                    .annotate(mes=TruncMonth('date_added')).values('mes').annotate(total=Sum('grand_total'))}
    meses_salidas = {m['mes']: float(m['total'] or 0) for m in
                     salidas_suc.filter(fecha__range=[inicio_doce, fin])
                     .annotate(mes=TruncMonth('fecha')).values('mes').annotate(total=Sum('monto'))}
    doce = {'etiquetas': [], 'ingresos': [], 'salidas': [], 'utilidad': [], 'urls': []}
    for i in range(meses_grafica):
        m = _sumar_meses(inicio_doce, i)
        ing, sal = meses_ventas.get(m, 0), meses_salidas.get(m, 0)
        doce['etiquetas'].append(f"{MESES_CORTOS[m.month - 1]} {str(m.year)[2:]}")
        doce['ingresos'].append(round(ing, 2))
        doce['salidas'].append(round(sal, 2))
        doce['utilidad'].append(round(ing - sal, 2))
        doce['urls'].append(f"?mes={m:%Y-%m}")

    # ---- Formas de pago ----
    formas = [
        {'forma': f['tipoPago__tipo'] or 'Sin forma de pago', 'total': dinero(f['total']), 'ventas': f['ventas']}
        for f in ventas.values('tipoPago__tipo').annotate(total=Sum('grand_total'), ventas=Count('id')).order_by('-total')
    ]
    for f in formas:
        f['porcentaje'] = round(float(f['total']) / float(ingresos) * 100) if ingresos else 0

    # ---- Productos y categorías ----
    items = salesItems.objects.filter(sale_id__in=ventas.values('id'))
    productos_todos = list(
        items.annotate(nombre=Coalesce('product_id__name', 'product_name', output_field=TextField()))
        .values('nombre', 'product_id__category_id__name')
        .annotate(total=Sum('total'), cantidad=Sum('qty'), ventas=Count('sale_id', distinct=True))
        .order_by('-total')
    )
    mayor_producto = float(productos_todos[0]['total'] or 0) if productos_todos else 0
    for p in productos_todos:
        p['nombre'] = p['nombre'] or 'Producto eliminado'
        p['ancho'] = round(float(p['total'] or 0) / mayor_producto * 100) if mayor_producto else 0
    productos = productos_todos[:10]
    categorias = [
        {'nombre': c['product_id__category_id__name'] or 'Sin categoría', 'total': dinero(c['total'])}
        for c in items.values('product_id__category_id__name').annotate(total=Sum('total')).order_by('-total')
    ]
    total_items = sum(float(c['total']) for c in categorias)
    for c in categorias:
        c['porcentaje'] = round(float(c['total']) / total_items * 100) if total_items else 0

    # ---- Alumnos ----
    clases = _pagos_de_clases(ventas)
    clases_ant = _pagos_de_clases(ventas_ant)
    ingresos_clases = dinero(Sales.objects.filter(id__in=clases.values('id')).aggregate(t=Sum('grand_total'))['t'])
    pagaron = set(clases.values_list('client_id', flat=True))
    pagaron_ant = set(clases_ant.values_list('client_id', flat=True))
    pagaron_cmp = len(set(_pagos_de_clases(ventas_cmp).values_list('client_id', flat=True)))
    nuevos = ventas_suc.values('client_id').annotate(primera=Min('date_added')).filter(
        client_id__in=ventas.values('client_id'), primera__date__range=[inicio, fin]).count()
    tipos_alumno, _ = clasificar_alumnos(ventas_suc, pagaron, inicio)
    composicion = {t: sum(1 for v in tipos_alumno.values() if v == t) for t in TIPOS_ALUMNO}
    alumnos_del_mes = sorted(
        ({'id': c.id, 'nombre': f"{c.nombre} {c.apellido_paterno} {c.apellido_materno}".strip(), 'celular': c.celular,
          'horario': c.horario, 'tipo': TIPOS_ALUMNO[tipos_alumno[c.id]]}
         for c in Clientes.objects.filter(id__in=pagaron)),
        key=lambda a: (list(TIPOS_ALUMNO.values()).index(a['tipo']), a['nombre'].lower()))

    pendientes_ids = pagaron_ant - pagaron
    ultimo_pago = {
        p['client_id']: p for p in
        _pagos_de_clases(ventas_suc.filter(client_id__in=pendientes_ids))
        .values('client_id', 'client__nombre', 'client__apellido_paterno', 'client__apellido_materno', 'client__celular')
        .annotate(ultimo=Max('date_added'), proximo=Max('proximo_pago'))
    }
    sin_renovar = sorted(
        ({'id': cid, 'nombre': f"{p['client__nombre']} {p['client__apellido_paterno']}".strip(),
          'completo': f"{p['client__nombre']} {p['client__apellido_paterno']} {p['client__apellido_materno']}".strip(),
          'celular': p['client__celular'], 'ultimo': timezone.localtime(p['ultimo']).date(), 'proximo': p['proximo']}
         for cid, p in ultimo_pago.items()),
        key=lambda a: a['proximo'] or a['ultimo'])
    # En el mes en curso, los que todavía tienen días pagados no cuentan como pendientes.
    # Sin fecha de próximo pago escrita se toma un mes desde su último pago
    if en_curso:
        for a in sin_renovar:
            a['vence'] = a['proximo'] or a['ultimo'] + timedelta(days=30)
        sin_renovar = [a for a in sin_renovar if a['vence'] < hoy]
    renovacion = round(len(pagaron_ant & pagaron) / len(pagaron_ant) * 100) if pagaron_ant else None

    asistencias = Asistencia.objects.filter(sucursal=sucursal, fecha__range=[inicio, fin], estado__in=['P', 'R'])
    asistencia = asistencias.aggregate(registros=Count('id'), alumnos=Count('cliente', distinct=True))

    # ---- A qué hora se cobra: día de la semana × hora ----
    celdas = {}
    for c in ventas.annotate(dia=ExtractWeekDay('date_added'), hora=ExtractHour('date_added')) \
            .values('dia', 'hora').annotate(total=Sum('grand_total'), numero=Count('id')):
        # ExtractWeekDay: domingo = 1 ... sábado = 7; lo pasamos a lunes = 0
        celdas[((c['dia'] + 5) % 7, c['hora'])] = (float(c['total'] or 0), c['numero'])
    horas = sorted({h for _, h in celdas})
    if horas:
        horas = list(range(min(horas), max(horas) + 1))
    mayor_celda = max((v[0] for v in celdas.values()), default=0)
    mapa = [
        {'dia': DIAS_SEMANA[d], 'celdas': [
            {'hora': h, 'total': celdas.get((d, h), (0, 0))[0], 'numero': celdas.get((d, h), (0, 0))[1],
             'nivel': min(4, int(celdas[(d, h)][0] / mayor_celda * 4) + 1) if (d, h) in celdas and mayor_celda else 0}
            for h in horas]}
        for d in range(7) if any((d, h) in celdas for h in horas)
    ]

    # ---- Salidas ----
    salidas_conceptos = [
        {'concepto': s['concepto'] or 'Sin concepto', 'total': dinero(s['total']), 'numero': s['numero']}
        for s in salidas.values('concepto').annotate(total=Sum('monto'), numero=Count('id')).order_by('-total')
    ]
    mayor_salida = float(salidas_conceptos[0]['total']) if salidas_conceptos else 0
    for s in salidas_conceptos:
        s['ancho'] = round(float(s['total']) / mayor_salida * 100) if mayor_salida else 0

    cajeros = [
        {'nombre': c['usuario__first_name'] or c['usuario__username'] or 'Sin usuario',
         'total': dinero(c['total']), 'ventas': c['ventas']}
        for c in ventas.values('usuario__first_name', 'usuario__username')
        .annotate(total=Sum('grand_total'), ventas=Count('id')).order_by('-total')
    ]

    opciones_mes = []
    m = hoy.replace(day=1)
    while m >= min(primer_mes, inicio) and len(opciones_mes) < 36:
        opciones_mes.append({'valor': f"{m:%Y-%m}", 'nombre': f"{MESES[m.month - 1].capitalize()} {m.year}"})
        m = _sumar_meses(m, -1)

    siguiente = _sumar_meses(inicio, 1)
    # Si el mes de comparación es de otro año, se dice el año para no confundir
    nombre_ant = MESES[inicio_ant.month - 1] + (f" {inicio_ant.year}" if inicio_ant.year != inicio.year else '')
    context = {
        'page_title': 'Reporte mensual',
        'sucursal': sucursal,
        'mes_nombre': MESES[inicio.month - 1],
        'mes_ant_nombre': nombre_ant,
        'mes_previo_nombre': MESES[inicio_previo.month - 1],
        'vs_valor': f"{inicio_ant:%Y-%m}" if vs_elegido else '',
        'vs_elegido': vs_elegido,
        'inicio': inicio,
        'fin': fin,
        'corte': corte,
        'corte_ant': corte_ant,
        'en_curso': en_curso,
        'mes_valor': f"{inicio:%Y-%m}",
        'opciones_mes': opciones_mes,
        'mes_anterior_url': f"?mes={inicio_previo:%Y-%m}" + (f"&vs={inicio_ant:%Y-%m}" if vs_elegido else ''),
        'mes_siguiente_url': (f"?mes={siguiente:%Y-%m}" + (f"&vs={inicio_ant:%Y-%m}" if vs_elegido else ''))
                             if siguiente <= hoy else None,

        'ingresos': ingresos,
        'total_salidas': total_salidas,
        'utilidad': utilidad,
        'utilidad_abs': abs(utilidad),
        'margen': round(float(utilidad) / float(ingresos) * 100) if ingresos else None,
        'numero_ventas': numero_ventas,
        'ticket': ticket,
        'cambios': {
            'ingresos': _cambio(ingresos, ingresos_ant),
            'salidas': _cambio(total_salidas, total_salidas_ant),
            'utilidad': _cambio(utilidad, utilidad_ant) if utilidad_ant > 0 else None,
            'ticket': _cambio(ticket, ticket_ant),
            'alumnos': _cambio(len(pagaron), pagaron_cmp),
        },
        'ingresos_ant': ingresos_mes_ant,
        'comparables': {'ingresos': ingresos_ant, 'salidas': total_salidas_ant, 'utilidad': utilidad_ant,
                        'ticket': ticket_ant, 'ventas': resumen_ant['numero'], 'alumnos': pagaron_cmp},
        'contra': f"{nombre_ant} al día {corte_ant.day}" if en_curso else nombre_ant,

        'al_corte': al_corte,
        'al_corte_ant': al_corte_ant,
        'diferencia_ritmo': al_corte - al_corte_ant,
        'diferencia_ritmo_abs': abs(al_corte - al_corte_ant),
        'cambio_ritmo': _cambio(al_corte, al_corte_ant),
        'carril': round(float(al_corte) / float(mayor_carril) * 100),
        'carril_ant': round(float(al_corte_ant) / float(mayor_carril) * 100),
        'proyeccion': proyeccion,
        'mejor_dia': {'fecha': mejor_dia[0], 'total': dinero(mejor_dia[1])} if mejor_dia else None,
        'dias_con_ventas': len(por_dia),

        'grafica': {
            'dias': dias, 'ingresos': ingresos_dia, 'salidas': salidas_por_dia,
            'acumulado': acumulado, 'acumulado_ant': acumulado_ant,
            'mes': MESES[inicio.month - 1], 'mes_ant': nombre_ant,
            'doce': doce,
            'formas': {'etiquetas': [f['forma'] for f in formas], 'valores': [float(f['total']) for f in formas]},
        },
        'formas': formas,
        'productos': productos,
        'productos_todos': productos_todos,
        'ventas_mes': ventas,
        'categorias': categorias,

        'alumnos_pagaron': len(pagaron),
        'alumnos_pagaron_ant': len(pagaron_ant),
        'alumnos_nuevos': nuevos,
        'composicion': composicion,
        'composicion_pct': {t: round(n * 100 / len(pagaron)) if pagaron else 0 for t, n in composicion.items()},
        'alumnos_del_mes': alumnos_del_mes,
        'nuevos_lista': [a for a in alumnos_del_mes if a['tipo'] == 'Nuevo'],
        'ingresos_clases': ingresos_clases,
        'porcentaje_clases': round(float(ingresos_clases) / float(ingresos) * 100) if ingresos else 0,
        'clientes_distintos': resumen['clientes'],
        'renovacion': renovacion,
        'sin_renovar': sin_renovar[:12],
        'sin_renovar_total': len(sin_renovar),
        'sin_renovar_todos': sin_renovar,
        'asistencia': asistencia,

        'mapa': mapa,
        'horas': horas,
        'salidas': salidas.order_by('-fecha', '-id'),
        'salidas_conceptos': salidas_conceptos,
        'cajeros': cajeros,
    }
    return context


@login_required
def reporte_mensual(request):
    sucursal, error = _sucursal_de_request(request)
    if error:
        return error
    return render(request, 'posApp/reporte_mensual.html', _datos_reporte_mensual(request, sucursal))


# ---------------------------------------------------------------------------
# Excel del reporte mensual
# ---------------------------------------------------------------------------
FOSA, CARRIL, AZULEJO, LINEA, ROJO, VERDE = '0B1F4D', '1668C7', 'EEF4F9', 'D8E2EE', 'CF3426', '12875A'
PESOS = '"$"#,##0.00;[Red]-"$"#,##0.00'
PESOS_ENTEROS = '"$"#,##0;[Red]-"$"#,##0'
PORCENTAJE = '0%;[Red]-0%'
FECHA = 'dd/mm/yyyy'


class _Hoja:
    """Ayuda a escribir hojas con el mismo formato: título, encabezados azules, totales y anchos."""

    def __init__(self, libro, titulo, encabezado, subtitulo, primera=False):
        from openpyxl.styles import Font
        self.ws = libro.active if primera else libro.create_sheet()
        self.ws.title = titulo
        self.ws.sheet_view.showGridLines = False
        self.ws['A1'] = encabezado
        self.ws['A1'].font = Font(name='Calibri', size=18, bold=True, color=FOSA)
        self.ws['A2'] = subtitulo
        self.ws['A2'].font = Font(name='Calibri', size=11, color='5B6B82')
        self.ws.row_dimensions[1].height = 28
        self.fila = 4

    def seccion(self, texto, columna=1):
        from openpyxl.styles import Font
        celda = self.ws.cell(row=self.fila, column=columna, value=texto)
        celda.font = Font(size=13, bold=True, color=FOSA)
        self.fila += 1

    def tabla(self, columnas, filas, formatos=None, total=None, columna=1, filtro=False):
        """Escribe encabezados y filas; regresa (fila_encabezado, fila_ultima)."""
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        ws, formatos = self.ws, formatos or {}
        borde = Border(bottom=Side(style='thin', color=LINEA))
        inicio = self.fila
        for i, nombre in enumerate(columnas):
            c = ws.cell(row=inicio, column=columna + i, value=nombre)
            c.font = Font(bold=True, color='FFFFFF')
            c.fill = PatternFill('solid', fgColor=FOSA)
            c.alignment = Alignment(vertical='center', horizontal='left' if i == 0 else 'center', wrap_text=True)
        ws.row_dimensions[inicio].height = 22
        for n, fila in enumerate(filas, start=1):
            for i, valor in enumerate(fila):
                c = ws.cell(row=inicio + n, column=columna + i, value=_valor_excel(valor))
                c.border = borde
                if i in formatos:
                    c.number_format = formatos[i]
                if n % 2 == 0:
                    c.fill = PatternFill('solid', fgColor=AZULEJO)
        ultima = inicio + len(filas)
        if total and filas:
            ultima += 1
            for i, valor in enumerate(total):
                c = ws.cell(row=ultima, column=columna + i, value=valor)
                c.font = Font(bold=True, color=FOSA)
                c.border = Border(top=Side(style='medium', color=FOSA))
                if i in formatos:
                    c.number_format = formatos[i]
        if filtro and filas:
            from openpyxl.utils import get_column_letter
            ws.auto_filter.ref = f"{get_column_letter(columna)}{inicio}:{get_column_letter(columna + len(columnas) - 1)}{inicio + len(filas)}"
        self.fila = ultima + 2
        return inicio, inicio + len(filas)

    def anchos(self, *anchos):
        from openpyxl.utils import get_column_letter
        for i, ancho in enumerate(anchos, start=1):
            self.ws.column_dimensions[get_column_letter(i)].width = ancho


def _valor_excel(valor):
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


def _grafica_barras(ws, titulo, categorias, series, ancla, apiladas=False, alto=8, ancho=18, colores=None):
    from openpyxl.chart import BarChart, Reference
    g = BarChart()
    g.title, g.style, g.height, g.width = titulo, 10, alto, ancho
    g.y_axis.numFmt = PESOS_ENTEROS
    g.y_axis.majorGridlines = None
    if apiladas:
        g.grouping, g.overlap = 'stacked', 100
    for (col, fila_ini, fila_fin) in series:
        g.add_data(Reference(ws, min_col=col, min_row=fila_ini, max_row=fila_fin), titles_from_data=True)
    g.set_categories(Reference(ws, min_col=categorias[0], min_row=categorias[1], max_row=categorias[2]))
    for serie, color in zip(g.series, colores or [CARRIL, ROJO, FOSA]):
        serie.graphicalProperties.solidFill = color
        serie.graphicalProperties.line.solidFill = color
    ws.add_chart(g, ancla)
    return g


@login_required
def reporte_mensual_excel(request):
    from openpyxl import Workbook
    from openpyxl.chart import LineChart, PieChart, Reference
    from openpyxl.chart.label import DataLabelList
    from openpyxl.formatting.rule import ColorScaleRule
    from openpyxl.styles import Alignment, Font, PatternFill
    from django.http import HttpResponse

    sucursal, error = _sucursal_de_request(request)
    if error:
        return error
    d = _datos_reporte_mensual(request, sucursal)
    mes, mes_ant = d['mes_nombre'], d['mes_ant_nombre']
    anio = d['inicio'].year
    encabezado = f"Reporte de {mes} {anio}"
    subtitulo = (f"{sucursal.nombre}. Datos al {d['corte'].day} de {mes}" if d['en_curso'] else sucursal.nombre)
    contra = d['contra']
    libro = Workbook()

    # ---- Resumen ----
    h = _Hoja(libro, 'Resumen', encabezado, subtitulo, primera=True)
    h.seccion('Cifras del mes')
    comp = d['comparables']

    def cambio(actual, anterior):
        return (float(actual) - float(anterior)) / float(anterior) if anterior else None

    filas = [
        ('Ingresos', d['ingresos'], comp['ingresos'], cambio(d['ingresos'], comp['ingresos'])),
        ('Salidas', d['total_salidas'], comp['salidas'], cambio(d['total_salidas'], comp['salidas'])),
        ('Utilidad', d['utilidad'], comp['utilidad'], cambio(d['utilidad'], comp['utilidad']) if comp['utilidad'] > 0 else None),
        ('Ticket promedio', d['ticket'], comp['ticket'], cambio(d['ticket'], comp['ticket'])),
        ('Número de ventas', d['numero_ventas'], comp['ventas'], cambio(d['numero_ventas'], comp['ventas'])),
        ('Alumnos que pagaron clases', d['alumnos_pagaron'], comp['alumnos'], cambio(d['alumnos_pagaron'], comp['alumnos'])),
    ]
    ini, fin_t = h.tabla(['Concepto', mes.capitalize(), contra.capitalize(), 'Cambio'], filas,
                         formatos={1: PESOS, 2: PESOS, 3: PORCENTAJE})
    for fila in (ini + 5, ini + 6):  # Conteos, no dinero
        for col in (2, 3):
            h.ws.cell(row=fila, column=col).number_format = '#,##0'
    h.ws.cell(row=ini + 3, column=1).font = Font(bold=True, color=FOSA)
    h.ws.cell(row=ini + 3, column=2).font = Font(bold=True, color=VERDE if d['utilidad'] >= 0 else ROJO)

    h.seccion(f"Ritmo contra {mes_ant}")
    ritmo = [
        (f"Llevas al día {d['corte'].day}", d['al_corte']),
        (f"{mes_ant.capitalize()} al día {d['corte_ant'].day}", d['al_corte_ant']),
        ('Diferencia', d['diferencia_ritmo']),
    ]
    if d['proyeccion']:
        ritmo.append(('Si sigue este ritmo, cierras en', d['proyeccion']))
    ritmo.append((f"{mes_ant.capitalize()} completo", d['ingresos_ant']))
    if d['mejor_dia']:
        ritmo.append((f"Mejor día ({d['mejor_dia']['fecha']:%d/%m})", d['mejor_dia']['total']))
    ritmo.append(('Días con ventas', f"{d['dias_con_ventas']} de {d['corte'].day}"))
    _, ultima_ritmo = h.tabla(['Concepto', 'Monto'], ritmo, formatos={1: PESOS})
    h.ws.cell(row=ultima_ritmo, column=2).alignment = Alignment(horizontal='right')

    h.seccion('Alumnos')
    inicio_alumnos, fin_alumnos = h.tabla(['Concepto', 'Valor'], [
        ('Pagaron clases', d['alumnos_pagaron']),
        (f"Pagaron clases en {mes_ant}", d['alumnos_pagaron_ant']),
        ('Nuevos (primera vez que pagan clases)', d['composicion']['nuevo']),
        (f"Siguen (también pagaron en {mes_ant})", d['composicion']['sigue']),
        ('Volvieron después de faltar (ya eran alumnos, no pagaron el mes anterior)', d['composicion']['regreso']),
        (f"Renovaron (de los que pagaron en {mes_ant})", d['renovacion'] / 100 if d['renovacion'] is not None else 'Sin datos'),
        ('Pagaron y ya se les venció', d['sin_renovar_total']),
        ('Ingreso por clases', d['ingresos_clases']),
        ('Clases como parte de los ingresos', d['porcentaje_clases'] / 100),
        ('Asistencias registradas', d['asistencia']['registros']),
        ('Alumnos distintos que asistieron', d['asistencia']['alumnos']),
        ('Clientes distintos que compraron', d['clientes_distintos']),
    ])
    for fila in range(inicio_alumnos + 1, fin_alumnos + 1):
        etiqueta = h.ws.cell(row=fila, column=1).value or ''
        celda = h.ws.cell(row=fila, column=2)
        if 'Ingreso' in etiqueta:
            celda.number_format = PESOS
        elif 'Renovaron' in etiqueta or 'parte de' in etiqueta:
            celda.number_format = '0%'
    h.anchos(52, 18, 22, 12)

    # ---- Día por día ----
    h = _Hoja(libro, 'Día por día', f"{encabezado}: día por día", subtitulo)
    g = d['grafica']
    filas = []
    for i, numero in enumerate(g['dias']):
        if g['ingresos'][i] is None:
            continue
        fecha = d['inicio'].replace(day=numero)
        ingreso, salida = g['ingresos'][i], -g['salidas'][i]
        filas.append((fecha, DIAS_SEMANA[fecha.weekday()], ingreso, salida, ingreso - salida,
                      g['acumulado'][i], g['acumulado_ant'][i]))
    ini, ult = h.tabla(['Fecha', 'Día', 'Ingresos', 'Salidas', 'Neto', 'Acumulado', f"Acumulado {mes_ant}"], filas,
                       formatos={0: FECHA, 2: PESOS, 3: PESOS, 4: PESOS, 5: PESOS, 6: PESOS},
                       total=['Total', '', sum(f[2] for f in filas), sum(f[3] for f in filas),
                              sum(f[4] for f in filas)])
    h.anchos(13, 8, 15, 15, 15, 16, 20)
    h.ws.freeze_panes = f"A{ini + 1}"
    if filas:
        _grafica_barras(h.ws, 'Ingresos y salidas por día', (1, ini + 1, ult), [(3, ini, ult), (4, ini, ult)], 'I4',
                        ancho=22)
        linea = LineChart()
        linea.title, linea.style, linea.height, linea.width = f"Acumulado contra {mes_ant}", 12, 8, 22
        linea.y_axis.numFmt = PESOS_ENTEROS
        linea.add_data(Reference(h.ws, min_col=6, max_col=7, min_row=ini, max_row=ult), titles_from_data=True)
        linea.set_categories(Reference(h.ws, min_col=1, min_row=ini + 1, max_row=ult))
        for serie, color in zip(linea.series, [CARRIL, '94A3B8']):
            serie.graphicalProperties.line.solidFill = color
            serie.graphicalProperties.line.width = 28000
            serie.smooth = False
        h.ws.add_chart(linea, 'I22')

    # ---- Formas de pago ----
    h = _Hoja(libro, 'Formas de pago', f"{encabezado}: cómo pagaron", subtitulo)
    filas = [(f['forma'], f['ventas'], f['total'], f['porcentaje'] / 100) for f in d['formas']]
    ini, ult = h.tabla(['Forma de pago', 'Ventas', 'Total', '% del mes'], filas, formatos={2: PESOS, 3: '0%'},
                       total=['Total', sum(f[1] for f in filas), float(d['ingresos']), 1 if filas else 0])
    h.anchos(26, 10, 16, 12)
    if filas:
        pastel = PieChart()
        pastel.title, pastel.height, pastel.width = 'Cómo pagaron', 9, 12
        pastel.add_data(Reference(h.ws, min_col=3, min_row=ini, max_row=ult), titles_from_data=True)
        pastel.set_categories(Reference(h.ws, min_col=1, min_row=ini + 1, max_row=ult))
        pastel.dataLabels = DataLabelList()
        pastel.dataLabels.showPercent = True
        h.ws.add_chart(pastel, 'F4')

    # ---- Productos ----
    h = _Hoja(libro, 'Productos', f"{encabezado}: productos vendidos", subtitulo)
    total_productos = sum(float(p['total'] or 0) for p in d['productos_todos'])
    filas = [(p['nombre'], p['product_id__category_id__name'] or 'Sin categoría', p['cantidad'], p['ventas'],
              p['total'], float(p['total'] or 0) / total_productos if total_productos else 0)
             for p in d['productos_todos']]
    ini, ult = h.tabla(['Producto', 'Categoría', 'Cantidad', 'Ventas', 'Total', '% del total'], filas,
                       formatos={2: '#,##0', 3: '#,##0', 4: PESOS, 5: '0.0%'},
                       total=['Total', '', sum(f[2] or 0 for f in filas), '', total_productos, 1 if filas else 0],
                       filtro=True)
    h.ws.freeze_panes = f"A{ini + 1}"
    h.anchos(46, 26, 13, 11, 16, 14)
    if filas:
        _grafica_barras(h.ws, 'Lo que más se vendió', (1, ini + 1, min(ult, ini + 10)),
                        [(5, ini, min(ult, ini + 10))], 'H4', alto=10, ancho=20)

    # ---- Categorías y cajeros ----
    h = _Hoja(libro, 'Categorías y cajeros', f"{encabezado}: categorías y cajeros", subtitulo)
    h.seccion('Por categoría')
    filas = [(c['nombre'], c['total'], c['porcentaje'] / 100) for c in d['categorias']]
    ini, ult = h.tabla(['Categoría', 'Total', '%'], filas, formatos={1: PESOS, 2: '0%'},
                       total=['Total', sum(float(f[1]) for f in filas), 1 if filas else 0])
    if filas:
        pastel = PieChart()
        pastel.title, pastel.height, pastel.width = 'Por categoría', 8, 11
        pastel.add_data(Reference(h.ws, min_col=2, min_row=ini, max_row=ult), titles_from_data=True)
        pastel.set_categories(Reference(h.ws, min_col=1, min_row=ini + 1, max_row=ult))
        pastel.dataLabels = DataLabelList()
        pastel.dataLabels.showPercent = True
        h.ws.add_chart(pastel, 'F4')
    h.seccion('Quién cobró')
    filas = [(c['nombre'], c['ventas'], c['total']) for c in d['cajeros']]
    h.tabla(['Cajero', 'Ventas', 'Total'], filas, formatos={2: PESOS},
            total=['Total', sum(f[1] for f in filas), sum(float(f[2]) for f in filas)])
    h.anchos(30, 16, 14)

    # ---- Alumnos del mes ----
    h = _Hoja(libro, 'Alumnos del mes', f"{encabezado}: alumnos que pagaron clases", subtitulo)
    filas = [(a['nombre'], a['tipo'], a['celular'], a['horario']) for a in d['alumnos_del_mes']]
    ini, _ = h.tabla(['Alumno', 'Tipo', 'Celular', 'Horario'], filas, filtro=True)
    h.ws.freeze_panes = f"A{ini + 1}"
    h.anchos(42, 12, 16, 34)

    # ---- Por cobrar ----
    h = _Hoja(libro, 'Por cobrar', f"{encabezado}: pagaron en {mes_ant} y no han renovado", subtitulo)
    hoy = timezone.localdate()
    filas = []
    for a in d['sin_renovar_todos']:
        vence = a.get('vence') or a['proximo']
        filas.append((a['completo'], a['celular'], a['ultimo'], vence, (hoy - vence).days if vence else None))
    ini, _ = h.tabla(['Alumno', 'Celular', 'Último pago', 'Venció', 'Días vencido'], filas,
                     formatos={2: FECHA, 3: FECHA, 4: '#,##0'}, filtro=True)
    h.ws.freeze_panes = f"A{ini + 1}"
    h.anchos(42, 16, 16, 15, 16)
    if not filas:
        h.ws.cell(row=ini + 1, column=1, value=f"Todos los que pagaron en {mes_ant} ya renovaron.")

    # ---- Salidas ----
    h = _Hoja(libro, 'Salidas', f"{encabezado}: salidas", subtitulo)
    salidas = list(d['salidas'])
    filas = [(s.fecha, s.concepto or 'Sin concepto', s.comentario or '', s.monto) for s in salidas]
    ini, _ = h.tabla(['Fecha', 'Concepto', 'Comentario', 'Monto'], filas, formatos={0: FECHA, 3: PESOS},
                     total=['Total', '', '', float(d['total_salidas'])], filtro=True)
    if not filas:
        h.ws.cell(row=ini + 1, column=1, value=f"No hay salidas registradas en {mes}.")
    else:
        h.fila = 4
        h.seccion('Por concepto', columna=6)
        h.tabla(['Concepto', 'Veces', 'Total'], [(s['concepto'], s['numero'], s['total']) for s in d['salidas_conceptos']],
                formatos={2: PESOS}, columna=6)
    h.anchos(13, 32, 42, 15, 4, 30, 8, 15)

    # ---- Mes por mes ----
    h = _Hoja(libro, 'Mes por mes', f"{encabezado}: mes por mes", sucursal.nombre)
    doce = g['doce']
    filas = list(zip(doce['etiquetas'], doce['ingresos'], doce['salidas'], doce['utilidad']))
    ini, ult = h.tabla(['Mes', 'Ingresos', 'Salidas', 'Utilidad'], filas, formatos={1: PESOS, 2: PESOS, 3: PESOS},
                       total=['Total', sum(f[1] for f in filas), sum(f[2] for f in filas), sum(f[3] for f in filas)])
    h.anchos(12, 16, 16, 16)
    _grafica_barras(h.ws, 'Ingresos, salidas y utilidad', (1, ini + 1, ult),
                    [(2, ini, ult), (3, ini, ult), (4, ini, ult)], 'F4', ancho=20, alto=9)

    # ---- Cuándo se cobra ----
    h = _Hoja(libro, 'Cuándo se cobra', f"{encabezado}: cuándo se cobra", 'Total cobrado por día de la semana y hora')
    if d['mapa']:
        filas = [[fila['dia']] + [c['total'] or None for c in fila['celdas']] for fila in d['mapa']]
        horas = [f"{hora}:00" for hora in d['horas']]
        ini, ult = h.tabla(['Día'] + horas, filas, formatos={i: PESOS_ENTEROS for i in range(1, len(horas) + 1)})
        from openpyxl.utils import get_column_letter
        rango = f"B{ini + 1}:{get_column_letter(len(horas) + 1)}{ult}"
        h.ws.conditional_formatting.add(rango, ColorScaleRule(start_type='min', start_color='EEF4F9',
                                                              mid_type='percentile', mid_value=50, mid_color='7FCDE3',
                                                              end_type='max', end_color=CARRIL))
        h.anchos(8, *([10] * len(horas)))
    else:
        h.ws['A4'] = 'Sin ventas este mes.'

    # ---- Todas las ventas ----
    h = _Hoja(libro, 'Ventas', f"{encabezado}: todas las ventas", subtitulo)
    filas = []
    for v in d['ventas_mes'].select_related('client', 'tipoPago', 'usuario').prefetch_related(
            'salesitems_set__product_id').order_by('date_added'):
        momento = timezone.localtime(v.date_added)
        productos = ', '.join(
            (f"{int(i.qty)} × " if i.qty and i.qty != 1 else '') +
            (i.product_name or (i.product_id.name if i.product_id else 'Producto eliminado'))
            for i in v.salesitems_set.all())
        cliente = f"{v.client.nombre} {v.client.apellido_paterno} {v.client.apellido_materno}".strip() if v.client else ''
        filas.append((momento.date(), momento.strftime('%H:%M'), v.code, cliente, productos,
                      v.tipoPago.tipo if v.tipoPago else '', v.grand_total, v.proximo_pago,
                      (v.usuario.first_name or v.usuario.username) if v.usuario else '', v.comentario or ''))
    ini, _ = h.tabla(['Fecha', 'Hora', 'Folio', 'Cliente', 'Productos', 'Forma de pago', 'Total', 'Próximo pago',
                      'Cajero', 'Comentario'], filas, formatos={0: FECHA, 6: PESOS, 7: FECHA},
                     total=['Total', '', f"{len(filas)} ventas", '', '', '', float(d['ingresos'])], filtro=True)
    h.ws.freeze_panes = f"A{ini + 1}"
    h.anchos(13, 9, 16, 36, 50, 18, 13, 16, 14, 50)
    for fila in h.ws.iter_rows(min_row=ini + 1, min_col=5, max_col=5):
        for c in fila:
            c.alignment = Alignment(wrap_text=False)

    for ws in libro.worksheets:
        ws.sheet_properties.tabColor = CARRIL if ws.title != 'Por cobrar' else ROJO
        ws.page_setup.orientation = 'landscape'
        ws.page_setup.fitToWidth = 1
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToHeight = 0

    respuesta = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    nombre = f"reporte_{d['mes_valor']}_{sucursal.nombre}".replace(' ', '_')
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre}.xlsx"'
    libro.save(respuesta)
    return respuesta


# ---------------------------------------------------------------------------
# Comparar dos meses: cuántos alumnos de un mes regresaron en otro, y cómo cambiaron ventas y tickets
# ---------------------------------------------------------------------------
def _leer_mes(texto, por_defecto):
    try:
        anio, mes = (int(x) for x in (texto or '').split('-'))
        return date(anio, mes, 1)
    except ValueError:
        return por_defecto


def _cifras_mes(ventas_suc, inicio, hoy):
    fin = min(_fin_de_mes(inicio), hoy)
    ventas = ventas_suc.filter(date_added__date__range=[inicio, fin])
    r = ventas.aggregate(total=Sum('grand_total'), numero=Count('id'))
    ingresos = dinero(r['total'])
    clases = Sales.objects.filter(id__in=_pagos_de_clases(ventas).values('id'))
    return {
        'inicio': inicio,
        'nombre': f"{MESES[inicio.month - 1]} {inicio.year}",
        'en_curso': inicio <= hoy <= _fin_de_mes(inicio),
        'corte': fin,
        'ingresos': ingresos,
        'ventas': r['numero'],
        'ticket': dinero(ingresos / r['numero']) if r['numero'] else dinero(0),
        'ingresos_clases': dinero(clases.aggregate(t=Sum('grand_total'))['t']),
        'ids': alumnos_que_pagaron(ventas_suc, inicio, fin),
    }


@login_required
def comparar_meses(request):
    sucursal, error = _sucursal_de_request(request)
    if error:
        return error
    hoy = timezone.localdate()
    ventas_suc = Sales.objects.filter(sucursal=sucursal)

    mes_b = min(_leer_mes(request.GET.get('b'), hoy.replace(day=1)), hoy.replace(day=1))
    mes_a = min(_leer_mes(request.GET.get('a'), _sumar_meses(mes_b, -1)), hoy.replace(day=1))
    a, b = _cifras_mes(ventas_suc, mes_a, hoy), _cifras_mes(ventas_suc, mes_b, hoy)

    volvieron = a['ids'] & b['ids']
    no_volvieron = a['ids'] - b['ids']
    llegaron = b['ids'] - a['ids']
    # De los que pagaron en B sin haber pagado en A: ¿es su primera vez o ya eran alumnos de antes?
    previos = {
        p['client_id'] for p in
        _pagos_de_clases(ventas_suc.filter(client_id__in=llegaron, date_added__date__lt=mes_b)).values('client_id')
    }
    nuevos = llegaron - previos
    de_antes = llegaron - nuevos

    ultimo_pago = {
        p['client_id']: p for p in
        _pagos_de_clases(ventas_suc.filter(client_id__in=a['ids'] | b['ids']))
        .values('client_id').annotate(ultimo=Max('date_added'), proximo=Max('proximo_pago'))
    }
    clientes = {c.id: c for c in Clientes.objects.filter(id__in=a['ids'] | b['ids'])}

    def lista(ids):
        filas = []
        for cid in ids:
            c, pago = clientes.get(cid), ultimo_pago.get(cid) or {}
            if not c:
                continue
            filas.append({'id': cid, 'nombre': f"{c.nombre} {c.apellido_paterno} {c.apellido_materno}".strip(),
                          'horario': c.horario, 'celular': c.celular,
                          'ultimo': timezone.localtime(pago['ultimo']).date() if pago.get('ultimo') else None})
        return sorted(filas, key=lambda f: f['nombre'].lower())

    def cambio(campo):
        return _cambio(b[campo], a[campo])

    primer = ventas_suc.aggregate(p=Min('date_added'))['p']
    primer = timezone.localtime(primer).date().replace(day=1) if primer else hoy.replace(day=1)
    opciones, m = [], hoy.replace(day=1)
    while m >= primer and len(opciones) < 60:
        opciones.append({'valor': f"{m:%Y-%m}", 'nombre': f"{MESES[m.month - 1].capitalize()} {m.year}"})
        m = _sumar_meses(m, -1)
    este_mes = hoy.replace(day=1)
    atajos = [
        ('Este mes vs el pasado', _sumar_meses(este_mes, -1), este_mes),
        ('Mes pasado vs antepasado', _sumar_meses(este_mes, -2), _sumar_meses(este_mes, -1)),
        ('Este mes vs hace un año', _sumar_meses(este_mes, -12), este_mes),
    ]

    total_a = len(a['ids'])
    return render(request, 'posApp/comparar_meses.html', {
        'page_title': 'Comparar meses',
        'sucursal': sucursal,
        'a': a, 'b': b,
        'a_valor': f"{mes_a:%Y-%m}", 'b_valor': f"{mes_b:%Y-%m}",
        'opciones': opciones,
        'atajos': [{'nombre': n, 'url': f"?a={x:%Y-%m}&b={y:%Y-%m}", 'activo': (x, y) == (mes_a, mes_b)}
                   for n, x, y in atajos],
        'cambios': {'alumnos': _cambio(len(b['ids']), total_a), 'ingresos': cambio('ingresos'),
                    'ventas': cambio('ventas'), 'ticket': cambio('ticket'), 'ingresos_clases': cambio('ingresos_clases')},
        'retencion': round(len(volvieron) * 100 / total_a) if total_a else None,
        'volvieron': lista(volvieron),
        'no_volvieron': lista(no_volvieron),
        'nuevos': lista(nuevos),
        'de_antes': lista(de_antes),
        'barra': {
            'volvieron': len(volvieron), 'nuevos': len(nuevos), 'de_antes': len(de_antes),
        },
    })
