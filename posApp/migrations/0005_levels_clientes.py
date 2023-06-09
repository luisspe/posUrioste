# Generated by Django 4.2 on 2023-04-18 23:18

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('posApp', '0004_salesitems'),
    ]

    operations = [
        migrations.CreateModel(
            name='Levels',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('level', models.CharField(max_length=100)),
            ],
        ),
        migrations.CreateModel(
            name='Clientes',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=50)),
                ('image_source', models.TextField()),
                ('apellido_materno', models.CharField(max_length=50)),
                ('apellido_paterno', models.CharField(max_length=50)),
                ('fecha_nacimiento', models.CharField(blank=True, max_length=100, null=True)),
                ('genero', models.CharField(choices=[('M', 'Hombre'), ('F', 'Mujer')], max_length=10)),
                ('direccion', models.CharField(max_length=200)),
                ('suburbio', models.CharField(max_length=200)),
                ('codigo_postal', models.CharField(max_length=10)),
                ('celular', models.CharField(max_length=12)),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('estado_civil', models.CharField(choices=[('S', 'Soltero'), ('M', 'Casado'), ('D', 'Divorsiado'), ('F', 'Union libre')], max_length=10)),
                ('escucho_de', models.CharField(choices=[('F', 'Facebook'), ('R', 'Recomendacion'), ('T', 'Transito'), ('F', 'Otro')], max_length=10)),
                ('sangre', models.CharField(max_length=50)),
                ('contacto_emergencia', models.CharField(max_length=200)),
                ('emergency_phone', models.CharField(max_length=20)),
                ('pay_day', models.CharField(max_length=200)),
                ('condicion_medica', models.TextField()),
                ('horario', models.TextField()),
                ('nivel', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.DO_NOTHING, to='posApp.levels')),
            ],
        ),
    ]
