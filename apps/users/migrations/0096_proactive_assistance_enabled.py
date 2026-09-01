# ==============================================================================
# File: apps/users/migrations/0096_proactive_assistance_enabled.py
# Description: Rename the assistant module toggle to what it now means.
# ==============================================================================
"""`personal_assistant_enabled` -> `proactive_assistance_enabled`.

The field was a module switch: turning it off removed the Chief of Staff completely —
every entry point vanished and the chat API refused. Someone who only wanted to stop
being interrupted had to give up the assistant to do it.

It now means one thing: may the Chief of Staff start something on its own. Access is
governed by consent (`personal_assistant_consent`), which is untouched here.

`RenameField` carries every existing value across, so nobody's choice changes: if it
used to interrupt you it still does, and if it did not it still does not.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0095_userpreferences_knowledge_invitations"),
    ]

    operations = [
        migrations.RenameField(
            model_name="userpreferences",
            old_name="personal_assistant_enabled",
            new_name="proactive_assistance_enabled",
        ),
        migrations.AlterField(
            model_name="userpreferences",
            name="proactive_assistance_enabled",
            field=models.BooleanField(
                default=False,
                verbose_name="Proactive assistance",
                help_text=(
                    "Let the Chief of Staff start things on its own — daily check-ins, "
                    "briefings, suggestions and the expanded panel. Turn this off and it "
                    "stays quiet until you open it; you keep full access from the menu."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="userpreferences",
            name="personal_assistant_consent",
            field=models.BooleanField(
                default=False,
                verbose_name="Chief of Staff",
                help_text=(
                    "User consents to Personal Assistant accessing journal entries, "
                    "tasks, goals, health data for personalized coaching"
                ),
            ),
        ),
    ]
