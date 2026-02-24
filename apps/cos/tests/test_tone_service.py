"""
CoS v2 — Phase 9 Tests: Tone Modes

Tests:
1. Tone selection by activity type
2. Time-of-day overrides (early morning → gentle, late evening → reflective)
3. Sentiment-aware overrides (negative streak → empathetic)
4. Response style instruction from user preference
5. Full prompt modifier building
6. Tone for prompt objects
7. Available tones API
"""

import datetime as dt

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.cos.services.tone_service import (
    ACTIVITY_TONE_MAP,
    RESPONSE_STYLE_INSTRUCTIONS,
    SENTIMENT_TONE_OVERRIDE,
    TIME_TONE_OVERRIDES,
    TONES,
    CosToneService,
)

User = get_user_model()


def _create_test_user(email="costone@example.com"):
    from apps.users.models import TermsAcceptance

    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


# ──────────────────────────────────────────────────────────
# Activity Type Tone Selection
# ──────────────────────────────────────────────────────────


class ActivityToneTests(TestCase):
    """Test tone selection by activity type."""

    def setUp(self):
        self.user = _create_test_user("activitytone@example.com")
        self.svc = CosToneService(self.user)

    def test_workout_is_energized(self):
        """Workout gets energized tone (during normal hours)."""
        midday = timezone.now().replace(hour=12, minute=0)
        tone = self.svc.select_tone(
            activity_type="workout", reference_time=midday,
        )
        self.assertEqual(tone, "energized")

    def test_meeting_is_direct(self):
        """Meeting gets direct tone."""
        midday = timezone.now().replace(hour=12, minute=0)
        tone = self.svc.select_tone(
            activity_type="meeting", reference_time=midday,
        )
        self.assertEqual(tone, "direct")

    def test_prayer_is_gentle(self):
        """Prayer gets gentle tone."""
        midday = timezone.now().replace(hour=12, minute=0)
        tone = self.svc.select_tone(
            activity_type="prayer", reference_time=midday,
        )
        self.assertEqual(tone, "gentle")

    def test_journaling_is_reflective(self):
        """Journaling gets reflective tone."""
        midday = timezone.now().replace(hour=12, minute=0)
        tone = self.svc.select_tone(
            activity_type="journaling", reference_time=midday,
        )
        self.assertEqual(tone, "reflective")

    def test_default_is_encouraging(self):
        """Unknown activity type gets encouraging tone."""
        midday = timezone.now().replace(hour=12, minute=0)
        tone = self.svc.select_tone(
            activity_type="unknown_type", reference_time=midday,
        )
        self.assertEqual(tone, "encouraging")

    def test_all_activity_types_have_tone(self):
        """Every activity type in the map has a valid tone."""
        for activity_type, expected_tone in ACTIVITY_TONE_MAP.items():
            self.assertIn(expected_tone, TONES)


# ──────────────────────────────────────────────────────────
# Time-of-Day Override Tests
# ──────────────────────────────────────────────────────────


class TimeToneOverrideTests(TestCase):
    """Test time-of-day tone overrides."""

    def setUp(self):
        self.user = _create_test_user("timetone@example.com")
        self.svc = CosToneService(self.user)

    def test_early_morning_overrides_to_gentle(self):
        """At 6am, even workout becomes gentle."""
        early = timezone.now().replace(hour=6, minute=0)
        tone = self.svc.select_tone(
            activity_type="workout", reference_time=early,
        )
        self.assertEqual(tone, "gentle")

    def test_late_evening_overrides_to_reflective(self):
        """At 9pm, even meeting becomes reflective."""
        late = timezone.now().replace(hour=21, minute=0)
        tone = self.svc.select_tone(
            activity_type="meeting", reference_time=late,
        )
        self.assertEqual(tone, "reflective")

    def test_midday_no_override(self):
        """At noon, activity type default is used."""
        noon = timezone.now().replace(hour=12, minute=0)
        tone = self.svc.select_tone(
            activity_type="workout", reference_time=noon,
        )
        # Should use activity default, not time override
        self.assertEqual(tone, "energized")


