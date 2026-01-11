"""
Management command to reset reading plan progress for users affected by the
notes-not-saving bug.

This is a ONE-TIME fix that runs automatically on deploy. It resets all
reading plan days that were marked complete but have no notes (indicating
they were affected by the bug where notes weren't saved).

After running once, this command is safe to run again - it will simply
report that no plans need resetting.
"""

from django.core.management.base import BaseCommand
from apps.faith.models import UserReadingPlan


class Command(BaseCommand):
    help = "Reset reading plan progress for users affected by the notes-not-saving bug"

    def handle(self, *args, **options):
        self.stdout.write("Checking for reading plans affected by notes-not-saving bug...")

        # Find all active/completed plans
        plans = UserReadingPlan.objects.filter(status__in=["active", "completed"])

        total_days_reset = 0
        plans_affected = 0

        for plan in plans:
            # Find days marked complete with no notes (potentially affected by bug)
            affected_days = plan.day_completions.filter(
                is_completed=True,
                notes=""
            ).order_by("plan_day__day_number")

            if not affected_days.exists():
                continue

            plans_affected += 1
            day_numbers = list(affected_days.values_list("plan_day__day_number", flat=True))
            count = affected_days.count()

            self.stdout.write(
                f"  {plan.user.email} - {plan.template.title}: "
                f"Resetting days {day_numbers}"
            )

            # Reset the affected days
            affected_days.update(is_completed=False, completed_at=None)

            # Reset current_day to the first incomplete day
            first_incomplete = plan.day_completions.filter(
                is_completed=False
            ).order_by("plan_day__day_number").first()

            if first_incomplete:
                old_day = plan.current_day
                plan.current_day = first_incomplete.plan_day.day_number
                plan.status = "active"
                plan.completed_at = None
                plan.save(update_fields=["current_day", "status", "completed_at", "updated_at"])

                self.stdout.write(
                    self.style.SUCCESS(
                        f"    -> Reset to day {plan.current_day} (was day {old_day})"
                    )
                )

            total_days_reset += count

        if plans_affected == 0:
            self.stdout.write(
                self.style.SUCCESS("No reading plans need resetting.")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Reset {total_days_reset} day(s) across {plans_affected} plan(s)."
                )
            )
