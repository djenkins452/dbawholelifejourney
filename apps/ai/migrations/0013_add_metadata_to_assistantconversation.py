# Generated manually for Task #193

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai', '0012_add_refresh_frequency_to_prompt_config'),
    ]

    operations = [
        migrations.AddField(
            model_name='assistantconversation',
            name='metadata',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Additional conversation state data',
            ),
        ),
    ]
