# ==============================================================================
# Data migration: Add 'emotional' to journal module's mapped_domain_keys
#
# The 'emotional' domain is registered as BEHAVIORAL in the domain registry
# (emotion-derived signals from structured journal entries). It must be owned
# by the journal module so registry health validation passes.
# ==============================================================================

from django.db import migrations


def add_emotional_domain(apps, schema_editor):
    ModuleDefinition = apps.get_model('users', 'ModuleDefinition')
    try:
        journal = ModuleDefinition.objects.get(slug='journal')
        if 'emotional' not in (journal.mapped_domain_keys or []):
            keys = list(journal.mapped_domain_keys or [])
            keys.append('emotional')
            journal.mapped_domain_keys = keys
            journal.save(update_fields=['mapped_domain_keys'])
    except ModuleDefinition.DoesNotExist:
        pass


def remove_emotional_domain(apps, schema_editor):
    ModuleDefinition = apps.get_model('users', 'ModuleDefinition')
    try:
        journal = ModuleDefinition.objects.get(slug='journal')
        keys = list(journal.mapped_domain_keys or [])
        if 'emotional' in keys:
            keys.remove('emotional')
            journal.mapped_domain_keys = keys
            journal.save(update_fields=['mapped_domain_keys'])
    except ModuleDefinition.DoesNotExist:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0080_add_sports_module_definition'),
    ]

    operations = [
        migrations.RunPython(add_emotional_domain, remove_emotional_domain),
    ]
