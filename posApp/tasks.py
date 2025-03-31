# import logging
# from celery import shared_task
# from django.utils import timezone
# from posApp.models import Clientes

# # Configura el logger para registrar información sobre la
# logger = logging.getLogger(__name__)

# @shared_task
# def status_mensualidades():
#     # Log para indicar el inicio de la tarea
#     logger.info("Ejecutando tarea de actualización de mensualidades...")

#     # Obtener todos los clientes con sus mensualidades relacionadas
#     all_clients = Clientes.objects.prefetch_related('mensualidad_set').all()

#     # Iterar sobre todos los clientes
#     for client in all_clients:
#         # Obtener todas las mensualidades del cliente
#         mensualidades = client.mensualidad_set.all()

#         # Si el cliente no tiene mensualidades
#         if not mensualidades.exists():
#             client.estado_mensualidad = 'Sin mensualidades'
#         else:
#             # Obtener la última mensualidad basada en la fecha de vencimiento
#             ultima_mensualidad = mensualidades.latest('fecha_vencimiento')

#             # Verificar si la última mensualidad está vencida
#             if ultima_mensualidad.fecha_vencimiento < timezone.now().date():
#                 client.estado_mensualidad = 'Vencido'
#             # Verificar si hay mensualidades pendientes de pago
#             elif mensualidades.filter(pagado=False).exists():
#                 client.estado_mensualidad = 'Pendiente'
#             # Si todas las mensualidades están al corriente