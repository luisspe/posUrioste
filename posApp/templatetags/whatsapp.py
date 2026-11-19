import re
from urllib.parse import quote

from django import template

register = template.Library()


def numero_whatsapp(celular):
    """El celular en el formato que pide WhatsApp: con lada de país y sin espacios ni guiones.
    Los números de 10 dígitos se toman como de México (52). Regresa None si no parece un celular."""
    digitos = re.sub(r'\D', '', celular or '')
    if len(digitos) == 10:
        return '52' + digitos
    if len(digitos) in (12, 13) and digitos.startswith('52'):
        return digitos
    return None


def mensaje_adeudo(cliente, pago):
    dias = pago.get('dias') or 0
    venció = pago.get('vigente_hasta')
    texto = 'Hola, le escribimos de Acuática Urioste. Le recordamos que la mensualidad de %s' % cliente.nombre
    if venció:
        texto += ' venció el %s' % venció.strftime('%d/%m/%Y')
    texto += ' y lleva %d día%s de atraso. ¿Nos ayuda a ponerse al corriente? Puede pagar en recepción. ¡Gracias!' % (
        dias, '' if dias == 1 else 's')
    return texto


@register.simple_tag
def whatsapp_adeudo(cliente, pago):
    """Liga a WhatsApp Web con el recordatorio de pago ya escrito, o '' si no debe o no tiene celular."""
    if not cliente or not pago or pago.get('estado') != 'Vencido':
        return ''
    numero = numero_whatsapp(cliente.celular)
    if not numero:
        return ''
    return 'https://web.whatsapp.com/send?phone=%s&text=%s' % (numero, quote(mensaje_adeudo(cliente, pago)))
