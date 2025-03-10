# Generated by Django 5.0.12 on 2025-03-04 09:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0039_historical_position_closing_price'),
    ]

    operations = [
        migrations.CreateModel(
            name='historical_rate',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(verbose_name='日期')),
                ('currency', models.CharField(max_length=16, verbose_name='货币')),
                ('rate', models.DecimalField(decimal_places=4, max_digits=8, verbose_name='汇率')),
            ],
            options={
                'indexes': [models.Index(fields=['date', 'currency'], name='idx_date_currency')],
            },
        ),
    ]
