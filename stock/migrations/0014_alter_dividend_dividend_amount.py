# Generated by Django 3.2.6 on 2021-08-24 06:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0013_alter_dividend_dividend_per_share'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dividend',
            name='dividend_amount',
            field=models.DecimalField(decimal_places=2, max_digits=8, verbose_name='分红金额（税后）'),
        ),
    ]
