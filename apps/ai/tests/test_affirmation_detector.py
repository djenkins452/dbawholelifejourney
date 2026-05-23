# ==============================================================================
# File: test_affirmation_detector.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for user-affirmed completion detection and suppression
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-09
# ==============================================================================

from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.ai.affirmation_detector import (
    CHECK_IN_TYPE_MAP,
    detect_affirmed_completion,
    get_affirmed_completions,
    handle_affirmed_completion,
    identify_affirmed_activity,
    is_activity_affirmed,
    store_affirmed_completion,
)
from apps.ai.models import AssistantConversation, AssistantMessage
from apps.users.models import User


class AffirmationTestBase(TestCase):
    """Base class with shared setup for affirmation detector tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='affirm-test@example.com',
            password='testpass123',
        )
        # Onboarding setup
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

        self.conversation = AssistantConversation.objects.create(
            user=self.user,
            title='Test Conversation',
            is_active=True,
            metadata={},
        )


class TestDetectAffirmedCompletion(TestCase):
    """Test the affirmed completion pattern matching."""

    # -- Positive matches (should detect) --

    def test_already_did_it(self):
        detected, confidence = detect_affirmed_completion("I already did it")
        self.assertTrue(detected)
        self.assertGreaterEqual(confidence, 0.85)

    def test_already_completed_it(self):
        detected, confidence = detect_affirmed_completion("I already completed it")
        self.assertTrue(detected)
        self.assertGreaterEqual(confidence, 0.85)

    def test_already_took_care_of_it(self):
        detected, confidence = detect_affirmed_completion("I took care of that")
        self.assertTrue(detected)
        self.assertGreaterEqual(confidence, 0.85)

    def test_already_logged_it(self):
        detected, confidence = detect_affirmed_completion("I already logged it")
        self.assertTrue(detected)

    def test_already_finished(self):
        detected, confidence = detect_affirmed_completion("I already finished that")
        self.assertTrue(detected)

    def test_did_it_earlier(self):
        detected, confidence = detect_affirmed_completion("I did it earlier")
        self.assertTrue(detected)

    def test_completed_before_reminder(self):
        detected, confidence = detect_affirmed_completion(
            "I already completed it before I saw this reminder. This was a timing issue."
        )
        self.assertTrue(detected)
        self.assertGreaterEqual(confidence, 0.6)

    def test_already_worked_out(self):
        detected, confidence = detect_affirmed_completion("Already worked out this morning")
        self.assertTrue(detected)

    def test_already_journaled(self):
        detected, confidence = detect_affirmed_completion("I already journaled")
        self.assertTrue(detected)

    def test_already_prayed(self):
        detected, confidence = detect_affirmed_completion("Already prayed earlier")
        self.assertTrue(detected)

    def test_already_took_meds(self):
        detected, confidence = detect_affirmed_completion("Already took my meds")
        self.assertTrue(detected)

    def test_got_workout_done(self):
        detected, confidence = detect_affirmed_completion("Got my workout done")
        self.assertTrue(detected)

    def test_got_journal_in(self):
        detected, confidence = detect_affirmed_completion("Got my journal in")
        self.assertTrue(detected)

    def test_handled_it_earlier(self):
        detected, confidence = detect_affirmed_completion("I handled that earlier")
        self.assertTrue(detected)

    def test_did_that_before(self):
        detected, confidence = detect_affirmed_completion("I did that before")
        self.assertTrue(detected)

    def test_took_medicine_earlier(self):
        detected, confidence = detect_affirmed_completion(
            "I took my medicine earlier this morning"
        )
        self.assertTrue(detected)

    # -- Negative matches (should NOT detect) --

    def test_plain_yes(self):
        """Plain 'yes' is for confirmation_detector, not affirmation."""
        detected, _ = detect_affirmed_completion("yes")
        self.assertFalse(detected)

    def test_plain_done(self):
        """Plain 'done' is for confirmation_detector."""
        detected, _ = detect_affirmed_completion("done")
        self.assertFalse(detected)

    def test_no(self):
        detected, _ = detect_affirmed_completion("no")
        self.assertFalse(detected)

    def test_unrelated_message(self):
        detected, _ = detect_affirmed_completion("What's on my schedule today?")
        self.assertFalse(detected)

    def test_future_tense(self):
        """Future intent should not match affirmation patterns."""
        detected, _ = detect_affirmed_completion("I will do it later")
        self.assertFalse(detected)

    def test_empty_message(self):
        detected, _ = detect_affirmed_completion("")
        self.assertFalse(detected)

    # -- Tier 2 patterns: "just finished", "I finished X", "X is done" --

    def test_just_finished_my_journal(self):
        """The exact failing case from the bug report."""
        detected, confidence = detect_affirmed_completion("I just finished my journal")
        self.assertTrue(detected)
        self.assertGreaterEqual(confidence, 0.75)

    def test_just_did_my_workout(self):
        detected, confidence = detect_affirmed_completion("just did my workout")
        self.assertTrue(detected)

    def test_i_finished_my_prayer(self):
        detected, confidence = detect_affirmed_completion("I finished my prayer")
        self.assertTrue(detected)

    def test_i_completed_my_reading(self):
        detected, confidence = detect_affirmed_completion("I completed my reading")
        self.assertTrue(detected)

    def test_journal_is_done(self):
        detected, confidence = detect_affirmed_completion("journal is done")
        self.assertTrue(detected)

    def test_workout_is_complete(self):
        detected, confidence = detect_affirmed_completion("workout is complete")
        self.assertTrue(detected)

    def test_i_journaled(self):
        detected, confidence = detect_affirmed_completion("I journaled")
        self.assertTrue(detected)

    def test_i_worked_out(self):
        detected, confidence = detect_affirmed_completion("I worked out")
        self.assertTrue(detected)

    def test_i_prayed(self):
        detected, confidence = detect_affirmed_completion("I prayed")
        self.assertTrue(detected)

    def test_i_took_my_meds(self):
        detected, confidence = detect_affirmed_completion("I took my meds")
        self.assertTrue(detected)

    def test_i_did_my_workout(self):
        detected, confidence = detect_affirmed_completion("I did my workout")
        self.assertTrue(detected)

    # -- Forward intent (should NOT match) --

    def test_about_to_take_medicine(self):
        """Forward intent should not be treated as completion."""
        detected, _ = detect_affirmed_completion("I'm about to take my medicine")
        self.assertFalse(detected)

    def test_going_to_journal(self):
        """Forward intent should not be treated as completion."""
        detected, _ = detect_affirmed_completion("I'm going to journal now")
        self.assertFalse(detected)

    def test_i_want_to_journal(self):
        """Request to create should not be treated as completion."""
        detected, _ = detect_affirmed_completion("I want to journal about today")
        self.assertFalse(detected)

    def test_none_message(self):
        detected, _ = detect_affirmed_completion(None)
        self.assertFalse(detected)

    # -- Confidence scoring --

    def test_short_message_higher_confidence(self):
        """Short messages should have higher confidence."""
        _, short_conf = detect_affirmed_completion("I already did it")
        _, long_conf = detect_affirmed_completion(
            "I already completed it before I saw this reminder. "
            "This was a timing issue. I was at the gym earlier today."
        )
        self.assertGreater(short_conf, long_conf)


class TestIdentifyAffirmedActivity(AffirmationTestBase):
    """Test identification of which activity is being affirmed."""

    def test_identifies_from_recent_proactive_medicine(self):
        """Should identify medicine type from recent proactive check-in."""
        AssistantMessage.objects.create(
            conversation=self.conversation,
            role='assistant',
            content='Your morning meds are due.',
            message_type='nudge',
            is_proactive=True,
            metadata={'check_in_type': 'medicine'},
        )
        activity = identify_affirmed_activity("I already took it", self.conversation)
        self.assertEqual(activity, 'medicine')

    def test_identifies_from_recent_proactive_journal(self):
        AssistantMessage.objects.create(
            conversation=self.conversation,
            role='assistant',
            content='No journal entry today. Want to log one?',
            message_type='nudge',
            is_proactive=True,
            metadata={'check_in_type': 'journal'},
        )
        activity = identify_affirmed_activity("I already did it", self.conversation)
        self.assertEqual(activity, 'journal')

    def test_identifies_from_recent_proactive_workout(self):
        AssistantMessage.objects.create(
            conversation=self.conversation,
            role='assistant',
            content='No workout logged today.',
            message_type='nudge',
            is_proactive=True,
            metadata={'check_in_type': 'workout'},
        )
        activity = identify_affirmed_activity("I already did it", self.conversation)
        self.assertEqual(activity, 'workout')

    def test_normalizes_medicine_group(self):
        """medicine_group should normalize to medicine."""
        AssistantMessage.objects.create(
            conversation=self.conversation,
            role='assistant',
            content='Your morning meds are due.',
            message_type='nudge',
            is_proactive=True,
            metadata={'check_in_type': 'medicine_group'},
        )
        activity = identify_affirmed_activity("I already took them", self.conversation)
        self.assertEqual(activity, 'medicine')

    def test_identifies_workout_from_keywords(self):
        """Falls back to keyword matching when no proactive message."""
        activity = identify_affirmed_activity(
            "I already worked out this morning", self.conversation
        )
        self.assertEqual(activity, 'workout')

    def test_identifies_medicine_from_keywords(self):
        activity = identify_affirmed_activity(
            "Already took my meds earlier", self.conversation
        )
        self.assertEqual(activity, 'medicine')

    def test_identifies_journal_from_keywords(self):
        activity = identify_affirmed_activity(
            "I already journaled today", self.conversation
        )
        self.assertEqual(activity, 'journal')

    def test_identifies_prayer_from_keywords(self):
        activity = identify_affirmed_activity(
            "I already prayed this morning", self.conversation
        )
        self.assertEqual(activity, 'faith_prayer')

    def test_returns_none_when_no_context(self):
        """Should return None when activity can't be identified."""
        activity = identify_affirmed_activity(
            "I already did it", self.conversation
        )
        self.assertIsNone(activity)

    def test_ignores_old_proactive_messages(self):
        """Proactive messages older than 4 hours should be ignored."""
        msg = AssistantMessage.objects.create(
            conversation=self.conversation,
            role='assistant',
            content='No journal entry today.',
            message_type='nudge',
            is_proactive=True,
            metadata={'check_in_type': 'journal'},
        )
        # Manually set created_at to 5 hours ago
        AssistantMessage.objects.filter(pk=msg.pk).update(
            created_at=timezone.now() - timedelta(hours=5)
        )
        activity = identify_affirmed_activity("I already did it", self.conversation)
        # Should fall back to keywords (which won't match "I already did it")
        self.assertIsNone(activity)


