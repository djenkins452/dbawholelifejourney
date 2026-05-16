"""
Data migration: Refresh all four Gospel reading plans with canonical day content.

The loader (load_gospel_plans) previously used get_or_create for day rows, which
silently dropped `defaults` when a row already existed. Production John (and any
other gospel days seeded during earlier loader iterations) was left holding stale
content — typically missing context summaries, commentary, or reflection prompts —
even though the loader file itself defined rich content for every day.

The loader has been switched to update_or_create, so running it now refreshes
every existing day row with the canonical text fields. This migration runs the
loader once at deploy time so production catches up immediately.

Safe by construction:
- update_or_create keys on (plan, day_number) so day IDs stay stable
- Only text content fields (title, context_summary, commentary_*, reflection_prompt,
  scripture_references) are touched on ReadingPlanDay
- UserReadingProgress (which holds user-authored reflection notes) FKs ReadingPlanDay
  by id and is untouched
"""

from django.db import migrations


def refresh_gospel_plan_content(apps, schema_editor):
    """Re-run the loader so update_or_create backfills canonical content."""
    from django.core.management import call_command

    call_command("load_gospel_plans", verbosity=0)


def reverse_noop(apps, schema_editor):
    """No-op reverse — content refresh is non-destructive."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("faith", "0020_complete_all_gospel_plans"),
    ]

    operations = [
        migrations.RunPython(refresh_gospel_plan_content, reverse_noop),
    ]
