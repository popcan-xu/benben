# Generated by Django 5.0.12 on 2025-06-11 06:45

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0049_currency'),
    ]

    operations = [
        migrations.AddField(
            model_name='market',
            name='currency',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='stock.currency', verbose_name='货币'),
        ),
    ]
