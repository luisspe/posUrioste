# Generated by Django 4.2 on 2023-04-20 17:31

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('posApp', '0009_remove_clientes_image_source'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientes',
            name='genero',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.DO_NOTHING, to='posApp.genero'),
        ),
    ]
