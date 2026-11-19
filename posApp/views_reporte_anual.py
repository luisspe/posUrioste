"""
Reporte anual para gerencia: cómo va el año contra el anterior, mes por mes, alumnos por mes, lo más vendido,
formas de pago y el histórico de todos los años.
"""
import calendar
from datetime import date

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Min, Sum, TextField
from django.db.models.functions import Coalesce, ExtractMonth, ExtractYear
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from posApp.models import Salida, Sales, salesItems
from posApp.views_asistencia import _sucursal_de_request
from posApp.views_reportes import (MESES, MESES_CORTOS, PESOS, PESOS_ENTEROS, PORCENTAJE, _cambio, _grafica_barras,
                                   _Hoja, _pagos_de_clases, dinero)


def _por_mes(qs, campo_fecha, campo_suma):
    """{mes: total} de un queryset, agrupado por mes."""
    return {f['mes']: float(f['total'] or 0) for f in
            qs.annotate(mes=ExtractMonth(campo_fecha)).values('mes').annotate(total=Sum(campo_suma))}


def _datos_reporte_anual(request, sucursal):
    hoy = timezone.localdate()
    ventas_suc = Sales.objects.filter(sucursal=sucursal)
    salidas_suc = Salida.objects.filter(sucursal=sucursal)

    primera = ventas_suc.aggregate(p=Min('date_added'))['p']
    primer_anio = timezone.localtime(primera).year if primera else hoy.year
    try:
        anio = int(request.GET.get('anio', ''))
    except ValueError:
        anio = hoy.year
    anio = min(max(anio, primer_anio), hoy.year)
    # Año contra el que se compara: el anterior, o el que elija gerencia
    try:
        anio_vs = int(request.GET.get('vs', ''))
    except ValueError:
        anio_vs = anio - 1
    if anio_vs == anio or anio_vs > hoy.year or anio_vs < 2000:
        anio_vs = anio - 1
    vs_elegido = anio_vs != anio - 1

    en_curso = anio == hoy.year
    corte = hoy if en_curso else date(anio, 12, 31)
    dia_ant = min(corte.day, calendar.monthrange(anio_vs, corte.month)[1])
    corte_ant = date(anio_vs, corte.month, dia_ant)  # El año pasado hasta la misma fecha

    ventas = ventas_suc.filter(date_added__date__range=[date(anio, 1, 1), corte])
    ventas_ant = ventas_suc.filter(date_added__year=anio_vs)
    ventas_cmp = ventas_ant.filter(date_added__date__lte=corte_ant)
    salidas = salidas_suc.filter(fecha__range=[date(anio, 1, 1), corte])
    salidas_cmp = salidas_suc.filter(fecha__range=[date(anio_vs, 1, 1), corte_ant])

    resumen = ventas.aggregate(total=Sum('grand_total'), numero=Count('id'))
    resumen_cmp = ventas_cmp.aggregate(total=Sum('grand_total'), numero=Count('id'))
    ingresos, ingresos_cmp = dinero(resumen['total']), dinero(resumen_cmp['total'])
    ingresos_ant_total = dinero(ventas_ant.aggregate(t=Sum('grand_total'))['t'])
    total_salidas = dinero(salidas.aggregate(t=Sum('monto'))['t'])
    total_salidas_cmp = dinero(salidas_cmp.aggregate(t=Sum('monto'))['t'])
    utilidad, utilidad_cmp = ingresos - total_salidas, ingresos_cmp - total_salidas_cmp
    ticket = dinero(ingresos / resumen['numero']) if resumen['numero'] else dinero(0)
    ticket_cmp = dinero(ingresos_cmp / resumen_cmp['numero']) if resumen_cmp['numero'] else dinero(0)
    alumnos = len(set(_pagos_de_clases(ventas).values_list('client_id', flat=True)))
    alumnos_cmp = len(set(_pagos_de_clases(ventas_cmp).values_list('client_id', flat=True)))

    # Proyección: si hay año anterior, se le aplica el mismo ritmo (respeta la temporada alta y baja);
    # si no, se reparte lo que va del año entre los días que han pasado
    proyeccion = None
    if en_curso and corte < date(anio, 12, 31):
        if ingresos_cmp and ingresos_ant_total:
            proyeccion = dinero(ingresos_ant_total * ingresos / ingresos_cmp)
        elif ingresos:
            transcurridos = (corte - date(anio, 1, 1)).days + 1
            proyeccion = dinero(ingresos / transcurridos * (366 if calendar.isleap(anio) else 365))

    # ---- Mes por mes ----
    ing_mes = _por_mes(ventas, 'date_added', 'grand_total')
    ing_mes_ant = _por_mes(ventas_ant, 'date_added', 'grand_total')
    sal_mes = _por_mes(salidas, 'fecha', 'monto')
    num_mes = {f['mes']: f['n'] for f in ventas.annotate(mes=ExtractMonth('date_added')).values('mes').annotate(n=Count('id'))}
    alumnos_mes = {f['mes']: f['n'] for f in _pagos_de_clases(ventas).annotate(mes=ExtractMonth('date_added'))
                   .values('mes').annotate(n=Count('client', distinct=True))}
    alumnos_mes_ant = {f['mes']: f['n'] for f in _pagos_de_clases(ventas_ant).annotate(mes=ExtractMonth('date_added'))
                       .values('mes').annotate(n=Count('client', distinct=True))}

    meses = []
    acumulado = acumulado_ant = 0
    grafica = {'etiquetas': MESES_CORTOS, 'ingresos': [], 'ingresos_ant': [], 'acumulado': [], 'acumulado_ant': [],
               'alumnos': [], 'alumnos_ant': [], 'utilidad': [], 'urls': [], 'anio': anio, 'anio_ant': anio_vs}
    for m in range(1, 13):
        futuro = date(anio, m, 1) > corte
        ing, ant, sal = ing_mes.get(m, 0), ing_mes_ant.get(m, 0), sal_mes.get(m, 0)
        acumulado += ing
        acumulado_ant += ant
        numero = num_mes.get(m, 0)
        meses.append({
            'numero': m, 'nombre': MESES[m - 1], 'futuro': futuro, 'mes_valor': f"{anio}-{m:02d}",
            'vs_valor': f"{anio_vs}-{m:02d}",
            'ingresos': dinero(ing), 'ingresos_ant': dinero(ant), 'cambio': None if futuro else _cambio(ing, ant),
            'salidas': dinero(sal), 'utilidad': dinero(ing - sal), 'ventas': numero,
            'ticket': dinero(ing / numero) if numero else None, 'alumnos': alumnos_mes.get(m, 0),
            'en_curso': en_curso and m == corte.month,
        })
        grafica['ingresos'].append(None if futuro else round(ing, 2))
        grafica['ingresos_ant'].append(round(ant, 2))
        grafica['acumulado'].append(None if futuro else round(acumulado, 2))
        grafica['acumulado_ant'].append(round(acumulado_ant, 2))
        grafica['alumnos'].append(None if futuro else alumnos_mes.get(m, 0))
        grafica['alumnos_ant'].append(alumnos_mes_ant.get(m, 0))
        grafica['utilidad'].append(None if futuro else round(ing - sal, 2))
        # Al abrir un mes, su reporte se compara contra el mismo mes del año de comparación
        grafica['urls'].append(f"{anio}-{m:02d}&vs={anio_vs}-{m:02d}")

    con_ventas = [m for m in meses if not m['futuro'] and m['ingresos']]
    mejor_mes = max(con_ventas, key=lambda m: m['ingresos']) if con_ventas else None
    meses_cerrados = [m for m in con_ventas if not m['en_curso']]
    promedio_mes = dinero(sum(m['ingresos'] for m in meses_cerrados) / len(meses_cerrados)) if meses_cerrados else None
    mayor_carril = max(ingresos, ingresos_cmp, dinero(1))

    # ---- Formas de pago, productos y categorías ----
    formas = [
        {'forma': f['tipoPago__tipo'] or 'Sin forma de pago', 'total': dinero(f['total']), 'ventas': f['ventas']}
        for f in ventas.values('tipoPago__tipo').annotate(total=Sum('grand_total'), ventas=Count('id')).order_by('-total')
    ]
    for f in formas:
        f['porcentaje'] = round(float(f['total']) / float(ingresos) * 100) if ingresos else 0
    items = salesItems.objects.filter(sale_id__in=ventas.values('id'))
    productos_todos = list(
        items.annotate(nombre=Coalesce('product_id__name', 'product_name', output_field=TextField()))
        .values('nombre', 'product_id__category_id__name')
        .annotate(total=Sum('total'), cantidad=Sum('qty'), ventas=Count('sale_id', distinct=True))
        .order_by('-total')
    )
    mayor = float(productos_todos[0]['total'] or 0) if productos_todos else 0
    for p in productos_todos:
        p['nombre'] = p['nombre'] or 'Producto eliminado'
        p['ancho'] = round(float(p['total'] or 0) / mayor * 100) if mayor else 0
    categorias = [
        {'nombre': c['product_id__category_id__name'] or 'Sin categoría', 'total': dinero(c['total'])}
        for c in items.values('product_id__category_id__name').annotate(total=Sum('total')).order_by('-total')
    ]
    total_items = sum(float(c['total']) for c in categorias)
    for c in categorias:
        c['porcentaje'] = round(float(c['total']) / total_items * 100) if total_items else 0

    # ---- Año por año ----
    anios_ventas = {a['anio']: a for a in ventas_suc.annotate(anio=ExtractYear('date_added')).values('anio')
                    .annotate(total=Sum('grand_total'), numero=Count('id'))}
    anios_salidas = {a['anio']: float(a['total'] or 0) for a in salidas_suc.exclude(fecha__isnull=True)
                     .annotate(anio=ExtractYear('fecha')).values('anio').annotate(total=Sum('monto'))}
    historico = []
    for a in range(primer_anio, hoy.year + 1):
        total = float((anios_ventas.get(a) or {}).get('total') or 0)
        anterior = float((anios_ventas.get(a - 1) or {}).get('total') or 0)
        historico.append({
            'anio': a, 'ingresos': dinero(total), 'salidas': dinero(anios_salidas.get(a, 0)),
            'utilidad': dinero(total - anios_salidas.get(a, 0)), 'ventas': (anios_ventas.get(a) or {}).get('numero', 0),
            'cambio': _cambio(total, anterior) if a != hoy.year else None, 'en_curso': a == hoy.year,
            'actual': a == anio,
        })
    mayor_anio = max((float(h['ingresos']) for h in historico), default=0)
    for h in historico:
        h['alto'] = round(float(h['ingresos']) / mayor_anio * 100) if mayor_anio else 0

    contra = f"{anio_vs} al {corte_ant.day} de {MESES[corte_ant.month - 1]}" if en_curso else str(anio_vs)
    return {
        'page_title': f'Reporte {anio}',
        'sucursal': sucursal,
        'anio': anio,
        'anio_ant': anio_vs,
        'en_curso': en_curso,
        'corte': corte,
        'corte_ant': corte_ant,
        'contra': contra,
        'anios': list(range(hoy.year, primer_anio - 1, -1)),
        'anio_anterior_url': (f"?anio={anio - 1}" + (f"&vs={anio_vs}" if vs_elegido else '')) if anio > primer_anio else None,
        'anio_siguiente_url': (f"?anio={anio + 1}" + (f"&vs={anio_vs}" if vs_elegido else '')) if anio < hoy.year else None,
        'vs_elegido': vs_elegido,
        'anio_previo': anio - 1,

        'ingresos': ingresos,
        'ingresos_cmp': ingresos_cmp,
        'ingresos_ant_total': ingresos_ant_total,
        'total_salidas': total_salidas,
        'utilidad': utilidad,
        'utilidad_abs': abs(utilidad),
        'margen': round(float(utilidad) / float(ingresos) * 100) if ingresos else None,
        'numero_ventas': resumen['numero'],
        'ticket': ticket,
        'alumnos': alumnos,
        'comparables': {'ingresos': ingresos_cmp, 'salidas': total_salidas_cmp, 'utilidad': utilidad_cmp,
                        'ticket': ticket_cmp, 'ventas': resumen_cmp['numero'], 'alumnos': alumnos_cmp},
        'cambios': {
            'ingresos': _cambio(ingresos, ingresos_cmp),
            'salidas': _cambio(total_salidas, total_salidas_cmp),
            'utilidad': _cambio(utilidad, utilidad_cmp) if utilidad_cmp > 0 else None,
            'ticket': _cambio(ticket, ticket_cmp),
            'alumnos': _cambio(alumnos, alumnos_cmp),
        },
        'diferencia': ingresos - ingresos_cmp,
        'diferencia_abs': abs(ingresos - ingresos_cmp),
        'cambio_anio': _cambio(ingresos, ingresos_cmp),
        'carril': round(float(ingresos) / float(mayor_carril) * 100),
        'carril_ant': round(float(ingresos_cmp) / float(mayor_carril) * 100),
        'proyeccion': proyeccion,
        'proyeccion_por_temporada': bool(ingresos_cmp and ingresos_ant_total),
        'mejor_mes': mejor_mes,
        'promedio_mes': promedio_mes,

        'meses': meses,
        'grafica': {**grafica, 'formas': {'etiquetas': [f['forma'] for f in formas],
                                          'valores': [float(f['total']) for f in formas]}},
        'formas': formas,
        'productos': productos_todos[:10],
        'productos_todos': productos_todos,
        'categorias': categorias,
        'historico': historico,
    }


