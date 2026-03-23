"""Tests for Phase 4/4.1 Signal Feedback — Integrity Hardened.

Covers:
1. Valid "yes" response → record created + completion triggered
2. Valid "no" response → record created, no completion
3. Invalid response → ignored (returns None)
4. Correct fingerprint stored
5. Multiple responses → multiple records (no dedup yet)
6. Completion uses existing services (not direct writes)
7. Case-insensitive response matching
8. Signal type gating (only possible_completion triggers completion)

v4.1 Hardening:
A. Idempotency — first yes completes, second yes skips execution
B. Fingerprint normalization — case/whitespace invariant
C. Context binding — feedback maps to correct signal
D. Handler routing — domain+item → correct handler
E. Response filtering — sanitization edge cases
F. Execution conditions — 4-gate check
"""

from datetime import time
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.core.signals.feedback_service import (
    _generate_fingerprint,
    _get_completion_handler,
    _is_already_completed,
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


# ===================================================================
# Phase 4 — Original tests
# ===================================================================


class TestRecordFeedbackBasics(TestCase):
    """Basic feedback recording tests."""

    def setUp(self):
        from apps.users.models import User

        self.user = User.objects.create_user(
            email="signaltest@example.com", password="testpass123"
        )

    @patch(
        "apps.core.signals.feedback_service._get_completion_handler",
        return_value=MagicMock(return_value={"success": True, "reason": "completed"}),
    )
    @patch(
        "apps.core.signals.feedback_service._is_already_completed",
        return_value=False,
    )
    def test_yes_response_creates_record_and_triggers_completion(
        self, mock_truth, mock_handler
    ):
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

    @patch(
        "apps.core.signals.feedback_service._get_completion_handler",
        return_value=MagicMock(return_value={"success": True}),
    )
    @patch(
        "apps.core.signals.feedback_service._is_already_completed",
        return_value=False,
    )
    def test_case_insensitive_responses(self, mock_truth, mock_handler):
        """Yes/No accepted in any case."""
        signal = _make_signal()

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
        fp1 = _generate_fingerprint(
            _make_signal(signal_type=POSSIBLE_COMPLETION, timestamp=ts)
        )
        fp2 = _generate_fingerprint(
            _make_signal(signal_type=EFFORT_SIGNAL, timestamp=ts)
        )
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

    @patch(
        "apps.core.signals.feedback_service._get_completion_handler",
        return_value=MagicMock(return_value={"success": True}),
    )
    @patch(
        "apps.core.signals.feedback_service._is_already_completed",
        return_value=False,
    )
    def test_multiple_responses_create_multiple_records(
        self, mock_truth, mock_handler
    ):
        """Same signal responded to multiple times → multiple records."""
        signal = _make_signal()

        record_signal_feedback(self.user, signal, "no")
        record_signal_feedback(self.user, signal, "no")
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
        "apps.core.signals.feedback_service._get_completion_handler",
        return_value=MagicMock(return_value={"success": True, "reason": "completed"}),
    )
    @patch(
        "apps.core.signals.feedback_service._is_already_completed",
        return_value=False,
    )
    def test_possible_completion_yes_triggers_action(
        self, mock_truth, mock_handler
    ):
        """possible_completion + yes triggers completion."""
        signal = _make_signal(signal_type=POSSIBLE_COMPLETION)
        result = record_signal_feedback(self.user, signal, "yes")

        self.assertTrue(result["completion_triggered"])

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
    @patch(
        "apps.core.signals.feedback_service._is_already_completed",
        return_value=False,
    )
    def test_completion_calls_toggle_routine(self, mock_truth, mock_toggle):
        """Completion bridge uses toggle_routine_completion, not direct writes."""
        from apps.life.models import Routine, RoutineSchedule

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
        with patch(
            "apps.core.signals.feedback_service._is_already_completed",
            return_value=False,
        ):
            result = record_signal_feedback(self.user, signal, "yes")

        self.assertTrue(result["recorded"])
        self.assertFalse(result["completion_triggered"])
        self.assertEqual(
            result["completion_detail"]["reason"], "no_matching_schedule"
        )

    def test_unmapped_item_returns_no_handler(self):
        """Signal item with no handler reports accordingly."""
        signal = _make_signal(
            signal_type=POSSIBLE_COMPLETION,
            domain="purpose",
            item="goal_work",
        )
        result = record_signal_feedback(self.user, signal, "yes")

        self.assertTrue(result["recorded"])
        self.assertFalse(result["completion_triggered"])
        self.assertEqual(
            result["completion_detail"]["reason"], "no_handler"
        )


