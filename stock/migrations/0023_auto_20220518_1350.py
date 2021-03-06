# Generated by Django 3.2.6 on 2022-05-18 13:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0022_auto_20220517_2105'),
    ]

    operations = [
        migrations.AddField(
            model_name='stock',
            name='last_dividend_date',
            field=models.DateField(blank=True, null=True, verbose_name='上次分红日期'),
        ),
        migrations.AddField(
            model_name='stock',
            name='next_dividend_date',
            field=models.DateField(blank=True, null=True, verbose_name='下次分红日期'),
        ),
    ]