class TestAffirmedCompletionStorage(AffirmationTestBase):
    """Test metadata storage and retrieval."""

    def test_store_affirmed_completion(self):
        store_affirmed_completion(self.conversation, 'journal')
        self.conversation.refresh_from_db()
        affirmed = self.conversation.metadata.get('affirmed_completions', {})
        self.assertIn('journal', affirmed)

    def test_store_multiple_completions(self):
        store_affirmed_completion(self.conversation, 'journal')
        store_affirmed_completion(self.conversation, 'workout')
        self.conversation.refresh_from_db()
        affirmed = self.conversation.metadata.get('affirmed_completions', {})
        self.assertIn('journal', affirmed)
        self.assertIn('workout', affirmed)

    def test_get_affirmed_completions_empty(self):
        result = get_affirmed_completions(self.conversation)
        self.assertEqual(result, {})

    def test_get_affirmed_completions_with_data(self):
        store_affirmed_completion(self.conversation, 'medicine')
        result = get_affirmed_completions(self.conversation)
        self.assertIn('medicine', result)

    def test_is_activity_affirmed_true(self):
        store_affirmed_completion(self.conversation, 'workout')
        self.assertTrue(is_activity_affirmed(self.conversation, 'workout'))

    def test_is_activity_affirmed_false(self):
        self.assertFalse(is_activity_affirmed(self.conversation, 'workout'))

    def test_check_in_type_normalization(self):
        """medicine_group should be treated same as medicine."""
        store_affirmed_completion(self.conversation, 'medicine')
        self.assertTrue(is_activity_affirmed(self.conversation, 'medicine_group'))

    def test_journal_gap_normalization(self):
        """journal_gap and journal_concern normalize to journal."""
        store_affirmed_completion(self.conversation, 'journal')
        self.assertTrue(is_activity_affirmed(self.conversation, 'journal_gap'))
        self.assertTrue(is_activity_affirmed(self.conversation, 'journal_concern'))

    def test_none_conversation(self):
        """Should handle None conversation gracefully."""
        self.assertEqual(get_affirmed_completions(None), {})
        self.assertFalse(is_activity_affirmed(None, 'workout'))