# ===================================================================
# Phase 4.1 — Integrity Hardening tests
# ===================================================================


class TestIdempotencyGuard(TestCase):
    """A. Idempotency — duplicate yes must not trigger duplicate execution."""

    def setUp(self):
        from apps.users.models import User

        self.user = User.objects.create_user(
            email="idempotent@example.com", password="testpass123"
        )

    @patch("apps.life.services.routine_helpers.toggle_routine_completion")
    def test_first_yes_completes_second_yes_skips(self, mock_toggle):
        """First yes → completion triggered. Second yes → already_completed."""
        from apps.life.models import Routine, RoutineSchedule

        routine = Routine.objects.create(
            user=self.user, name="Morning Routine", is_active=True,
        )
        today = timezone.localdate()
        schedule = RoutineSchedule.objects.create(
            routine=routine,
            name="Prayer",
            scheduled_time=time(6, 0),
            days_of_week=str(today.weekday()),
        )

        mock_toggle.return_value = {"is_completed": True, "status": "completed"}

        signal = _make_signal(
            signal_type=POSSIBLE_COMPLETION, domain="faith", item="prayer",
        )

        # First yes — not completed yet → triggers completion
        with patch(
            "apps.core.signals.feedback_service._is_already_completed",
            return_value=False,
        ):
            r1 = record_signal_feedback(self.user, signal, "yes")

        self.assertTrue(r1["completion_triggered"])
        self.assertEqual(r1["completion_detail"]["reason"], "completed")
        mock_toggle.assert_called_once()

        # Second yes — already completed → skips execution
        with patch(
            "apps.core.signals.feedback_service._is_already_completed",
            return_value=True,
        ):
            r2 = record_signal_feedback(self.user, signal, "yes")

        self.assertTrue(r2["completion_triggered"])
        self.assertEqual(r2["completion_detail"]["reason"], "already_completed")
        # toggle was NOT called again
        mock_toggle.assert_called_once()

        # Both responses recorded
        self.assertEqual(
            SignalFeedback.objects.filter(user=self.user).count(), 2
        )

    def test_feedback_always_recorded_even_when_idempotent(self):
        """Even when completion is skipped, feedback record is always created."""
        signal = _make_signal(
            signal_type=POSSIBLE_COMPLETION, domain="faith", item="prayer",
        )
        with patch(
            "apps.core.signals.feedback_service._is_already_completed",
            return_value=True,
        ):
            result = record_signal_feedback(self.user, signal, "yes")

        self.assertTrue(result["recorded"])
        self.assertEqual(
            SignalFeedback.objects.filter(user=self.user).count(), 1
        )


class TestFingerprintNormalization(TestCase):
    """B. Fingerprint normalization — case and whitespace invariant."""

    def test_case_insensitive_fingerprint(self):
        """'Prayer' vs 'prayer' → same fingerprint."""
        ts = timezone.now()
        fp1 = _generate_fingerprint(_make_signal(item="Prayer", timestamp=ts))
        fp2 = _generate_fingerprint(_make_signal(item="prayer", timestamp=ts))
        self.assertEqual(fp1, fp2)

    def test_whitespace_insensitive_fingerprint(self):
        """'  prayer  ' vs 'prayer' → same fingerprint."""
        ts = timezone.now()
        fp1 = _generate_fingerprint(_make_signal(item="  prayer  ", timestamp=ts))
        fp2 = _generate_fingerprint(_make_signal(item="prayer", timestamp=ts))
        self.assertEqual(fp1, fp2)

    def test_domain_case_normalized(self):
        """'Faith' vs 'faith' → same fingerprint."""
        ts = timezone.now()
        fp1 = _generate_fingerprint(_make_signal(domain="Faith", timestamp=ts))
        fp2 = _generate_fingerprint(_make_signal(domain="faith", timestamp=ts))
        self.assertEqual(fp1, fp2)

    def test_type_case_normalized(self):
        """'POSSIBLE_COMPLETION' vs 'possible_completion' → same fingerprint."""
        ts = timezone.now()
        fp1 = _generate_fingerprint(
            _make_signal(signal_type="POSSIBLE_COMPLETION", timestamp=ts)
        )
        fp2 = _generate_fingerprint(
            _make_signal(signal_type="possible_completion", timestamp=ts)
        )
        self.assertEqual(fp1, fp2)

    def test_stored_fields_are_normalized(self):
        """Fields stored in DB are normalized (lowercase, stripped)."""
        from apps.users.models import User

        user = User.objects.create_user(
            email="normtest@example.com", password="testpass123"
        )
        signal = _make_signal(
            signal_type="POSSIBLE_COMPLETION",
            domain="  Faith  ",
            item="  Prayer  ",
            source="  Journal  ",
        )
        result = record_signal_feedback(user, signal, "no")
        fb = SignalFeedback.objects.get(id=result["feedback_id"])

        self.assertEqual(fb.signal_type, "possible_completion")
        self.assertEqual(fb.domain, "faith")
        self.assertEqual(fb.item, "prayer")
        self.assertEqual(fb.source, "journal")


