# Generated by Django 3.2.8 on 2021-11-27 16:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0042_taskstage_is_public'),
    ]

    operations = [
        migrations.AddField(
            model_name='copyfield',
            name='copy_all',
            field=models.BooleanField(default=False, help_text='Copy all fields and ignore fields_to_copy.'),
        ),
        migrations.AlterField(
            model_name='copyfield',
            name='copy_by',
            field=models.CharField(choices=[('US', 'User'), ('CA', 'Case')], default='US', help_text='Where to copy fields from', max_length=2),
        ),
    ]
