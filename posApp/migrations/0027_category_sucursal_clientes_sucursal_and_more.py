# Generated by Django 4.2 on 2024-10-05 00:40

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('posApp', '0026_salida_planinscripcion_mensualidad'),
    ]

    operations = [
        migrations.AddField(
            model_name='category',
            name='sucursal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='posApp.sucursal'),
        ),
        migrations.AddField(
            model_name='clientes',
            name='sucursal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='posApp.sucursal'),
        ),
        migrations.AddField(
            model_name='products',
            name='sucursal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='posApp.sucursal'),
        ),
        migrations.AddField(
            model_name='sales',
            name='sucursal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='posApp.sucursal'),
        ),
        migrations.AddField(
            model_name='salesitems',
            name='sucursal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='posApp.sucursal'),
        ),
    ]
