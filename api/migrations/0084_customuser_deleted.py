# Generated by Django 3.2.8 on 2023-01-18 06:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0083_webhook_which_responses'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='deleted',
            field=models.BooleanField(default=False, help_text='Is user deleted.'),
        ),
    ]