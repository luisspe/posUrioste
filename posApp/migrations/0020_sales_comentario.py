# Generated by Django 4.2 on 2023-06-14 02:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('posApp', '0019_sales_usuario'),
    ]

    operations = [
        migrations.AddField(
            model_name='sales',
            name='comentario',
            field=models.CharField(max_length=300, null=True),
        ),
    ]
