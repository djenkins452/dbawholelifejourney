"""
Phase 18.3 — Conversation Mode & Context Governance tests.

Verifies that:
1. Reflective questions NEVER produce execution responses
2. Execution requests NEVER produce reflection content
3. Mode persists across turns (not switching unexpectedly)
4. The router yields to LLM for reflective-mode conversations
5. Check-ins are suppressed during reflective mode
"""

from datetime import date
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from apps.users.models import User


def _make_user(email):
    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(
        email=email, password="testpass123",
        date_of_birth=date(1990, 1, 1),
    )
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


# ══════════════════════════════════════════════════════════════
# Rule 1: Reflective question → NEVER returns execution
# ══════════════════════════════════════════════════════════════

class ReflectiveNeverReturnsExecutionTests(TestCase):
    def setUp(self):
        self.user = _make_user("reflective@test.com")

    def test_faith_question_yields_to_llm(self):
        """A faith question must NOT be intercepted by the
        execution router. The route must be 'reflective_mode_yield'."""
        from apps.ai.deterministic_router import classify_and_route
        result = classify_and_route(
            "What does the Bible say about idols?", self.user,
        )
        self.assertIn(
            result.route_name,
            ('reflective_mode_yield', 'no_route'),
            f"Faith question was intercepted by execution route: "
            f"{result.route_name}",
        )
        # Must NOT return an execution response
        if result.response:
            self.assertNotIn("Do this next:", result.response)
            self.assertNotIn("Start ", result.response)

    def test_prayer_reflection_yields_to_llm(self):
        from apps.ai.deterministic_router import classify_and_route
        result = classify_and_route(
            "How should I pray about temptation?", self.user,
        )
        self.assertIn(
            result.route_name,
            ('reflective_mode_yield', 'no_route'),
        )

    def test_journal_reflection_yields_to_llm(self):
        from apps.ai.deterministic_router import classify_and_route
        result = classify_and_route(
            "I'm struggling with anxiety today. Can we reflect on that?",
            self.user,
        )
        self.assertIn(
            result.route_name,
            ('reflective_mode_yield', 'no_route'),
        )


# ══════════════════════════════════════════════════════════════
# Rule 2: Execution request → NEVER returns reflection
# ══════════════════════════════════════════════════════════════

class ExecutionNeverReturnsReflectionTests(TestCase):
    def setUp(self):
        self.user = _make_user("execution@test.com")

    def test_what_should_i_do_returns_execution(self):
        """An explicit execution request must NOT yield to LLM —
        it must be handled by the decision router."""
        from apps.ai.deterministic_router import classify_and_route
        result = classify_and_route(
            "What should I do right now?", self.user,
        )
        # Decision queries are intercepted by the router
        self.assertTrue(
            result.route_name.startswith("decision_query")
            or result.route_name == 'focus_query',
            f"Execution query was NOT handled by router: "
            f"{result.route_name}",
        )


# ══════════════════════════════════════════════════════════════
# Rule 3: Mode persistence — faith mode stays active
# ══════════════════════════════════════════════════════════════

class ModePersistenceTests(TestCase):
    def setUp(self):
        self.user = _make_user("mode_persist@test.com")
        try:
            self.user.operating_blueprint
        except Exception:
            from apps.core.blueprint.models import PersonalOperatingBlueprint
            PersonalOperatingBlueprint.objects.create(user=self.user)

    def test_faith_mode_persists(self):
        """After a faith question sets the mode, a follow-up
        question (even ambiguous) should stay in faith mode."""
        from apps.core.blueprint.conversation_mode import (
            update_mode_from_message,
            get_active_mode,
        )

        # First message: explicit faith
        update_mode_from_message(self.user, "What does the Bible say about idols?")
        self.assertEqual(get_active_mode(self.user), 'faith')

        # Second message: ambiguous follow-up
        update_mode_from_message(self.user, "How do I apply that to my life?")
        # Mode should persist (no mode-break detected)
        self.assertEqual(get_active_mode(self.user), 'faith')

    def test_mode_breaks_on_explicit_phrase(self):
        from apps.core.blueprint.conversation_mode import (
            update_mode_from_message,
            get_active_mode,
        )

        update_mode_from_message(self.user, "Let's talk about prayer")
        self.assertEqual(get_active_mode(self.user), 'faith')

        # Mode-break phrase
        update_mode_from_message(self.user, "What's next on my schedule?")
        self.assertEqual(get_active_mode(self.user), 'general')


# ══════════════════════════════════════════════════════════════
# Rule 4: Check-in suppressed during reflective mode
# ══════════════════════════════════════════════════════════════

class CheckInSuppressedDuringReflectionTests(TestCase):
    def setUp(self):
        self.user = _make_user("suppress_checkin@test.com")
        # Ensure blueprint exists for mode persistence
        try:
            self.user.operating_blueprint
        except Exception:
            from apps.core.blueprint.models import PersonalOperatingBlueprint
            PersonalOperatingBlueprint.objects.create(user=self.user)

    def test_workout_checkin_suppressed_in_faith_mode(self):
        from apps.core.blueprint.conversation_mode import (
            set_conversation_mode,
            should_suppress_proactive,
        )

        set_conversation_mode(self.user, 'faith')
        self.assertTrue(
            should_suppress_proactive(self.user, 'workout'),
            "Workout check-in should be suppressed during faith mode",
        )

    def test_medication_never_suppressed(self):
        """Medication overdue is NEVER suppressed, even in faith mode."""
        from apps.core.blueprint.conversation_mode import (
            set_conversation_mode,
            should_suppress_proactive,
        )

        set_conversation_mode(self.user, 'faith')
        self.assertFalse(
            should_suppress_proactive(self.user, 'medication'),
            "Medication check-in must NEVER be suppressed",
        )


# ══════════════════════════════════════════════════════════════
# Rule 5: Mode detection keywords
# ══════════════════════════════════════════════════════════════

class ModeDetectionTests(TestCase):
    def test_idol_triggers_faith(self):
        from apps.core.blueprint.conversation_mode import (
            detect_conversation_mode,
        )
        self.assertEqual(
            detect_conversation_mode("What are idols in modern life?"),
            'faith',
        )

    def test_struggling_triggers_journal(self):
        from apps.core.blueprint.conversation_mode import (
            detect_conversation_mode,
        )
        self.assertEqual(
            detect_conversation_mode("I'm struggling with something"),
            'journal',
        )

    def test_what_should_i_do_is_not_reflective(self):
        """Execution queries should NOT trigger a reflective mode."""
        from apps.core.blueprint.conversation_mode import (
            detect_conversation_mode,
        )
        mode = detect_conversation_mode("What should I do right now?")
        self.assertNotIn(mode, ('faith', 'journal'))
        # Should be 'undetected' (no keywords) or 'general' (break phrase)
        self.assertIn(mode, ('undetected', 'general', 'planning'))