class TestHandleAffirmedCompletion(AffirmationTestBase):
    """Test the main entry point integration."""

    def test_full_flow_journal_affirmation(self):
        """Full flow: proactive message -> user affirms -> handled."""
        # Create a proactive journal check-in
        AssistantMessage.objects.create(
            conversation=self.conversation,
            role='assistant',
            content='No journal entry today. Want to log one?',
            message_type='nudge',
            is_proactive=True,
            metadata={'check_in_type': 'journal'},
        )

        result = handle_affirmed_completion(
            self.user,
            "I already completed it before I saw this reminder.",
            self.conversation,
        )

        self.assertIsNotNone(result)
        self.assertTrue(result['handled'])
        self.assertEqual(result['activity_type'], 'journal')
        self.assertIn('journal', result['response'].lower())

    def test_full_flow_workout_affirmation(self):
        AssistantMessage.objects.create(
            conversation=self.conversation,
            role='assistant',
            content='No workout logged today.',
            message_type='nudge',
            is_proactive=True,
            metadata={'check_in_type': 'workout'},
        )

        result = handle_affirmed_completion(
            self.user,
            "I already worked out this morning",
            self.conversation,
        )

        self.assertIsNotNone(result)
        self.assertTrue(result['handled'])
        self.assertEqual(result['activity_type'], 'workout')

    def test_full_flow_medicine_affirmation(self):
        AssistantMessage.objects.create(
            conversation=self.conversation,
            role='assistant',
            content='Your morning meds are due.',
            message_type='nudge',
            is_proactive=True,
            metadata={'check_in_type': 'medicine'},
        )

        result = handle_affirmed_completion(
            self.user,
            "Already took my meds earlier",
            self.conversation,
        )

        self.assertIsNotNone(result)
        self.assertTrue(result['handled'])
        self.assertEqual(result['activity_type'], 'medicine')

    def test_full_flow_habit_affirmation(self):
        AssistantMessage.objects.create(
            conversation=self.conversation,
            role='assistant',
            content='Your morning routine streak is at risk.',
            message_type='nudge',
            is_proactive=True,
            metadata={'check_in_type': 'habit_streak'},
        )

        result = handle_affirmed_completion(
            self.user,
            "I already took care of that",
            self.conversation,
        )

        self.assertIsNotNone(result)
        self.assertTrue(result['handled'])
        self.assertEqual(result['activity_type'], 'habit')

    def test_does_not_create_database_records(self):
        """Affirming completion must NOT create any activity records."""
        from apps.journal.models import JournalEntry

        AssistantMessage.objects.create(
            conversation=self.conversation,
            role='assistant',
            content='No journal entry today.',
            message_type='nudge',
            is_proactive=True,
            metadata={'check_in_type': 'journal'},
        )

        journal_count_before = JournalEntry.objects.filter(user=self.user).count()

        handle_affirmed_completion(
            self.user,
            "I already completed it",
            self.conversation,
        )

        journal_count_after = JournalEntry.objects.filter(user=self.user).count()
        self.assertEqual(journal_count_before, journal_count_after)

    def test_stores_affirmation_in_metadata(self):
        """Should store affirmation in conversation metadata."""
        AssistantMessage.objects.create(
            conversation=self.conversation,
            role='assistant',
            content='No workout logged today.',
            message_type='nudge',
            is_proactive=True,
            metadata={'check_in_type': 'workout'},
        )

        handle_affirmed_completion(
            self.user,
            "I already worked out",
            self.conversation,
        )

        self.conversation.refresh_from_db()
        affirmed = self.conversation.metadata.get('affirmed_completions', {})
        self.assertIn('workout', affirmed)

    def test_marks_proactive_message_as_handled(self):
        """Should mark the proactive message quick_reply_used."""
        msg = AssistantMessage.objects.create(
            conversation=self.conversation,
            role='assistant',
            content='No journal entry today.',
            message_type='nudge',
            is_proactive=True,
            metadata={'check_in_type': 'journal'},
            quick_reply_used='',
        )

        handle_affirmed_completion(
            self.user,
            "I already completed it before I saw this",
            self.conversation,
        )

        msg.refresh_from_db()
        self.assertEqual(msg.quick_reply_used, 'user_affirmed')

    def test_returns_none_for_non_affirmation(self):
        """Normal messages should return None."""
        result = handle_affirmed_completion(
            self.user,
            "What's the weather like?",
            self.conversation,
        )
        self.assertIsNone(result)

    def test_returns_none_when_activity_unidentifiable(self):
        """Should return None when we can't determine the activity."""
        # No proactive message and message has no activity keywords
        result = handle_affirmed_completion(
            self.user,
            "I already did it",
            self.conversation,
        )
        self.assertIsNone(result)

    def test_offers_logging_option(self):
        """Response should offer to log/record the completion."""
        AssistantMessage.objects.create(
            conversation=self.conversation,
            role='assistant',
            content='No workout logged.',
            message_type='nudge',
            is_proactive=True,
            metadata={'check_in_type': 'workout'},
        )

        result = handle_affirmed_completion(
            self.user,
            "I already worked out",
            self.conversation,
        )

        self.assertIn('record', result['response'].lower())


