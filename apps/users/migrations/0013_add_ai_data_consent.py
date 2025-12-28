# Generated manually for Security Fix C-3
# Adds explicit AI data consent field to UserPreferences

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0012_update_coaching_style_field'),
    ]

    operations = [
        migrations.AddField(
            model_name='userpreferences',
            name='ai_data_consent',
            field=models.BooleanField(
                default=False,
                help_text='User has consented to AI processing of their personal data (journal entries, health data, etc.)',
            ),
        ),
        migrations.AddField(
            model_name='userpreferences',
            name='ai_data_consent_date',
            field=models.DateTimeField(
                blank=True,
                help_text='Date when user consented to AI data processing',
                null=True,
            ),
        ),
    ]