class TestContextBinding(TestCase):
    """C. Context binding — feedback maps to the exact presented signal."""

    def setUp(self):
        from apps.users.models import User

        self.user = User.objects.create_user(
            email="contexttest@example.com", password="testpass123"
        )

    def test_feedback_maps_to_correct_signal(self):
        """Two different signals produce distinct feedback records."""
        signal_prayer = _make_signal(domain="faith", item="prayer")
        signal_workout = _make_signal(domain="health", item="workout")

        r1 = record_signal_feedback(self.user, signal_prayer, "no")
        r2 = record_signal_feedback(self.user, signal_workout, "no")

        fb1 = SignalFeedback.objects.get(id=r1["feedback_id"])
        fb2 = SignalFeedback.objects.get(id=r2["feedback_id"])

        self.assertEqual(fb1.domain, "faith")
        self.assertEqual(fb1.item, "prayer")
        self.assertEqual(fb2.domain, "health")
        self.assertEqual(fb2.item, "workout")
        self.assertNotEqual(fb1.fingerprint, fb2.fingerprint)

    def test_no_cross_signal_contamination(self):
        """Responding to signal A does not affect signal B."""
        signal_a = _make_signal(domain="faith", item="prayer")
        signal_b = _make_signal(domain="health", item="workout")

        # Respond yes to prayer, no to workout
        with patch(
            "apps.core.signals.feedback_service._get_completion_handler",
            return_value=MagicMock(return_value={"success": True}),
        ), patch(
            "apps.core.signals.feedback_service._is_already_completed",
            return_value=False,
        ):
            r1 = record_signal_feedback(self.user, signal_a, "yes")
        r2 = record_signal_feedback(self.user, signal_b, "no")

        self.assertTrue(r1["completion_triggered"])
        self.assertFalse(r2["completion_triggered"])

        # Only 2 records, each with correct signal
        self.assertEqual(
            SignalFeedback.objects.filter(user=self.user).count(), 2
        )


class TestHandlerRouting(TestCase):
    """D. Handler routing — domain+item dispatches to correct handler."""

    def test_registered_domains_have_handlers(self):
        """All expected domain+item pairs have handlers."""
        expected = [
            ("faith", "prayer"),
            ("faith", "bible_reading"),
            ("health", "workout"),
            ("health", "running"),
            ("health", "walking"),
            ("health", "yoga"),
            ("journal", "journal_entry"),
        ]
        for domain, item in expected:
            handler = _get_completion_handler(domain, item)
            self.assertIsNotNone(
                handler, f"No handler for ({domain}, {item})"
            )

    def test_unknown_domain_returns_no_handler(self):
        """Unknown domain+item → None (no handler)."""
        self.assertIsNone(_get_completion_handler("unknown", "thing"))
        self.assertIsNone(_get_completion_handler("purpose", "goal_work"))

    def test_no_handler_records_feedback_only(self):
        """When no handler exists, feedback is recorded but no execution."""
        from apps.users.models import User

        user = User.objects.create_user(
            email="nohandler@example.com", password="testpass123"
        )
        signal = _make_signal(
            signal_type=POSSIBLE_COMPLETION,
            domain="purpose",
            item="goal_work",
        )
        result = record_signal_feedback(user, signal, "yes")

        self.assertTrue(result["recorded"])
        self.assertFalse(result["completion_triggered"])
        self.assertEqual(result["completion_detail"]["reason"], "no_handler")
        self.assertEqual(
            SignalFeedback.objects.filter(user=user).count(), 1
        )