# ──────────────────────────────────────────────────────────
# Sentiment Override Tests
# ──────────────────────────────────────────────────────────


class SentimentToneOverrideTests(TestCase):
    """Test sentiment-aware tone overrides."""

    def setUp(self):
        self.user = _create_test_user("sentitone@example.com")
        self.svc = CosToneService(self.user)

    def test_negative_streak_becomes_empathetic(self):
        """2+ day negative streak → empathetic regardless of activity."""
        midday = timezone.now().replace(hour=12, minute=0)
        tone = self.svc.select_tone(
            activity_type="workout",
            reference_time=midday,
            sentiment_context={"recent_sentiment": "negative", "streak_days": 3},
        )
        self.assertEqual(tone, "empathetic")

    def test_positive_streak_becomes_celebratory(self):
        """3+ day positive streak → celebratory."""
        midday = timezone.now().replace(hour=12, minute=0)
        tone = self.svc.select_tone(
            activity_type="task",
            reference_time=midday,
            sentiment_context={"recent_sentiment": "positive", "streak_days": 4},
        )
        self.assertEqual(tone, "celebratory")

    def test_short_negative_streak_no_override(self):
        """1-day negative doesn't trigger override."""
        midday = timezone.now().replace(hour=12, minute=0)
        tone = self.svc.select_tone(
            activity_type="workout",
            reference_time=midday,
            sentiment_context={"recent_sentiment": "negative", "streak_days": 1},
        )
        # Falls through to activity default
        self.assertEqual(tone, "energized")

    def test_sentiment_takes_priority_over_time(self):
        """Sentiment override beats time-of-day override."""
        early = timezone.now().replace(hour=6, minute=0)
        tone = self.svc.select_tone(
            activity_type="workout",
            reference_time=early,
            sentiment_context={"recent_sentiment": "negative", "streak_days": 3},
        )
        # Sentiment override wins over early-morning gentle
        self.assertEqual(tone, "empathetic")


# ──────────────────────────────────────────────────────────
# Tone Instruction Tests
# ──────────────────────────────────────────────────────────


class ToneInstructionTests(TestCase):
    """Test tone instruction text retrieval."""

    def setUp(self):
        self.user = _create_test_user("instruction@example.com")
        self.svc = CosToneService(self.user)

    def test_known_tone_has_instruction(self):
        """All non-neutral tones have instruction text."""
        for key, tone_def in TONES.items():
            if key != "neutral":
                instruction = self.svc.get_tone_instruction(key)
                self.assertTrue(
                    len(instruction) > 0,
                    f"Tone '{key}' should have an instruction",
                )

    def test_neutral_has_empty_instruction(self):
        """Neutral tone has no instruction (use base style)."""
        instruction = self.svc.get_tone_instruction("neutral")
        self.assertEqual(instruction, "")

    def test_unknown_tone_returns_empty(self):
        """Unknown tone key returns empty string."""
        instruction = self.svc.get_tone_instruction("nonexistent")
        self.assertEqual(instruction, "")


# ──────────────────────────────────────────────────────────
# Response Style Tests
# ──────────────────────────────────────────────────────────


class ResponseStyleTests(TestCase):
    """Test response style instruction from user preferences."""

    def setUp(self):
        self.user = _create_test_user("style@example.com")
        self.svc = CosToneService(self.user)

    def test_default_balanced(self):
        """Default cos_response_style is 'balanced'."""
        instruction = self.svc.get_response_style_instruction()
        self.assertEqual(
            instruction, RESPONSE_STYLE_INSTRUCTIONS["balanced"],
        )

    def test_concise_style(self):
        """Concise response style returns concise instruction."""
        self.user.preferences.cos_response_style = "concise"
        self.user.preferences.save()
        instruction = self.svc.get_response_style_instruction()
        self.assertIn("1-2 sentences", instruction)

    def test_deep_dive_style(self):
        """Deep dive response style returns detailed instruction."""
        self.user.preferences.cos_response_style = "deep_dive"
        self.user.preferences.save()
        instruction = self.svc.get_response_style_instruction()
        self.assertIn("3-5 sentences", instruction)


