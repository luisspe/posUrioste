from django.core.management.base import BaseCommand
from posApp.models import Clientes, PlanInscripcion

class Command(BaseCommand):
    help = 'Asigna el plan de inscripción "Prueba Urioste Chuburna" a todos los clientes'

    def handle(self, *args, **options):
        # Asegúrate de cambiar 'plan_name' por el nombre exacto del plan en tu base de datos
        plan_name = "plan prueba urioste chuburna"
        try:
            plan = PlanInscripcion.objects.get(nombre=plan_name)
            clientes = Clientes.objects.all()
            for cliente in clientes:
                cliente.plan_inscripcion = plan
                cliente.save()
            self.stdout.write(self.style.SUCCESS(f'Todos los clientes han sido actualizados con el plan "{plan_name}".'))
        except PlanInscripcion.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'El plan "{plan_name}" no existe en la base de datos.'))
