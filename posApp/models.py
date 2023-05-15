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

class Genero(models.Model):
    genero = models.CharField(max_length=20)

    def __str__(self):
        return str(self.genero)




class Levels(models.Model):
    level = models.CharField(max_length=100)

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

    def __str__(self):
        return str(self.nombre)

class Category(models.Model):
    name = models.TextField()
    description = models.TextField()
    status = models.IntegerField(default=1) 
    date_added = models.DateTimeField(default=timezone.now) 
    date_updated = models.DateTimeField(auto_now=True) 

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
    amount_change = models.FloatField(default=0)
    date_added = models.DateTimeField(default=timezone.now) 
    date_updated = models.DateTimeField(auto_now=True)
    client = models.ForeignKey(Clientes, on_delete=models.CASCADE)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    tipoPago = models.ForeignKey(FormaPago, on_delete=models.CASCADE) 
    
    def __str__(self):
        return self.code

class salesItems(models.Model):
    sale_id = models.ForeignKey(Sales,on_delete=models.CASCADE)
    product_id = models.ForeignKey(Products,on_delete=models.CASCADE)
    price = models.FloatField(default=0)
    qty = models.FloatField(default=0)
    total = models.FloatField(default=0)
    client = models.ForeignKey(Clientes, on_delete=models.CASCADE)
    


