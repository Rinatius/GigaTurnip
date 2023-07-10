# Generated by Django 3.2.8 on 2023-06-19 09:52

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0102_alter_webhook_url'),
    ]

    operations = [
        migrations.CreateModel(
            name='TranslateKey',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(help_text='Hash text for text.', max_length=64)),
                ('text', models.TextField(help_text='Text to translation.')),
                ('campaign', models.ForeignKey(help_text='Campaign that translate text.', on_delete=django.db.models.deletion.CASCADE, to='api.campaign')),
            ],
            options={
                'unique_together': {('campaign', 'key')},
            },
        ),
        migrations.AlterField(
            model_name='adminpreference',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, help_text='Time of creation'),
        ),
        migrations.AlterField(
            model_name='adminpreference',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, help_text='Last update time'),
        ),
        migrations.AlterField(
            model_name='autonotification',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, help_text='Time of creation'),
        ),
        migrations.AlterField(
            model_name='autonotification',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, help_text='Last update time'),
        ),
        migrations.AlterField(
            model_name='notification',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, help_text='Time of creation'),
        ),
        migrations.AlterField(
            model_name='notification',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, help_text='Last update time'),
        ),
        migrations.AlterField(
            model_name='notificationstatus',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, help_text='Time of creation'),
        ),
        migrations.AlterField(
            model_name='notificationstatus',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, help_text='Last update time'),
        ),
        migrations.CreateModel(
            name='TranslationAdapter',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, help_text='Time of creation')),
                ('updated_at', models.DateTimeField(auto_now=True, help_text='Last update time')),
                ('source', models.ForeignKey(help_text='From what language text must be translated.', on_delete=django.db.models.deletion.CASCADE, related_name='source_translations', to='api.language')),
                ('stage', models.OneToOneField(help_text='Which stage modifier.', on_delete=django.db.models.deletion.CASCADE, related_name='translation_adapter', to='api.taskstage')),
                ('target', models.ForeignKey(help_text='On what language text mus be translated.', on_delete=django.db.models.deletion.CASCADE, related_name='target_translations', to='api.language')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Translation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.TextField(help_text='Translations.')),
                ('status', models.CharField(choices=[('AN', 'ANSWERED'), ('PE', 'PENDING'), ('FR', 'FREE')], default='FR', help_text='Status of translation answer.', max_length=2)),
                ('key', models.ForeignKey(blank=True, help_text='All translations for the key.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='translations', to='api.translatekey')),
                ('language', models.ForeignKey(blank=True, help_text='All translations for the key.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='translations', to='api.language')),
            ],
            options={
                'unique_together': {('key', 'language')},
            },
        ),
    ]
