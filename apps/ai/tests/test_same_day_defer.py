"""Same-day defer guard (trust-correct routine-nudge replies).

The incident this test file guards against:
  Beth asks: "Shower (7:00 AM) has slipped. Can you get to it this afternoon?"
  User says: "I will shower when I am done with some chores. I can do it later."
  Beth used to respond with an action card: "Action: Reschedule Routine Item /
  Impact: Creates a new entry." — silently mutating the RoutineSchedule
  even though the user only meant "still today, just later."

The deterministic guard in `apps.ai.confirmation_detector` must:
  - fire BEFORE the LLM intent path
  - require a recent proactive Beth nudge (no global suppression elsewhere)
  - produce a conversational ack with the routine name
  - NOT mutate any schedule, log, or pending action
  - leave true reschedule / day-shift / skip phrases for the existing path
"""

from datetime import time as dtime
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from apps.ai.confirmation_detector import (
    SAME_DAY_DEFER_PATTERNS,
    handle_proactive_confirmation,
    is_timeless_same_day_defer,
    _extract_routine_label_from_nudge,
)
from apps.ai.models import AssistantConversation, AssistantMessage
from apps.users.models import TermsAcceptance, User


def _make_user(email="defer@test.com"):
    u = User.objects.create_user(email=email, password="x")
    TermsAcceptance.objects.create(
        user=u,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _make_proactive_nudge(user, content):
    conv = AssistantConversation.objects.create(user=user, is_active=True)
    return AssistantMessage.objects.create(
        conversation=conv,
        role='assistant',
        content=content,
        is_proactive=True,
        message_type='nudge',
        metadata={'check_in_type': 'midday_alignment'},
        quick_replies=[],
    )


# ── Pure pattern coverage (table from the spec) ──────────────────────

SAME_DAY_DEFER_CASES = [
    "I'll do it later",
    "I will do it later",
    "After chores",
    "I'll do it after chores",
    "I'll shower after chores",
    "This afternoon",
    "Tonight is fine",
    "Maybe later",
    "Not now",
    "Give me an hour",
    "I'll do it after dinner",
    "Later today",
    "I can still do it",
    "I'll get to it",
    "Soon",
    "In a bit",
    "When I finish work",
    "When I'm done with chores",
    "I will shower when I am done with some chores. I can do it later.",
]

EXPLICIT_RESCHEDULE_CASES = [
    "Move it to 7pm",
    "Push to 8 PM",
    "Reschedule shower to 5:30pm",
    "Move to tomorrow",
    "I won't get to this today",
    "Skip today",
    "Skip shower",
    "Move it to 14:00",
    "I'll do it at 7pm",
    "Reschedule for Friday",
    "Cancel it",
    "Push to next Monday",
]


class TimelessDeferDetectorTests(TestCase):
    def test_all_same_day_defer_phrases_classified_as_defer(self):
        for phrase in SAME_DAY_DEFER_CASES:
            self.assertTrue(
                is_timeless_same_day_defer(phrase),
                f"Expected TRUE for same-day defer: {phrase!r}",
            )

    def test_all_explicit_reschedule_phrases_rejected(self):
        for phrase in EXPLICIT_RESCHEDULE_CASES:
            self.assertFalse(
                is_timeless_same_day_defer(phrase),
                f"Expected FALSE (true reschedule/day-shift): {phrase!r}",
            )

    def test_empty_message_returns_false(self):
        self.assertFalse(is_timeless_same_day_defer(""))
        self.assertFalse(is_timeless_same_day_defer(None))

    def test_unrelated_chat_returns_false(self):
        for phrase in [
            "How are you?",
            "Tell me about my goals",
            "What's the weather",
            "Log my weight",
        ]:
            self.assertFalse(is_timeless_same_day_defer(phrase))


class RoutineLabelExtractorTests(TestCase):
    def test_extracts_label_from_has_slipped(self):
        content = "Shower (7:00 AM) has slipped. Can you get to it this afternoon?"
        self.assertEqual(_extract_routine_label_from_nudge(content), "Shower")

    def test_extracts_label_from_slipping_bullets(self):
        content = (
            "Slow start — 1 of 4 done so far.\n"
            "\n"
            "Slipping:\n"
            "• Bible Reading\n"
            "• Workout\n"
        )
        self.assertEqual(
            _extract_routine_label_from_nudge(content), "Bible Reading",
        )

    def test_prefers_user_mentioned_item(self):
        content = (
            "Slipping:\n"
            "• Bible Reading\n"
            "• Workout\n"
        )
        # User reply mentions "workout" — prefer that over the first bullet.
        self.assertEqual(
            _extract_routine_label_from_nudge(
                content, user_message="I'll do my workout later",
            ),
            "Workout",
        )

    def test_returns_none_when_no_label_present(self):
        self.assertIsNone(_extract_routine_label_from_nudge(""))
        self.assertIsNone(
            _extract_routine_label_from_nudge("Strong progress — 3 of 4 done."),
        )


# ── Integration: handle_proactive_confirmation behavior ──────────────

class SameDayDeferGuardIntegrationTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    # The headline incident scenario.
    def test_shower_after_chores_routes_to_defer_ack_not_reschedule(self):
        nudge = _make_proactive_nudge(
            self.user,
            "Shower (7:00 AM) has slipped. Can you get to it this afternoon?",
        )
        result = handle_proactive_confirmation(
            self.user,
            "I will shower when I am done with some chores. I can do it later.",
        )
        self.assertIsNotNone(result)
        self.assertTrue(result['handled'])
        self.assertEqual(
            result['action_result']['action_type'],
            'same_day_defer_acknowledge',
        )
        # Required Beth wording: "Understood. I'll leave Shower …"
        self.assertEqual(
            result['response'],
            "Understood. I'll leave Shower on today's list and check back later.",
        )
        # Nudge is marked as handled so it isn't double-processed.
        nudge.refresh_from_db()
        self.assertEqual(nudge.quick_reply_used, 'same_day_defer_text')

    def test_bible_reading_later_uses_dynamic_task_name(self):
        _make_proactive_nudge(
            self.user,
            "Bible Reading (8:00 AM) has slipped. Can you get to it this afternoon?",
        )
        result = handle_proactive_confirmation(
            self.user, "I'll do Bible reading later",
        )
        self.assertEqual(
            result['response'],
            "Understood. I'll leave Bible Reading on today's list and check back later.",
        )

    def test_generic_defer_with_no_extractable_label_falls_back_gracefully(self):
        _make_proactive_nudge(self.user, "Strong progress — 3 of 4 done.")
        result = handle_proactive_confirmation(self.user, "Later")
        # Even without an extractable label, no schedule write occurs.
        self.assertTrue(result['handled'])
        self.assertIn("on today's list", result['response'])

    def test_guard_does_not_fire_without_recent_proactive_nudge(self):
        """The deterministic guard must be narrowly scoped — without a
        recent proactive Beth nudge, "I'll do it later" must NOT
        short-circuit the normal intent pipeline elsewhere in WLJ."""
        # No proactive nudge in DB.
        result = handle_proactive_confirmation(self.user, "I'll do it later")
        # Returns None → falls through to LLM intent path.
        self.assertIsNone(result)

    def test_true_reschedule_still_falls_through_to_existing_path(self):
        """Explicit-time reschedule must NOT be intercepted by the
        defer guard. The existing reschedule_routine_item path stays."""
        _make_proactive_nudge(
            self.user,
            "Shower (7:00 AM) has slipped. Can you get to it this afternoon?",
        )
        result = handle_proactive_confirmation(self.user, "Move it to 7pm")
        # Defer guard does NOT fire — explicit "7pm" rejects the guard.
        # With no quick_replies on the nudge, the existing path also
        # returns None, leaving the LLM to do the reschedule.
        self.assertIsNone(result)

    def test_skip_phrase_falls_through_to_existing_path(self):
        _make_proactive_nudge(
            self.user,
            "Shower (7:00 AM) has slipped. Can you get to it this afternoon?",
        )
        result = handle_proactive_confirmation(self.user, "Skip today")
        self.assertIsNone(result)

    def test_tomorrow_phrase_falls_through_to_existing_path(self):
        _make_proactive_nudge(
            self.user,
            "Shower (7:00 AM) has slipped. Can you get to it this afternoon?",
        )
        result = handle_proactive_confirmation(self.user, "Move to tomorrow")
        self.assertIsNone(result)

    def test_wont_get_to_today_falls_through_to_existing_path(self):
        _make_proactive_nudge(
            self.user,
            "Shower (7:00 AM) has slipped. Can you get to it this afternoon?",
        )
        result = handle_proactive_confirmation(self.user, "I won't get to this today")
        self.assertIsNone(result)

    def test_defer_ack_does_not_mutate_any_routine_schedule(self):
        """Critical trust assertion — the defer guard MUST NOT touch
        RoutineSchedule, RoutineLog, or any other state."""
        from apps.life.models import (
            Routine, RoutineSchedule, RoutineLog,
        )

        routine = Routine.objects.create(user=self.user, name="Morning")
        sched = RoutineSchedule.objects.create(
            routine=routine,
            name="Shower",
            scheduled_time=dtime(7, 0),
            days_of_week="0,1,2,3,4,5,6",
            is_active=True,
        )

        _make_proactive_nudge(
            self.user,
            "Shower (7:00 AM) has slipped. Can you get to it this afternoon?",
        )

        # Snapshot state.
        sched_before = {
            "scheduled_time": sched.scheduled_time,
            "is_active": sched.is_active,
            "specific_date": getattr(sched, 'specific_date', None),
        }
        log_count_before = RoutineLog.objects.filter(schedule=sched).count()

        handle_proactive_confirmation(
            self.user,
            "I will shower when I am done with some chores. I can do it later.",
        )

        sched.refresh_from_db()
        self.assertEqual(sched.scheduled_time, sched_before["scheduled_time"])
        self.assertEqual(sched.is_active, sched_before["is_active"])
        self.assertEqual(
            getattr(sched, 'specific_date', None),
            sched_before["specific_date"],
        )
        self.assertEqual(
            RoutineLog.objects.filter(schedule=sched).count(),
            log_count_before,
        )
