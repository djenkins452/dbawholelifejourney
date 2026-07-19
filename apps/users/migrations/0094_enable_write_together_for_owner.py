# ==============================================================================
# Data migration: enable the Journal "Write Together" experience (Chief of Staff
# writing companion — Milestone 1) for the owner (Danny) so the intended M1
# experience — the quiet three-method intro row (Just Write / Write Together /
# Talk It Through) plus the Write Together companion — can be validated in
# production while remaining OFF for everyone else.
#
# The compose page gates on BOTH the 'write_together' key in the journal_features
# JSONField AND personal_assistant_enabled, so this ensures both for the owner
# (it only turns PA on if it was off — it never disables it). Reverse turns the
# preview flag back off (a one-flag toggle) and leaves the CoS setting untouched.
# ==============================================================================
from django.db import migrations

OWNER_EMAIL = "dannyjenkins71@gmail.com"


def _set_write_together(apps, value, ensure_pa):
    User = apps.get_model("users", "User")
    UserPreferences = apps.get_model("users", "UserPreferences")
    try:
        user = User.objects.get(email__iexact=OWNER_EMAIL)
    except User.DoesNotExist:
        return  # safe no-op if the account isn't present in this environment
    prefs = UserPreferences.objects.filter(user=user).first()
    if prefs is None:
        return

    features = dict(prefs.journal_features or {})
    features["write_together"] = value
    prefs.journal_features = features
    update_fields = ["journal_features"]

    # The compose page also requires the Chief of Staff to be enabled. Only turn
    # it on (never off) so validating the preview doesn't fight an existing choice.
    if ensure_pa and value and not prefs.personal_assistant_enabled:
        prefs.personal_assistant_enabled = True
        update_fields.append("personal_assistant_enabled")

    prefs.save(update_fields=update_fields)


def enable(apps, schema_editor):
    _set_write_together(apps, True, ensure_pa=True)


def disable(apps, schema_editor):
    _set_write_together(apps, False, ensure_pa=False)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0093_enable_first_light_for_owner"),
    ]

    operations = [
        migrations.RunPython(enable, disable),
    ]
