from datetime import datetime
from unicodedata import category
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
# Create your models here.

# class Employees(models.Model):
#     code = models.CharField(max_length=100,blank=True) 
#     firstname = models.TextField() 
#     middlename = models.TextField(blank=True,null= True) 
#     lastname = models.TextField() 
#     gender = models.TextField(blank=True,null= True) 
#     dob = models.DateField(blank=True,null= True) 
#     contact = models.TextField() 
#     address = models.TextField() 
#     email = models.TextField() 
#     department_id = models.ForeignKey(Department, on_delete=models.CASCADE) 
#     position_id = models.ForeignKey(Position, on_delete=models.CASCADE) 
#     date_hired = models.DateField() 
#     salary = models.FloatField(default=0) 
#     status = models.IntegerField() 
#     date_added = models.DateTimeField(default=timezone.now) 
#     date_updated = models.DateTimeField(auto_now=True) 

    # def __str__(self):
    #     return self.firstname + ' ' +self.middlename + ' '+self.lastname + ' '

class Sucursal(models.Model):
    nombre = models.CharField(max_length=100)
    direccion = models.CharField(max_length=200, blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.nombre

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.SET_NULL, null=True, blank=True)
    is_admin = models.BooleanField(default=False)
    is_seller = models.BooleanField(default=False)
    is_manager = models.BooleanField(default=False)
    sucursales = models.ManyToManyField(Sucursal, related_name='managers', blank=True)
    is_modelo = models.BooleanField(default=False)  # Nuevo campo para Acuática Modelo
    is_modelo_manager = models.BooleanField(default=False)  # Nuevo campo para Acuática Modelo Manager

    def __str__(self):
        return self.user.username

class Genero(models.Model):
    genero = models.CharField(max_length=20)

    def __str__(self):
        return str(self.genero)


class PlanInscripcion(models.Model):
    nombre = models.CharField(max_length=100, blank=True, null=True)
    descripcion = models.TextField(blank=True, null=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.SET_NULL, null=True, blank=True)
    duracion = models.IntegerField(default=30)  # Duración en días
    sucursal = models.ForeignKey(Sucursal, on_delete=models.SET_NULL, null=True, blank=True)
    def __str__(self):
        return self.nombre




class Levels(models.Model):
    level = models.CharField(max_length=100, blank=True, null=True)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.SET_NULL, null=True, blank=True)
    def __str__(self):
        return str(self.level)
    

class Clientes(models.Model):
    MALE = 'M'
    FEMALE = 'F'
    SEX_CHOICE = (
        (MALE, 'Hombre'),
        (FEMALE, 'Mujer')
    )

    SINGLE = 'S'
    MARRIED = 'M'
    DIVORCE = 'D'
    FREE = 'F'
    CIVIL_CHOICE = (
        (SINGLE, 'Soltero'),
        (MARRIED, 'Casado'),
        (DIVORCE, 'Divorsiado'),
        (FREE, 'Union libre')
    )

    FACEBOOK = 'F'
    RECOMANDATION = 'R'
    TRANSIT = 'T'
    OTHER = 'F'
    FIND_CHOICES = (
        (FACEBOOK, 'Facebook'),
        (RECOMANDATION, 'Recomendacion'),
        (TRANSIT, 'Transito'),
        (OTHER, 'Otro')
    )

    nombre = models.CharField(max_length=50)
    #picture = models.ImageField(verbose_name='foto', null=True, blank=True)
    #image_source = models.TextField()
    apellido_materno = models.CharField(max_length=50)
    apellido_paterno = models.CharField(max_length=50)
    fecha_nacimiento = models.CharField(max_length=100,blank=True, null=True)
    genero = models.ForeignKey(Genero, on_delete=models.DO_NOTHING, null=True, blank=True)
    direccion = models.CharField(max_length=200)
    suburbio = models.CharField(max_length=200)
    codigo_postal = models.CharField(max_length=10)
    celular = models.CharField(max_length=12)
    email = models.EmailField(blank=True, null=True)
    #estado_civil = models.CharField(max_length=10, choices=CIVIL_CHOICE)
    
    sangre = models.CharField(max_length=50)
    contacto_emergencia = models.CharField(max_length=200)
    emergency_phone = models.CharField(max_length=20)
    pay_day = models.CharField(max_length=200)
    condicion_medica = models.TextField()
    horario = models.TextField()
    nivel = models.ForeignKey(Levels, on_delete=models.DO_NOTHING, null=True, blank=True)
    status = models.IntegerField(default=1)
    plan_inscripcion = models.ForeignKey(PlanInscripcion, on_delete=models.SET_NULL, null=True, blank=True)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.SET_NULL, null=True, blank=True)
    estado_mensualidad = models.CharField(max_length=20, default='Sin mensualidades') 

    def __str__(self):
        return str(self.nombre)

    @property
    def iniciales(self):
        # Varios nombres se capturaron con espacios o puntos al inicio
        letras = [next((ch for ch in (texto or '') if ch.isalpha()), '') for texto in (self.nombre, self.apellido_paterno)]
        return ''.join(letras).upper() or '?'

    @property
    def codigo_asistencia(self):
        # Contenido del QR de la credencial; el check-in también acepta solo el número
        return f"URI{self.id}"
    
