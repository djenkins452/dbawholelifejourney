"""
Backfill RoutineSchedule.obligation_type from existing item names.

Uses the canonical name sets from execution_truth_engine to classify
existing routine items, eliminating the need for runtime string matching.
"""

from django.db import migrations


# Copied from apps/core/execution/execution_truth_engine.py to ensure
# the migration is self-contained and doesn't break if names change later.
_WORKOUT_NAMES = frozenset({
    'workout', 'exercise', 'gym', 'training', 'run', 'running',
    'morning workout', 'evening workout', 'cardio', 'strength training',
    'yoga', 'stretching', 'walk', 'walking', 'hike', 'hiking',
    'swim', 'swimming', 'cycling', 'bike', 'fitness',
})

_JOURNAL_NAMES = frozenset({
    'journal', 'journaling', 'journal entry', 'daily journal',
    'morning journal', 'evening journal', 'reflection', 'daily reflection',
    'gratitude journal', 'gratitude',
})

_FAITH_PRAYER_NAMES = frozenset({
    'prayer time', 'prayer', 'morning prayer', 'evening prayer',
})

_FAITH_BIBLE_NAMES = frozenset({
    'bible reading', 'bible study', 'scripture reading', 'devotional',
})


def backfill_obligation_type(apps, schema_editor):
    RoutineSchedule = apps.get_model('life', 'RoutineSchedule')

    for item in RoutineSchedule.objects.filter(obligation_type='', is_active=True):
        name_lower = item.name.lower().strip()
        if name_lower in _WORKOUT_NAMES:
            item.obligation_type = 'workout'
        elif name_lower in _JOURNAL_NAMES:
            item.obligation_type = 'journal'
        elif name_lower in _FAITH_PRAYER_NAMES:
            item.obligation_type = 'faith_prayer'
        elif name_lower in _FAITH_BIBLE_NAMES:
            item.obligation_type = 'faith_bible'
        else:
            continue
        item.save(update_fields=['obligation_type'])


class Migration(migrations.Migration):

    dependencies = [
        ('life', '0045_routine_obligation_type'),
    ]

    operations = [
        migrations.RunPython(
            backfill_obligation_type,
            migrations.RunPython.noop,
        ),
    ]
