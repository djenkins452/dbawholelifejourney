# Generated migration for AI personal profile feature

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0015_add_biometric_login'),
    ]

    operations = [
        migrations.AddField(
            model_name='userpreferences',
            name='ai_profile',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Personal details for AI personalization (age, family, interests, goals, health conditions, etc.)',
            ),
        ),
    ]
