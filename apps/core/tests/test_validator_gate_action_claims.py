"""
Phase 8 — Unverifiable Action-Claim Guardrail Tests.

Tests for the no-action guardrail that prevents the LLM from claiming
it performed backend actions (scheduled, removed, confirmed, etc.)
when no tool actually executed.

Covers:
    - Action-claim detection patterns (checkmark, "I've", "I removed", etc.)
    - Blocking when action_executed=False and claims detected
    - Pass-through when action_executed=True (legitimate action)
    - Pass-through when action_executed=None (legacy callers)
    - SelfError, DecisionRecord, OpsAnomaly governance logging
    - No interference with ECC short-circuit / canned responses
    - Validator crash path still returns safe response (no regression)
"""

from unittest.mock import patch

from django.test import TestCase


def _create_test_user(email='action-claim-test@example.com'):
    from apps.users.models import User
    return User.objects.create_user(email=email, password='testpass123')


# =========================================================================
# ACTION-CLAIM DETECTION — BLOCKING WHEN NO ACTION EXECUTED
# =========================================================================


class ActionClaimBlockingTests(TestCase):
    """When action_executed=False and LLM claims an action, BLOCK."""

    def setUp(self):
        self.user = _create_test_user()

    def test_checkmark_scheduled_blocked(self):
        """'✓ Scheduled' with no action → blocked, template returned."""
        from apps.core.ai_governance.validator_gate import (
            UNVERIFIABLE_ACTION_CLAIM_RESPONSE,
            validate_response,
        )

        response = "✓ Scheduled: Workout on Mar 02 at 6:15 AM"
        result = validate_response(response, self.user, action_executed=False)

        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], UNVERIFIABLE_ACTION_CLAIM_RESPONSE)
        self.assertTrue(any('ACTION_CLAIM' in v for v in result['violations']))

    def test_checkmark_removed_blocked(self):
        """'✓ Removed' with no action → blocked."""
        from apps.core.ai_governance.validator_gate import (
            UNVERIFIABLE_ACTION_CLAIM_RESPONSE,
            validate_response,
        )

        response = "✓ Removed incorrect entries from your calendar."
        result = validate_response(response, self.user, action_executed=False)

        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], UNVERIFIABLE_ACTION_CLAIM_RESPONSE)

    def test_checkmark_confirmed_blocked(self):
        """'✓ Confirmed' with no action → blocked."""
        from apps.core.ai_governance.validator_gate import (
            UNVERIFIABLE_ACTION_CLAIM_RESPONSE,
            validate_response,
        )

        response = "✓ Confirmed — your event is set for February 25."
        result = validate_response(response, self.user, action_executed=False)

        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], UNVERIFIABLE_ACTION_CLAIM_RESPONSE)

    def test_ive_scheduled_blocked(self):
        """'I've scheduled' with no action → blocked."""
        from apps.core.ai_governance.validator_gate import (
            UNVERIFIABLE_ACTION_CLAIM_RESPONSE,
            validate_response,
        )

        response = "I've scheduled your workout for Wednesday at 6:15 AM."
        result = validate_response(response, self.user, action_executed=False)

        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], UNVERIFIABLE_ACTION_CLAIM_RESPONSE)

    def test_ive_removed_blocked(self):
        """'I've removed' with no action → blocked."""
        from apps.core.ai_governance.validator_gate import (
            UNVERIFIABLE_ACTION_CLAIM_RESPONSE,
            validate_response,
        )

        response = "I've removed the two incorrect entries from your calendar."
        result = validate_response(response, self.user, action_executed=False)

        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], UNVERIFIABLE_ACTION_CLAIM_RESPONSE)

    def test_i_deleted_it_blocked(self):
        """'I deleted it' with no action → blocked."""
        from apps.core.ai_governance.validator_gate import (
            UNVERIFIABLE_ACTION_CLAIM_RESPONSE,
            validate_response,
        )

        response = "I deleted it from your calendar as requested."
        result = validate_response(response, self.user, action_executed=False)

        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], UNVERIFIABLE_ACTION_CLAIM_RESPONSE)

    def test_i_rescheduled_your_blocked(self):
        """'I rescheduled your' with no action → blocked."""
        from apps.core.ai_governance.validator_gate import (
            UNVERIFIABLE_ACTION_CLAIM_RESPONSE,
            validate_response,
        )

        response = "I rescheduled your workout to February 25 at 6:15 AM."
        result = validate_response(response, self.user, action_executed=False)

        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], UNVERIFIABLE_ACTION_CLAIM_RESPONSE)

    def test_i_updated_it_blocked(self):
        """'I updated it' with no action → blocked."""
        from apps.core.ai_governance.validator_gate import (
            UNVERIFIABLE_ACTION_CLAIM_RESPONSE,
            validate_response,
        )

        response = "I updated it to the correct date."
        result = validate_response(response, self.user, action_executed=False)

        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], UNVERIFIABLE_ACTION_CLAIM_RESPONSE)

    def test_its_set_blocked(self):
        """'It's set' with no action → blocked."""
        from apps.core.ai_governance.validator_gate import (
            UNVERIFIABLE_ACTION_CLAIM_RESPONSE,
            validate_response,
        )

        response = "It's set for Wednesday at 6:15 AM."
        result = validate_response(response, self.user, action_executed=False)

        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], UNVERIFIABLE_ACTION_CLAIM_RESPONSE)

    def test_its_been_scheduled_blocked(self):
        """'It's been scheduled' with no action → blocked."""
        from apps.core.ai_governance.validator_gate import (
            UNVERIFIABLE_ACTION_CLAIM_RESPONSE,
            validate_response,
        )

        response = "It's been scheduled. You'll see it on your calendar."
        result = validate_response(response, self.user, action_executed=False)

        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], UNVERIFIABLE_ACTION_CLAIM_RESPONSE)

    def test_i_took_care_of_that_blocked(self):
        """'I took care of that' with no action → blocked."""
        from apps.core.ai_governance.validator_gate import (
            UNVERIFIABLE_ACTION_CLAIM_RESPONSE,
            validate_response,
        )

        response = "I took care of that. The incorrect entries are removed."
        result = validate_response(response, self.user, action_executed=False)

        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], UNVERIFIABLE_ACTION_CLAIM_RESPONSE)

    def test_ive_added_blocked(self):
        """'I've added' with no action → blocked."""
        from apps.core.ai_governance.validator_gate import (
            UNVERIFIABLE_ACTION_CLAIM_RESPONSE,
            validate_response,
        )

        response = "I've added it to your calendar now."
        result = validate_response(response, self.user, action_executed=False)

        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], UNVERIFIABLE_ACTION_CLAIM_RESPONSE)

    def test_case_insensitive_detection(self):
        """Detection is case-insensitive."""
        from apps.core.ai_governance.validator_gate import (
            UNVERIFIABLE_ACTION_CLAIM_RESPONSE,
            validate_response,
        )

        response = "I'VE SCHEDULED your workout for Wednesday."
        result = validate_response(response, self.user, action_executed=False)

        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], UNVERIFIABLE_ACTION_CLAIM_RESPONSE)

    def test_unicode_checkmark_variants_blocked(self):
        """Various checkmark symbols are detected."""
        from apps.core.ai_governance.validator_gate import (
            UNVERIFIABLE_ACTION_CLAIM_RESPONSE,
            validate_response,
        )

        for checkmark in ['✓', '✔', '☑']:
            response = f"{checkmark} Removed the event."
            result = validate_response(response, self.user, action_executed=False)
            self.assertTrue(
                result['blocked'],
                f"Failed to block checkmark variant: {checkmark}"
            )
            self.assertEqual(result['response'], UNVERIFIABLE_ACTION_CLAIM_RESPONSE)

    def test_ive_cancelled_blocked(self):
        """'I've cancelled' with no action → blocked."""
        from apps.core.ai_governance.validator_gate import (
            UNVERIFIABLE_ACTION_CLAIM_RESPONSE,
            validate_response,
        )

        response = "I've cancelled those two events as requested."
        result = validate_response(response, self.user, action_executed=False)

        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], UNVERIFIABLE_ACTION_CLAIM_RESPONSE)


