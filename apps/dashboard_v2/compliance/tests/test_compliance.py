"""
Tests for the Compliance Audit System.

Covers:
- ComplianceEvent model creation
- Domain adapters (medication, workout, routine, task, journal, faith)
- Rollup service counts
- Status classification (completed, late, missed, skipped, overdue)
- Edge cases (no data, inactive schedules, rest days)
"""

from datetime import date, time, timedelta

from django.conf import settings
from django.test import TestCase

from apps.dashboard_v2.compliance.constants import (
    BUCKET_MEDICATION,
    BUCKET_ROUTINE,
    BUCKET_TASK,
    BUCKET_WORKOUT,
    DOMAIN_MEDICATION,
    DOMAIN_ROUTINE,
    DOMAIN_TASK,
    DOMAIN_WORKOUT,
    FINAL_COMPLETED,
    FINAL_COMPLETED_LATE,
    FINAL_MISSED,
    FINAL_OVERDUE,
    FINAL_SKIPPED,
)
from apps.dashboard_v2.compliance.models import ComplianceEvent
from apps.dashboard_v2.compliance.service import ComplianceService
from apps.users.models import User


def _create_test_user(email="compliance_test@example.com"):
    """Create a test user with required onboarding."""
    from apps.users.models import TermsAcceptance

    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


class ComplianceEventModelTest(TestCase):
    """Test ComplianceEvent model basics."""

    def setUp(self):
        self.user = _create_test_user()

    def test_create_event(self):
        event = ComplianceEvent.objects.create(
            user=self.user,
            event_date=date.today(),
            domain=DOMAIN_MEDICATION,
            scoring_bucket=BUCKET_MEDICATION,
            item_type="MedicineSchedule",
            item_id=1,
            item_label="Aspirin (8:00 AM)",
            expected_at=time(8, 0),
            expected=True,
            actual_status="completed",
            final_status=FINAL_COMPLETED,
            reason_code="on_time",
            source_system="medicine_log",
        )
        self.assertEqual(event.domain, DOMAIN_MEDICATION)
        self.assertEqual(event.final_status, FINAL_COMPLETED)
        self.assertEqual(event.reason_label, "Completed within grace period")
        self.assertEqual(event.final_status_label, "Completed")

    def test_str_representation(self):
        event = ComplianceEvent.objects.create(
            user=self.user,
            event_date=date.today(),
            domain=DOMAIN_TASK,
            scoring_bucket=BUCKET_TASK,
            item_type="Task",
            item_id=1,
            item_label="Write report",
            expected=True,
            actual_status="open",
            final_status=FINAL_OVERDUE,
            reason_code="overdue_due_date",
            source_system="task",
        )
        self.assertIn("Write report", str(event))
        self.assertIn("overdue", str(event))


