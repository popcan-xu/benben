# Generated by Django 3.2.6 on 2021-08-24 03:01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0012_auto_20210815_1928'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dividend',
            name='dividend_per_share',
            field=models.DecimalField(decimal_places=3, default=0.0, max_digits=8, verbose_name='每股分红'),
        ),
    ]
