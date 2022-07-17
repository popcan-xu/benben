# Generated by Django 2.1.7 on 2021-06-26 05:53

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0003_auto_20210625_1445'),
    ]

    operations = [
        migrations.CreateModel(
            name='industry',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('industry_code', models.CharField(max_length=32, unique=True, verbose_name='行业代码')),
                ('industry_name', models.CharField(max_length=32, verbose_name='行业名称')),
                ('industry_abbreviation', models.CharField(max_length=32, verbose_name='行业简称')),
            ],
        ),
        migrations.AddField(
            model_name='stock',
            name='industry',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to='stock.industry', verbose_name='行业'),
            preserve_default=False,
        ),
    ]
