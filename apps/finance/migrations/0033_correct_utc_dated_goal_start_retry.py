# ==============================================================================
# File: apps/finance/migrations/0033_correct_utc_dated_goal_start_retry.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Redo of 0032, which silently repaired nothing.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""0032 ran, reported success, and corrected zero rows.

It called `get_user_today(goal.user)`, which reads `preferences.timezone_iana` — a
**@property**. Historical models keep FIELDS but drop properties and methods, so every
row raised `AttributeError: 'UserPreferences' object has no attribute 'timezone_iana'`
and a broad `except Exception: continue` swallowed it. The migration was marked applied
and the Emergency Fund still read "Started August 30".

This one resolves the timezone from the `timezone` FIELD, which historical models do
keep, and reproduces the one line of `timezone_iana` that matters (the legacy-name map)
rather than reaching for the property. Failures are COUNTED and printed instead of
being passed over silently — a repair that cannot report what it skipped is a repair
nobody can trust.

Same conservative guard as before: only a `started_at` in that user's FUTURE is
touched, which is impossible for a start date and is the exact signature of the bug.
Idempotent; a second run corrects nothing.
"""
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import migrations
from django.utils import timezone

#: The legacy names `UserPreferences.timezone_iana` maps. Reproduced deliberately:
#: the property is unavailable here, and importing the live model into a migration
#: would couple this frozen step to whatever that model becomes later.
LEGACY_TZ = {
    "US/Eastern": "America/New_York",
    "US/Central": "America/Chicago",
    "US/Mountain": "America/Denver",
    "US/Pacific": "America/Los_Angeles",
    "US/Alaska": "America/Anchorage",
    "US/Hawaii": "Pacific/Honolulu",
}


def _user_today(user, now):
    """That user's calendar date, from the timezone FIELD."""
    name = "UTC"
    preferences = getattr(user, "preferences", None)
    if preferences is not None:
        name = getattr(preferences, "timezone", None) or "UTC"
    name = LEGACY_TZ.get(name, name)
    try:
        zone = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        zone = dt_timezone.utc
    return now.astimezone(zone).date()


def correct_future_start_dates(apps, schema_editor):
    FinancialGoal = apps.get_model("finance", "FinancialGoal")

    now = timezone.now()
    corrected = skipped = failed = 0

    for goal in FinancialGoal.objects.select_related("user__preferences").exclude(
            user=None):
        try:
            today = _user_today(goal.user, now)
        except Exception as exc:                       # counted, never silent
            failed += 1
            print(f"    Could not resolve a timezone for goal {goal.pk}: "
                  f"{type(exc).__name__}")
            continue

        if goal.started_at and goal.started_at > today:
            goal.started_at = today
            goal.save(update_fields=["started_at"])
            corrected += 1
        else:
            skipped += 1

    print(f"\n    Goal start dates — corrected {corrected}, already correct {skipped}, "
          f"could not resolve {failed}.")


def noop(apps, schema_editor):
    """Not reversible: the previous value was wrong, not merely different."""


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0032_correct_utc_dated_goal_start"),
    ]

    operations = [
        migrations.RunPython(correct_future_start_dates, noop),
    ]
