# ==============================================================================
# Data migration: make the owner Alpha User #1 for the ChatGPT CoS.
# Enables UserPreferences.use_chatgpt_cos for the owner account on deploy.
# Reverse disables it (zero-deploy rollback also available via admin toggle).
# ==============================================================================
from django.db import migrations

OWNER_EMAIL = "dannyjenkins71@gmail.com"


def _set_for_owner(apps, value):
    User = apps.get_model("users", "User")
    UserPreferences = apps.get_model("users", "UserPreferences")
    try:
        user = User.objects.get(email__iexact=OWNER_EMAIL)
    except User.DoesNotExist:
        return  # safe no-op if the account isn't present in this environment
    UserPreferences.objects.filter(user=user).update(use_chatgpt_cos=value)


def enable(apps, schema_editor):
    _set_for_owner(apps, True)


def disable(apps, schema_editor):
    _set_for_owner(apps, False)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0085_userpreferences_use_chatgpt_cos"),
    ]

    operations = [
        migrations.RunPython(enable, disable),
    ]