class TestResponseFiltering(TestCase):
    """E. Response filtering — sanitization edge cases."""

    def setUp(self):
        from apps.users.models import User

        self.user = User.objects.create_user(
            email="filtertest@example.com", password="testpass123"
        )

    def test_whitespace_padded_yes_accepted(self):
        """' YES ' → accepted as yes."""
        signal = _make_signal()
        with patch(
            "apps.core.signals.feedback_service._get_completion_handler",
            return_value=MagicMock(return_value={"success": True}),
        ), patch(
            "apps.core.signals.feedback_service._is_already_completed",
            return_value=False,
        ):
            result = record_signal_feedback(self.user, signal, " YES ")
        self.assertIsNotNone(result)
        self.assertTrue(result["recorded"])

    def test_maybe_ignored(self):
        """'maybe' → ignored, no record."""
        signal = _make_signal()
        result = record_signal_feedback(self.user, signal, "maybe")
        self.assertIsNone(result)
        self.assertEqual(
            SignalFeedback.objects.filter(user=self.user).count(), 0
        )

    def test_none_response_ignored(self):
        """None → ignored."""
        signal = _make_signal()
        result = record_signal_feedback(self.user, signal, None)
        self.assertIsNone(result)

    def test_empty_string_ignored(self):
        """Empty/whitespace → ignored."""
        signal = _make_signal()
        for val in ["", "  ", "\t", "\n"]:
            result = record_signal_feedback(self.user, signal, val)
            self.assertIsNone(result)


class TestExecutionConditions(TestCase):
    """F. Execution conditions — 4-gate check validation."""

    def setUp(self):
        from apps.users.models import User

        self.user = User.objects.create_user(
            email="gatetest@example.com", password="testpass123"
        )

    def test_gate_signal_type_blocks_non_completion(self):
        """Gate 2: Non-completion types never trigger execution."""
        for sig_type in [EFFORT_SIGNAL, INTENT_SIGNAL, INCONSISTENCY_SIGNAL]:
            signal = _make_signal(signal_type=sig_type)
            result = record_signal_feedback(self.user, signal, "yes")
            self.assertFalse(result["completion_triggered"])
            self.assertNotIn("completion_detail", result)

    def test_gate_response_blocks_no(self):
        """Gate 3: 'no' on possible_completion → no execution."""
        signal = _make_signal(signal_type=POSSIBLE_COMPLETION)
        result = record_signal_feedback(self.user, signal, "no")
        self.assertFalse(result["completion_triggered"])
        self.assertNotIn("completion_detail", result)

    def test_gate_handler_blocks_unregistered(self):
        """Gate 4: No handler → no execution, records feedback only."""
        signal = _make_signal(
            signal_type=POSSIBLE_COMPLETION,
            domain="purpose",
            item="goal_work",
        )
        result = record_signal_feedback(self.user, signal, "yes")
        self.assertFalse(result["completion_triggered"])
        self.assertEqual(result["completion_detail"]["reason"], "no_handler")

    def test_gate_truth_blocks_already_completed(self):
        """Gate 5: Already completed → no execution, reports already_completed."""
        signal = _make_signal(
            signal_type=POSSIBLE_COMPLETION,
            domain="faith",
            item="prayer",
        )
        with patch(
            "apps.core.signals.feedback_service._is_already_completed",
            return_value=True,
        ):
            result = record_signal_feedback(self.user, signal, "yes")

        self.assertTrue(result["completion_triggered"])
        self.assertEqual(
            result["completion_detail"]["reason"], "already_completed"
        )

    @patch(
        "apps.core.signals.feedback_service._get_completion_handler",
        return_value=MagicMock(return_value={"success": True, "reason": "completed"}),
    )
    @patch(
        "apps.core.signals.feedback_service._is_already_completed",
        return_value=False,
    )
    def test_all_gates_pass_triggers_completion(self, mock_truth, mock_handler):
        """All 4 gates pass → completion triggered."""
        signal = _make_signal(
            signal_type=POSSIBLE_COMPLETION,
            domain="faith",
            item="prayer",
        )
        result = record_signal_feedback(self.user, signal, "yes")
        self.assertTrue(result["completion_triggered"])
        self.assertEqual(result["completion_detail"]["reason"], "completed")
