# Generated by Django 5.0.12 on 2025-06-12 06:01

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0052_remove_market_transaction_currency1'),
    ]

    operations = [
        migrations.AddField(
            model_name='position',
            name='currency',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='stock.currency', verbose_name='货币'),
        ),
    ]
