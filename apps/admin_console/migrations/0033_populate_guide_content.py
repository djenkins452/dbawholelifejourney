# Generated manually — data migration to populate Data Dictionary + User Guide

from django.db import migrations


def sync_guides(apps, schema_editor):
    """Run guide sync commands to populate Data Dictionary and User Guide content."""
    from django.core.management import call_command
    from django.db import connection

    # Each call must be wrapped in a savepoint so that if it fails
    # (e.g. help_helptopic table doesn't exist yet during test DB creation),
    # PostgreSQL can roll back just that savepoint without aborting the
    # entire migration transaction.
    for cmd_name in ('sync_data_dictionary', 'sync_user_guide'):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SAVEPOINT _migration_guide_sync")
            call_command(cmd_name, verbosity=1)
            with connection.cursor() as cursor:
                cursor.execute("RELEASE SAVEPOINT _migration_guide_sync")
        except Exception as e:
            print(f'  {cmd_name} failed: {e}')
            try:
                with connection.cursor() as cursor:
                    cursor.execute("ROLLBACK TO SAVEPOINT _migration_guide_sync")
            except Exception:
                pass


class Migration(migrations.Migration):

    dependencies = [
        ('admin_console', '0032_add_guide_type_to_guide_models'),
    ]

    operations = [
        migrations.RunPython(sync_guides, migrations.RunPython.noop),
    ]
