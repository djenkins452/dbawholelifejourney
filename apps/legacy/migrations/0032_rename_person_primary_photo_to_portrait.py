"""Rename Person.primary_photo → Person.portrait.

Conceptually the Person owns a canonical PORTRAIT; the Media model just stores the
file. RenameField preserves the existing column data (no data loss).
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("legacy", "0031_restore_confident_step_parents"),
    ]

    operations = [
        migrations.RenameField(
            model_name="person",
            old_name="primary_photo",
            new_name="portrait",
        ),
    ]
