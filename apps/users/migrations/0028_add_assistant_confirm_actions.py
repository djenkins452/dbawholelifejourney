# Generated manually for assistant_confirm_actions preference

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0027_signup_security'),
    ]

    operations = [
        migrations.AddField(
            model_name='userpreferences',
            name='assistant_confirm_actions',
            field=models.BooleanField(
                default=False,
                help_text='Require confirmation before AI assistant logs health data (default: log immediately)',
            ),
        ),
    ]
