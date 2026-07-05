"""Phase 1 — Class A health events defer DailyHealthSummaryBuilder
to Celery (saves ~1.5–3s on the request path). Class B (glucose, BP,
sync_completed) remain synchronous because the next reasoning pass
must see the just-written value.

These tests guard the routing — a Class B event misrouted to async
could leave Beth blind to a hypoglycemic event for seconds. That's
the failure mode SYNC_HEALTH_EVENTS in subscribers.py prevents.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.core.events.domain_events import EventTypes, safe_emit_event
from apps.core.events.subscribers import SYNC_HEALTH_EVENTS


User = get_user_model()


def _make_user(email="async@test.com"):
    return User.objects.create_user(email=email, password="x" * 20)


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
class ClassAvsClassBRoutingTests(TestCase):
    """With EAGER disabled we can prove the deferred task was enqueued
    (queued via the non-blocking safe_enqueue → apply_async) rather than
    executed inline. Class A never touches the sync builder; a broker
    outage would be swallowed by safe_enqueue, never a request-path
    rebuild. The EAGER=True test below proves correctness end-to-end."""

    def setUp(self):
        self.user = _make_user()

    def test_class_a_water_log_defers_summary_builder(self):
        """Water log → deferred_rebuild_health_summary enqueued via
        apply_async (fire-and-forget), builder NOT invoked synchronously."""
        with patch(
            "apps.health.tasks.deferred_rebuild_health_summary"
        ) as mock_task, patch(
            "apps.health.services.daily_summary_builder.DailyHealthSummaryBuilder.build_for_date"
        ) as mock_sync_builder:
            # Use a non-colliding entry_id — the event bus has a
            # 5-second process-level dedupe cache keyed by entry_id, and
            # other test suites in this run create WaterEntry rows with
            # small ids that would otherwise dedupe this event.
            safe_emit_event(
                EventTypes.HEALTH_WATER_LOGGED, self.user,
                {"entry_id": 9_000_000 + self.user.id},
            )
            # Enqueued fire-and-forget via safe_enqueue → .delay.
            mock_task.delay.assert_called_once()
            args, _ = mock_task.delay.call_args
            self.assertEqual(args[0], self.user.id)
            # Sync builder must NOT have run for Class A.
            mock_sync_builder.assert_not_called()

    def test_class_a_medication_taken_defers_summary_builder(self):
        with patch(
            "apps.health.tasks.deferred_rebuild_health_summary"
        ) as mock_task, patch(
            "apps.health.services.daily_summary_builder.DailyHealthSummaryBuilder.build_for_date"
        ) as mock_sync_builder:
            safe_emit_event(
                EventTypes.HEALTH_MEDICATION_TAKEN, self.user, {},
            )
            mock_task.delay.assert_called_once()
            mock_sync_builder.assert_not_called()

    def test_class_a_weight_logged_defers_summary_builder(self):
        with patch(
            "apps.health.tasks.deferred_rebuild_health_summary"
        ) as mock_task, patch(
            "apps.health.services.daily_summary_builder.DailyHealthSummaryBuilder.build_for_date"
        ) as mock_sync_builder:
            safe_emit_event(
                EventTypes.HEALTH_WEIGHT_LOGGED, self.user, {},
            )
            mock_task.delay.assert_called_once()
            mock_sync_builder.assert_not_called()

    def test_class_b_glucose_logged_runs_summary_builder_sync(self):
        """Glucose is safety-critical — the builder MUST run on the
        request thread so the next CoS/Beth read sees the value."""
        with patch(
            "apps.health.tasks.deferred_rebuild_health_summary"
        ) as mock_task, patch(
            "apps.health.services.daily_summary_builder.DailyHealthSummaryBuilder.build_for_date"
        ) as mock_sync_builder:
            mock_delay = mock_task.delay
            mock_sync = mock_sync_builder
            safe_emit_event(
                EventTypes.HEALTH_GLUCOSE_LOGGED, self.user, {"value": 65},
            )
            mock_sync_builder.assert_called_once()
            mock_delay.assert_not_called()

    def test_class_b_bp_logged_runs_summary_builder_sync(self):
        """All BP is treated as Class B because crisis-range readings
        cannot be allowed to defer."""
        with patch(
            "apps.health.tasks.deferred_rebuild_health_summary"
        ) as mock_task, patch(
            "apps.health.services.daily_summary_builder.DailyHealthSummaryBuilder.build_for_date"
        ) as mock_sync_builder:
            mock_delay = mock_task.delay
            mock_sync = mock_sync_builder
            safe_emit_event(
                EventTypes.HEALTH_BP_LOGGED, self.user,
                {"systolic": 190, "diastolic": 125},
            )
            mock_sync_builder.assert_called_once()
            mock_delay.assert_not_called()

    def test_class_b_sync_completed_runs_summary_builder_sync(self):
        """iOS/CGM batch ingestion may carry glucose values — sync."""
        with patch(
            "apps.health.tasks.deferred_rebuild_health_summary"
        ) as mock_task, patch(
            "apps.health.services.daily_summary_builder.DailyHealthSummaryBuilder.build_for_date"
        ) as mock_sync_builder:
            mock_delay = mock_task.delay
            mock_sync = mock_sync_builder
            safe_emit_event(
                EventTypes.HEALTH_SYNC_COMPLETED, self.user,
                {"source": "apple_health"},
            )
            mock_sync_builder.assert_called_once()
            mock_delay.assert_not_called()


class SyncSetSafetyTests(TestCase):
    """Explicit registry test — SYNC_HEALTH_EVENTS must contain the
    full approved Class B list. A missing event here = silent latency
    win that violates safety; an extra event here = latency regression
    on a Class A path. Either way we want a CI failure."""

    def test_sync_set_contents_match_approved_class_b_list(self):
        expected = {
            EventTypes.HEALTH_GLUCOSE_LOGGED,
            EventTypes.HEALTH_BP_LOGGED,
            EventTypes.HEALTH_SYNC_COMPLETED,
        }
        self.assertEqual(
            SYNC_HEALTH_EVENTS, expected,
            "SYNC_HEALTH_EVENTS drifted from the approved Class B list. "
            "Any change must be reviewed and the changelog updated.",
        )


class DeferredTaskCorrectnessTests(TestCase):
    """The Celery task wrapper must produce the same DailyHealthSummary
    row as a direct sync builder call — same data, just async."""

    def setUp(self):
        self.user = _make_user("celery-correctness@test.com")

    def test_deferred_task_builds_summary_for_user(self):
        from datetime import date
        from apps.health.tasks import deferred_rebuild_health_summary
        result = deferred_rebuild_health_summary(
            self.user.id, date.today().isoformat(),
        )
        # acks=ok means the builder ran without raising.
        self.assertEqual(result.get("status"), "ok")
        self.assertEqual(result.get("user_id"), self.user.id)

    def test_deferred_task_returns_user_not_found_for_bad_id(self):
        from datetime import date
        from apps.health.tasks import deferred_rebuild_health_summary
        result = deferred_rebuild_health_summary(
            999_999, date.today().isoformat(),
        )
        self.assertEqual(result.get("status"), "user_not_found")

    def test_deferred_task_returns_bad_date_for_garbage_input(self):
        from apps.health.tasks import deferred_rebuild_health_summary
        result = deferred_rebuild_health_summary(self.user.id, "not-a-date")
        self.assertEqual(result.get("status"), "bad_date")