class MedicationAdapterTest(TestCase):
    """Test medication compliance adapter."""

    def setUp(self):
        self.user = _create_test_user("med_test@example.com")
        self.today = date.today()

    def test_no_medicines_returns_empty(self):
        from apps.dashboard_v2.compliance.adapters.medication import evaluate_medication
        result = evaluate_medication(self.user, self.today, self.today)
        self.assertEqual(result, [])

    def test_active_medicine_with_log(self):
        from apps.health.models import Medicine, MedicineLog, MedicineSchedule

        med = Medicine.objects.create(
            user=self.user, name="TestMed", dose="10mg",
            medicine_status=Medicine.STATUS_ACTIVE,
            start_date=self.today,
        )
        schedule = MedicineSchedule.objects.create(
            medicine=med, scheduled_time=time(8, 0),
            days_of_week="0,1,2,3,4,5,6", is_active=True,
        )
        MedicineLog.objects.create(
            user=self.user, medicine=med, schedule=schedule,
            scheduled_date=self.today, scheduled_time=time(8, 0),
            log_status="taken",
        )

        from apps.dashboard_v2.compliance.adapters.medication import evaluate_medication
        events = evaluate_medication(self.user, self.today, self.today)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["final_status"], FINAL_COMPLETED)
        self.assertEqual(events[0]["reason_code"], "on_time")

    def test_missed_dose_no_log(self):
        from apps.health.models import Medicine, MedicineSchedule

        med = Medicine.objects.create(
            user=self.user, name="TestMed2", dose="5mg",
            medicine_status=Medicine.STATUS_ACTIVE,
            start_date=self.today,
        )
        MedicineSchedule.objects.create(
            medicine=med, scheduled_time=time(9, 0),
            days_of_week="0,1,2,3,4,5,6", is_active=True,
        )

        from apps.dashboard_v2.compliance.adapters.medication import evaluate_medication
        events = evaluate_medication(self.user, self.today, self.today)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["final_status"], FINAL_MISSED)
        self.assertEqual(events[0]["reason_code"], "no_log")

    def test_late_dose(self):
        from apps.health.models import Medicine, MedicineLog, MedicineSchedule

        med = Medicine.objects.create(
            user=self.user, name="LateMed", dose="10mg",
            medicine_status=Medicine.STATUS_ACTIVE,
            start_date=self.today,
        )
        schedule = MedicineSchedule.objects.create(
            medicine=med, scheduled_time=time(8, 0),
            days_of_week="0,1,2,3,4,5,6", is_active=True,
        )
        MedicineLog.objects.create(
            user=self.user, medicine=med, schedule=schedule,
            scheduled_date=self.today, scheduled_time=time(8, 0),
            log_status="late",
        )

        from apps.dashboard_v2.compliance.adapters.medication import evaluate_medication
        events = evaluate_medication(self.user, self.today, self.today)

        self.assertEqual(events[0]["final_status"], FINAL_COMPLETED_LATE)

    def test_skipped_dose(self):
        from apps.health.models import Medicine, MedicineLog, MedicineSchedule

        med = Medicine.objects.create(
            user=self.user, name="SkipMed", dose="10mg",
            medicine_status=Medicine.STATUS_ACTIVE,
            start_date=self.today,
        )
        schedule = MedicineSchedule.objects.create(
            medicine=med, scheduled_time=time(8, 0),
            days_of_week="0,1,2,3,4,5,6", is_active=True,
        )
        MedicineLog.objects.create(
            user=self.user, medicine=med, schedule=schedule,
            scheduled_date=self.today, scheduled_time=time(8, 0),
            log_status="skipped",
        )

        from apps.dashboard_v2.compliance.adapters.medication import evaluate_medication
        events = evaluate_medication(self.user, self.today, self.today)

        self.assertEqual(events[0]["final_status"], FINAL_SKIPPED)


class TaskAdapterTest(TestCase):
    """Test task compliance adapter."""

    def setUp(self):
        self.user = _create_test_user("task_test@example.com")
        self.today = date.today()

    def test_completed_task(self):
        from apps.life.models import Task
        from django.utils import timezone

        Task.objects.create(
            user=self.user, title="Done task",
            due_date=self.today, is_routine=False,
            completion_status="completed", completed_at=timezone.now(),
        )

        from apps.dashboard_v2.compliance.adapters.task import evaluate_task
        events = evaluate_task(self.user, self.today, self.today)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["final_status"], FINAL_COMPLETED)

    def test_pending_task_is_missed(self):
        from apps.life.models import Task

        Task.objects.create(
            user=self.user, title="Pending task",
            due_date=self.today, is_routine=False,
            completion_status="pending",
        )

        from apps.dashboard_v2.compliance.adapters.task import evaluate_task
        events = evaluate_task(self.user, self.today, self.today)

        self.assertEqual(events[0]["final_status"], FINAL_MISSED)

    def test_overdue_task(self):
        from apps.life.models import Task

        yesterday = self.today - timedelta(days=1)
        Task.objects.create(
            user=self.user, title="Overdue task",
            due_date=yesterday, is_routine=False,
            completion_status="pending",
        )

        from apps.dashboard_v2.compliance.adapters.task import evaluate_task
        events = evaluate_task(self.user, self.today, self.today)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["final_status"], FINAL_OVERDUE)

    def test_routine_tasks_excluded(self):
        from apps.life.models import Task

        Task.objects.create(
            user=self.user, title="Routine task",
            due_date=self.today, is_routine=True,
            completion_status="pending",
        )

        from apps.dashboard_v2.compliance.adapters.task import evaluate_task
        events = evaluate_task(self.user, self.today, self.today)

        self.assertEqual(len(events), 0)

    def test_skipped_task(self):
        from apps.life.models import Task

        Task.objects.create(
            user=self.user, title="Skipped task",
            due_date=self.today, is_routine=False,
            completion_status="skipped",
        )

        from apps.dashboard_v2.compliance.adapters.task import evaluate_task
        events = evaluate_task(self.user, self.today, self.today)

        self.assertEqual(events[0]["final_status"], FINAL_SKIPPED)


