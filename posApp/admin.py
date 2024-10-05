from django.contrib import admin
from posApp.models import Category, Products, Sales, salesItems, Clientes, Genero, Levels, FormaPago, UserProfile, Sucursal,Salida, PlanInscripcion, Mensualidad

# Register your models here.
admin.site.register(Category)
admin.site.register(Products)
admin.site.register(Sales)
admin.site.register(salesItems)
admin.site.register(Clientes)
admin.site.register(Genero)
admin.site.register(Levels)
admin.site.register(FormaPago)
admin.site.register(UserProfile)
admin.site.register(Sucursal)
admin.site.register(Salida)
admin.site.register(PlanInscripcion)
admin.site.register(Mensualidad)
# admin.site.register(Employees)
