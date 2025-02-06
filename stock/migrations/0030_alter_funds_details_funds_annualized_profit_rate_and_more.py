# Generated by Django 4.0.5 on 2025-01-14 14:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0029_funds_details_funds_current_profit_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='funds_details',
            name='funds_annualized_profit_rate',
            field=models.DecimalField(decimal_places=4, default=0.0, max_digits=12, verbose_name='基金年化收益率'),
        ),
        migrations.AlterField(
            model_name='funds_details',
            name='funds_current_profit_rate',
            field=models.DecimalField(decimal_places=4, default=0.0, max_digits=12, verbose_name='基金当期收益率'),
        ),
        migrations.AlterField(
            model_name='funds_details',
            name='funds_profit_rate',
            field=models.DecimalField(decimal_places=4, default=0.0, max_digits=12, verbose_name='基金收益率'),
        ),
    ]
