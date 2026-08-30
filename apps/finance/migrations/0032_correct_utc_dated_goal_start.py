# ==============================================================================
# File: apps/finance/migrations/0032_correct_utc_dated_goal_start.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Repair goal start dates that were stamped in UTC, not the user's day.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""`started_at` defaulted to `timezone.now` — a UTC *datetime* coerced into a DateField.

For anyone west of Greenwich creating a goal in the evening, that stored TOMORROW: a
goal created 21:45 on Aug 29 in New York was saved as Aug 30 and the page read
"Started August 30" to someone for whom it was still the 29th.

The default is now `timezone.localdate` and the create view narrows it to the user's own
day, so this cannot recur. This migration repairs the rows already stored that way.

Deliberately conservative: it only touches a goal whose `started_at` is in that user's
FUTURE, which is impossible for a start date and is the exact signature of the bug. A
legitimately back-dated or today-dated goal is left alone, and re-running changes
nothing.
"""
from django.db import migrations


def correct_future_start_dates(apps, schema_editor):
    FinancialGoal = apps.get_model("finance", "FinancialGoal")
    from apps.core.utils import get_user_today

    corrected = 0
    for goal in FinancialGoal.objects.select_related("user").exclude(user=None):
        try:
            today = get_user_today(goal.user)
        except Exception:
            continue
        if goal.started_at and goal.started_at > today:
            goal.started_at = today
            goal.save(update_fields=["started_at"])
            corrected += 1

    if corrected:
        print(f"\n    Corrected {corrected} goal start date(s) stamped in UTC.")


def noop(apps, schema_editor):
    """Not reversible on purpose — the previous value was wrong, not merely different."""


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0031_goal_started_at_local_date"),
    ]

    operations = [
        migrations.RunPython(correct_future_start_dates, noop),
    ]
