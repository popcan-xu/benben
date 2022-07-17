# Generated by Django 2.1.7 on 2021-06-29 07:11

import datetime
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0010_auto_20210629_1503'),
    ]

    operations = [
        migrations.CreateModel(
            name='trade',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('trade_date', models.DateField(verbose_name='交易日期')),
                ('trade_type', models.PositiveIntegerField(choices=[(1, '买入'), (2, '卖出')], default=1, verbose_name='交易类型')),
                ('trade_quantity', models.IntegerField(default=0, verbose_name='交易数量')),
                ('trade_price', models.DecimalField(decimal_places=3, max_digits=8, verbose_name='交易价格')),
                ('filed_time', models.DateTimeField(default=datetime.datetime(1970, 1, 1, 0, 0), verbose_name='归档时间')),
                ('created_time', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('modified_time', models.DateTimeField(auto_now=True, verbose_name='修改时间')),
                ('account', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='stock.account', verbose_name='证券账户')),
                ('stock', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='stock.stock', verbose_name='股票')),
            ],
        ),
    ]