"""
Update theme choices and default to new personality-based themes.

Generated 2026-01-27
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0056_add_custom_theme_colors'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userpreferences',
            name='theme',
            field=models.CharField(
                choices=[
                    ('scholar', 'Scholar'),
                    ('momentum', 'Momentum'),
                    ('wanderer', 'Wanderer'),
                    ('creature', 'Creature'),
                    ('sanctuary', 'Sanctuary'),
                    ('zen', 'Zen'),
                    ('electric', 'Electric'),
                    ('coastal', 'Coastal'),
                    ('ember', 'Ember'),
                    ('midnight', 'Midnight'),
                    ('custom', 'Custom'),
                ],
                default='sanctuary',
                max_length=20,
            ),
        ),
    ]
