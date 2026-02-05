# ==============================================================================
# File: apps/users/migrations/0060_cleanup_invalid_bible_ids.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Clean up invalid Bible translation IDs from user preferences
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-05
# ==============================================================================
"""
Data migration to clean up invalid Bible translation IDs.

After migrating from API.Bible (UUID format) to YouVersion (numeric IDs),
some users may have old API.Bible IDs saved in their default_bible_translation
preference. This migration clears those invalid IDs.

Valid YouVersion Bible IDs are numeric (e.g., "111" for NIV, "3034" for BSB).
Invalid IDs include:
- Old API.Bible UUIDs (e.g., "de4e12af7f28f599-02")
- Non-numeric strings
- Empty strings are already handled by the model default
"""

from django.db import migrations


def cleanup_invalid_bible_ids(apps, schema_editor):
    """
    Clear default_bible_translation if it contains an invalid YouVersion ID.

    Valid YouVersion IDs are purely numeric. Anything else (UUIDs, letters, etc.)
    is cleared so the user gets the default fallback.
    """
    UserPreferences = apps.get_model('users', 'UserPreferences')

    # Find preferences with non-numeric Bible IDs
    invalid_prefs = []
    for pref in UserPreferences.objects.exclude(default_bible_translation=''):
        bible_id = pref.default_bible_translation
        # Valid YouVersion IDs are numeric only
        if not bible_id.isdigit():
            invalid_prefs.append(pref.pk)

    if invalid_prefs:
        count = UserPreferences.objects.filter(pk__in=invalid_prefs).update(
            default_bible_translation=''
        )
        print(f"\n  Cleared {count} invalid Bible translation IDs from user preferences")
    else:
        print("\n  No invalid Bible translation IDs found")


def noop_reverse(apps, schema_editor):
    """No reverse - we can't restore old invalid IDs."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0059_add_proactive_checkin_preferences'),
    ]

    operations = [
        migrations.RunPython(cleanup_invalid_bible_ids, noop_reverse),
    ]
