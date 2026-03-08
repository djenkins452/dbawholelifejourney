# Generated manually — data migration to populate Data Dictionary + User Guide

from django.db import migrations


def sync_guides(apps, schema_editor):
    """Run guide sync commands to populate Data Dictionary and User Guide content."""
    from django.core.management import call_command
    from django.db import connection
    try:
        call_command('sync_data_dictionary', verbosity=1)
    except Exception as e:
        print(f'  sync_data_dictionary failed: {e}')
        # Reset connection state if transaction was poisoned
        if connection.needs_rollback:
            connection.cursor()  # Force transaction cleanup
    try:
        # Check if help_helptopic table exists before running sync
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name = 'help_helptopic'"
            )
            if cursor.fetchone():
                call_command('sync_user_guide', verbosity=1)
            else:
                print('  sync_user_guide skipped: help_helptopic table does not exist yet')
    except Exception as e:
        print(f'  sync_user_guide failed: {e}')


class Migration(migrations.Migration):

    dependencies = [
        ('admin_console', '0032_add_guide_type_to_guide_models'),
    ]

    operations = [
        migrations.RunPython(sync_guides, migrations.RunPython.noop),
    ]