# ──────────────────────────────────────────────────────────
# Prompt Modifier Tests
# ──────────────────────────────────────────────────────────


class PromptModifierTests(TestCase):
    """Test full prompt modifier building."""

    def setUp(self):
        self.user = _create_test_user("modifier@example.com")
        self.svc = CosToneService(self.user)

    def test_build_modifier_includes_tone(self):
        """Modifier includes tone instruction."""
        midday = timezone.now().replace(hour=12, minute=0)
        modifier = self.svc.build_prompt_modifier(
            activity_type="workout",
            reference_time=midday,
            include_sentiment=False,
        )
        # Workout at midday → energized
        self.assertIn("energetic", modifier.lower())

    def test_build_modifier_includes_response_style(self):
        """Modifier includes response style instruction."""
        midday = timezone.now().replace(hour=12, minute=0)
        modifier = self.svc.build_prompt_modifier(
            activity_type="workout",
            reference_time=midday,
            include_sentiment=False,
        )
        # Default balanced → should have "2-3 sentences"
        self.assertIn("2-3 sentences", modifier)

    def test_modifier_without_response_style(self):
        """Can exclude response style from modifier."""
        midday = timezone.now().replace(hour=12, minute=0)
        modifier = self.svc.build_prompt_modifier(
            activity_type="workout",
            reference_time=midday,
            include_sentiment=False,
            include_response_style=False,
        )
        self.assertNotIn("sentences", modifier)


# ──────────────────────────────────────────────────────────
# Available Tones API Tests
# ──────────────────────────────────────────────────────────


class AvailableTonesTests(TestCase):
    """Test available tones metadata."""

    def test_get_available_tones_excludes_neutral(self):
        """Available tones list excludes neutral."""
        tones = CosToneService.get_available_tones()
        keys = [t["key"] for t in tones]
        self.assertNotIn("neutral", keys)
        self.assertIn("encouraging", keys)
        self.assertIn("gentle", keys)

    def test_get_activity_tone_defaults(self):
        """Activity tone defaults returns complete mapping."""
        defaults = CosToneService.get_activity_tone_defaults()
        self.assertEqual(defaults["workout"], "energized")
        self.assertEqual(defaults["meeting"], "direct")
        self.assertEqual(defaults["prayer"], "gentle")


# ──────────────────────────────────────────────────────────
# Prompt Tone Selection Tests
# ──────────────────────────────────────────────────────────


class PromptToneSelectionTests(TestCase):
    """Test tone selection for prompt objects."""

    def setUp(self):
        self.user = _create_test_user("prompttone@example.com")
        self.svc = CosToneService(self.user)

    def test_select_tone_for_prompt(self):
        """Selects tone from prompt's activity_type and scheduled_for."""

        class MockPrompt:
            activity_type = "workout"
            scheduled_for = timezone.now().replace(hour=12, minute=0)

        tone_key, instruction = self.svc.select_tone_for_prompt(MockPrompt())
        self.assertEqual(tone_key, "energized")
        self.assertIn("energetic", instruction.lower())

    def test_select_tone_for_prompt_no_activity(self):
        """Handles prompt with no activity_type."""

        class MockPrompt:
            activity_type = None
            scheduled_for = timezone.now().replace(hour=12, minute=0)

        tone_key, _ = self.svc.select_tone_for_prompt(MockPrompt())
        # Falls back to "default" → encouraging
        self.assertEqual(tone_key, "encouraging")
