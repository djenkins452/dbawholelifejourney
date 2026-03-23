"""Tests for Phase 4 Signal Feedback — Confirmation + Learning Loop.

Covers:
1. Valid "yes" response → record created + completion triggered
2. Valid "no" response → record created, no completion
3. Invalid response → ignored (returns None)
4. Correct fingerprint stored
5. Multiple responses → multiple records (no dedup yet)
6. Completion uses existing services (not direct writes)
7. Case-insensitive response matching
8. Signal type gating (only possible_completion triggers completion)
"""

from datetime import time
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.core.signals.feedback_service import (
    _generate_fingerprint,
    record_signal_feedback,
)
from apps.core.signals.models import SignalFeedback
from apps.core.signals.signal_engine import (
    EFFORT_SIGNAL,
    INCONSISTENCY_SIGNAL,
    INTENT_SIGNAL,
    POSSIBLE_COMPLETION,
)


def _make_signal(
    signal_type=POSSIBLE_COMPLETION,
    domain="faith",
    item="prayer",
    confidence=0.85,
    source="journal",
    text="I prayed this morning",
    timestamp=None,
):
    """Helper to create a test signal dict."""
    return {
        "type": signal_type,
        "domain": domain,
        "item": item,
        "confidence": confidence,
        "source": source,
        "text": text,
        "timestamp": timestamp or timezone.now(),
    }


class TestRecordFeedbackBasics(TestCase):
    """Basic feedback recording tests."""

    def setUp(self):
        from apps.users.models import User

        self.user = User.objects.create_user(
            email="signaltest@example.com", password="testpass123"
        )

    @patch(
        "apps.core.signals.feedback_service._trigger_completion",
        return_value={"success": True, "reason": "completed"},
    )
    def test_yes_response_creates_record_and_triggers_completion(self, mock_complete):
        """Valid 'yes' on possible_completion → record + completion."""
        signal = _make_signal()
        result = record_signal_feedback(self.user, signal, "yes")

        self.assertIsNotNone(result)
        self.assertTrue(result["recorded"])
        self.assertTrue(result["completion_triggered"])

        # Verify DB record
        fb = SignalFeedback.objects.get(user=self.user)
        self.assertEqual(fb.signal_type, POSSIBLE_COMPLETION)
        self.assertEqual(fb.domain, "faith")
        self.assertEqual(fb.item, "prayer")
        self.assertEqual(fb.response, "yes")
        self.assertEqual(fb.source, "journal")

        # Verify completion was called
        mock_complete.assert_called_once_with(self.user, "faith", "prayer")

    def test_no_response_creates_record_no_completion(self):
        """Valid 'no' → record created, no completion triggered."""
        signal = _make_signal()
        result = record_signal_feedback(self.user, signal, "no")

        self.assertIsNotNone(result)
        self.assertTrue(result["recorded"])
        self.assertFalse(result["completion_triggered"])

        fb = SignalFeedback.objects.get(user=self.user)
        self.assertEqual(fb.response, "no")

    def test_invalid_response_ignored(self):
        """Invalid response (not yes/no) → returns None, no record."""
        signal = _make_signal()

        for invalid in ["maybe", "sure", "", "   ", "yep", "nah", "1", None]:
            result = record_signal_feedback(self.user, signal, invalid)
            self.assertIsNone(result)

        self.assertEqual(SignalFeedback.objects.filter(user=self.user).count(), 0)

    def test_case_insensitive_responses(self):
        """Yes/No accepted in any case."""
        signal = _make_signal()

        # Mock completion for yes responses
        with patch(
            "apps.core.signals.feedback_service._trigger_completion",
            return_value={"success": True},
        ):
            for resp in ["YES", "Yes", "yEs", "  yes  "]:
                record_signal_feedback(self.user, signal, resp)

        for resp in ["NO", "No", "nO", "  no  "]:
            record_signal_feedback(self.user, signal, resp)

        total = SignalFeedback.objects.filter(user=self.user).count()
        self.assertEqual(total, 8)  # 4 yes + 4 no


