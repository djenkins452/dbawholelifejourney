"""
Tests for WorkoutPlan and WorkoutSchedule models + setup_strength_split command.
"""

import datetime
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from apps.health.models import (
    Exercise,
    TemplateExercise,
    TransformationProtocol,
    WorkoutPlan,
    WorkoutSchedule,
    WorkoutSession,
    WorkoutTemplate,
)
from apps.users.models import TermsAcceptance, User


class WorkoutPlanTestMixin:
    """Common setup for workout plan tests."""

    def create_user(self, email="test@example.com", password="testpass123"):
        user = User.objects.create_user(email=email, password=password)
        TermsAcceptance.objects.create(
            user=user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user

    def create_exercise(self, name, muscle_group="Chest"):
        return Exercise.objects.create(
            name=name, category="resistance", muscle_group=muscle_group, is_active=True
        )

    def create_template(self, user, name="Push Day"):
        return WorkoutTemplate.objects.create(user=user, name=name)


class WorkoutPlanModelTest(WorkoutPlanTestMixin, TestCase):
    """Tests for WorkoutPlan model."""

    def setUp(self):
        self.user = self.create_user()

    def test_create_plan(self):
        plan = WorkoutPlan.objects.create(
            user=self.user,
            name="Test Split",
            days_per_week=6,
            goal="fat loss",
        )
        self.assertEqual(plan.name, "Test Split")
        self.assertTrue(plan.is_active)
        self.assertEqual(plan.days_per_week, 6)

    def test_plan_str(self):
        plan = WorkoutPlan.objects.create(user=self.user, name="My Plan")
        self.assertEqual(str(plan), "My Plan")

    def test_plan_template_count(self):
        plan = WorkoutPlan.objects.create(user=self.user, name="Split")
        t1 = self.create_template(self.user, "A")
        t2 = self.create_template(self.user, "B")
        WorkoutSchedule.objects.create(plan=plan, day_of_week=0, template=t1)
        WorkoutSchedule.objects.create(plan=plan, day_of_week=1, template=t2)
        WorkoutSchedule.objects.create(plan=plan, day_of_week=2, template=t1)
        self.assertEqual(plan.template_count, 2)

    def test_plan_scheduled_days(self):
        plan = WorkoutPlan.objects.create(user=self.user, name="Split")
        t1 = self.create_template(self.user, "A")
        WorkoutSchedule.objects.create(plan=plan, day_of_week=0, template=t1)
        WorkoutSchedule.objects.create(plan=plan, day_of_week=2, template=t1)
        self.assertEqual(plan.scheduled_days, ["Monday", "Wednesday"])

    def test_plan_links_to_protocol(self):
        protocol = TransformationProtocol.objects.create(
            user=self.user,
            name="12-Week Cut",
            protocol_type="cut",
            start_date=datetime.date.today(),
        )
        plan = WorkoutPlan.objects.create(
            user=self.user,
            name="Split",
            transformation_protocol=protocol,
        )
        self.assertEqual(plan.transformation_protocol, protocol)
        self.assertIn(plan, protocol.workout_plans.all())

    def test_plan_soft_delete(self):
        plan = WorkoutPlan.objects.create(user=self.user, name="Split")
        plan.soft_delete()
        self.assertEqual(WorkoutPlan.objects.filter(user=self.user).count(), 0)


class WorkoutScheduleModelTest(WorkoutPlanTestMixin, TestCase):
    """Tests for WorkoutSchedule model."""

    def setUp(self):
        self.user = self.create_user()
        self.plan = WorkoutPlan.objects.create(user=self.user, name="Split")
        self.template = self.create_template(self.user, "Push Day")

    def test_create_schedule_entry(self):
        entry = WorkoutSchedule.objects.create(
            plan=self.plan,
            day_of_week=0,
            template=self.template,
            preferred_time=datetime.time(17, 0),
        )
        self.assertEqual(entry.day_of_week, 0)
        self.assertEqual(entry.preferred_time, datetime.time(17, 0))
        self.assertFalse(entry.is_rest_day)

    def test_schedule_str_workout_day(self):
        entry = WorkoutSchedule.objects.create(
            plan=self.plan, day_of_week=0, template=self.template
        )
        self.assertEqual(str(entry), "Monday: Push Day")

    def test_schedule_str_rest_day(self):
        entry = WorkoutSchedule.objects.create(
            plan=self.plan, day_of_week=6, template=self.template, is_rest_day=True
        )
        self.assertEqual(str(entry), "Sunday: Rest")

    def test_unique_day_per_plan(self):
        WorkoutSchedule.objects.create(
            plan=self.plan, day_of_week=0, template=self.template
        )
        with self.assertRaises(Exception):
            WorkoutSchedule.objects.create(
                plan=self.plan, day_of_week=0, template=self.template
            )

    def test_cascade_delete_plan(self):
        WorkoutSchedule.objects.create(
            plan=self.plan, day_of_week=0, template=self.template
        )
        WorkoutSchedule.objects.create(
            plan=self.plan, day_of_week=1, template=self.template
        )
        self.plan.delete()
        self.assertEqual(WorkoutSchedule.objects.count(), 0)

    def test_ordering(self):
        t2 = self.create_template(self.user, "Pull Day")
        WorkoutSchedule.objects.create(
            plan=self.plan, day_of_week=4, template=self.template
        )
        WorkoutSchedule.objects.create(plan=self.plan, day_of_week=1, template=t2)
        entries = list(self.plan.schedule_entries.all())
        self.assertEqual(entries[0].day_of_week, 1)
        self.assertEqual(entries[1].day_of_week, 4)


class WorkoutSessionFromTemplateTest(WorkoutPlanTestMixin, TestCase):
    """Verify existing from_template FK works with planned templates."""

    def setUp(self):
        self.user = self.create_user()
        self.exercise = self.create_exercise("Bench Press")
        self.template = self.create_template(self.user, "Group A: Push + Arms")
        TemplateExercise.objects.create(
            template=self.template, exercise=self.exercise, order=1, default_sets=4
        )

    def test_log_workout_from_plan_template(self):
        """WorkoutSession.from_template links logged workouts to plan templates."""
        plan = WorkoutPlan.objects.create(user=self.user, name="Split")
        WorkoutSchedule.objects.create(
            plan=plan, day_of_week=0, template=self.template
        )

        session = WorkoutSession.objects.create(
            user=self.user,
            date=datetime.date.today(),
            name="Group A: Push + Arms",
            from_template=self.template,
        )
        self.assertEqual(session.from_template, self.template)
        self.assertIn(session, self.template.workout_sessions.all())


class SetupStrengthSplitCommandTest(WorkoutPlanTestMixin, TestCase):
    """Tests for the setup_strength_split management command."""

    def setUp(self):
        self.user = self.create_user(email="danny@test.com")
        # Create all required exercises
        exercises = [
            ("Bench Press", "Chest"),
            ("Dumbbell Shoulder Press", "Shoulders"),
            ("Lateral Raise", "Shoulders"),
            ("Overhead Tricep Extension", "Triceps"),
            ("Bicep Curl", "Biceps"),
            ("Deadlift", "Back"),
            ("Single Arm Dumbbell Row", "Back"),
            ("Shrugs", "Shoulders"),
            ("Romanian Deadlift", "Legs"),
            ("Walking Lunges", "Legs"),
        ]
        for name, muscle in exercises:
            self.create_exercise(name, muscle)

    def _run_command(self, email="danny@test.com", clear=False):
        out = StringIO()
        args = [email]
        kwargs = {"stdout": out, "stderr": out}
        if clear:
            kwargs["clear"] = True
        call_command("setup_strength_split", *args, **kwargs)
        return out.getvalue()

    def test_creates_plan_and_schedule(self):
        output = self._run_command()
        self.assertIn("Done", output)

        plan = WorkoutPlan.objects.get(user=self.user, name="2-Group Strength Split")
        self.assertTrue(plan.is_active)
        self.assertEqual(plan.days_per_week, 6)
        self.assertEqual(plan.goal, "fat loss")
        self.assertEqual(plan.schedule_entries.count(), 6)

    def test_creates_two_templates(self):
        self._run_command()
        templates = WorkoutTemplate.objects.filter(user=self.user)
        names = set(templates.values_list("name", flat=True))
        self.assertIn("Group A: Push + Arms", names)
        self.assertIn("Group B: Pull + Legs", names)

    def test_template_a_has_5_exercises(self):
        self._run_command()
        template = WorkoutTemplate.objects.get(
            user=self.user, name="Group A: Push + Arms"
        )
        self.assertEqual(template.template_exercises.count(), 5)

    def test_template_b_has_5_exercises(self):
        self._run_command()
        template = WorkoutTemplate.objects.get(
            user=self.user, name="Group B: Pull + Legs"
        )
        self.assertEqual(template.template_exercises.count(), 5)

    def test_schedule_alternates_ab(self):
        self._run_command()
        plan = WorkoutPlan.objects.get(user=self.user)
        entries = list(plan.schedule_entries.order_by("day_of_week"))
        template_names = [e.template.name for e in entries]
        expected = [
            "Group A: Push + Arms",  # Mon
            "Group B: Pull + Legs",  # Tue
            "Group A: Push + Arms",  # Wed
            "Group B: Pull + Legs",  # Thu
            "Group A: Push + Arms",  # Fri
            "Group B: Pull + Legs",  # Sat
        ]
        self.assertEqual(template_names, expected)

    def test_preferred_time_set(self):
        self._run_command()
        plan = WorkoutPlan.objects.get(user=self.user)
        for entry in plan.schedule_entries.all():
            self.assertEqual(entry.preferred_time, datetime.time(17, 0))

    def test_no_sunday_entry(self):
        self._run_command()
        plan = WorkoutPlan.objects.get(user=self.user)
        self.assertFalse(plan.schedule_entries.filter(day_of_week=6).exists())

    def test_idempotent_skips_existing(self):
        self._run_command()
        output = self._run_command()
        self.assertIn("already exists", output)
        self.assertEqual(WorkoutPlan.objects.filter(user=self.user).count(), 1)

    def test_clear_recreates(self):
        self._run_command()
        self._run_command(clear=True)
        self.assertEqual(
            WorkoutPlan.objects.filter(
                user=self.user, name="2-Group Strength Split"
            ).count(),
            1,
        )

    def test_links_active_protocol(self):
        protocol = TransformationProtocol.objects.create(
            user=self.user,
            name="Cut",
            protocol_type="cut",
            start_date=datetime.date.today(),
            is_active=True,
        )
        self._run_command()
        plan = WorkoutPlan.objects.get(user=self.user)
        self.assertEqual(plan.transformation_protocol, protocol)

    def test_no_protocol_still_creates(self):
        self._run_command()
        plan = WorkoutPlan.objects.get(user=self.user)
        self.assertIsNone(plan.transformation_protocol)

    def test_user_not_found(self):
        out = StringIO()
        call_command(
            "setup_strength_split",
            "nobody@test.com",
            stdout=out,
            stderr=out,
        )
        self.assertIn("not found", out.getvalue())
