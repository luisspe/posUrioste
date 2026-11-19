from django.core.management.base import BaseCommand
from django.db.models import Q
from posApp.models import Products

# Palabras que indican que un producto NO es pago de clases aunque esté en la categoría Clases
EXCLUIR = ['inscrip', 'recargo', 'aclaraci', 'baja', 'constancia', 'visita', 'gorra', 'playera', 'goggle', 'prueba', 'dia ins', 'personalizada']


class Command(BaseCommand):
    help = ('Propone dias_vigencia para los productos que son pago de clases/membresías '
            '(categorías "Clases" o "Membresías" con precio >= 400). Usa --aplicar para guardar.')

    def add_arguments(self, parser):
        parser.add_argument('--dias', type=int, default=30, help='Días de vigencia a asignar (default 30)')
        parser.add_argument('--aplicar', action='store_true', help='Guarda los cambios; sin esto solo muestra la lista')

    def handle(self, *args, **options):
        candidatos = (Products.objects
                      .filter(dias_vigencia__isnull=True, price__gte=400)
                      .filter(Q(category_id__name__icontains='clase') | Q(category_id__name__icontains='membres'))
                      .select_related('category_id', 'sucursal')
                      .order_by('sucursal__nombre', 'name'))
        candidatos = [p for p in candidatos if not any(x in p.name.lower() for x in EXCLUIR)]

        for p in candidatos:
            self.stdout.write(f"[{p.sucursal}] {p.category_id.name} | {p.name} (${p.price:.2f})")

        if not options['aplicar']:
            self.stdout.write(self.style.WARNING(
                f"{len(candidatos)} productos candidatos. Revisa la lista y vuelve a correr con --aplicar."))
            return

        Products.objects.filter(id__in=[p.id for p in candidatos]).update(dias_vigencia=options['dias'])
        self.stdout.write(self.style.SUCCESS(f"{len(candidatos)} productos marcados con {options['dias']} días de vigencia."))
