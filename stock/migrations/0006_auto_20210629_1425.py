# Generated by Django 2.1.7 on 2021-06-29 06:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0005_trade_filed_time'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trade',
            name='filed_time',
            field=models.DateTimeField(default='1900-01-01 00:00:00', verbose_name='归档时间'),
        ),
    ]
