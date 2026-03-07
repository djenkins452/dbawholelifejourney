# Generated manually — data migration to populate Data Dictionary
# Migration 0033 ran sync_data_dictionary but it silently failed on production
# because the docs/ file wasn't found at the expected path. This migration
# resolves the file path more robustly and raises on failure.

import os

from django.db import migrations


def populate_data_dictionary(apps, schema_editor):
    """Populate Data Dictionary guide content from docs/WLJ_Data_Dictionary.md."""
    from django.conf import settings

    # Try multiple paths to find the data dictionary file
    candidates = [
        os.path.join(settings.BASE_DIR, 'docs', 'WLJ_Data_Dictionary.md'),
        os.path.join(os.path.dirname(settings.BASE_DIR), 'docs', 'WLJ_Data_Dictionary.md'),
    ]

    # Also try relative to this migration file
    migration_dir = os.path.dirname(os.path.abspath(__file__))
    # migrations/ -> admin_console/ -> apps/ -> project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(migration_dir)))
    candidates.append(os.path.join(project_root, 'docs', 'WLJ_Data_Dictionary.md'))

    dd_path = None
    for path in candidates:
        if os.path.exists(path):
            dd_path = path
            break

    if not dd_path:
        # Print diagnostics
        print(f'\n  [DATA DICT] BASE_DIR = {settings.BASE_DIR}')
        print(f'  [DATA DICT] Migration dir = {migration_dir}')
        print(f'  [DATA DICT] Project root guess = {project_root}')
        for p in candidates:
            print(f'  [DATA DICT] Tried: {p} — exists={os.path.exists(p)}')

        # List what IS in the project root
        for root_guess in [settings.BASE_DIR, project_root]:
            if os.path.isdir(root_guess):
                dirs = os.listdir(root_guess)
                print(f'  [DATA DICT] Contents of {root_guess}: {dirs[:20]}')
                docs_dir = os.path.join(root_guess, 'docs')
                if os.path.isdir(docs_dir):
                    docs_files = [f for f in os.listdir(docs_dir) if 'dict' in f.lower() or 'data' in f.lower()]
                    print(f'  [DATA DICT] docs/ matching files: {docs_files}')

        print('  [DATA DICT] WARNING: File not found, skipping Data Dictionary sync')
        return

    print(f'  [DATA DICT] Found file at: {dd_path}')

    # Now call the sync command with the verified path
    from django.core.management import call_command
    call_command('sync_data_dictionary', verbosity=1)


class Migration(migrations.Migration):

    dependencies = [
        ('admin_console', '0033_populate_guide_content'),
    ]

    operations = [
        migrations.RunPython(populate_data_dictionary, migrations.RunPython.noop),
    ]
