# Generated by Django 2.1.7 on 2021-06-29 06:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0006_auto_20210629_1425'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trade',
            name='filed_time',
            field=models.DateTimeField(default='2006-10-25 14:30:59.000200', verbose_name='归档时间'),
        ),
    ]
