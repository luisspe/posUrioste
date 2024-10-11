import os
from celery import Celery
from celery.schedules import crontab, timedelta

# Establecer el entorno de Django para Celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pos.settings')

app = Celery('pos')
app.conf.timezone = 'America/Mexico_City'

# Configuración de Celery a través de las settings de Django, usando el prefijo CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')

# Autodiscover de las tareas registradas en las apps de Django
app.autodiscover_tasks()

# Configuración de Celery Beat para tareas periódicas
app.conf.beat_schedule = {
    'check_mensualidades_a_la_1am': {
        'task': 'posApp.tasks.status_mensualidades',
        'schedule': crontab(hour=1, minute=0),  # A la 1:00 AM
    },
}

# Debugging task para verificar que Celery está funcionando (opcional)
@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