class TestFingerprintGeneration(TestCase):
    """Fingerprint generation and storage tests."""

    def setUp(self):
        from apps.users.models import User

        self.user = User.objects.create_user(
            email="fptest@example.com", password="testpass123"
        )

    def test_fingerprint_stored_correctly(self):
        """Generated fingerprint is stored in the record."""
        signal = _make_signal()
        expected_fp = _generate_fingerprint(signal)

        result = record_signal_feedback(self.user, signal, "no")

        fb = SignalFeedback.objects.get(id=result["feedback_id"])
        self.assertEqual(fb.fingerprint, expected_fp)
        self.assertEqual(len(fb.fingerprint), 32)

    def test_fingerprint_deterministic(self):
        """Same signal produces same fingerprint."""
        ts = timezone.now()
        s1 = _make_signal(timestamp=ts)
        s2 = _make_signal(timestamp=ts)

        self.assertEqual(_generate_fingerprint(s1), _generate_fingerprint(s2))

    def test_fingerprint_varies_by_type(self):
        """Different signal types produce different fingerprints."""
        ts = timezone.now()
        fp1 = _generate_fingerprint(_make_signal(signal_type=POSSIBLE_COMPLETION, timestamp=ts))
        fp2 = _generate_fingerprint(_make_signal(signal_type=EFFORT_SIGNAL, timestamp=ts))
        self.assertNotEqual(fp1, fp2)

    def test_fingerprint_varies_by_domain(self):
        """Different domains produce different fingerprints."""
        ts = timezone.now()
        fp1 = _generate_fingerprint(_make_signal(domain="faith", timestamp=ts))
        fp2 = _generate_fingerprint(_make_signal(domain="health", timestamp=ts))
        self.assertNotEqual(fp1, fp2)

    def test_custom_fingerprint_preserved(self):
        """If signal already has a fingerprint, it's used as-is."""
        signal = _make_signal()
        signal["fingerprint"] = "custom_fp_abc123"

        result = record_signal_feedback(self.user, signal, "no")
        fb = SignalFeedback.objects.get(id=result["feedback_id"])
        self.assertEqual(fb.fingerprint, "custom_fp_abc123")


class TestMultipleResponses(TestCase):
    """Multiple response handling — no dedup in Phase 4."""

    def setUp(self):
        from apps.users.models import User

        self.user = User.objects.create_user(
            email="multitest@example.com", password="testpass123"
        )

    def test_multiple_responses_create_multiple_records(self):
        """Same signal responded to multiple times → multiple records."""
        signal = _make_signal()

        record_signal_feedback(self.user, signal, "no")
        record_signal_feedback(self.user, signal, "no")

        with patch(
            "apps.core.signals.feedback_service._trigger_completion",
            return_value={"success": True},
        ):
            record_signal_feedback(self.user, signal, "yes")

        self.assertEqual(
            SignalFeedback.objects.filter(user=self.user).count(), 3
        )


class TestCompletionBridge(TestCase):
    """Execution bridge tests — completion only for possible_completion + yes."""

    def setUp(self):
        from apps.users.models import User

        self.user = User.objects.create_user(
            email="bridgetest@example.com", password="testpass123"
        )

    def test_only_possible_completion_triggers_action(self):
        """Non-completion signal types never trigger completion."""
        for sig_type in [EFFORT_SIGNAL, INTENT_SIGNAL, INCONSISTENCY_SIGNAL]:
            signal = _make_signal(signal_type=sig_type)
            result = record_signal_feedback(self.user, signal, "yes")

            self.assertIsNotNone(result)
            self.assertTrue(result["recorded"])
            self.assertFalse(result["completion_triggered"])

    @patch(
        "apps.core.signals.feedback_service._trigger_completion",
        return_value={"success": True, "reason": "completed"},
    )
    def test_possible_completion_yes_triggers_action(self, mock_complete):
        """possible_completion + yes triggers completion."""
        signal = _make_signal(signal_type=POSSIBLE_COMPLETION)
        result = record_signal_feedback(self.user, signal, "yes")

        self.assertTrue(result["completion_triggered"])
        mock_complete.assert_called_once()

    def test_possible_completion_no_does_not_trigger(self):
        """possible_completion + no does NOT trigger completion."""
        signal = _make_signal(signal_type=POSSIBLE_COMPLETION)
        result = record_signal_feedback(self.user, signal, "no")

        self.assertFalse(result["completion_triggered"])


