# Generated by Django 4.2 on 2023-06-15 21:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('posApp', '0020_sales_comentario'),
    ]

    operations = [
        migrations.AddField(
            model_name='sales',
            name='tendered_amount_card',
            field=models.FloatField(default=0),
        ),
    ]