class TestProactiveCheckInSuppression(AffirmationTestBase):
    """Test that affirmed completions suppress new proactive check-ins."""

    def test_suppresses_check_in_after_affirmation(self):
        """_create_proactive_message should return None for affirmed types."""
        from apps.ai.proactive_checkins import ProactiveCheckInService

        # Store affirmation for journal
        store_affirmed_completion(self.conversation, 'journal')

        service = ProactiveCheckInService(self.user)

        # Try to create a journal check-in — should be suppressed
        result = service._create_proactive_message(
            content='No journal entry today.',
            message_type='nudge',
            metadata={'check_in_type': 'journal'},
            quick_replies=[],
        )

        self.assertIsNone(result)

    def test_does_not_suppress_unaffirmed_type(self):
        """Check-ins for unaffirmed types should still be created."""
        from apps.ai.proactive_checkins import ProactiveCheckInService

        # Affirm journal but not workout
        store_affirmed_completion(self.conversation, 'journal')

        service = ProactiveCheckInService(self.user)

        # Workout check-in should NOT be suppressed
        result = service._create_proactive_message(
            content='No workout logged today.',
            message_type='nudge',
            metadata={'check_in_type': 'workout'},
            quick_replies=[],
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.content, 'No workout logged today.')

    def test_suppresses_normalized_type(self):
        """medicine_group should be suppressed when medicine is affirmed."""
        from apps.ai.proactive_checkins import ProactiveCheckInService

        store_affirmed_completion(self.conversation, 'medicine')

        service = ProactiveCheckInService(self.user)

        result = service._create_proactive_message(
            content='Your morning meds are due.',
            message_type='nudge',
            metadata={'check_in_type': 'medicine_group'},
            quick_replies=[],
        )

        self.assertIsNone(result)


