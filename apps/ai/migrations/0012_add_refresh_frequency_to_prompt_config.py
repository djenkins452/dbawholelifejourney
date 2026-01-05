# Generated manually for Task #135

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0011_add_home_page_insight_prompt_types"),
    ]

    operations = [
        migrations.AddField(
            model_name="aipromptconfig",
            name="refresh_frequency",
            field=models.CharField(
                choices=[
                    ("daily", "Once per day"),
                    ("twice_daily", "Twice per day"),
                    ("three_times_daily", "Three times per day"),
                    ("four_times_daily", "Four times per day"),
                    ("on_data_change", "On data change"),
                    ("daily_and_on_change", "Daily + on data change"),
                ],
                default="daily_and_on_change",
                help_text="How often the insight should be refreshed",
                max_length=30,
            ),
        ),
    ]