# =========================================================================
# PASS-THROUGH WHEN ACTION WAS EXECUTED (LEGITIMATE)
# =========================================================================


class ActionClaimPassThroughTests(TestCase):
    """When action_executed=True, action-claim language is legitimate."""

    def setUp(self):
        self.user = _create_test_user('passthrough-test@example.com')

    def test_checkmark_scheduled_passes_when_action_executed(self):
        """'✓ Scheduled' with action_executed=True → NOT blocked."""
        from apps.core.ai_governance.validator_gate import validate_response

        response = "✓ Scheduled: Workout on Feb 25 at 6:15 AM"
        result = validate_response(response, self.user, action_executed=True)

        self.assertFalse(result['blocked'])
        self.assertEqual(result['response'], response)

    def test_ive_scheduled_passes_when_action_executed(self):
        """'I've scheduled' with action_executed=True → NOT blocked."""
        from apps.core.ai_governance.validator_gate import validate_response

        response = "I've scheduled your workout for Wednesday at 6:15 AM."
        result = validate_response(response, self.user, action_executed=True)

        self.assertFalse(result['blocked'])
        self.assertEqual(result['response'], response)

    def test_action_executed_none_skips_check(self):
        """action_executed=None (legacy caller) → action-claim check skipped."""
        from apps.core.ai_governance.validator_gate import validate_response

        response = "✓ Scheduled: Workout on Feb 25 at 6:15 AM"
        result = validate_response(response, self.user, action_executed=None)

        self.assertFalse(result['blocked'])
        self.assertEqual(result['response'], response)

    def test_action_executed_default_skips_check(self):
        """Default (no action_executed param) → action-claim check skipped."""
        from apps.core.ai_governance.validator_gate import validate_response

        response = "✓ Scheduled: Workout on Feb 25 at 6:15 AM"
        result = validate_response(response, self.user)

        self.assertFalse(result['blocked'])
        self.assertEqual(result['response'], response)


