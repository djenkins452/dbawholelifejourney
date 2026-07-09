# ==============================================================================
# Data migration: enable the model-interface runtime for the owner in READ-ONLY.
# Sets use_model_interface=True, use_model_interface_writes=False (no write tools).
# Reverse disables it (rollback is also a one-flag admin toggle).
# ==============================================================================
from django.db import migrations

OWNER_EMAIL = "dannyjenkins71@gmail.com"


def enable(apps, schema_editor):
    User = apps.get_model("users", "User")
    UserPreferences = apps.get_model("users", "UserPreferences")
    try:
        user = User.objects.get(email__iexact=OWNER_EMAIL)
    except User.DoesNotExist:
        return  # safe no-op if the account isn't present in this environment
    UserPreferences.objects.filter(user=user).update(
        use_model_interface=True,
        use_model_interface_writes=False,   # READ-ONLY stage
    )


def disable(apps, schema_editor):
    User = apps.get_model("users", "User")
    UserPreferences = apps.get_model("users", "UserPreferences")
    try:
        user = User.objects.get(email__iexact=OWNER_EMAIL)
    except User.DoesNotExist:
        return
    UserPreferences.objects.filter(user=user).update(use_model_interface=False)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0089_userpreferences_use_model_interface_writes"),
    ]

    operations = [
        migrations.RunPython(enable, disable),
    ]
