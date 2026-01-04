# Generated manually for Task #137

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admin_console', '0014_add_future_never_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='adminproject',
            name='priority',
            field=models.PositiveIntegerField(
                choices=[(1, '1'), (2, '2'), (3, '3'), (4, '4'), (5, '5'),
                         (6, '6'), (7, '7'), (8, '8'), (9, '9'), (10, '10')],
                default=5,
                help_text='Project priority (1=highest, 10=lowest)'
            ),
        ),
        migrations.AlterModelOptions(
            name='adminproject',
            options={
                'ordering': ['priority', 'name'],
                'verbose_name': 'Admin Project',
                'verbose_name_plural': 'Admin Projects'
            },
        ),
    ]
