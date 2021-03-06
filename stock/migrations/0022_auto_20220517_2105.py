# Generated by Django 3.2.6 on 2022-05-17 21:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0021_dividend_history'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dividend_history',
            name='announcement_date',
            field=models.DateField(blank=True, null=True, verbose_name='公告日'),
        ),
        migrations.AlterField(
            model_name='dividend_history',
            name='dividend_date',
            field=models.DateField(blank=True, null=True, verbose_name='派息日'),
        ),
        migrations.AlterField(
            model_name='dividend_history',
            name='ex_right_date',
            field=models.DateField(blank=True, null=True, verbose_name='除权除息日'),
        ),
        migrations.AlterField(
            model_name='dividend_history',
            name='registration_date',
            field=models.DateField(blank=True, null=True, verbose_name='股权登记日'),
        ),
        migrations.AlterField(
            model_name='dividend_history',
            name='reporting_period',
            field=models.CharField(blank=True, max_length=64, null=True, verbose_name='报告期'),
        ),
    ]