# =========================================================================
# CLEAN RESPONSES — NO FALSE POSITIVES
# =========================================================================


class ActionClaimFalsePositiveTests(TestCase):
    """Conversational language without action claims must pass through."""

    def setUp(self):
        self.user = _create_test_user('fp-test@example.com')

    def test_conversational_response_passes(self):
        """Normal conversational text → not blocked."""
        from apps.core.ai_governance.validator_gate import validate_response

        response = (
            "I can't remove calendar entries through chat yet, but you can "
            "delete them directly from the Time Command Center page."
        )
        result = validate_response(response, self.user, action_executed=False)

        self.assertFalse(result['blocked'])
        self.assertEqual(result['response'], response)

    def test_explaining_capabilities_passes(self):
        """Explaining what the system can do → not blocked."""
        from apps.core.ai_governance.validator_gate import validate_response

        response = (
            "I can create new calendar events for you. To remove or update "
            "existing entries, please use the calendar page directly."
        )
        result = validate_response(response, self.user, action_executed=False)

        self.assertFalse(result['blocked'])
        self.assertEqual(result['response'], response)

    def test_question_about_schedule_passes(self):
        """'When is it scheduled?' → not blocked (asking, not claiming)."""
        from apps.core.ai_governance.validator_gate import validate_response

        response = "Your workout is currently scheduled for Wednesday at 6:15 AM."
        result = validate_response(response, self.user, action_executed=False)

        self.assertFalse(result['blocked'])
        self.assertEqual(result['response'], response)

    def test_done_in_normal_context_passes(self):
        """'Done' in normal context like 'Well done!' → not blocked."""
        from apps.core.ai_governance.validator_gate import validate_response

        response = "Well done on completing your workout today!"
        result = validate_response(response, self.user, action_executed=False)

        self.assertFalse(result['blocked'])
        self.assertEqual(result['response'], response)

    def test_ecc_canned_response_passes(self):
        """ECC short-circuit canned response → not blocked (no action claims)."""
        from apps.core.ai_governance.validator_gate import validate_response

        # ECC responses are canned templates, don't contain action claims
        response = (
            "I hear you. That commitment matters — let me help you "
            "figure out the next step."
        )
        result = validate_response(response, self.user, action_executed=False)

        self.assertFalse(result['blocked'])
        self.assertEqual(result['response'], response)


# =========================================================================
# GOVERNANCE LOGGING
# =========================================================================


