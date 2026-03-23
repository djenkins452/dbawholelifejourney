"""
Data migration: Complete all four Gospel reading plans.

Runs the load_gospel_plans management command which is now fully idempotent
(uses get_or_create for all days). This ensures all plans have complete
day records in production:
- Matthew: 36 days (was 28, missing chapters 22-28)
- Mark: 19 days (already fixed in 0019)
- Luke: 32 days (was 24, missing chapters 18-24)
- John: 22 days (was 21, missing chapter 21)

Also creates UserReadingProgress entries for any active/paused user plans
so existing users see new days immediately.
"""

from django.db import migrations


def complete_all_gospel_plans(apps, schema_editor):
    """Run the gospel plans loader and backfill user progress."""
    from django.core.management import call_command

    # The loader is fully idempotent — get_or_create for templates and days
    call_command("load_gospel_plans", verbosity=0)

    # Backfill UserReadingProgress for any active plans missing days
    ReadingPlanTemplate = apps.get_model("faith", "ReadingPlanTemplate")
    ReadingPlanDay = apps.get_model("faith", "ReadingPlanDay")
    UserReadingPlan = apps.get_model("faith", "UserReadingPlan")
    UserReadingProgress = apps.get_model("faith", "UserReadingProgress")

    gospel_slugs = [
        "journey-through-matthew",
        "journey-through-mark",
        "journey-through-luke",
        "journey-through-john",
    ]

    for slug in gospel_slugs:
        try:
            template = ReadingPlanTemplate.objects.get(slug=slug)
        except ReadingPlanTemplate.DoesNotExist:
            continue

        all_days = list(ReadingPlanDay.objects.filter(plan=template))
        active_plans = UserReadingPlan.objects.filter(
            template=template,
            plan_status__in=["active", "paused"],
        )

        for user_plan in active_plans:
            existing_day_ids = set(
                UserReadingProgress.objects.filter(
                    user_plan=user_plan,
                ).values_list("plan_day_id", flat=True)
            )
            for day in all_days:
                if day.id not in existing_day_ids:
                    UserReadingProgress.objects.create(
                        user_plan=user_plan,
                        plan_day=day,
                        user=user_plan.user,
                    )


def reverse_noop(apps, schema_editor):
    """No-op reverse — days are safe to leave in place."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("faith", "0019_complete_mark_plan"),
    ]

    operations = [
        migrations.RunPython(complete_all_gospel_plans, reverse_noop),
    ]
