# Generated by Django 4.0.5 on 2025-02-27 13:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0036_historical_position_unique_daily_position'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='historical_position',
            index=models.Index(fields=['stock_id', 'currency'], name='idx_stock_currency'),
        ),
        migrations.AlterModelTable(
            name='historical_position',
            table='historical_position',
        ),
        migrations.AlterModelTable(
            name='trade',
            table='trade',
        ),
    ]
