# Generated by Django 2.1.7 on 2021-06-02 05:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='broker',
            name='broker_script',
            field=models.CharField(max_length=32, null=True, verbose_name='备注'),
        ),
        migrations.AlterField(
            model_name='account',
            name='account_number',
            field=models.CharField(max_length=32, unique=True, verbose_name='账号'),
        ),
        migrations.AlterField(
            model_name='broker',
            name='broker_name',
            field=models.CharField(max_length=32, unique=True, verbose_name='券商名称'),
        ),
        migrations.AlterField(
            model_name='market',
            name='market_name',
            field=models.CharField(max_length=32, unique=True, verbose_name='市场名称'),
        ),
        migrations.AlterField(
            model_name='stock',
            name='stock_code',
            field=models.CharField(max_length=32, unique=True, verbose_name='股票代码'),
        ),
    ]
