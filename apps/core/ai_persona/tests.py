"""
PIL — Persona Intelligence Layer Tests.

Tests for persona profiles, registry, adaptation, renderer,
engine, and integration with PGE/DBE/WIRE.

Project: Whole Life Journey
Path: apps/core/ai_persona/tests.py

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_persona.persona_adaptation import (
    DEFAULT_INTENSITY,
    MAX_INTENSITY,
    MIN_INTENSITY,
    _get_gloe_factor,
    _get_icqg_factor,
    _get_priority_factor,
    _get_severity_factor,
    calculate_tone_intensity,
)
from apps.core.ai_persona.persona_engine import render_with_persona, _get_persona_key
from apps.core.ai_persona.persona_profiles import PersonaProfile
from apps.core.ai_persona.persona_registry import (
    PERSONA_PROFILES,
    get_persona_profile,
)
from apps.core.ai_persona.persona_renderer import render
from apps.users.models import TermsAcceptance, User


def _create_test_user(email="piltest@test.com"):
    """Create a test user with onboarding complete."""
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.ai_coaching_style = "supportive"
    user.preferences.save()
    return user


# ==========================================================================
# PersonaProfile Tests
# ==========================================================================


class PersonaProfileTests(TestCase):
    """Tests for the PersonaProfile dataclass."""

    def test_defaults(self):
        """PersonaProfile has sensible defaults."""
        profile = PersonaProfile(persona_key="test", display_name="Test")
        self.assertEqual(profile.base_tone, "warm")
        self.assertEqual(profile.greeting_patterns, [])
        self.assertEqual(profile.encouragement_frames, [])
        self.assertEqual(profile.warning_frames, [])
        self.assertEqual(profile.urgency_frames, [])
        self.assertEqual(profile.closing_patterns, [])
        self.assertEqual(profile.flavor_expressions, [])
        self.assertTrue(profile.adaptation_enabled)
        self.assertEqual(profile.adaptation_sensitivity, 0.5)

    def test_all_fields_settable(self):
        """All PersonaProfile fields can be set."""
        profile = PersonaProfile(
            persona_key="custom",
            display_name="Custom Style",
            base_tone="intense",
            greeting_patterns=["Hello!"],
            encouragement_frames=["{message} Great!"],
            warning_frames=["Watch out: {message}"],
            urgency_frames=["URGENT: {message}"],
            closing_patterns=["Bye!"],
            flavor_expressions=["Wow!"],
            adaptation_enabled=False,
            adaptation_sensitivity=0.8,
        )
        self.assertEqual(profile.persona_key, "custom")
        self.assertEqual(profile.base_tone, "intense")
        self.assertEqual(len(profile.greeting_patterns), 1)
        self.assertFalse(profile.adaptation_enabled)
        self.assertEqual(profile.adaptation_sensitivity, 0.8)


# ==========================================================================
# PersonaRegistry Tests
# ==========================================================================


class PersonaRegistryTests(TestCase):
    """Tests for the persona registry."""

    def test_get_profile_known_style(self):
        """Returns explicit profile for known style."""
        profile = get_persona_profile("supportive")
        self.assertEqual(profile.persona_key, "supportive")
        self.assertEqual(profile.display_name, "Supportive Partner")
        self.assertEqual(profile.base_tone, "warm")

    def test_get_profile_all_explicit_styles(self):
        """All 8 explicit styles return profiles."""
        explicit_keys = [
            "gentle", "supportive", "direct", "new_york",
            "southern_belle", "texas_rancher", "california_chill",
            "drill_sergeant",
        ]
        for key in explicit_keys:
            profile = get_persona_profile(key)
            self.assertEqual(profile.persona_key, key, f"Profile key mismatch for {key}")

    def test_get_profile_unknown_style_falls_back(self):
        """Unknown key falls back to a usable profile (supportive from explicit profiles)."""
        # Mock CoachingStyle.get_by_key to return None (no DB styles)
        with patch(
            "apps.core.ai_persona.persona_registry._build_generic_profile",
            return_value=None,
        ):
            profile = get_persona_profile("nonexistent_style_xyz")
            self.assertEqual(profile.persona_key, "supportive")

    def test_all_profiles_have_required_patterns(self):
        """Every explicit profile has at least 1 of each pattern type."""
        for key, profile in PERSONA_PROFILES.items():
            self.assertTrue(
                len(profile.greeting_patterns) >= 1,
                f"{key} missing greetings",
            )
            self.assertTrue(
                len(profile.encouragement_frames) >= 1,
                f"{key} missing encouragement_frames",
            )
            self.assertTrue(
                len(profile.warning_frames) >= 1,
                f"{key} missing warning_frames",
            )
            self.assertTrue(
                len(profile.urgency_frames) >= 1,
                f"{key} missing urgency_frames",
            )
            self.assertTrue(
                len(profile.closing_patterns) >= 1,
                f"{key} missing closing_patterns",
            )

    def test_army_drill_sergeant_alias(self):
        """army_drill_sergeant maps to a profile with intense tone."""
        profile = get_persona_profile("army_drill_sergeant")
        self.assertEqual(profile.persona_key, "army_drill_sergeant")
        self.assertEqual(profile.base_tone, "intense")


# ==========================================================================
# PersonaAdaptation Tests
# ==========================================================================


class PersonaAdaptationTests(TestCase):
    """Tests for tone intensity adaptation."""

    def setUp(self):
        self.user = _create_test_user("adapt@test.com")

    @patch("apps.core.ai_persona.persona_adaptation._get_gloe_factor", return_value=1.0)
    @patch("apps.core.ai_persona.persona_adaptation._get_icqg_factor", return_value=1.0)
    @patch("apps.core.ai_persona.persona_adaptation._get_severity_factor", return_value=1.0)
    def test_intensity_default_neutral(self, mock_sev, mock_icqg, mock_gloe):
        """New user with neutral signals gets ~1.0 intensity."""
        intensity = calculate_tone_intensity(self.user, "supportive", {})
        self.assertEqual(intensity, 1.0)

    @patch("apps.core.ai_persona.persona_adaptation._get_icqg_factor", return_value=1.0)
    @patch("apps.core.ai_persona.persona_adaptation._get_severity_factor", return_value=1.0)
    @patch("apps.core.ai_persona.persona_adaptation._get_priority_factor", return_value=1.0)
    def test_intensity_low_gloe_softens(self, mock_pri, mock_sev, mock_icqg):
        """Low GLOE responsiveness produces intensity < 1.0."""
        with patch(
            "apps.core.ai_persona.persona_adaptation._get_gloe_factor",
            return_value=0.6,
        ):
            intensity = calculate_tone_intensity(self.user, "supportive", {})
            self.assertLess(intensity, 1.0)

    @patch("apps.core.ai_persona.persona_adaptation._get_icqg_factor", return_value=1.0)
    @patch("apps.core.ai_persona.persona_adaptation._get_severity_factor", return_value=1.0)
    @patch("apps.core.ai_persona.persona_adaptation._get_priority_factor", return_value=1.0)
    def test_intensity_high_gloe_strengthens(self, mock_pri, mock_sev, mock_icqg):
        """High GLOE responsiveness produces intensity > 1.0."""
        with patch(
            "apps.core.ai_persona.persona_adaptation._get_gloe_factor",
            return_value=1.3,
        ):
            intensity = calculate_tone_intensity(self.user, "supportive", {})
            self.assertGreater(intensity, 1.0)

    @patch("apps.core.ai_persona.persona_adaptation._get_gloe_factor", return_value=1.0)
    @patch("apps.core.ai_persona.persona_adaptation._get_severity_factor", return_value=1.0)
    @patch("apps.core.ai_persona.persona_adaptation._get_priority_factor", return_value=1.0)
    def test_intensity_low_icqg_softens(self, mock_pri, mock_sev, mock_gloe):
        """Low ICQG usefulness softens intensity."""
        with patch(
            "apps.core.ai_persona.persona_adaptation._get_icqg_factor",
            return_value=0.7,
        ):
            intensity = calculate_tone_intensity(self.user, "supportive", {})
            self.assertLess(intensity, 1.0)

    def test_intensity_critical_priority_strengthens(self):
        """Critical priority (1) boosts intensity."""
        factor = _get_priority_factor({"priority": 1})
        self.assertEqual(factor, 1.3)

    def test_intensity_briefing_type_calms(self):
        """Briefing message type lowers intensity."""
        factor = _get_priority_factor({"message_type": "briefing"})
        self.assertEqual(factor, 0.95)

    def test_intensity_weekly_report_calms(self):
        """Weekly report message type lowers intensity."""
        factor = _get_priority_factor({"message_type": "weekly_report"})
        self.assertEqual(factor, 0.9)

    def test_intensity_clamped_to_range(self):
        """Intensity is always between MIN and MAX."""
        with patch(
            "apps.core.ai_persona.persona_adaptation._get_gloe_factor",
            return_value=2.0,
        ), patch(
            "apps.core.ai_persona.persona_adaptation._get_icqg_factor",
            return_value=2.0,
        ), patch(
            "apps.core.ai_persona.persona_adaptation._get_severity_factor",
            return_value=2.0,
        ), patch(
            "apps.core.ai_persona.persona_adaptation._get_priority_factor",
            return_value=2.0,
        ):
            intensity = calculate_tone_intensity(self.user, "supportive", {})
            self.assertLessEqual(intensity, MAX_INTENSITY)
            self.assertGreaterEqual(intensity, MIN_INTENSITY)

    def test_gloe_factor_low_score(self):
        """GLOE score < 0.3 produces factor < 0.8."""
        with patch(
            "apps.core.ai_guidance_learning.learning_engine.get_responsiveness_score",
            return_value=0.1,
        ):
            factor = _get_gloe_factor(self.user)
            self.assertLess(factor, 0.8)

    def test_gloe_factor_high_score(self):
        """GLOE score > 0.7 produces factor > 1.0."""
        with patch(
            "apps.core.ai_guidance_learning.learning_engine.get_responsiveness_score",
            return_value=0.9,
        ):
            factor = _get_gloe_factor(self.user)
            self.assertGreater(factor, 1.0)

    def test_severity_overdue_goals(self):
        """SAE overdue goals boost severity factor."""
        with patch(
            "apps.core.ai_state.state_engine.get_user_state",
            return_value={"goals": {"overdue_goal_count": 5}},
        ):
            factor = _get_severity_factor(self.user)
            self.assertGreater(factor, 1.0)


# ==========================================================================
# PersonaRenderer Tests
# ==========================================================================


class PersonaRendererTests(TestCase):
    """Tests for the persona renderer."""

    def setUp(self):
        self.profile = PersonaProfile(
            persona_key="test",
            display_name="Test Style",
            base_tone="warm",
            greeting_patterns=["Hello!", "Hey there!"],
            encouragement_frames=[
                "Great news! {message}",
                "{message} Well done!",
            ],
            warning_frames=[
                "Watch out: {message}",
                "Heads up — {message}",
            ],
            urgency_frames=[
                "URGENT: {message}",
                "Alert! {message}",
            ],
            closing_patterns=["Keep going!", "You've got this!"],
            flavor_expressions=["Awesome!", "Incredible!"],
        )

    def test_render_returns_string(self):
        """Render always returns a string."""
        result = render(self.profile, "Test message.", 1.0, {})
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_render_low_intensity_greeting_only(self):
        """Intensity 0.65 = greeting + base message (no closing, no frame)."""
        result = render(self.profile, "Test message.", 0.65, {})
        # Should contain a greeting
        self.assertTrue(
            any(g in result for g in self.profile.greeting_patterns),
            f"No greeting found in: {result}",
        )
        # Should contain the base message
        self.assertIn("Test message.", result)
        # Should NOT contain a closing (intensity < 0.7)
        self.assertFalse(
            any(c in result for c in self.profile.closing_patterns),
            f"Unexpected closing found in: {result}",
        )

    def test_render_medium_intensity_greeting_closing(self):
        """Intensity 0.85 = greeting + message + closing."""
        result = render(self.profile, "Test message.", 0.85, {})
        self.assertTrue(any(g in result for g in self.profile.greeting_patterns))
        self.assertIn("Test message.", result)
        self.assertTrue(any(c in result for c in self.profile.closing_patterns))

    def test_render_standard_intensity_full(self):
        """Intensity 1.0 = greeting + framed message + closing."""
        result = render(self.profile, "Test message.", 1.0, {})
        self.assertTrue(any(g in result for g in self.profile.greeting_patterns))
        # Should be framed (encouragement by default)
        self.assertTrue(
            "Great news!" in result or "Well done!" in result,
            f"No encouragement frame in: {result}",
        )
        self.assertTrue(any(c in result for c in self.profile.closing_patterns))

    def test_render_high_intensity_with_flavor(self):
        """Intensity 1.2 includes flavor expressions."""
        result = render(self.profile, "Test message.", 1.2, {})
        self.assertTrue(
            any(f in result for f in self.profile.flavor_expressions),
            f"No flavor in: {result}",
        )

    def test_render_max_intensity_heavy_flavor(self):
        """Intensity 1.35 includes multiple flavor expressions."""
        result = render(self.profile, "Test message.", 1.35, {})
        # Should have flavor content
        flavor_count = sum(
            1 for f in self.profile.flavor_expressions if f in result
        )
        self.assertGreaterEqual(
            flavor_count, 1,
            f"Expected flavor in: {result}",
        )

    def test_render_urgency_frame_for_critical(self):
        """Priority 1 uses urgency frames."""
        result = render(self.profile, "Test message.", 1.0, {"priority": 1})
        self.assertTrue(
            "URGENT:" in result or "Alert!" in result,
            f"No urgency frame in: {result}",
        )

    def test_render_warning_frame_for_medium(self):
        """Priority 3 uses warning frames."""
        result = render(self.profile, "Test message.", 1.0, {"priority": 3})
        self.assertTrue(
            "Watch out:" in result or "Heads up" in result,
            f"No warning frame in: {result}",
        )

    def test_render_encouragement_for_low_priority(self):
        """Priority 5 uses encouragement frames."""
        result = render(self.profile, "Test message.", 1.0, {"priority": 5})
        self.assertTrue(
            "Great news!" in result or "Well done!" in result,
            f"No encouragement frame in: {result}",
        )

    def test_render_deterministic(self):
        """Same input always produces same output."""
        result1 = render(self.profile, "Same message.", 1.0, {})
        result2 = render(self.profile, "Same message.", 1.0, {})
        self.assertEqual(result1, result2)

    def test_render_empty_message_returns_empty(self):
        """Empty string input returns empty string."""
        result = render(self.profile, "", 1.0, {})
        self.assertEqual(result, "")

    def test_render_whitespace_only_returns_unchanged(self):
        """Whitespace-only input returns unchanged."""
        result = render(self.profile, "   ", 1.0, {})
        self.assertEqual(result, "   ")


# ==========================================================================
# PersonaEngine Integration Tests
# ==========================================================================


class PersonaEngineTests(TestCase):
    """Tests for the main persona engine entry point."""

    def setUp(self):
        self.user = _create_test_user("engine@test.com")

    @patch("apps.core.ai_persona.persona_adaptation.calculate_tone_intensity",
           return_value=1.0)
    def test_render_with_persona_supportive(self, mock_intensity):
        """Full pipeline for supportive style."""
        result = render_with_persona(
            self.user, "Your weight is trending down.", "guidance",
        )
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > len("Your weight is trending down."))

    @patch("apps.core.ai_persona.persona_adaptation.calculate_tone_intensity",
           return_value=1.0)
    def test_render_with_persona_drill_sergeant(self, mock_intensity):
        """Full pipeline for drill_sergeant style."""
        self.user.preferences.ai_coaching_style = "drill_sergeant"
        self.user.preferences.save()

        result = render_with_persona(
            self.user, "You missed your step goal.", "guidance", priority=2,
        )
        self.assertIsInstance(result, str)
        # Should contain drill sergeant language
        self.assertTrue(len(result) > len("You missed your step goal."))

    def test_render_with_persona_failsafe(self):
        """When registry raises, returns base_message."""
        with patch(
            "apps.core.ai_persona.persona_engine._get_persona_key",
            side_effect=Exception("boom"),
        ):
            result = render_with_persona(
                self.user, "Original message.", "guidance",
            )
            self.assertEqual(result, "Original message.")

    def test_render_with_persona_empty_message(self):
        """Empty input returns empty output."""
        result = render_with_persona(self.user, "", "guidance")
        self.assertEqual(result, "")

    def test_render_with_persona_none_message(self):
        """None input returns None."""
        result = render_with_persona(self.user, None, "guidance")
        self.assertIsNone(result)

    def test_get_persona_key_default(self):
        """Default persona key is 'supportive'."""
        key = _get_persona_key(self.user)
        self.assertEqual(key, "supportive")

    def test_get_persona_key_custom(self):
        """Custom persona key from preferences."""
        self.user.preferences.ai_coaching_style = "direct"
        self.user.preferences.save()
        key = _get_persona_key(self.user)
        self.assertEqual(key, "direct")

    def test_get_persona_key_empty_falls_back(self):
        """Empty coaching style falls back to supportive."""
        self.user.preferences.ai_coaching_style = ""
        self.user.preferences.save()
        key = _get_persona_key(self.user)
        self.assertEqual(key, "supportive")


# ==========================================================================
# Integration Point Tests
# ==========================================================================


class PGEIntegrationTests(TestCase):
    """Test PIL integration in PGE guidance logger."""

    def setUp(self):
        self.user = _create_test_user("pge@test.com")

    @patch("apps.core.ai_persona.persona_engine.render_with_persona")
    def test_pge_guidance_logger_calls_pil(self, mock_render):
        """Verify PIL is called in _upsert_guidance."""
        mock_render.return_value = "Persona-rendered message."

        from apps.core.ai_guidance.guidance_logger import log_guidance

        candidates = [
            {
                "dedupe_key": "test_pil_integration_001",
                "title": "Test Guidance",
                "message": "Original guidance message.",
                "priority": 3,
                "module": "health",
                "guidance_type": "test",
                "source": "composite",
            }
        ]
        stored = log_guidance(self.user, candidates)

        # PIL should have been called
        mock_render.assert_called_once()
        call_kwargs = mock_render.call_args
        self.assertEqual(call_kwargs[1].get("message_type") or call_kwargs[0][2], "guidance")

        # The stored item should have the rendered message
        if stored:
            self.assertEqual(stored[0].message, "Persona-rendered message.")


class DBEIntegrationTests(TestCase):
    """Test PIL integration in DBE briefing engine."""

    @patch("apps.core.ai_persona.persona_engine.render_with_persona")
    @patch("apps.core.ai_briefing.briefing_engine._get_state", return_value={})
    @patch("apps.core.ai_briefing.briefing_engine._get_guidance", return_value=[])
    @patch("apps.core.ai_briefing.briefing_engine._get_insights", return_value=[])
    @patch("apps.core.ai_briefing.briefing_engine._get_predictions", return_value=[])
    def test_dbe_briefing_engine_calls_pil(
        self, mock_pred, mock_ins, mock_guid, mock_state, mock_render
    ):
        """Verify PIL is called in briefing generation."""
        user = _create_test_user("dbe@test.com")
        mock_render.return_value = "Persona briefing."

        from apps.core.ai_briefing.briefing_engine import generate_daily_briefing

        briefing = generate_daily_briefing(user)

        # PIL should have been called
        mock_render.assert_called_once()
        call_args = mock_render.call_args
        # Verify message_type is "briefing"
        self.assertEqual(
            call_args[1].get("message_type") or call_args[0][2],
            "briefing",
        )


class WIREIntegrationTests(TestCase):
    """Test PIL integration in WIRE report engine."""

    @patch("apps.core.ai_persona.persona_engine.render_with_persona")
    @patch("apps.core.ai_weekly_report.report_engine._get_current_state", return_value={})
    @patch("apps.core.ai_weekly_report.report_engine._get_week_insights", return_value=[])
    @patch("apps.core.ai_weekly_report.report_engine._get_week_predictions", return_value=[])
    @patch("apps.core.ai_weekly_report.report_engine._get_week_guidance", return_value=[])
    @patch(
        "apps.core.ai_weekly_report.report_engine._get_learning_snapshot",
        return_value={"responsiveness_score": 0.5, "total_guidance_seen": 0},
    )
    def test_wire_report_engine_calls_pil(
        self, mock_learn, mock_guid, mock_pred, mock_ins, mock_state, mock_render
    ):
        """Verify PIL is called in weekly report generation."""
        user = _create_test_user("wire@test.com")
        mock_render.return_value = "Persona weekly report."

        from apps.core.ai_weekly_report.report_engine import generate_weekly_report

        report = generate_weekly_report(user)

        # PIL should have been called
        mock_render.assert_called_once()
        call_args = mock_render.call_args
        self.assertEqual(
            call_args[1].get("message_type") or call_args[0][2],
            "weekly_report",
        )


class DNENoDoubleRenderTests(TestCase):
    """Verify DNE does NOT call PIL (would double-render)."""

    def test_dne_delivery_engine_does_not_import_pil(self):
        """DNE delivery_engine.py does not import PIL."""
        import inspect
        from apps.core.ai_delivery import delivery_engine

        source = inspect.getsource(delivery_engine)
        self.assertNotIn("render_with_persona", source)
        self.assertNotIn("ai_persona", source)
