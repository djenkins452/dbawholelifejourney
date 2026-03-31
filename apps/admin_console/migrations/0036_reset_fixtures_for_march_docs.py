"""
Data migration to reset fixture loaders so they reload with updated content.

Resets: help_topics, teaching_destinations, release_notes

New content:
- 7 new help topics (Dashboard V2, Brain Training Hub, Bulk Recipe Import,
  Morning Reconciliation, Compliance, Goal Cockpit, Behavioral Signals)
- Updated HEALTH_WATER topic with drink types and hydration coefficients
- 5 new teaching destinations (Dashboard V2, Routine Adherence, Routine Migration,
  Signal Insights, Sports Hub)
- 5 new release notes (Hydration Drink Types, Compliance Engine, Physical Intelligence,
  Signals V3, Stale DB Recovery)
"""

from django.db import migrations


def reset_loaders(apps, schema_editor):
    """Reset fixture loaders so they run again on next deploy."""
    DataLoadConfig = apps.get_model('admin_console', 'DataLoadConfig')

    for loader_name in ['help_topics', 'teaching_destinations', 'release_notes']:
        try:
            config = DataLoadConfig.objects.get(loader_name=loader_name)
            config.is_loaded = False
            config.save(update_fields=['is_loaded'])
        except DataLoadConfig.DoesNotExist:
            pass


def noop(apps, schema_editor):
    """No-op for reverse migration."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('admin_console', '0035_embed_data_dictionary'),
    ]

    operations = [
        migrations.RunPython(
            reset_loaders,
            noop,
        ),
    ]
