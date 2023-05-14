# Generated by Django 4.2 on 2023-04-26 00:10

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('posApp', '0014_sales_client'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='sales',
            name='client',
        ),
        migrations.AddField(
            model_name='salesitems',
            name='client',
            field=models.ForeignKey(default='1', on_delete=django.db.models.deletion.CASCADE, to='posApp.clientes'),
            preserve_default=False,
        ),
    ]
