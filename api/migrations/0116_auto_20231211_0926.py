# Generated by Django 3.2.8 on 2023-12-11 09:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0115_counttasksmodifier'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='fcm_token',
            field=models.CharField(blank=True, help_text='FCM registration token', max_length=255, null=True),
        )
    ]