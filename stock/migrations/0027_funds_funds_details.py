# Generated by Django 4.0.5 on 2023-01-06 18:34

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0026_remove_market_exchange_rate_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='funds',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('funds_name', models.CharField(db_index=True, max_length=32, unique=True, verbose_name='基金名称')),
                ('funds_script', models.CharField(max_length=32, null=True, verbose_name='备注')),
                ('funds_create_date', models.DateField(blank=True, null=True, verbose_name='基金创立日期')),
                ('funds_value', models.DecimalField(decimal_places=2, default=0.0, max_digits=12, verbose_name='基金价值')),
                ('funds_principal', models.DecimalField(decimal_places=2, default=0.0, max_digits=12, verbose_name='基金本金')),
                ('funds_PHR', models.DecimalField(decimal_places=2, default=0.0, max_digits=12, verbose_name='基金份数')),
                ('funds_net_value', models.DecimalField(decimal_places=4, default=0.0, max_digits=12, verbose_name='基金净值')),
                ('modified_time', models.DateTimeField(auto_now=True, verbose_name='修改时间')),
            ],
        ),
        migrations.CreateModel(
            name='funds_details',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(blank=True, null=True, verbose_name='记账日期')),
                ('funds_value', models.DecimalField(decimal_places=2, default=0.0, max_digits=12, verbose_name='基金价值')),
                ('funds_in_out', models.DecimalField(decimal_places=2, default=0.0, max_digits=12, verbose_name='出入金')),
                ('funds_principal', models.DecimalField(decimal_places=2, default=0.0, max_digits=12, verbose_name='基金本金')),
                ('funds_PHR', models.DecimalField(decimal_places=2, default=0.0, max_digits=12, verbose_name='基金份数')),
                ('funds_net_value', models.DecimalField(decimal_places=4, default=0.0, max_digits=12, verbose_name='基金净值')),
                ('modified_time', models.DateTimeField(auto_now=True, verbose_name='修改时间')),
                ('funds', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='stock.funds', verbose_name='基金')),
            ],
        ),
    ]
