# Generated by Django 4.2 on 2024-10-04 23:38

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('posApp', '0024_userprofile'),
    ]

    operations = [
        migrations.AddField(
            model_name='sucursal',
            name='fecha_actualizacion',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name='sucursal',
            name='fecha_creacion',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]