class ActionClaimGovernanceTests(TestCase):
    """Governance artifacts created when action claim is blocked."""

    def setUp(self):
        self.user = _create_test_user('gov-test@example.com')

    def test_self_error_created_on_block(self):
        """Blocked action claim → SelfError Level 2, STRUCTURAL, was_blocked=True."""
        from apps.core.ai_governance.models import SelfError
        from apps.core.ai_governance.validator_gate import validate_response

        validate_response(
            "✓ Removed incorrect entries.",
            self.user,
            action_executed=False,
        )

        err = SelfError.objects.filter(
            user=self.user,
            category='STRUCTURAL',
            trigger_code='UNVERIFIABLE_ACTION_CLAIM',
            was_blocked=True,
        ).first()
        self.assertIsNotNone(err)
        self.assertEqual(err.level, SelfError.LEVEL_MODERATE)

    def test_decision_record_created_on_block(self):
        """Blocked action claim → DecisionRecord type='validation'."""
        from apps.core.ai_observability.models import DecisionRecord
        from apps.core.ai_governance.validator_gate import validate_response

        validate_response(
            "I've scheduled your workout for Wednesday.",
            self.user,
            action_executed=False,
        )

        dr = DecisionRecord.objects.filter(
            decision_type='validation',
            engine_name='VGE',
            decision='BLOCK_UNVERIFIABLE_ACTION_CLAIM',
        ).first()
        self.assertIsNotNone(dr)
        self.assertEqual(dr.confidence, 1.0)
        self.assertEqual(dr.user_id, self.user.id)

    def test_ops_anomaly_created_on_block(self):
        """Blocked action claim → OpsAnomaly STRUCTURAL_VIOLATION."""
        from apps.core.ai_observability.models import OpsAnomaly
        from apps.core.ai_governance.validator_gate import validate_response

        validate_response(
            "I took care of that. The entries are removed.",
            self.user,
            action_executed=False,
        )

        anomaly = OpsAnomaly.objects.filter(
            engine_name='VGE',
            anomaly_type='STRUCTURAL_VIOLATION',
            summary__contains='fabricated action confirmation',
        ).first()
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly.severity, 'P2')

    def test_no_governance_artifacts_when_action_executed(self):
        """action_executed=True → no SelfError, no DecisionRecord for action claims."""
        from apps.core.ai_governance.models import SelfError
        from apps.core.ai_observability.models import DecisionRecord
        from apps.core.ai_governance.validator_gate import validate_response

        validate_response(
            "✓ Scheduled: Workout on Feb 25 at 6:15 AM",
            self.user,
            action_executed=True,
        )

        self.assertFalse(SelfError.objects.filter(
            user=self.user,
            trigger_code='UNVERIFIABLE_ACTION_CLAIM',
        ).exists())
        self.assertFalse(DecisionRecord.objects.filter(
            decision='BLOCK_UNVERIFIABLE_ACTION_CLAIM',
        ).exists())


# =========================================================================
# NO REGRESSION — VALIDATOR CRASH + STRUCTURAL + NUMERIC STILL WORK
# =========================================================================


class ActionClaimNoRegressionTests(TestCase):
    """Adding action-claim check must not regress existing validator behavior."""

    def setUp(self):
        self.user = _create_test_user('regression-test@example.com')

    def test_structural_violation_still_blocks(self):
        """Banned terms still blocked (structural takes priority)."""
        from apps.core.ai_governance.validator_gate import (
            STRUCTURAL_BLOCK_RESPONSE,
            validate_response,
        )

        response = "Your drift pressure is rising, so let's focus."
        result = validate_response(response, self.user, action_executed=False)

        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], STRUCTURAL_BLOCK_RESPONSE)
        # Structural, not action claim
        self.assertTrue(any('STRUCTURAL' in v for v in result['violations']))
        self.assertFalse(any('ACTION_CLAIM' in v for v in result['violations']))

    def test_numeric_deviation_still_observes(self):
        """Numeric leakage still observe-only."""
        from apps.core.ai_governance.validator_gate import validate_response

        response = "Your pressure index is 72 today."
        result = validate_response(response, self.user, action_executed=False)

        self.assertFalse(result['blocked'])
        self.assertEqual(result['response'], response)
        self.assertTrue(any('NUMERIC' in v for v in result['violations']))

    def test_validator_crash_still_returns_safe_response(self):
        """Validator crash → crash response (not action-claim response)."""
        from apps.core.ai_governance.validator_gate import (
            VALIDATOR_CRASH_RESPONSE,
            validate_response,
        )

        with patch(
            'apps.core.ai_governance.validator_gate._validate_response_inner',
            side_effect=RuntimeError("unexpected null pointer"),
        ):
            result = validate_response(
                "some output", self.user, action_executed=False
            )

        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], VALIDATOR_CRASH_RESPONSE)

    def test_clean_response_still_passes(self):
        """Clean conversational response → not blocked."""
        from apps.core.ai_governance.validator_gate import validate_response

        response = "Let's focus on your workout today."
        result = validate_response(response, self.user, action_executed=False)

        self.assertFalse(result['blocked'])
        self.assertEqual(result['response'], response)
        self.assertEqual(result['violations'], [])