class Grupo(models.Model):
    """Una clase que se repite: por ejemplo "Niños martes y jueves 17:00"."""
    nombre = models.CharField(max_length=100)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE)
    # Días de la semana como dígitos (0 = lunes ... 6 = domingo); vacío = todos los días
    dias = models.CharField(max_length=7, blank=True, default='')
    hora_inicio = models.TimeField(null=True, blank=True)
    nivel = models.ForeignKey(Levels, on_delete=models.SET_NULL, null=True, blank=True)
    activo = models.BooleanField(default=True)
    clientes = models.ManyToManyField(Clientes, related_name='grupos', blank=True)

    class Meta:
        ordering = ['hora_inicio', 'nombre']

    def __str__(self):
        return self.nombre

    @property
    def dias_texto(self):
        from posApp.horarios import describir_dias
        return describir_dias(self.dias)

    def toca_el(self, fecha):
        return not self.dias or str(fecha.weekday()) in self.dias

    def se_cruza_con(self, otro):
        """Dos clases chocan si empiezan con menos de 45 min de diferencia y comparten algún día."""
        if not self.hora_inicio or not otro.hora_inicio:
            return False
        minutos = lambda h: h.hour * 60 + h.minute
        if abs(minutos(self.hora_inicio) - minutos(otro.hora_inicio)) >= 45:
            return False
        return not self.dias or not otro.dias or bool(set(self.dias) & set(otro.dias))

    def inscribir(self, cliente, actualizar_horario=False):
        """
        Inscribe al alumno por un pago y lo saca de los grupos de su sucursal que chocan con este
        (no puede estar en dos clases a la misma hora). Regresa los grupos de los que salió.
        Con actualizar_horario, el horario del alumno pasa a ser el nombre del grupo.
        """
        cruzados = [g for g in cliente.grupos.filter(sucursal=self.sucursal).exclude(id=self.id) if self.se_cruza_con(g)]
        for grupo in cruzados:
            grupo.clientes.remove(cliente)
        self.clientes.add(cliente)
        if actualizar_horario and cliente.horario != self.nombre:
            cliente.horario = self.nombre
            Clientes.objects.filter(id=cliente.id).update(horario=self.nombre)
        return cruzados


class Mensualidad(models.Model):
    cliente = models.ForeignKey(Clientes, on_delete=models.CASCADE, blank=True, null=True)
    fecha_vencimiento = models.DateField(blank=True, null=True)
    monto = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    pagado = models.BooleanField(default=False, blank=True, null=True)
    fecha_pago = models.DateField(null=True, blank=True)
    plan_inscripcion = models.ForeignKey(PlanInscripcion, on_delete=models.CASCADE, blank=True, null=True)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.SET_NULL, null=True, blank=True)
    def __str__(self):
        return f"{self.cliente.nombre} - {self.fecha_vencimiento} - {'Pagado' if self.pagado else 'Pendiente'}"

class Category(models.Model):
    name = models.TextField()
    description = models.TextField()
    status = models.IntegerField(default=1) 
    date_added = models.DateTimeField(default=timezone.now) 
    date_updated = models.DateTimeField(auto_now=True)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.SET_NULL, null=True, blank=True) 

    def __str__(self):
        return self.name

