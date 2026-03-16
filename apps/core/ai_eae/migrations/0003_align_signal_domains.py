# ==============================================================================
# Phase 4: Align SignalSnapshot domain values with Domain Registry
#
# Historical SignalSnapshot rows used 'mind' as the domain for
# mental_reflection and cognitive_fitness signals. The Domain Registry
# uses 'journal' and 'brain_training' as the canonical domain keys.
# This migration updates existing rows to match.
# ==============================================================================

from django.db import migrations


def align_signal_domains(apps, schema_editor):
    """Update historical SignalSnapshot domain values to registry-aligned keys."""
    SignalSnapshot = apps.get_model('ai_eae', 'SignalSnapshot')

    # mental_reflection: 'mind' -> 'journal'
    updated_journal = SignalSnapshot.objects.filter(
        signal_type='mental_reflection',
        domain='mind',
    ).update(domain='journal')

    # cognitive_fitness: 'mind' -> 'brain_training'
    updated_bt = SignalSnapshot.objects.filter(
        signal_type='cognitive_fitness',
        domain='mind',
    ).update(domain='brain_training')

    if updated_journal or updated_bt:
        print(
            f"  Phase 4: Aligned signal domains — "
            f"mental_reflection: {updated_journal} rows -> 'journal', "
            f"cognitive_fitness: {updated_bt} rows -> 'brain_training'"
        )


def reverse_signal_domains(apps, schema_editor):
    """Reverse: restore 'mind' domain for mental_reflection and cognitive_fitness."""
    SignalSnapshot = apps.get_model('ai_eae', 'SignalSnapshot')

    SignalSnapshot.objects.filter(
        signal_type='mental_reflection',
        domain='journal',
    ).update(domain='mind')

    SignalSnapshot.objects.filter(
        signal_type='cognitive_fitness',
        domain='brain_training',
    ).update(domain='mind')


class Migration(migrations.Migration):

    dependencies = [
        ('ai_eae', '0002_signalsnapshot'),
    ]

    operations = [
        migrations.RunPython(
            align_signal_domains,
            reverse_signal_domains,
        ),
    ]