# =========================================================================
# PATTERN DETECTION UNIT TESTS
# =========================================================================


class ActionClaimPatternTests(TestCase):
    """Direct unit tests for _check_action_claims()."""

    def test_checkmark_variants(self):
        from apps.core.ai_governance.validator_gate import _check_action_claims

        self.assertTrue(_check_action_claims("✓ Scheduled event"))
        self.assertTrue(_check_action_claims("✔ Removed entry"))
        self.assertTrue(_check_action_claims("☑ Confirmed change"))
        self.assertTrue(_check_action_claims("✓ Deleted the event"))
        self.assertTrue(_check_action_claims("✓ Updated your calendar"))
        self.assertTrue(_check_action_claims("✓ Rescheduled for Monday"))
        self.assertTrue(_check_action_claims("✓ Added to calendar"))
        self.assertTrue(_check_action_claims("✓ Created the event"))
        self.assertTrue(_check_action_claims("✓ Cancelled the meeting"))

    def test_ive_patterns(self):
        from apps.core.ai_governance.validator_gate import _check_action_claims

        self.assertTrue(_check_action_claims("I've scheduled your event"))
        self.assertTrue(_check_action_claims("I've removed those entries"))
        self.assertTrue(_check_action_claims("I've deleted it"))
        self.assertTrue(_check_action_claims("I've added it to your calendar"))
        self.assertTrue(_check_action_claims("I've rescheduled the workout"))
        self.assertTrue(_check_action_claims("I've updated your event"))
        self.assertTrue(_check_action_claims("I've confirmed the change"))
        self.assertTrue(_check_action_claims("I've created a new event"))
        self.assertTrue(_check_action_claims("I've cancelled the appointment"))
        self.assertTrue(_check_action_claims("I've taken care of it"))

    def test_i_verb_object_patterns(self):
        from apps.core.ai_governance.validator_gate import _check_action_claims

        self.assertTrue(_check_action_claims("I removed those entries"))
        self.assertTrue(_check_action_claims("I deleted the event"))
        self.assertTrue(_check_action_claims("I scheduled it for Monday"))
        self.assertTrue(_check_action_claims("I updated your calendar"))
        self.assertTrue(_check_action_claims("I rescheduled it"))
        self.assertTrue(_check_action_claims("I cancelled them"))
        self.assertTrue(_check_action_claims("I added those events"))
        self.assertTrue(_check_action_claims("I confirmed all the changes"))

    def test_its_patterns(self):
        from apps.core.ai_governance.validator_gate import _check_action_claims

        self.assertTrue(_check_action_claims("It's set for Wednesday"))
        self.assertTrue(_check_action_claims("It's been scheduled for tomorrow"))
        self.assertTrue(_check_action_claims("It's been removed from your calendar"))
        self.assertTrue(_check_action_claims("It's been deleted"))
        self.assertTrue(_check_action_claims("It's been updated"))
        self.assertTrue(_check_action_claims("It's been rescheduled"))

    def test_took_care_patterns(self):
        from apps.core.ai_governance.validator_gate import _check_action_claims

        self.assertTrue(_check_action_claims("I took care of that"))
        self.assertTrue(_check_action_claims("I took care of it"))
        self.assertTrue(_check_action_claims("I took care of those"))

    def test_clean_text_no_false_positives(self):
        from apps.core.ai_governance.validator_gate import _check_action_claims

        self.assertFalse(_check_action_claims("How are you doing today?"))
        self.assertFalse(_check_action_claims("Let's focus on your workout."))
        self.assertFalse(_check_action_claims(
            "I can create new events for you."
        ))
        self.assertFalse(_check_action_claims(
            "Calendar updates aren't available through chat yet."
        ))
        self.assertFalse(_check_action_claims("Well done on your progress!"))
        self.assertFalse(_check_action_claims(
            "Your workout is currently scheduled for Wednesday."
        ))
