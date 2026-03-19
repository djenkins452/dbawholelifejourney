"""
Data migration: Fix routines and schedule items created with is_active=False.

Root cause: The RoutineForm included is_active in Meta.fields, but the create
template only rendered the checkbox during edit. Django interpreted the missing
checkbox as False, so all routines created before the code fix were saved with
is_active=False — making them invisible to all queries.

This migration repairs existing records by setting is_active=True for:
  - Routine records with status='active' but is_active=False
  - RoutineSchedule records with status='active' (via routine) but is_active=False
"""

from django.db import migrations


def fix_routine_is_active(apps, schema_editor):
    Routine = apps.get_model('life', 'Routine')
    RoutineSchedule = apps.get_model('life', 'RoutineSchedule')

    # Fix routines: status=active means user hasn't deleted them,
    # so is_active should be True (they were only False due to the form bug)
    routines_fixed = Routine.objects.filter(
        status='active', is_active=False
    ).update(is_active=True)

    # Fix schedule items: same bug affected the formset
    items_fixed = RoutineSchedule.objects.filter(
        is_active=False,
        routine__status='active',
    ).update(is_active=True)

    if routines_fixed or items_fixed:
        print(f"\n  Fixed {routines_fixed} routine(s) and {items_fixed} schedule item(s) with is_active=False")


def reverse_noop(apps, schema_editor):
    pass  # Cannot reverse — we don't know which were originally False


class Migration(migrations.Migration):
    dependencies = [
        ('life', '0033_task_is_foundational'),
    ]

    operations = [
        migrations.RunPython(fix_routine_is_active, reverse_noop),
    ]
