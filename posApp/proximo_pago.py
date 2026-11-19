"""
Lee la fecha de "próximo pago" que recepción escribe en el comentario del ticket, por ejemplo:
"Próxima fecha de pago 9 de octubre", "proximo pago 15 d enov", "proxima fecha de pago 1 al 5 de febrero".
"""
import difflib
import re
import unicodedata
from datetime import date, timedelta

MESES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6, 'julio': 7,
    'agosto': 8, 'septiembre': 9, 'setiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12,
}
ABREVIATURAS = {
    'ene': 1, 'feb': 2, 'mar': 3, 'abr': 4, 'may': 5, 'jun': 6, 'jul': 7, 'ago': 8,
    'sep': 9, 'sept': 9, 'set': 9, 'oct': 10, 'nov': 11, 'dic': 12,
}

# "prox..." o "pago" y, poco después, un día (o rango de días) y un mes escrito con letras o número
_PATRON = re.compile(
    r'(?:prox\w*|pago)\D{0,40}?'
    r'(?<!\d)(?P<dia>\d{1,2})(?!\d)\s*(?:o|ro|ero|er|vo|a)?\s*'
    r'(?:(?:al|a|-|y)\s*(?P<dia_fin>\d{1,2})(?!\d)\s*(?:o|ro|ero|er|vo|a)?\s*)?'
    r'(?:(?:(?:de|del)\s*)?(?P<mes>[a-z]{3,})|/\s*(?P<mes_num>\d{1,2})(?!\d))'
    r'(?:\s*(?:de|del|/)?\s*(?P<anio>20\d{2}))?'
)


def _normalizar(texto):
    texto = unicodedata.normalize('NFKD', texto.lower()).encode('ascii', 'ignore').decode()
    # Error de dedo frecuente: "9 d ejunio" -> "9 de junio"
    return re.sub(r'\bd e(?=[a-z])', 'de ', texto)


def _mes(token):
    if token.isdigit():
        mes = int(token)
        return mes if 1 <= mes <= 12 else None
    if token in MESES:
        return MESES[token]
    if token[:4] in ABREVIATURAS:
        return ABREVIATURAS[token[:4]]
    if token[:3] in ABREVIATURAS and len(token) <= 4:
        return ABREVIATURAS[token[:3]]
    # Faltas de ortografía: "npoviembre", "msyo", "cotubre", "spetiembre". Pide más parecido si no
    # empieza con la misma letra, para no confundir palabras como "años" con un mes
    mejor, puntaje = None, 0
    for nombre, numero in MESES.items():
        parecido = difflib.SequenceMatcher(None, token, nombre).ratio()
        minimo = 0.6 if token[0] == nombre[0] else 0.8
        if parecido >= minimo and parecido > puntaje:
            mejor, puntaje = numero, parecido
    return mejor


def leer_proximo_pago(comentario, fecha_venta):
    """
    Regresa la fecha de próximo pago escrita en el comentario, o None si no hay una clara.
    Como casi nunca escriben el año, se toma la siguiente vez que cae ese día después de la venta.
    En un rango ("1 al 5 de febrero") se toma el último día, que es cuando vence sin recargo.
    """
    if not comentario:
        return None
    for match in _PATRON.finditer(_normalizar(comentario)):
        mes = _mes(match.group('mes') or match.group('mes_num'))
        if not mes:
            continue
        dia = int(match.group('dia_fin') or match.group('dia'))
        anio = int(match.group('anio')) if match.group('anio') else fecha_venta.year
        try:
            fecha = date(anio, mes, dia)
        except ValueError:
            continue
        if not match.group('anio') and fecha < fecha_venta - timedelta(days=7):
            try:
                fecha = date(anio + 1, mes, dia)
            except ValueError:
                continue
        # Descarta fechas absurdas (en el pasado o a más de un año)
        if fecha_venta - timedelta(days=7) <= fecha <= fecha_venta + timedelta(days=400):
            return fecha
    return None


def dia_de_pago(pay_day):
    """El día del mes en que paga el cliente, tomado de su campo libre ("1 de cada mes", "15")."""
    numero = re.search(r'\d{1,2}', pay_day or '')
    if numero and 1 <= int(numero.group()) <= 31:
        return int(numero.group())
    return None
