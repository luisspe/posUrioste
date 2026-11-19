"""
Convierte el texto libre de horario/grupo ("5 pm", "17:00 PRINCIPIANTES", "Niños Martes y Jueves 5pm",
"JUEVES Y VIERNES 6:00 AM") en hora, días y etiqueta para armar los grupos.
"""
import re
import unicodedata
from datetime import time

# Lunes = 0 ... Domingo = 6 (igual que date.weekday())
_DIAS = [
    (r'lun\w*', 0), (r'mar(?:tes|\.)?(?=\W|$)', 1), (r'mie\w*', 2), (r'jue\w*', 3), (r'vie\w*', 4),
    (r'sab\w*', 5), (r'dom\w*', 6),
]
_RANGO_DIAS = re.compile(r'\b(lun\w*|l)\s*(?:a|-)\s*(vie\w*|v)\b')
_HORA = re.compile(r'(?<![\d:])(\d{1,2})(?:[:.](\d{2}))?\s*(a\.?\s?m\.?|p\.?\s?m\.?|hrs?|h)?(?![\d])')


def _normalizar(texto):
    return unicodedata.normalize('NFKD', (texto or '').lower()).encode('ascii', 'ignore').decode()


def leer_dias(texto):
    """Regresa los días como texto de dígitos ("13" = martes y jueves); "" si no menciona días."""
    t = _normalizar(texto)
    if _RANGO_DIAS.search(t) or 'lunes a viernes' in t:
        return '01234'
    dias = set()
    for patron, numero in _DIAS:
        if re.search(r'\b' + patron, t):
            dias.add(numero)
    if 'sabatino' in t:
        dias.add(5)
    return ''.join(str(d) for d in sorted(dias))


def leer_hora(texto):
    """Primera hora que aparezca. Sin am/pm, de la 1 a las 6 se toma como de la tarde (horario de alberca)."""
    t = _normalizar(texto)
    for match in _HORA.finditer(t):
        hora, minutos, sufijo = int(match.group(1)), int(match.group(2) or 0), (match.group(3) or '').replace('.', '').replace(' ', '')
        # "3 clases", "2 cla x sem" no son horas
        resto = t[match.end():match.end() + 6]
        if not sufijo and not match.group(2) and re.match(r'\s*(cla|ses|dia|x\b)', resto):
            continue
        # Rango "3 a 6pm" o "3-5pm": la hora de inicio toma el am/pm del final
        rango = re.match(r'\s*(?:a|-)\s*\d{1,2}(?:[:.]\d{2})?\s*(a\.?\s?m|p\.?\s?m)', t[match.end():])
        if not sufijo and rango:
            sufijo = rango.group(1).replace('.', '').replace(' ', '')
        if minutos > 59 or hora > 23:
            continue
        if sufijo.startswith('p') and hora < 12:
            hora += 12
        elif sufijo.startswith('a') and hora == 12:
            hora = 0
        elif not sufijo and not match.group(2) and 1 <= hora <= 6:
            hora += 12
        return time(hora, minutos)
    return None


def leer_etiqueta(texto):
    """Lo que queda del texto quitando la hora y los días: "PRINCIPIANTES", "EQUIPO A", "AGUAS ABIERTAS"."""
    t = re.sub(r'\d{1,2}(?:[:.]\d{2})?\s*(?:a|-)\s*\d{1,2}(?:[:.]\d{2})?\s*(?:a\.?\s?m\.?|p\.?\s?m\.?)?', ' ', _normalizar(texto))
    t = _HORA.sub(' ', t)
    t = _RANGO_DIAS.sub(' ', t)
    for patron, _ in _DIAS:
        t = re.sub(r'\b' + patron, ' ', t)
    t = re.sub(r'\ba las\b', ' ', t)
    t = re.sub(r'\b(y|de|del|las|los|el|la|hrs?|horas?)\b', ' ', t)
    t = re.sub(r'(^|\s)a(?=\s*$)', ' ', t) if not re.search(r'\b(equipo|grupo|nivel)\s+a\s*$', t) else t
    t = re.sub(r'[^a-z0-9ñ ]', ' ', t)
    return ' '.join(t.split()).upper()


def leer_horario(texto):
    """(hora, dias, etiqueta) a partir del texto libre."""
    return leer_hora(texto), leer_dias(texto), leer_etiqueta(texto)


NOMBRES_DIAS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']


def describir_dias(dias):
    if not dias:
        return 'Todos los días'
    if dias == '01234':
        return 'Lunes a viernes'
    if dias == '0123456':
        return 'Diario'
    return ', '.join(NOMBRES_DIAS[int(d)] for d in dias)
