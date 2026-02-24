"""
CoS v2 — Phase 9 Integration Tests: End-to-End Flows

Tests the full CoS pipeline across services:
1. Event → Prompt scheduling → Delivery with tone → Response → Reflection
2. Reflection → Pattern detection → Goal suggestion
3. Auto-shift with tone-aware proposal
4. Action router tone enrichment
5. Cross-service feature flag gating
"""

import datetime as dt
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone

from apps.calendar_engine.models import CalendarEvent
from apps.cos.models import (
    CosAutoShiftLog,
    CosGoalSuggestion,
    CosPromptSchedule,
    CosReflection,
)
from apps.cos.services.auto_shift_service import CosAutoShiftService
from apps.cos.services.pattern_service import CosPatternService
from apps.cos.services.prompt_service import CosPromptService
from apps.cos.services.reflection_service import CosReflectionService
from apps.cos.services.tone_service import CosToneService

User = get_user_model()


def _create_test_user(email="cosintegration@example.com", cos_enabled=True):
    from apps.users.models import TermsAcceptance

    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.cos_v2_enabled = cos_enabled
    user.preferences.save()
    return user


def _create_event(user, title, start_dt=None, duration_hours=1, is_protected=False):
    """Create a calendar event."""
    if not start_dt:
        start_dt = timezone.now() + dt.timedelta(hours=2)
    end_dt = start_dt + dt.timedelta(hours=duration_hours)
    return CalendarEvent.objects.create(
        user=user,
        title=title,
        start_dt=start_dt,
        end_dt=end_dt,
        is_protected=is_protected,
        idempotency_key=uuid4().hex,
    )


# ──────────────────────────────────────────────────────────
# Full Pipeline Integration Tests
# ──────────────────────────────────────────────────────────


class EventToReflectionPipelineTests(TestCase):
    """Test: Event → Prompt → Delivery → Response → Reflection."""

    def setUp(self):
        self.user = _create_test_user("pipeline@example.com")

    def test_event_creates_prompts_with_correct_type(self):
        """Creating an event and scheduling prompts detects activity type."""
        # Future event
        start = timezone.now() + dt.timedelta(hours=3)
        event = _create_event(self.user, "Morning Workout", start_dt=start)

        svc = CosPromptService(self.user)
        prompts = svc.schedule_prompts_for_event(event)

        # Should create pre and post prompts
        self.assertEqual(len(prompts), 2)
        for prompt in prompts:
            self.assertEqual(prompt.activity_type, "workout")

    def test_prompt_delivery_applies_tone_metadata(self):
        """Delivering a prompt stores tone in metadata."""
        # Create a pre-event prompt directly (avoid scheduling time edge cases)
        start = timezone.now() + dt.timedelta(hours=2)
        event = _create_event(self.user, "Evening Prayer", start_dt=start)

        ct = ContentType.objects.get_for_model(event)
        prompt = CosPromptSchedule.objects.create(
            user=self.user,
            content_type=ct,
            object_id=event.pk,
            timing=CosPromptSchedule.TIMING_PRE,
            scheduled_for=timezone.now() - dt.timedelta(minutes=1),
            activity_type="prayer",
            prompt_text="Your prayer time is coming up.",
        )

        # Deliver
        svc = CosPromptService(self.user)
        delivered = svc.deliver_prompt(prompt)
        self.assertTrue(delivered)

        # Check metadata
        prompt.refresh_from_db()
        self.assertIn("tone", prompt.metadata)
        # Prayer → gentle (unless time override applies)
        self.assertIn(
            prompt.metadata["tone"],
            ["gentle", "reflective"],  # gentle or reflective depending on time
        )

    def test_response_creates_reflection_with_sentiment(self):
        """Responding to a post-event prompt creates a reflection."""
        start = timezone.now() - dt.timedelta(hours=2)
        event = _create_event(
            self.user, "Morning Workout",
            start_dt=start,
        )

        # Create a post-event prompt manually
        ct = ContentType.objects.get_for_model(event)
        prompt = CosPromptSchedule.objects.create(
            user=self.user,
            content_type=ct,
            object_id=event.pk,
            timing=CosPromptSchedule.TIMING_POST,
            scheduled_for=timezone.now() - dt.timedelta(minutes=5),
            activity_type="workout",
            prompt_text="How was your workout?",
            status=CosPromptSchedule.STATUS_DELIVERED,
        )

        # User responds positively with text
        svc = CosPromptService(self.user)
        result = svc.handle_response(
            prompt_id=prompt.pk,
            positive=True,
            response_text="Great workout! Felt really energized and strong.",
        )

        self.assertTrue(result["success"])

        # Check reflection was created
        reflections = CosReflection.objects.filter(user=self.user)
        self.assertEqual(reflections.count(), 1)
        self.assertEqual(reflections.first().sentiment, "positive")


