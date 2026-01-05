# Generated manually for Task #134

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("life", "0006_significantevent"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="start_date",
            field=models.DateField(
                blank=True,
                help_text="Start date for recurring tasks",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="task",
            name="end_date",
            field=models.DateField(
                blank=True,
                help_text="End date for recurring tasks (optional)",
                null=True,
            ),
        ),
    ]
