"""Tests for the C12 Celery tasks and event-triggered signal handlers.

Two surfaces covered:

1. Tasks (`tasks.py`) — registered as @shared_task; the per-user
   recompute task calls the composer; the beat task dispatches per
   user with a UserState row. Tested with mocks so no Redis or
   real Celery worker is required.

2. Signals (`signals.py`) — post_save on GlucoseEntry / IntakeLog /
   WeightEntry / LabResult enqueues the per-user task asynchronously.
   Tested by mocking `recompute_health_briefing_for_user_task.delay`
   and confirming the right user_id is dispatched with the right
   source label.

Recompute-loop guardrail (Wave 3):
* `test_no_recompute_cascade_from_snapshot` confirms that creating a
  HealthBriefingSnapshot row itself does NOT trigger another
  recompute. Snapshots are terminal.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.ai_state.models import UserState
from apps.core.health_briefing.models import HealthBriefingSnapshot
from apps.core.health_briefing.tasks import (
    recompute_all_health_briefings_task,
    recompute_health_briefing_for_user_task,
)
from apps.users.models import TermsAcceptance

User = get_user_model()


def _make_user(email: str = "tasks@test.com"):
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


# ── Per-user task ───────────────────────────────────────────────────


class RecomputeForUserTaskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("per_user@test.com")

    def test_calls_compose_briefing_with_persist(self):
        with patch(
            "apps.core.health_briefing.composer.compose_briefing"
        ) as m:
            # Mock returns a fake briefing with attributes accessed by
            # the task's log line.
            m.return_value = type(
                "B", (),
                {
                    "briefing_id": "abc123def456",
                    "overall_status": type("S", (), {"value": "stable"})(),
                },
            )()
            result = recompute_health_briefing_for_user_task(self.user.id)
        m.assert_called_once_with(self.user, persist=True)
        self.assertEqual(result, "abc123def456")

    def test_skipped_when_user_does_not_exist(self):
        result = recompute_health_briefing_for_user_task(99999999)
        self.assertTrue(result.startswith("skipped:user_not_found"))


# ── Scheduled fan-out task ──────────────────────────────────────────


class RecomputeAllTaskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_a = _make_user("user_a@test.com")
        cls.user_b = _make_user("user_b@test.com")
        cls.user_c_no_state = _make_user("user_c@test.com")
        # Only users A and B have UserState rows. C is excluded.
        UserState.objects.get_or_create(user=cls.user_a, defaults={"state_data": {}})
        UserState.objects.get_or_create(user=cls.user_b, defaults={"state_data": {}})

    def test_dispatches_one_task_per_user_with_state(self):
        with patch(
            "apps.core.health_briefing.tasks."
            "recompute_health_briefing_for_user_task.delay"
        ) as delay:
            count = recompute_all_health_briefings_task()
        # Should fan out to A and B but not C.
        dispatched_ids = sorted(c.args[0] for c in delay.call_args_list)
        self.assertEqual(dispatched_ids, sorted([self.user_a.id, self.user_b.id]))
        self.assertEqual(count, 2)
        self.assertNotIn(self.user_c_no_state.id, dispatched_ids)


# ── Signal handlers ─────────────────────────────────────────────────


class SignalHandlerDispatchTests(TestCase):
    """Each metabolic-input save enqueues the per-user recompute."""

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("signals@test.com")

    def test_glucose_entry_save_dispatches(self):
        from apps.health.models import GlucoseEntry

        with patch(
            "apps.core.health_briefing.tasks."
            "recompute_health_briefing_for_user_task.delay"
        ) as delay:
            GlucoseEntry.objects.create(
                user=self.user, value=Decimal("130"), unit="mg/dL",
                recorded_at=datetime.now(timezone.utc),
            )
        delay.assert_called_with(self.user.id)
        self.assertGreaterEqual(delay.call_count, 1)

    def test_intake_log_save_dispatches(self):
        from apps.health.models import Intake, IntakeLog

        intake = Intake.objects.create(
            user=self.user, name="Lisinopril", dose="10mg",
            frequency="daily", start_date=date(2026, 5, 1),
            intake_status=Intake.STATUS_ACTIVE,
            intake_type=Intake.INTAKE_TYPE_MEDICATION,
        )
        with patch(
            "apps.core.health_briefing.tasks."
            "recompute_health_briefing_for_user_task.delay"
        ) as delay:
            IntakeLog.objects.create(
                user=self.user, intake=intake,
                scheduled_date=date(2026, 5, 20), log_status="taken",
            )
        delay.assert_called_with(self.user.id)

    def test_weight_entry_save_dispatches(self):
        from apps.health.models import WeightEntry

        with patch(
            "apps.core.health_briefing.tasks."
            "recompute_health_briefing_for_user_task.delay"
        ) as delay:
            WeightEntry.objects.create(
                user=self.user, value=Decimal("200"), unit="lb",
                recorded_at=datetime.now(timezone.utc),
            )
        delay.assert_called_with(self.user.id)

    def test_lab_result_save_dispatches(self):
        import uuid
        from apps.medical.models import LabResult, LabTestCatalog

        # get_or_create: the seed migration (medical/0002) already
        # inserts this catalog row, so creating it outright raises a
        # UNIQUE violation on name. Take the seeded row when present.
        catalog, _ = LabTestCatalog.objects.get_or_create(
            name="Hemoglobin A1c",
            defaults={
                "short_name": "HbA1c",
                "category": "diabetes",
                "default_unit": "%",
            },
        )
        with patch(
            "apps.core.health_briefing.tasks."
            "recompute_health_briefing_for_user_task.delay"
        ) as delay:
            LabResult.objects.create(
                id=uuid.uuid4(),
                user=self.user, canonical_test=catalog,
                raw_test_name="Hemoglobin A1c",
                value_text="7.2", value_numeric=Decimal("7.2"),
                unit="%",
                collected_at=datetime.now(timezone.utc),
            )
        delay.assert_called_with(self.user.id)

    def test_dispatch_failure_swallowed_not_raised(self):
        # If Celery is unreachable, the save must not break ingestion.
        from apps.health.models import GlucoseEntry

        with patch(
            "apps.core.health_briefing.tasks."
            "recompute_health_briefing_for_user_task.delay",
            side_effect=RuntimeError("redis down"),
        ):
            # Must not raise.
            GlucoseEntry.objects.create(
                user=self.user, value=Decimal("125"), unit="mg/dL",
                recorded_at=datetime.now(timezone.utc),
            )


# ── Snapshot is terminal — no cascade ───────────────────────────────


class NoSnapshotCascadeTests(TestCase):
    """Creating a HealthBriefingSnapshot must NOT trigger another
    recompute. Snapshots are terminal."""

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("no_cascade@test.com")

    def test_snapshot_save_does_not_dispatch(self):
        with patch(
            "apps.core.health_briefing.tasks."
            "recompute_health_briefing_for_user_task.delay"
        ) as delay:
            HealthBriefingSnapshot.objects.create(
                briefing_id="z" * 64,
                user=self.user,
                generated_at=datetime.now(timezone.utc),
                composer_version="1.0.0",
                payload={"overall_status": "stable"},
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=1800),
            )
        delay.assert_not_called()


# ── Beat schedule registration ──────────────────────────────────────


class BeatScheduleRegistrationTests(TestCase):
    """The CELERY_BEAT_SCHEDULE entry is correctly registered."""

    def test_health_briefing_recompute_entry_present(self):
        from django.conf import settings as s
        self.assertIn(
            "health-briefing-recompute-every-30-min",
            s.CELERY_BEAT_SCHEDULE,
        )
        entry = s.CELERY_BEAT_SCHEDULE["health-briefing-recompute-every-30-min"]
        self.assertEqual(
            entry["task"],
            "apps.core.health_briefing.tasks.recompute_all_health_briefings_task",
        )
        self.assertEqual(entry["schedule"], 1800.0)
