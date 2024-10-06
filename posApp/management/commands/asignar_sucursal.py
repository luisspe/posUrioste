from django.core.management.base import BaseCommand
from posApp.models import Sucursal, Clientes, Mensualidad, Category, Products, Sales, salesItems, Salida, PlanInscripcion, Levels

class Command(BaseCommand):
    help = 'Assigns a default Sucursal to all records missing a sucursal.'

    def handle(self, *args, **kwargs):
        # Fetch the default sucursal "Acuatica Urioste Chuburna"
        try:
            default_sucursal = Sucursal.objects.get(nombre="Acuatica Urioste Chuburna")
        except Sucursal.DoesNotExist:
            self.stdout.write(self.style.ERROR('Sucursal "Acuatica Urioste Chuburna" does not exist.'))
            return

        models_to_update = [
            Clientes, Mensualidad, Category, Products, Sales, salesItems, Salida, PlanInscripcion, Levels
        ]

        for model in models_to_update:
            instances = model.objects.filter(sucursal__isnull=True)
            count = instances.update(sucursal=default_sucursal)
            self.stdout.write(self.style.SUCCESS(f'{count} {model.__name__} records updated with the default sucursal.'))

        self.stdout.write(self.style.SUCCESS('Finished assigning the default sucursal to all applicable records.'))
