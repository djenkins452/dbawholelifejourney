# ==============================================================================
# Data migration: enable the Faith "First Light — Formation" experience for the
# owner (Danny) so it can be validated in production while remaining OFF for
# everyone else. First Light is stored in the faith_features JSONField under the
# 'first_light' key. Reverse turns it back off (rollback is a one-flag toggle).
# ==============================================================================
from django.db import migrations

OWNER_EMAIL = "dannyjenkins71@gmail.com"


def _set_first_light(apps, value):
    User = apps.get_model("users", "User")
    UserPreferences = apps.get_model("users", "UserPreferences")
    try:
        user = User.objects.get(email__iexact=OWNER_EMAIL)
    except User.DoesNotExist:
        return  # safe no-op if the account isn't present in this environment
    prefs = UserPreferences.objects.filter(user=user).first()
    if prefs is None:
        return
    features = dict(prefs.faith_features or {})
    features["first_light"] = value
    prefs.faith_features = features
    prefs.save(update_fields=["faith_features"])


def enable(apps, schema_editor):
    _set_first_light(apps, True)


def disable(apps, schema_editor):
    _set_first_light(apps, False)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0092_remove_userpreferences_carbs_percentage_and_more"),
    ]

    operations = [
        migrations.RunPython(enable, disable),
    ]
