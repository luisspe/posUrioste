# Generated by Django 4.2 on 2025-06-16 17:13

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('posApp', '0033_alter_sales_client'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sales',
            name='date_added',
            field=models.DateTimeField(db_index=True, default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name='sales',
            name='tipoPago',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='posApp.formapago'),
        ),
    ]
