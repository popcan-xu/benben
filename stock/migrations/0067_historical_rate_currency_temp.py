# Generated by Django 5.0.12 on 2025-06-23 03:08

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0066_remove_historical_position_unique_daily_position_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='historical_rate',
            name='currency_temp',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='stock.currency', verbose_name='临时货币外键'),
        ),
    ]