class RollupServiceTest(TestCase):
    """Test rollup counts from ComplianceEvent."""

    def setUp(self):
        self.user = _create_test_user("rollup_test@example.com")
        self.today = date.today()

    def test_rollup_counts(self):
        # Create 3 completed + 2 missed events
        for i in range(3):
            ComplianceEvent.objects.create(
                user=self.user, event_date=self.today,
                domain=DOMAIN_MEDICATION, scoring_bucket=BUCKET_MEDICATION,
                item_type="MedicineSchedule", item_id=i,
                item_label=f"Med {i}", expected=True,
                actual_status="completed", final_status=FINAL_COMPLETED,
                reason_code="on_time", source_system="medicine_log",
            )
        for i in range(2):
            ComplianceEvent.objects.create(
                user=self.user, event_date=self.today,
                domain=DOMAIN_MEDICATION, scoring_bucket=BUCKET_MEDICATION,
                item_type="MedicineSchedule", item_id=10 + i,
                item_label=f"Missed Med {i}", expected=True,
                actual_status="none", final_status=FINAL_MISSED,
                reason_code="no_log", source_system="medicine_schedule",
            )

        svc = ComplianceService(self.user)
        rollup = svc.get_rollup(BUCKET_MEDICATION, self.today, self.today)

        self.assertEqual(rollup["expected"], 5)
        self.assertEqual(rollup["completed"], 3)
        self.assertEqual(rollup["missed"], 2)
        self.assertEqual(rollup["completion_pct"], 60)
        self.assertIn("Missed 2", rollup["missed_label"])

    def test_skipped_excluded_from_denominator(self):
        # 2 completed + 1 skipped = 100% (skipped excluded)
        for i in range(2):
            ComplianceEvent.objects.create(
                user=self.user, event_date=self.today,
                domain=DOMAIN_ROUTINE, scoring_bucket=BUCKET_ROUTINE,
                item_type="RoutineSchedule", item_id=i,
                item_label=f"Routine {i}", expected=True,
                actual_status="completed", final_status=FINAL_COMPLETED,
                reason_code="on_time", source_system="routine_log",
            )
        ComplianceEvent.objects.create(
            user=self.user, event_date=self.today,
            domain=DOMAIN_ROUTINE, scoring_bucket=BUCKET_ROUTINE,
            item_type="RoutineSchedule", item_id=99,
            item_label="Skipped Routine", expected=True,
            actual_status="skipped", final_status=FINAL_SKIPPED,
            reason_code="explicit_skip", source_system="routine_log",
        )

        svc = ComplianceService(self.user)
        rollup = svc.get_rollup(BUCKET_ROUTINE, self.today, self.today)

        self.assertEqual(rollup["expected"], 3)
        self.assertEqual(rollup["completed"], 2)
        self.assertEqual(rollup["skipped"], 1)
        self.assertEqual(rollup["completion_pct"], 100)

    def test_empty_rollup(self):
        svc = ComplianceService(self.user)
        rollup = svc.get_rollup(BUCKET_WORKOUT, self.today, self.today)

        self.assertEqual(rollup["expected"], 0)
        self.assertEqual(rollup["completion_pct"], 100)
        self.assertIsNone(rollup["missed_label"])

    def test_get_all_rollups(self):
        svc = ComplianceService(self.user)
        all_rollups = svc.get_all_rollups(self.today, self.today)

        self.assertIn(BUCKET_MEDICATION, all_rollups)
        self.assertIn(BUCKET_WORKOUT, all_rollups)
        self.assertIn(BUCKET_ROUTINE, all_rollups)
        self.assertIn(BUCKET_TASK, all_rollups)


class ComplianceDetailTest(TestCase):
    """Test detail query grouping."""

    def setUp(self):
        self.user = _create_test_user("detail_test@example.com")
        self.today = date.today()
        self.yesterday = self.today - timedelta(days=1)

    def test_detail_grouped_by_date(self):
        for day in [self.today, self.yesterday]:
            ComplianceEvent.objects.create(
                user=self.user, event_date=day,
                domain=DOMAIN_MEDICATION, scoring_bucket=BUCKET_MEDICATION,
                item_type="MedicineSchedule", item_id=1,
                item_label="Med A", expected=True,
                actual_status="completed", final_status=FINAL_COMPLETED,
                reason_code="on_time", source_system="medicine_log",
            )

        svc = ComplianceService(self.user)
        detail = svc.get_detail(BUCKET_MEDICATION, self.yesterday, self.today)

        self.assertEqual(len(detail), 2)
        # Newest first
        self.assertEqual(detail[0]["date"], self.today)
        self.assertEqual(detail[1]["date"], self.yesterday)

    def test_detail_with_status_filter(self):
        ComplianceEvent.objects.create(
            user=self.user, event_date=self.today,
            domain=DOMAIN_MEDICATION, scoring_bucket=BUCKET_MEDICATION,
            item_type="MedicineSchedule", item_id=1,
            item_label="Completed Med", expected=True,
            actual_status="completed", final_status=FINAL_COMPLETED,
            reason_code="on_time", source_system="medicine_log",
        )
        ComplianceEvent.objects.create(
            user=self.user, event_date=self.today,
            domain=DOMAIN_MEDICATION, scoring_bucket=BUCKET_MEDICATION,
            item_type="MedicineSchedule", item_id=2,
            item_label="Missed Med", expected=True,
            actual_status="none", final_status=FINAL_MISSED,
            reason_code="no_log", source_system="medicine_schedule",
        )

        svc = ComplianceService(self.user)
        missed_detail = svc.get_detail(
            BUCKET_MEDICATION, self.today, self.today,
            status_filter="missed",
        )

        self.assertEqual(len(missed_detail), 1)
        self.assertEqual(len(missed_detail[0]["items"]), 1)
        self.assertEqual(missed_detail[0]["items"][0]["item_label"], "Missed Med")