# ──────────────────────────────────────────────────────────
# Reflection to Pattern Pipeline Tests
# ──────────────────────────────────────────────────────────


class ReflectionToPatternPipelineTests(TestCase):
    """Test: Multiple reflections → Pattern detection → Goal suggestion."""

    def setUp(self):
        self.user = _create_test_user("pattern_pipe@example.com")

    def test_negative_reflections_detect_pattern(self):
        """3+ negative reflections trigger pattern detection."""
        ref_svc = CosReflectionService(self.user)
        start = timezone.now() - dt.timedelta(hours=2)

        # Create negative reflections over 3 days
        for i in range(4):
            event = _create_event(
                self.user, f"Workout {i}",
                start_dt=start - dt.timedelta(days=i),
            )
            ref_svc.create_reflection(
                source_entity=event,
                text="Struggled today, felt exhausted and frustrated",
                activity_type="workout",
                activity_date=(
                    timezone.now() - dt.timedelta(days=i)
                ).date(),
            )

        # Run pattern detection
        pat_svc = CosPatternService(self.user)
        patterns = pat_svc.detect_all_patterns(days=14)

        # Should detect negative streak or fatigue
        self.assertTrue(len(patterns) > 0)
        pattern_types = [p["pattern_type"] for p in patterns]
        self.assertTrue(
            "negative_streak" in pattern_types or "fatigue" in pattern_types,
            f"Expected negative_streak or fatigue, got: {pattern_types}",
        )


# ──────────────────────────────────────────────────────────
# Auto-Shift with Tone Tests
# ──────────────────────────────────────────────────────────


class AutoShiftToneTests(TestCase):
    """Test auto-shift proposals include activity-type context."""

    def setUp(self):
        self.user = _create_test_user("shifttone@example.com")

    def test_shift_proposal_includes_activity_type(self):
        """Shift proposal knows the activity type for tone context."""
        start = timezone.now().replace(hour=10, minute=0) + dt.timedelta(days=1)
        event = _create_event(self.user, "Evening Prayer", start_dt=start)

        shift_svc = CosAutoShiftService(self.user)
        proposal = shift_svc.propose_shift(
            event,
            conflicting_end=start + dt.timedelta(hours=1),
        )

        self.assertEqual(proposal["activity_type"], "prayer")
        self.assertEqual(proposal["priority"], "low")

        # Verify tone would be appropriate for this activity
        tone_svc = CosToneService(self.user)
        tone = tone_svc.select_tone(
            activity_type=proposal["activity_type"],
            reference_time=proposal.get("proposed_start"),
        )
        # Prayer → gentle (unless time override)
        self.assertIn(tone, ["gentle", "reflective"])


# ──────────────────────────────────────────────────────────
# Action Router Tone Enrichment Tests
# ──────────────────────────────────────────────────────────


