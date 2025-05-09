# Generated by Django 4.0.5 on 2023-01-14 15:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0027_funds_funds_details'),
    ]

    operations = [
        migrations.AddField(
            model_name='funds_details',
            name='funds_annualized_profit_rate',
            field=models.DecimalField(decimal_places=2, default=0.0, max_digits=12, verbose_name='基金年化收益率'),
        ),
        migrations.AddField(
            model_name='funds_details',
            name='funds_profit',
            field=models.DecimalField(decimal_places=2, default=0.0, max_digits=12, verbose_name='基金收益'),
        ),
        migrations.AddField(
            model_name='funds_details',
            name='funds_profit_rate',
            field=models.DecimalField(decimal_places=2, default=0.0, max_digits=12, verbose_name='基金收益率'),
        ),
    ]
