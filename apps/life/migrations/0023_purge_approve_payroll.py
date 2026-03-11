"""
Data migration to purge all "Approve Payroll" corrupted objects.

Removes:
- LifeTask instances (including soft-deleted, recurring series)
- CalendarEvent instances (including recurring series)
- Orphaned RecurrenceRule records (no linked event)
"""

from django.db import migrations


def purge_approve_payroll(apps, schema_editor):
    Task = apps.get_model('life', 'Task')
    CalendarEvent = apps.get_model('calendar_engine', 'CalendarEvent')
    RecurrenceRule = apps.get_model('calendar_engine', 'RecurrenceRule')

    # 1. Hard-delete all "Approve Payroll" tasks (including soft-deleted)
    task_qs = Task.objects.filter(title__icontains='Approve Payroll')
    t_count, _ = task_qs.delete()

    # 2. Hard-delete all "Approve Payroll" calendar events
    event_qs = CalendarEvent.objects.filter(title__icontains='Approve Payroll')
    e_count, _ = event_qs.delete()

    # 3. Clean up orphaned recurrence rules
    orphan_qs = RecurrenceRule.objects.filter(event__isnull=True)
    r_count, _ = orphan_qs.delete()

    if t_count or e_count or r_count:
        print(
            f"\n  Purged Approve Payroll: "
            f"{t_count} tasks, {e_count} events, {r_count} orphan rules"
        )


class Migration(migrations.Migration):

    dependencies = [
        ('life', '0022_commitment_level'),
        ('calendar_engine', '0008_declinedsuggestion'),
    ]

    operations = [
        migrations.RunPython(
            purge_approve_payroll,
            migrations.RunPython.noop,
        ),
    ]