class ActionRouterToneTests(TestCase):
    """Test tone enrichment in action router."""

    def setUp(self):
        self.user = _create_test_user("routertone@example.com")

    def test_route_action_with_tone(self):
        """Action router enriches with tone when user has CoS enabled."""
        from apps.core.ai_orchestrator.action_router import route_action

        action = route_action(
            intent_type="log_weight",
            parameters={"weight": 180, "activity_type": "workout"},
            user=self.user,
        )
        # Should have tone enrichment
        self.assertIsNotNone(action.tone)
        self.assertIn(action.tone, [
            "energized", "gentle", "reflective", "encouraging",
            "direct", "empathetic", "celebratory",
        ])

    def test_route_action_without_user(self):
        """Action router works without user (no tone enrichment)."""
        from apps.core.ai_orchestrator.action_router import route_action

        action = route_action(
            intent_type="log_weight",
            parameters={"weight": 180},
        )
        self.assertIsNone(action.tone)

    def test_route_action_cos_disabled(self):
        """No tone enrichment when CoS v2 is disabled."""
        from apps.core.ai_orchestrator.action_router import route_action

        disabled_user = _create_test_user(
            "disabled@example.com", cos_enabled=False,
        )
        action = route_action(
            intent_type="log_weight",
            parameters={"weight": 180},
            user=disabled_user,
        )
        self.assertIsNone(action.tone)

    def test_enriched_action_to_dict(self):
        """to_dict includes tone when present."""
        from apps.core.ai_orchestrator.action_router import route_action

        action = route_action(
            intent_type="log_weight",
            parameters={"weight": 180, "activity_type": "meeting"},
            user=self.user,
        )
        d = action.to_dict()
        if action.tone:
            self.assertIn("tone", d)


# ──────────────────────────────────────────────────────────
# Feature Flag Integration Tests
# ──────────────────────────────────────────────────────────


class FeatureFlagIntegrationTests(TestCase):
    """Test CoS v2 feature flag gating across services."""

    def setUp(self):
        self.enabled_user = _create_test_user("enabled@example.com")
        self.disabled_user = _create_test_user(
            "disabled2@example.com", cos_enabled=False,
        )

    def test_batch_delivery_skips_disabled_users(self):
        """Batch prompt delivery skips users without cos_v2_enabled."""
        # Schedule prompts for both users
        start = timezone.now() + dt.timedelta(hours=2)

        for user in [self.enabled_user, self.disabled_user]:
            event = _create_event(user, "Test Event", start_dt=start)
            ct = ContentType.objects.get_for_model(event)
            CosPromptSchedule.objects.create(
                user=user,
                content_type=ct,
                object_id=event.pk,
                timing=CosPromptSchedule.TIMING_PRE,
                scheduled_for=timezone.now() - dt.timedelta(minutes=1),
                activity_type="meeting",
                prompt_text="Test prompt",
            )

        # Run batch delivery
        result = CosPromptService.deliver_all_due_for_all_users()

        # Only enabled user should have prompts delivered
        self.assertEqual(result["users"], 1)
        self.assertEqual(result["delivered"], 1)


# ──────────────────────────────────────────────────────────
# Cross-Service Consistency Tests
# ──────────────────────────────────────────────────────────


class CrossServiceConsistencyTests(TestCase):
    """Test that services are consistent with each other."""

    def setUp(self):
        self.user = _create_test_user("consistent@example.com")

    def test_tone_service_knows_all_prompt_activity_types(self):
        """Every activity type in prompt templates has a tone mapping."""
        from apps.cos.services.prompt_templates import ACTIVITY_TYPE_PATTERNS

        tone_defaults = CosToneService.get_activity_tone_defaults()
        for activity_type in ACTIVITY_TYPE_PATTERNS:
            self.assertIn(
                activity_type, tone_defaults,
                f"Activity type '{activity_type}' has no tone mapping",
            )

    def test_auto_shift_priorities_align_with_tones(self):
        """Activity types in auto-shift have corresponding tone mappings."""
        from apps.cos.services.auto_shift_service import ACTIVITY_PRIORITY

        tone_defaults = CosToneService.get_activity_tone_defaults()
        for activity_type in ACTIVITY_PRIORITY:
            self.assertIn(
                activity_type, tone_defaults,
                f"Priority type '{activity_type}' has no tone mapping",
            )

    def test_reflection_sentiment_informs_tone_selection(self):
        """Negative sentiment correctly maps to empathetic tone."""
        tone_svc = CosToneService(self.user)
        midday = timezone.now().replace(hour=12, minute=0)

        # Negative context
        tone = tone_svc.select_tone(
            activity_type="workout",
            reference_time=midday,
            sentiment_context={"recent_sentiment": "negative", "streak_days": 3},
        )
        self.assertEqual(tone, "empathetic")

        # Positive context
        tone = tone_svc.select_tone(
            activity_type="workout",
            reference_time=midday,
            sentiment_context={"recent_sentiment": "positive", "streak_days": 5},
        )
        self.assertEqual(tone, "celebratory")