class TestCompletionViaRoutine(TestCase):
    """Tests that completion uses existing routine services."""

    def setUp(self):
        from apps.users.models import User

        self.user = User.objects.create_user(
            email="routinetest@example.com", password="testpass123"
        )

    @patch("apps.life.services.routine_helpers.toggle_routine_completion")
    def test_completion_calls_toggle_routine(self, mock_toggle):
        """Completion bridge uses toggle_routine_completion, not direct writes."""
        from apps.life.models import Routine, RoutineSchedule

        # Create a routine with a prayer item scheduled today
        routine = Routine.objects.create(
            user=self.user,
            name="Morning Routine",
            is_active=True,
        )
        today = timezone.localdate()
        day_of_week = str(today.weekday())
        schedule = RoutineSchedule.objects.create(
            routine=routine,
            name="Prayer",
            scheduled_time=time(6, 0),
            days_of_week=day_of_week,
        )

        mock_toggle.return_value = {"is_completed": True, "status": "completed"}

        signal = _make_signal(
            signal_type=POSSIBLE_COMPLETION,
            domain="faith",
            item="prayer",
        )
        result = record_signal_feedback(self.user, signal, "yes")

        self.assertTrue(result["completion_triggered"])
        mock_toggle.assert_called_once_with(
            user=self.user,
            schedule=schedule,
            target_date=today,
        )

    def test_no_matching_schedule_returns_no_match(self):
        """If no routine schedule matches, completion reports no match."""
        signal = _make_signal(
            signal_type=POSSIBLE_COMPLETION,
            domain="faith",
            item="prayer",
        )
        result = record_signal_feedback(self.user, signal, "yes")

        # Record is still created
        self.assertTrue(result["recorded"])
        # But completion failed (no matching schedule)
        self.assertFalse(result["completion_triggered"])
        self.assertEqual(
            result["completion_detail"]["reason"], "no_matching_schedule"
        )

    def test_unmapped_item_returns_no_mapping(self):
        """Signal item with no routine mapping reports accordingly."""
        signal = _make_signal(
            signal_type=POSSIBLE_COMPLETION,
            domain="purpose",
            item="goal_work",
        )
        result = record_signal_feedback(self.user, signal, "yes")

        self.assertTrue(result["recorded"])
        self.assertFalse(result["completion_triggered"])
        self.assertEqual(
            result["completion_detail"]["reason"], "no_routine_mapping"
        )

    @patch("apps.life.services.routine_helpers.toggle_routine_completion")
    def test_already_completed_skips_toggle(self, mock_toggle):
        """If routine item already completed today, skip toggle."""
        from apps.life.models import Routine, RoutineLog, RoutineSchedule

        routine = Routine.objects.create(
            user=self.user,
            name="Morning Routine",
            is_active=True,
        )
        today = timezone.localdate()
        day_of_week = str(today.weekday())
        schedule = RoutineSchedule.objects.create(
            routine=routine,
            name="Prayer",
            scheduled_time=time(6, 0),
            days_of_week=day_of_week,
        )
        # Pre-existing completed log
        RoutineLog.objects.create(
            user=self.user,
            schedule=schedule,
            scheduled_date=today,
            log_status="completed",
            completed_at=timezone.now(),
        )

        signal = _make_signal(
            signal_type=POSSIBLE_COMPLETION,
            domain="faith",
            item="prayer",
        )
        result = record_signal_feedback(self.user, signal, "yes")

        self.assertTrue(result["completion_triggered"])
        self.assertEqual(result["completion_detail"]["reason"], "already_completed")
        mock_toggle.assert_not_called()