@login_required
def reporte_anual(request):
    sucursal, error = _sucursal_de_request(request)
    if error:
        return error
    return render(request, 'posApp/reporte_anual.html', _datos_reporte_anual(request, sucursal))


@login_required
def reporte_anual_excel(request):
    from openpyxl import Workbook
    from openpyxl.chart import LineChart, PieChart, Reference
    from openpyxl.chart.label import DataLabelList
    from openpyxl.styles import Font

    sucursal, error = _sucursal_de_request(request)
    if error:
        return error
    d = _datos_reporte_anual(request, sucursal)
    anio = d['anio']
    encabezado = f"Reporte {anio}"
    subtitulo = (f"{sucursal.nombre}. Datos al {d['corte'].day} de {MESES[d['corte'].month - 1]}"
                 if d['en_curso'] else sucursal.nombre)
    libro = Workbook()

    # ---- Resumen ----
    h = _Hoja(libro, 'Resumen', encabezado, subtitulo, primera=True)
    h.seccion('Cifras del año')
    comp = d['comparables']

    def cambio(actual, anterior):
        return (float(actual) - float(anterior)) / float(anterior) if anterior else None

    filas = [
        ('Ingresos', d['ingresos'], comp['ingresos'], cambio(d['ingresos'], comp['ingresos'])),
        ('Salidas', d['total_salidas'], comp['salidas'], cambio(d['total_salidas'], comp['salidas'])),
        ('Utilidad', d['utilidad'], comp['utilidad'], cambio(d['utilidad'], comp['utilidad']) if comp['utilidad'] > 0 else None),
        ('Ticket promedio', d['ticket'], comp['ticket'], cambio(d['ticket'], comp['ticket'])),
        ('Número de ventas', d['numero_ventas'], comp['ventas'], cambio(d['numero_ventas'], comp['ventas'])),
        ('Alumnos que pagaron clases', d['alumnos'], comp['alumnos'], cambio(d['alumnos'], comp['alumnos'])),
    ]
    ini, _ = h.tabla(['Concepto', str(anio), d['contra'].capitalize(), 'Cambio'], filas,
                     formatos={1: PESOS, 2: PESOS, 3: PORCENTAJE})
    for fila in (ini + 5, ini + 6):
        for col in (2, 3):
            h.ws.cell(row=fila, column=col).number_format = '#,##0'
    h.ws.cell(row=ini + 3, column=1).font = Font(bold=True)

    h.seccion('Cómo va el año')
    extras = []
    if d['proyeccion']:
        extras.append(('Si sigue este ritmo, cierras el año en', d['proyeccion']))
    extras.append((f"{d['anio_ant']} completo", d['ingresos_ant_total']))
    if d['mejor_mes']:
        extras.append((f"Mejor mes ({d['mejor_mes']['nombre']})", d['mejor_mes']['ingresos']))
    if d['promedio_mes']:
        extras.append(('Promedio por mes cerrado', d['promedio_mes']))
    h.tabla(['Concepto', 'Monto'], extras, formatos={1: PESOS})
    h.anchos(40, 18, 26, 12)

    # ---- Mes por mes ----
    h = _Hoja(libro, 'Mes por mes', f"{encabezado}: mes por mes", subtitulo)
    filas = [(m['nombre'].capitalize(), m['ingresos'], m['ingresos_ant'],
              None if m['cambio'] is None else m['cambio'] / 100, m['salidas'], m['utilidad'], m['ventas'],
              m['ticket'], m['alumnos'])
             for m in d['meses'] if not m['futuro']]
    ini, ult = h.tabla(['Mes', str(anio), str(d['anio_ant']), 'Cambio', 'Salidas', 'Utilidad', 'Ventas', 'Ticket promedio',
                        'Alumnos que pagaron'], filas,
                       formatos={1: PESOS, 2: PESOS, 3: PORCENTAJE, 4: PESOS, 5: PESOS, 6: '#,##0', 7: PESOS,
                                 8: '#,##0'},
                       total=['Total', float(d['ingresos']), sum(float(f[2]) for f in filas), None,
                              float(d['total_salidas']), float(d['utilidad']), d['numero_ventas']])
    h.anchos(14, 16, 16, 10, 15, 16, 10, 16, 14)
    if filas:
        _grafica_barras(h.ws, f"{anio} contra {d['anio_ant']}", (1, ini + 1, ult), [(2, ini, ult), (3, ini, ult)], 'K4',
                        ancho=22, alto=9, colores=['1668C7', '94A3B8'])
        linea = LineChart()
        linea.title, linea.style, linea.height, linea.width = 'Alumnos que pagaron por mes', 12, 8, 22
        linea.add_data(Reference(h.ws, min_col=9, min_row=ini, max_row=ult), titles_from_data=True)
        linea.set_categories(Reference(h.ws, min_col=1, min_row=ini + 1, max_row=ult))
        linea.series[0].graphicalProperties.line.solidFill = '0B1F4D'
        linea.series[0].graphicalProperties.line.width = 28000
        h.ws.add_chart(linea, 'K24')

    # ---- Formas de pago ----
    h = _Hoja(libro, 'Formas de pago', f"{encabezado}: cómo pagaron", subtitulo)
    filas = [(f['forma'], f['ventas'], f['total'], f['porcentaje'] / 100) for f in d['formas']]
    ini, ult = h.tabla(['Forma de pago', 'Ventas', 'Total', '% del año'], filas, formatos={2: PESOS, 3: '0%'},
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

    # ---- Productos y categorías ----
    h = _Hoja(libro, 'Productos', f"{encabezado}: productos vendidos", subtitulo)
    total_productos = sum(float(p['total'] or 0) for p in d['productos_todos'])
    filas = [(p['nombre'], p['product_id__category_id__name'] or 'Sin categoría', p['cantidad'], p['ventas'],
              p['total'], float(p['total'] or 0) / total_productos if total_productos else 0)
             for p in d['productos_todos']]
    ini, _ = h.tabla(['Producto', 'Categoría', 'Cantidad', 'Ventas', 'Total', '% del total'], filas,
                     formatos={2: '#,##0', 3: '#,##0', 4: PESOS, 5: '0.0%'},
                     total=['Total', '', sum(f[2] or 0 for f in filas), '', total_productos, 1 if filas else 0],
                     filtro=True)
    h.ws.freeze_panes = f"A{ini + 1}"
    h.fila = 4
    h.seccion('Por categoría', columna=8)
    h.tabla(['Categoría', 'Total', '%'], [(c['nombre'], c['total'], c['porcentaje'] / 100) for c in d['categorias']],
            formatos={1: PESOS, 2: '0%'}, columna=8)
    h.anchos(46, 26, 13, 11, 16, 14, 4, 28, 16, 8)

    # ---- Año por año ----
    h = _Hoja(libro, 'Año por año', 'Histórico de todos los años', sucursal.nombre)
    filas = [(str(a['anio']) + (' (en curso)' if a['en_curso'] else ''), a['ingresos'],
              None if a['cambio'] is None else a['cambio'] / 100, a['salidas'], a['utilidad'], a['ventas'])
             for a in d['historico']]
    ini, ult = h.tabla(['Año', 'Ingresos', 'Cambio', 'Salidas', 'Utilidad', 'Ventas'], filas,
                       formatos={1: PESOS, 2: PORCENTAJE, 3: PESOS, 4: PESOS, 5: '#,##0'})
    h.anchos(18, 18, 10, 16, 18, 10)
    if filas:
        _grafica_barras(h.ws, 'Ingresos por año', (1, ini + 1, ult), [(2, ini, ult)], 'H4', ancho=18)

    for ws in libro.worksheets:
        ws.sheet_properties.tabColor = '1668C7'
        ws.page_setup.orientation = 'landscape'
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True

    respuesta = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    nombre = f"reporte_{anio}_{sucursal.nombre}".replace(' ', '_')
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre}.xlsx"'
    libro.save(respuesta)
    return respuesta
