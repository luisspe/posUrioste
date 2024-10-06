import logging
from celery import shared_task
from django.utils import timezone
from posApp.models import Clientes


# Configura el logger
logger = logging.getLogger(__name__)

@shared_task
def status_mensualidades():
    logger.info("Ejecutando tarea de actualización de mensualidades...")

    # Obtener todos los clientes con sus mensualidades
    all_clients = Clientes.objects.prefetch_related('mensualidad_set').all()

    for client in all_clients:
        mensualidades = client.mensualidad_set.all()
        if not mensualidades.exists():
            client.estado_mensualidad = 'Sin mensualidades'
        else:
            ultima_mensualidad = mensualidades.latest('fecha_vencimiento')
            if ultima_mensualidad.fecha_vencimiento < timezone.now().date():
                client.estado_mensualidad = 'Vencido'
            elif mensualidades.filter(pagado=False).exists():
                client.estado_mensualidad = 'Pendiente'
            else:
                client.estado_mensualidad = 'Al corriente'

        client.save()  # Guardar el estado actualizado en la base de datos

    logger.info("Actualización de mensualidades completada.")