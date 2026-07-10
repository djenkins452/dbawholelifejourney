# ==============================================================================
# Data migration: enable WRITE (action) tools on the model-interface for the owner.
# The write path is validated (live mutate_task proof) and the "results-not-intentions"
# behavioral rule is now in the constitution. Reverse returns to read-only.
# ==============================================================================
from django.db import migrations

OWNER_EMAIL = "dannyjenkins71@gmail.com"


def enable(apps, schema_editor):
    User = apps.get_model("users", "User")
    UserPreferences = apps.get_model("users", "UserPreferences")
    try:
        user = User.objects.get(email__iexact=OWNER_EMAIL)
    except User.DoesNotExist:
        return
    UserPreferences.objects.filter(user=user).update(use_model_interface_writes=True)


def disable(apps, schema_editor):
    User = apps.get_model("users", "User")
    UserPreferences = apps.get_model("users", "UserPreferences")
    try:
        user = User.objects.get(email__iexact=OWNER_EMAIL)
    except User.DoesNotExist:
        return
    UserPreferences.objects.filter(user=user).update(use_model_interface_writes=False)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0090_enable_model_interface_readonly_for_owner"),
    ]

    operations = [
        migrations.RunPython(enable, disable),
    ]
