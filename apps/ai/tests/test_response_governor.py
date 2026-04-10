"""
Response Governor — Single Response Authority tests.

Verifies that the governor is the ONLY authority determining response
type, and that no system can bypass it.

Test 1: Faith continuity (3-turn thread → all REFLECTIVE)
Test 2: Explicit break switches to EXECUTION
Test 3: Briefing suppressed during faith mode
Test 4: Proactive suppressed during faith mode
Test 5: Health exception (medication crisis → ALERT)
"""

from datetime import date
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from apps.ai.response_governor import (
    ResponseType,
    is_response_allowed,
    resolve_response_type,
)
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


class FaithContinuityTests(TestCase):
    """Test 1: A 3-turn faith thread must produce REFLECTIVE on all
    turns, including the ambiguous follow-up with no faith keywords."""

    def setUp(self):
        self.user = _make_user("faith_cont@test.com")
        try:
            self.user.operating_blueprint
        except Exception:
            from apps.core.blueprint.models import PersonalOperatingBlueprint
            PersonalOperatingBlueprint.objects.create(user=self.user)

    def test_three_turn_faith_thread_all_reflective(self):
        from apps.core.blueprint.conversation_mode import (
            update_mode_from_message,
        )

        turns = [
            "Do I have to give up comfort to make God my priority?",
            "Am I idolizing comfort?",
            "What does this mean for how I should live?",
        ]

        for i, msg in enumerate(turns):
            # Update mode first (as production does)
            update_mode_from_message(self.user, msg)
            # Then resolve
            rt = resolve_response_type(self.user, msg)
            self.assertEqual(
                rt, ResponseType.REFLECTIVE,
                f"Turn {i+1} ({msg[:40]}) should be REFLECTIVE, "
                f"got {rt}",
            )


class ExplicitBreakTests(TestCase):
    """Test 2: An explicit break phrase switches to EXECUTION."""

    def setUp(self):
        self.user = _make_user("break@test.com")
        try:
            self.user.operating_blueprint
        except Exception:
            from apps.core.blueprint.models import PersonalOperatingBlueprint
            PersonalOperatingBlueprint.objects.create(user=self.user)

    def test_break_phrase_switches_to_execution(self):
        from apps.core.blueprint.conversation_mode import (
            update_mode_from_message,
            set_conversation_mode,
        )

        # Lock into faith mode
        set_conversation_mode(self.user, 'faith')
        rt1 = resolve_response_type(self.user, "Tell me about grace")
        self.assertEqual(rt1, ResponseType.REFLECTIVE)

        # Break phrase
        update_mode_from_message(self.user, "What should I do right now?")
        rt2 = resolve_response_type(self.user, "What should I do right now?")
        self.assertEqual(rt2, ResponseType.EXECUTION)


class BriefingSuppressionTests(TestCase):
    """Test 3: During faith mode, briefing must NEVER be approved."""

    def test_briefing_blocked_in_reflective(self):
        self.assertFalse(
            is_response_allowed(ResponseType.REFLECTIVE, 'briefing'),
        )

    def test_briefing_allowed_in_execution(self):
        self.assertTrue(
            is_response_allowed(ResponseType.EXECUTION, 'briefing'),
        )


class ProactiveSuppressionTests(TestCase):
    """Test 4: During faith mode, no nudges/check-ins/affirmations."""

    def test_proactive_blocked_in_reflective(self):
        self.assertFalse(
            is_response_allowed(ResponseType.REFLECTIVE, 'proactive'),
        )
        self.assertFalse(
            is_response_allowed(ResponseType.REFLECTIVE, 'ecc'),
        )
        self.assertFalse(
            is_response_allowed(ResponseType.REFLECTIVE, 'affirmation'),
        )
        self.assertFalse(
            is_response_allowed(ResponseType.REFLECTIVE, 'intent'),
        )
        self.assertFalse(
            is_response_allowed(ResponseType.REFLECTIVE, 'execution'),
        )

    def test_reflection_allowed_in_reflective(self):
        self.assertTrue(
            is_response_allowed(ResponseType.REFLECTIVE, 'reflection'),
        )


class HealthExceptionTests(TestCase):
    """Test 5: Medication crisis → ALERT even in faith mode."""

    def setUp(self):
        self.user = _make_user("health_exc@test.com")
        try:
            self.user.operating_blueprint
        except Exception:
            from apps.core.blueprint.models import PersonalOperatingBlueprint
            PersonalOperatingBlueprint.objects.create(user=self.user)

    def test_medication_crisis_overrides_faith(self):
        from apps.core.blueprint.conversation_mode import (
            set_conversation_mode,
        )
        from apps.core.ai_orchestrator import cos_context

        set_conversation_mode(self.user, 'faith')

        def fake_fresh(user, module):
            if module == 'medicine':
                return {
                    'medication_status': 'overdue',
                    'expected_today': 10,
                    'today_taken': 0,
                }
            return {}

        with patch.object(cos_context, '_fresh_module_state', fake_fresh):
            rt = resolve_response_type(
                self.user, "Tell me about forgiveness",
                active_mode='faith',
            )

        self.assertEqual(rt, ResponseType.ALERT)

    def test_no_crisis_stays_reflective(self):
        from apps.core.ai_orchestrator import cos_context

        def fake_fresh(user, module):
            if module == 'medicine':
                return {
                    'medication_status': 'on_track',
                    'expected_today': 10,
                    'today_taken': 8,
                }
            return {}

        with patch.object(cos_context, '_fresh_module_state', fake_fresh):
            rt = resolve_response_type(
                self.user, "What does the Bible say about idols?",
                active_mode='faith',
            )

        self.assertEqual(rt, ResponseType.REFLECTIVE)


class RouterIntegrationTests(TestCase):
    """The router must use the governor as its first gate."""

    def setUp(self):
        self.user = _make_user("router_gov@test.com")
        try:
            self.user.operating_blueprint
        except Exception:
            from apps.core.blueprint.models import PersonalOperatingBlueprint
            PersonalOperatingBlueprint.objects.create(user=self.user)

    def test_faith_question_yields_via_governor(self):
        from apps.ai.deterministic_router import classify_and_route
        from apps.core.blueprint.conversation_mode import (
            set_conversation_mode,
        )

        set_conversation_mode(self.user, 'faith')
        result = classify_and_route(
            "What does this mean for how I should live?", self.user,
        )
        self.assertEqual(result.route_name, 'governor_reflective')
        self.assertTrue(result.skip_intent)
        self.assertIsNone(result.response)

    def test_execution_question_not_governor_blocked(self):
        from apps.ai.deterministic_router import classify_and_route

        result = classify_and_route(
            "What should I do right now?", self.user,
        )
        # Should NOT be governor_reflective — should be a decision route
        self.assertNotEqual(result.route_name, 'governor_reflective')
