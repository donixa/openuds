# Generated by Django 3.0.3 on 2020-02-08 18:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('uds', '0036_auto_20200131_1224'),
    ]

    operations = [
        migrations.AddField(
            model_name='service',
            name='token',
            field=models.CharField(blank=True, default=None, max_length=32, null=True, unique=True),
        ),
    ]
