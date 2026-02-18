"""
Management command to set up a 2-group strength training split for a user.

Creates workout templates (Group A: Push+Arms, Group B: Pull+Legs),
a WorkoutPlan, and a weekly WorkoutSchedule.

Safe to run multiple times - skips if plan already exists.

Usage:
    python manage.py setup_strength_split dannyjenkins71@gmail.com
    python manage.py setup_strength_split dannyjenkins71@gmail.com --clear
"""

import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.health.models import (
    Exercise,
    TemplateExercise,
    TransformationProtocol,
    WorkoutPlan,
    WorkoutSchedule,
    WorkoutTemplate,
)
from apps.users.models import User


PLAN_NAME = "2-Group Strength Split"

# Group A — Push + Arms (Chest, Shoulders, Triceps, Biceps)
GROUP_A = {
    "name": "Group A: Push + Arms",
    "description": (
        "Upper body push with arm accessory work. "
        "Chest, shoulders, triceps, biceps. "
        "Optional finisher: push-up burnout set to failure."
    ),
    "exercises": [
        # (exercise_name, default_sets, notes)
        ("Bench Press", 4, "3-4 sets x 6-10 reps"),
        ("Dumbbell Shoulder Press", 3, "3 sets x 8-12 reps"),
        ("Lateral Raise", 3, "3 sets x 10-15 reps"),
        ("Overhead Tricep Extension", 3, "3 sets x 8-12 reps"),
        ("Bicep Curl", 3, "3 sets x 8-12 reps (barbell or dumbbell)"),
    ],
}

# Group B — Pull + Legs (Back, Hamstrings, Glutes, Traps)
GROUP_B = {
    "name": "Group B: Pull + Legs",
    "description": (
        "Posterior chain and pulling strength. "
        "Back, hamstrings, glutes, traps. "
        "Optional core: plank hold 3x45-60 sec."
    ),
    "exercises": [
        ("Deadlift", 3, "3 sets x 5-8 reps"),
        ("Single Arm Dumbbell Row", 3, "3 sets x 8-12 reps per arm"),
        ("Shrugs", 3, "3 sets x 10-15 reps (barbell or dumbbell)"),
        ("Romanian Deadlift", 3, "3 sets x 8-12 reps (dumbbell)"),
        ("Walking Lunges", 3, "3 sets x 10-12 steps per leg (dumbbell)"),
    ],
}

# Weekly rotation: Mon-Sat alternating A/B, Sunday rest
# day_of_week: 0=Monday ... 6=Sunday
WEEKLY_SCHEDULE = [
    (0, "A"),   # Monday
    (1, "B"),   # Tuesday
    (2, "A"),   # Wednesday
    (3, "B"),   # Thursday
    (4, "A"),   # Friday
    (5, "B"),   # Saturday
    # Sunday (6) is rest — no entry needed
]

PREFERRED_TIME = datetime.time(17, 0)  # 5:00 PM


class Command(BaseCommand):
    help = "Set up a 2-group strength training split with weekly schedule"

    def add_arguments(self, parser):
        parser.add_argument(
            "email",
            nargs="?",
            default="dannyjenkins71@gmail.com",
            type=str,
            help="Email of the user (default: dannyjenkins71@gmail.com)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Remove existing plan with this name before creating",
        )

    def handle(self, *args, **options):
        email = options["email"]

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            self.stdout.write(
                self.style.WARNING(f"User {email} not found. Skipping strength split setup.")
            )
            return

        self.stdout.write(f"Setting up strength split for {user.email}...")

        with transaction.atomic():
            # Check for existing plan
            existing = WorkoutPlan.objects.filter(
                user=user, name=PLAN_NAME, status="active"
            )
            if existing.exists() and not options["clear"]:
                self.stdout.write(
                    self.style.WARNING(
                        f"Plan '{PLAN_NAME}' already exists. Use --clear to recreate."
                    )
                )
                return

            if options["clear"]:
                deleted = existing.count()
                existing.delete()
                if deleted:
                    self.stdout.write(f"  Removed {deleted} existing plan(s)")

            # Step 1: Ensure exercises exist
            self._ensure_exercises()

            # Step 2: Create templates
            template_a = self._create_template(user, GROUP_A)
            template_b = self._create_template(user, GROUP_B)

            # Step 3: Find active TransformationProtocol
            protocol = TransformationProtocol.objects.filter(
                user=user, is_active=True, status="active"
            ).first()

            # Step 4: Create WorkoutPlan
            plan = WorkoutPlan.objects.create(
                user=user,
                name=PLAN_NAME,
                description=(
                    "Alternating push/pull split, 6 days/week. "
                    "Goal: accelerated fat loss while preserving muscle mass. "
                    "Garage gym: bench+rack, Olympic bar, dumbbells to 55lb, "
                    "curl bar, preacher curl attachment."
                ),
                is_active=True,
                days_per_week=6,
                goal="fat loss",
                transformation_protocol=protocol,
            )
            self.stdout.write(f"  + Created plan: {plan.name}")

            if protocol:
                self.stdout.write(
                    f"  + Linked to TransformationProtocol: {protocol.name}"
                )
            else:
                self.stdout.write("  - No active TransformationProtocol found")

            # Step 5: Create weekly schedule
            template_map = {"A": template_a, "B": template_b}
            for day_of_week, group in WEEKLY_SCHEDULE:
                WorkoutSchedule.objects.create(
                    plan=plan,
                    day_of_week=day_of_week,
                    template=template_map[group],
                    preferred_time=PREFERRED_TIME,
                )

            day_names = dict(WorkoutSchedule._meta.get_field("day_of_week").choices)
            self.stdout.write("\n  Weekly schedule:")
            for day_of_week, group in WEEKLY_SCHEDULE:
                self.stdout.write(
                    f"    {day_names[day_of_week]}: {template_map[group].name}"
                )
            self.stdout.write(f"    Sunday: Rest")

            self.stdout.write(
                self.style.SUCCESS(
                    f"\nDone. Plan '{PLAN_NAME}' created with "
                    f"2 templates and 6 scheduled days."
                )
            )

    def _ensure_exercises(self):
        """Verify all required exercises exist in the library."""
        all_exercises = []
        for group in [GROUP_A, GROUP_B]:
            for name, _, _ in group["exercises"]:
                all_exercises.append(name)

        missing = []
        for name in all_exercises:
            if not Exercise.objects.filter(name=name).exists():
                missing.append(name)

        if missing:
            self.stderr.write(
                self.style.ERROR(
                    f"Missing exercises: {', '.join(missing)}. "
                    f"Run 'manage.py populate_exercises' first."
                )
            )
            raise SystemExit(1)

        self.stdout.write(f"  All {len(all_exercises)} exercises verified")

    def _create_template(self, user, group_def):
        """Create a WorkoutTemplate with its exercises, or return existing."""
        template, created = WorkoutTemplate.objects.get_or_create(
            user=user,
            name=group_def["name"],
            status="active",
            defaults={"description": group_def["description"]},
        )

        if not created:
            self.stdout.write(f"  - Template exists: {template.name}")
            return template

        for order, (exercise_name, default_sets, notes) in enumerate(
            group_def["exercises"], start=1
        ):
            exercise = Exercise.objects.get(name=exercise_name)
            TemplateExercise.objects.create(
                template=template,
                exercise=exercise,
                order=order,
                default_sets=default_sets,
                notes=notes,
            )

        self.stdout.write(
            f"  + Created template: {template.name} "
            f"({template.exercise_count} exercises)"
        )
        return template
