# Generated manually — data migration to populate Data Dictionary + User Guide

from django.db import migrations


def sync_guides(apps, schema_editor):
    """Run guide sync commands to populate Data Dictionary and User Guide content."""
    from django.core.management import call_command
    try:
        call_command('sync_data_dictionary', verbosity=1)
    except Exception as e:
        print(f'  sync_data_dictionary failed: {e}')
    try:
        call_command('sync_user_guide', verbosity=1)
    except Exception as e:
        print(f'  sync_user_guide failed: {e}')


class Migration(migrations.Migration):

    dependencies = [
        ('admin_console', '0032_add_guide_type_to_guide_models'),
    ]

    operations = [
        migrations.RunPython(sync_guides, migrations.RunPython.noop),
    ]