class Products(models.Model):
    code = models.CharField(max_length=100)
    category_id = models.ForeignKey(Category, on_delete=models.CASCADE)
    name = models.TextField()
    description = models.TextField()
    price = models.FloatField(default=0)
    status = models.IntegerField(default=1)
    date_added = models.DateTimeField(default=timezone.now)
    date_updated = models.DateTimeField(auto_now=True)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.SET_NULL, null=True, blank=True)
    cantidad_disponible = models.IntegerField(default=0)  # Nueva columna para inventario
    # Días de clases que cubre al venderse (ej. 30 para una mensualidad). Vacío = no cuenta como pago de clases
    dias_vigencia = models.PositiveIntegerField(null=True, blank=True)
    # Al venderlo, el cliente queda inscrito en este grupo
    grupo = models.ForeignKey('Grupo', on_delete=models.SET_NULL, null=True, blank=True, related_name='productos')

    def __str__(self):
        return self.code + " - " + self.name

    
class FormaPago(models.Model):
    tipo = models.CharField(max_length=100)

    def __str__(self):
        return self.tipo
    

class Sales(models.Model):
    code = models.CharField(max_length=100)
    sub_total = models.FloatField(default=0)
    grand_total = models.FloatField(default=0)
    tax_amount = models.FloatField(default=0)
    tax = models.FloatField(default=0)
    tendered_amount = models.FloatField(default=0)
    tendered_amount_card = models.FloatField(default=0)
    amount_change = models.FloatField(default=0)
    date_added = models.DateTimeField(default=timezone.now, db_index=True)
    date_updated = models.DateTimeField(auto_now=True)
    client = models.ForeignKey(Clientes, on_delete=models.PROTECT, db_index=True)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    tipoPago = models.ForeignKey(FormaPago, on_delete=models.PROTECT, db_index=True)
    comentario = models.CharField(max_length=700, null=True)
    # Fecha en que el cliente debe volver a pagar; antes solo se anotaba a mano en el comentario del ticket
    proximo_pago = models.DateField(null=True, blank=True)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.SET_NULL, null=True, blank=True, db_index=True)

    def __str__(self):
        return self.code

    class Meta:
        indexes = [
            models.Index(fields=['sucursal', 'date_added'], name='sales_sucursal_date_idx'),
        ]
class salesItems(models.Model):
    sale_id = models.ForeignKey(Sales,on_delete=models.CASCADE)
    product_id = models.ForeignKey(Products,on_delete=models.CASCADE, blank=True, null=True)
    product_name = models.CharField(max_length=255, blank=True, null=True)  # Nuevo campo
    price = models.FloatField(default=0)
    qty = models.FloatField(default=0)
    total = models.FloatField(default=0)
    client = models.ForeignKey(Clientes, on_delete=models.CASCADE)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.SET_NULL, null=True, blank=True)
    

class Salida(models.Model):
    concepto = models.CharField(max_length=200, blank=True, null=True)
    monto = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    fecha = models.DateField(blank=True, null=True)
    comentario = models.TextField(blank=True, null=True)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.SET_NULL, null=True, blank=True)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.SET_NULL, null=True, blank=True)
    def __str__(self):
        return f"{self.concepto} - {self.monto} - {self.fecha}"


class Asistencia(models.Model):
    PRESENTE = 'P'
    FALTA = 'F'
    RETARDO = 'R'
    JUSTIFICADA = 'J'
    ESTADO_CHOICES = (
        (PRESENTE, 'Presente'),
        (FALTA, 'Falta'),
        (RETARDO, 'Retardo'),
        (JUSTIFICADA, 'Justificada'),
    )

    cliente = models.ForeignKey(Clientes, on_delete=models.CASCADE)
    fecha = models.DateField(db_index=True)
    estado = models.CharField(max_length=1, choices=ESTADO_CHOICES)
    comentario = models.CharField(max_length=200, blank=True, default='')
    hora_llegada = models.TimeField(null=True, blank=True)  # Se llena al hacer check-in con QR
    grupo = models.ForeignKey(Grupo, on_delete=models.SET_NULL, null=True, blank=True)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.SET_NULL, null=True, blank=True)
    registrado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    fecha_registro = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.cliente} - {self.fecha} - {self.get_estado_display()}"

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['cliente', 'fecha'], name='asistencia_cliente_fecha_uniq'),
        ]
        indexes = [
            models.Index(fields=['sucursal', 'fecha'], name='asistencia_sucursal_fecha_idx'),
        ]
