# ==============================================================================
# File: 0024_convert_legacy_timezones.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Data migration to convert legacy US/* timezone names to IANA format
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-02
# Last Updated: 2026-01-02
# ==============================================================================
"""
Data migration to convert legacy timezone names to IANA format.

PostgreSQL requires IANA timezone names (e.g., 'America/New_York') and does not
recognize legacy US/* timezone names (e.g., 'US/Eastern').

This migration converts any existing legacy timezone values in the database to
their IANA equivalents.
"""

from django.db import migrations


# Mapping from legacy timezone names to IANA format
TIMEZONE_LEGACY_MAP = {
    "US/Eastern": "America/New_York",
    "US/Central": "America/Chicago",
    "US/Mountain": "America/Denver",
    "US/Pacific": "America/Los_Angeles",
}


def convert_legacy_timezones(apps, schema_editor):
    """Convert legacy US/* timezone names to IANA format."""
    UserPreferences = apps.get_model('users', 'UserPreferences')

    for legacy_tz, iana_tz in TIMEZONE_LEGACY_MAP.items():
        updated = UserPreferences.objects.filter(timezone=legacy_tz).update(timezone=iana_tz)
        if updated:
            print(f"  Converted {updated} user(s) from {legacy_tz} to {iana_tz}")


def reverse_migration(apps, schema_editor):
    """Reverse the migration - convert IANA back to legacy format."""
    UserPreferences = apps.get_model('users', 'UserPreferences')

    # Reverse mapping
    for legacy_tz, iana_tz in TIMEZONE_LEGACY_MAP.items():
        updated = UserPreferences.objects.filter(timezone=iana_tz).update(timezone=legacy_tz)
        if updated:
            print(f"  Reverted {updated} user(s) from {iana_tz} to {legacy_tz}")


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0023_userpreferences_sms_significant_event_reminders"),
    ]

    operations = [
        migrations.RunPython(
            convert_legacy_timezones,
            reverse_code=reverse_migration,
        ),
    ]