class WorkoutAdapterTest(TestCase):
    """Test workout compliance adapter — WorkoutSession as single source of truth."""

    def setUp(self):
        self.user = _create_test_user("workout_test@example.com")
        self.today = date.today()
        # Ensure today is a weekday we can schedule on
        self.day_of_week = self.today.weekday()

    def _create_plan_with_schedule(self):
        """Create an active workout plan with a schedule entry for today."""
        from apps.health.models import (
            WorkoutPlan,
            WorkoutSchedule,
            WorkoutTemplate,
        )

        template = WorkoutTemplate.objects.create(
            user=self.user, name="Chest Day",
        )
        plan = WorkoutPlan.objects.create(
            user=self.user, name="Test Plan",
            is_active=True, status="active",
        )
        schedule = WorkoutSchedule.objects.create(
            plan=plan, day_of_week=self.day_of_week,
            template=template, preferred_time=time(17, 0),
            is_rest_day=False,
        )
        return plan, schedule, template

    def test_completed_session_marks_completed(self):
        """WorkoutSession with completed_at → COMPLETED (raw truth)."""
        from django.utils import timezone

        from apps.health.models import WorkoutSession

        plan, schedule, template = self._create_plan_with_schedule()

        # Create a completed workout session (no template link needed)
        WorkoutSession.objects.create(
            user=self.user, date=self.today,
            name="Chest Day",
            completed_at=timezone.now(),
        )

        from apps.dashboard_v2.compliance.adapters.workout import evaluate_workout
        events = evaluate_workout(self.user, self.today, self.today)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["final_status"], FINAL_COMPLETED)
        self.assertEqual(events[0]["reason_code"], "completed_via_session")
        self.assertEqual(events[0]["source_system"], "workout_session")

    def test_session_without_completed_at_marks_missed(self):
        """WorkoutSession exists but completed_at is NULL → MISSED."""
        from apps.health.models import WorkoutSession

        plan, schedule, template = self._create_plan_with_schedule()

        # Create an incomplete workout session
        WorkoutSession.objects.create(
            user=self.user, date=self.today,
            name="Chest Day",
            completed_at=None,
        )

        from apps.dashboard_v2.compliance.adapters.workout import evaluate_workout
        events = evaluate_workout(self.user, self.today, self.today)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["final_status"], FINAL_MISSED)
        self.assertEqual(events[0]["reason_code"], "not_completed")

    def test_schedule_log_still_used_when_present(self):
        """WorkoutScheduleLog exists → use existing log-based logic."""
        from django.utils import timezone

        from apps.health.models import WorkoutScheduleLog, WorkoutSession

        plan, schedule, template = self._create_plan_with_schedule()

        session = WorkoutSession.objects.create(
            user=self.user, date=self.today,
            name="Chest Day", from_template=template,
            completed_at=timezone.now(),
        )
        # The post_save signal may have already created a log — update it
        # to completed_late to verify the adapter uses log status over session
        WorkoutScheduleLog.objects.update_or_create(
            schedule=schedule,
            scheduled_date=self.today,
            defaults={
                "user": self.user,
                "log_status": "completed_late",
                "session": session,
                "completed_at": timezone.now(),
            },
        )

        from apps.dashboard_v2.compliance.adapters.workout import evaluate_workout
        events = evaluate_workout(self.user, self.today, self.today)

        self.assertEqual(len(events), 1)
        # Should use the log's more specific status (completed_late)
        self.assertEqual(events[0]["final_status"], FINAL_COMPLETED_LATE)
        self.assertEqual(events[0]["reason_code"], "after_grace")
        self.assertEqual(events[0]["source_system"], "workout_schedule_log")

    def test_no_session_no_log_marks_missed(self):
        """No WorkoutSession and no WorkoutScheduleLog → MISSED."""
        plan, schedule, template = self._create_plan_with_schedule()

        from apps.dashboard_v2.compliance.adapters.workout import evaluate_workout
        events = evaluate_workout(self.user, self.today, self.today)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["final_status"], FINAL_MISSED)
        self.assertEqual(events[0]["reason_code"], "not_completed")
        self.assertEqual(events[0]["source_system"], "workout_schedule")

    def test_no_active_plan_returns_empty(self):
        """No active workout plan → no events."""
        from apps.dashboard_v2.compliance.adapters.workout import evaluate_workout
        events = evaluate_workout(self.user, self.today, self.today)
        self.assertEqual(events, [])

    def test_rest_day_not_counted(self):
        """Rest day schedule entries are excluded."""
        from apps.health.models import WorkoutPlan, WorkoutSchedule, WorkoutTemplate

        template = WorkoutTemplate.objects.create(
            user=self.user, name="Rest",
        )
        plan = WorkoutPlan.objects.create(
            user=self.user, name="Test Plan",
            is_active=True, status="active",
        )
        WorkoutSchedule.objects.create(
            plan=plan, day_of_week=self.day_of_week,
            template=template, is_rest_day=True,
        )

        from apps.dashboard_v2.compliance.adapters.workout import evaluate_workout
        events = evaluate_workout(self.user, self.today, self.today)
        self.assertEqual(events, [])

    def test_ad_hoc_session_satisfies_schedule(self):
        """Ad-hoc workout (no template) with completed_at satisfies schedule."""
        from django.utils import timezone

        from apps.health.models import WorkoutSession

        plan, schedule, template = self._create_plan_with_schedule()

        # Ad-hoc workout — no from_template
        WorkoutSession.objects.create(
            user=self.user, date=self.today,
            name="Quick Workout",
            completed_at=timezone.now(),
            from_template=None,
        )

        from apps.dashboard_v2.compliance.adapters.workout import evaluate_workout
        events = evaluate_workout(self.user, self.today, self.today)

        self.assertEqual(len(events), 1)
        # Should be completed via session fallback
        self.assertEqual(events[0]["final_status"], FINAL_COMPLETED)
        self.assertEqual(events[0]["reason_code"], "completed_via_session")

    def test_skipped_log_takes_precedence_over_session(self):
        """WorkoutScheduleLog with skipped status takes precedence."""
        from django.utils import timezone

        from apps.health.models import WorkoutScheduleLog

        plan, schedule, template = self._create_plan_with_schedule()

        # Create skip log directly (no session needed for skip)
        WorkoutScheduleLog.objects.create(
            user=self.user, schedule=schedule,
            scheduled_date=self.today,
            log_status="skipped",
        )

        from apps.dashboard_v2.compliance.adapters.workout import evaluate_workout
        events = evaluate_workout(self.user, self.today, self.today)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["final_status"], FINAL_SKIPPED)
        self.assertEqual(events[0]["reason_code"], "explicit_skip")


class EvaluateAndRollupIntegrationTest(TestCase):
    """Test full flow: evaluate → persist → rollup."""

    def setUp(self):
        self.user = _create_test_user("integration_test@example.com")
        self.today = date.today()

    def test_evaluate_week_creates_events(self):
        svc = ComplianceService(self.user)
        count = svc.evaluate_week()
        # Even with no domain data, should return 0 (no exceptions)
        self.assertEqual(count, 0)

    def test_evaluate_replaces_old_events(self):
        svc = ComplianceService(self.user)

        # Create a stale event
        ComplianceEvent.objects.create(
            user=self.user, event_date=self.today,
            domain=DOMAIN_TASK, scoring_bucket=BUCKET_TASK,
            item_type="Task", item_id=999,
            item_label="Stale event", expected=True,
            actual_status="none", final_status=FINAL_MISSED,
            reason_code="no_log", source_system="task",
        )
        self.assertEqual(ComplianceEvent.objects.filter(user=self.user).count(), 1)

        # Evaluate replaces
        svc.evaluate_week()
        # Stale event should be gone (replaced by fresh evaluation)
        self.assertFalse(
            ComplianceEvent.objects.filter(
                user=self.user, item_label="Stale event"
            ).exists()
        )