class TestCheckInTypeMap(TestCase):
    """Test the CHECK_IN_TYPE_MAP coverage."""

    def test_all_check_in_types_have_mapping(self):
        """All known check_in_types should have a mapping."""
        expected_types = [
            'medicine', 'medicine_group', 'workout', 'journal',
            'task_overdue', 'nn_skip_streak', 'faith_reading',
            'faith_prayer', 'habit_streak', 'journal_concern',
            'journal_gap',
        ]
        for t in expected_types:
            self.assertIn(
                t, CHECK_IN_TYPE_MAP,
                f"Missing mapping for check_in_type: {t}"
            )


# ──────────────────────────────────────────────────────────────────────
# Phase 1.2 Trust Contract — Inferred Medicine Completion Disabled
#
# Background: Pre-existing `_try_auto_complete_medicine` created
# IntakeLog rows with log_status='taken' when user messages matched
# affirmation regex patterns. That violates the WLJ trust contract:
# supplements/medicine must NEVER auto-complete without explicit user
# action. The function is now neutered (returns None unconditionally).
# These tests lock that behavior in CI so the violation cannot regress.
# ──────────────────────────────────────────────────────────────────────


class TestMedicineAutoCompleteDisabled(AffirmationTestBase):
    """Lock-in: inferred medicine completion via affirmation must NEVER
    create an IntakeLog. The trust contract forbids inferred adherence.

    These tests fail if anyone re-enables the auto-complete path.
    """

    def _create_active_medicine(self, name="Thorne Creatine"):
        from datetime import date
        from apps.health.models import Intake
        return Intake.objects.create(
            user=self.user,
            name=name,
            dose="5g",
            intake_type=Intake.INTAKE_TYPE_SUPPLEMENT,
            intake_status=Intake.STATUS_ACTIVE,
            start_date=date(2026, 1, 1),
        )

    def test_try_auto_complete_medicine_returns_none(self):
        """Direct unit test: the function returns None for any input."""
        from apps.ai.affirmation_detector import _try_auto_complete_medicine
        self._create_active_medicine()
        result = _try_auto_complete_medicine(self.user, "I already took my meds")
        self.assertIsNone(result)

    def test_try_auto_complete_medicine_creates_zero_intake_logs(self):
        """The function must not write to IntakeLog under any input."""
        from apps.ai.affirmation_detector import _try_auto_complete_medicine
        from apps.health.models import IntakeLog
        self._create_active_medicine()

        for message in [
            "I already took my meds",
            "Already took my medicine earlier",
            "Took my pills this morning",
            "I just took my creatine",
            "Got my meds done",
            "Already took it",
            "Took my medication",
            "i took my meds",
        ]:
            _try_auto_complete_medicine(self.user, message)

        self.assertEqual(
            IntakeLog.objects.filter(intake__user=self.user).count(), 0,
            "Trust contract violation: inferred medicine completion wrote "
            "an IntakeLog. _try_auto_complete_medicine must return None "
            "unconditionally and create zero rows.",
        )

    def test_handle_affirmed_completion_creates_zero_intake_logs(self):
        """Full flow: affirming medicine via the public entry point must
        acknowledge the user but NEVER write IntakeLog.

        This is the canonical regression test for the trust violation.
        """
        from apps.health.models import IntakeLog
        self._create_active_medicine()

        # Proactive medicine check-in is the precondition for affirmation routing.
        AssistantMessage.objects.create(
            conversation=self.conversation,
            role='assistant',
            content='Your morning meds are due.',
            message_type='nudge',
            is_proactive=True,
            metadata={'check_in_type': 'medicine'},
        )

        count_before = IntakeLog.objects.filter(intake__user=self.user).count()

        result = handle_affirmed_completion(
            self.user,
            "Already took my meds earlier",
            self.conversation,
        )

        # Surrounding flow still works (acknowledgment + activity identified).
        self.assertIsNotNone(result)
        self.assertTrue(result['handled'])
        self.assertEqual(result['activity_type'], 'medicine')
        # Auto-complete is now never true (function returns None).
        self.assertFalse(result.get('auto_completed', False))

        count_after = IntakeLog.objects.filter(intake__user=self.user).count()
        self.assertEqual(
            count_after, count_before,
            "Affirming medicine via natural language MUST NOT create an "
            "IntakeLog. Trust contract violation if this fires.",
        )

    def test_single_active_medicine_does_not_auto_complete(self):
        """Edge case: with exactly one active medicine, prior code marked
        it taken on ambiguous affirmations. Verify this no longer occurs.
        """
        from apps.ai.affirmation_detector import _try_auto_complete_medicine
        from apps.health.models import IntakeLog

        # Exactly one active intake (the historical risky case).
        self._create_active_medicine(name="Solo Med")

        result = _try_auto_complete_medicine(self.user, "already took it")
        self.assertIsNone(result)
        self.assertEqual(
            IntakeLog.objects.filter(intake__user=self.user).count(), 0,
        )
