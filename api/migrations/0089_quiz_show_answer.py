# Generated by Django 3.2.8 on 2023-03-28 11:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0088_auto_20230327_0714'),
    ]

    operations = [
        migrations.AddField(
            model_name='quiz',
            name='show_answer',
            field=models.CharField(choices=[('NE', 'Never'), ('AL', 'Always'), ('FA', 'On Fail'), ('PS', 'On Pass')], default='FA', max_length=2),
        ),
    ]