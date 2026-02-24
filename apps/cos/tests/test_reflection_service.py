"""
CoS v2 — Phase 5 Tests: Reflection Storage + Retrieval

Tests:
1. CRUD: create, get, update, delete reflections
2. Auto-sentiment detection from text
3. Entity retrieval: reflections attached to specific entities
4. Date-based retrieval: specific date, date range, recent
5. Activity type retrieval: by type, active types
6. Temporal comparisons: yesterday vs today, this week vs last
7. Streak detection: consecutive-day reflections
8. Sentiment trends: trend direction over time
9. Contextual prompt enrichment: build_contextual_prompt_prefix
10. SLCME integration: store/retrieve context snapshots
11. Reflection stats: summary statistics
"""

import datetime as dt
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone

from apps.calendar_engine.models import CalendarEvent
from apps.cos.models import CosReflection
from apps.cos.services.reflection_service import (
    CosReflectionService,
    detect_sentiment,
)

User = get_user_model()


def _create_test_user(email="cosrefl@example.com"):
    from apps.users.models import TermsAcceptance

    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


def _create_event(user, title, days_offset=0, hours=1):
    """Create a calendar event offset from today."""
    start = timezone.now() + dt.timedelta(days=days_offset, hours=2)
    end = start + dt.timedelta(hours=hours)
    return CalendarEvent.objects.create(
        user=user,
        title=title,
        start_dt=start,
        end_dt=end,
        idempotency_key=uuid4().hex,
    )


# ──────────────────────────────────────────────────────────
# Sentiment Detection Tests
# ──────────────────────────────────────────────────────────


class SentimentDetectionTests(TestCase):
    """Test keyword-based sentiment detection."""

    def test_positive_text(self):
        self.assertEqual(detect_sentiment("It was a great workout, felt amazing!"), "positive")

    def test_negative_text(self):
        self.assertEqual(detect_sentiment("Struggled through the whole thing, terrible day"), "negative")

    def test_neutral_text(self):
        self.assertEqual(detect_sentiment("Went to the gym today"), "neutral")

    def test_mixed_text(self):
        self.assertEqual(detect_sentiment("It was a great start but ended terribly"), "mixed")

    def test_empty_text(self):
        self.assertEqual(detect_sentiment(""), "neutral")

    def test_none_text(self):
        self.assertEqual(detect_sentiment(None), "neutral")


# ──────────────────────────────────────────────────────────
# CRUD Tests
# ──────────────────────────────────────────────────────────


class ReflectionCRUDTests(TestCase):
    """Test basic CRUD operations for reflections."""

    def setUp(self):
        self.user = _create_test_user("crud@example.com")
        self.svc = CosReflectionService(self.user)
        self.event = _create_event(self.user, "Morning Workout")

    def test_create_reflection(self):
        """Create a reflection attached to an entity."""
        ref = self.svc.create_reflection(
            source_entity=self.event,
            text="Great workout today!",
            activity_type="workout",
        )
        self.assertIsNotNone(ref.pk)
        self.assertEqual(ref.user, self.user)
        self.assertEqual(ref.text, "Great workout today!")
        self.assertEqual(ref.activity_type, "workout")
        self.assertEqual(ref.object_id, self.event.pk)

    def test_create_auto_detects_date(self):
        """Activity date auto-detected from entity start_dt."""
        ref = self.svc.create_reflection(
            source_entity=self.event,
            text="Good session",
            activity_type="workout",
        )
        self.assertEqual(ref.activity_date, self.event.start_dt.date())

    def test_create_auto_detects_sentiment(self):
        """Sentiment auto-detected from text."""
        ref = self.svc.create_reflection(
            source_entity=self.event,
            text="Amazing, felt really strong and proud!",
            activity_type="workout",
        )
        self.assertEqual(ref.sentiment, "positive")

    def test_create_explicit_sentiment_overrides(self):
        """Explicit sentiment overrides auto-detection."""
        ref = self.svc.create_reflection(
            source_entity=self.event,
            text="Amazing day",
            activity_type="workout",
            sentiment="neutral",
        )
        self.assertEqual(ref.sentiment, "neutral")

    def test_create_no_auto_sentiment(self):
        """auto_sentiment=False skips detection."""
        ref = self.svc.create_reflection(
            source_entity=self.event,
            text="Great workout",
            activity_type="workout",
            auto_sentiment=False,
        )
        self.assertEqual(ref.sentiment, "")

    def test_get_reflection(self):
        """Retrieve a reflection by ID."""
        ref = self.svc.create_reflection(
            source_entity=self.event,
            text="Good",
            activity_type="workout",
        )
        found = self.svc.get_reflection(ref.pk)
        self.assertEqual(found.pk, ref.pk)

    def test_get_reflection_wrong_user(self):
        """Cannot get another user's reflection."""
        ref = self.svc.create_reflection(
            source_entity=self.event,
            text="Good",
            activity_type="workout",
        )
        other = _create_test_user("other@example.com")
        other_svc = CosReflectionService(other)
        self.assertIsNone(other_svc.get_reflection(ref.pk))

    def test_get_reflection_not_found(self):
        """Returns None for non-existent ID."""
        self.assertIsNone(self.svc.get_reflection(99999))

    def test_update_reflection_text(self):
        """Update reflection text re-detects sentiment."""
        ref = self.svc.create_reflection(
            source_entity=self.event,
            text="Okay session",
            activity_type="workout",
        )
        updated = self.svc.update_reflection(ref.pk, text="Actually it was amazing!")
        self.assertEqual(updated.text, "Actually it was amazing!")
        self.assertEqual(updated.sentiment, "positive")

    def test_update_reflection_sentiment_only(self):
        """Update just sentiment without changing text."""
        ref = self.svc.create_reflection(
            source_entity=self.event,
            text="Good",
            activity_type="workout",
        )
        updated = self.svc.update_reflection(ref.pk, sentiment="negative")
        self.assertEqual(updated.sentiment, "negative")
        self.assertEqual(updated.text, "Good")

    def test_update_not_found(self):
        """Update returns None for non-existent ID."""
        self.assertIsNone(self.svc.update_reflection(99999, text="Nope"))

    def test_delete_reflection(self):
        """Delete a reflection."""
        ref = self.svc.create_reflection(
            source_entity=self.event,
            text="Gone",
            activity_type="workout",
        )
        self.assertTrue(self.svc.delete_reflection(ref.pk))
        self.assertIsNone(self.svc.get_reflection(ref.pk))

    def test_delete_not_found(self):
        """Delete returns False for non-existent ID."""
        self.assertFalse(self.svc.delete_reflection(99999))


# ──────────────────────────────────────────────────────────
# Entity Retrieval Tests
# ──────────────────────────────────────────────────────────


class EntityRetrievalTests(TestCase):
    """Test retrieving reflections by entity."""

    def setUp(self):
        self.user = _create_test_user("entity@example.com")
        self.svc = CosReflectionService(self.user)

    def test_get_reflections_for_entity(self):
        """Get all reflections attached to a specific entity."""
        event = _create_event(self.user, "Workout")
        self.svc.create_reflection(
            source_entity=event, text="First", activity_type="workout",
        )
        self.svc.create_reflection(
            source_entity=event, text="Second", activity_type="workout",
        )
        refs = self.svc.get_reflections_for_entity(event)
        self.assertEqual(refs.count(), 2)

    def test_entity_scoped_to_user(self):
        """Reflections are scoped to the current user."""
        event = _create_event(self.user, "Meeting")
        self.svc.create_reflection(
            source_entity=event, text="Mine", activity_type="meeting",
        )
        other = _create_test_user("other2@example.com")
        other_svc = CosReflectionService(other)
        refs = other_svc.get_reflections_for_entity(event)
        self.assertEqual(refs.count(), 0)


# ──────────────────────────────────────────────────────────
# Date-Based Retrieval Tests
# ──────────────────────────────────────────────────────────


class DateRetrievalTests(TestCase):
    """Test date-based retrieval methods."""

    def setUp(self):
        self.user = _create_test_user("dates@example.com")
        self.svc = CosReflectionService(self.user)
        self.today = timezone.now().date()

    def _create_ref_on_date(self, date, text="Reflection", activity_type="workout"):
        """Helper to create a reflection on a specific date."""
        event = _create_event(self.user, "Activity")
        return CosReflection.objects.create(
            user=self.user,
            content_type=ContentType.objects.get_for_model(CalendarEvent),
            object_id=event.pk,
            text=text,
            activity_date=date,
            activity_type=activity_type,
            sentiment=detect_sentiment(text),
        )

    def test_get_reflections_for_date(self):
        """Get reflections for a specific date."""
        self._create_ref_on_date(self.today, "Today's reflection")
        self._create_ref_on_date(self.today - dt.timedelta(days=1), "Yesterday")
        refs = self.svc.get_reflections_for_date(self.today)
        self.assertEqual(refs.count(), 1)
        self.assertEqual(refs.first().text, "Today's reflection")

    def test_get_reflections_for_date_range(self):
        """Get reflections within a date range."""
        for i in range(5):
            self._create_ref_on_date(self.today - dt.timedelta(days=i))
        refs = self.svc.get_reflections_for_date_range(
            self.today - dt.timedelta(days=2), self.today,
        )
        self.assertEqual(refs.count(), 3)

    def test_get_recent_reflections(self):
        """Get recent reflections within last N days."""
        for i in range(10):
            self._create_ref_on_date(self.today - dt.timedelta(days=i))
        refs = self.svc.get_recent_reflections(days=5, limit=20)
        # Days 0-5 = 6 days of reflections
        self.assertEqual(len(refs), 6)

    def test_get_recent_respects_limit(self):
        """Limit parameter caps results."""
        for i in range(10):
            self._create_ref_on_date(self.today - dt.timedelta(days=i))
        refs = self.svc.get_recent_reflections(days=30, limit=3)
        self.assertEqual(len(refs), 3)


# ──────────────────────────────────────────────────────────
# Activity Type Retrieval Tests
# ──────────────────────────────────────────────────────────


class TypeRetrievalTests(TestCase):
    """Test activity-type-based retrieval."""

    def setUp(self):
        self.user = _create_test_user("types@example.com")
        self.svc = CosReflectionService(self.user)
        self.today = timezone.now().date()

    def _create_ref(self, activity_type, text="Reflection"):
        event = _create_event(self.user, "Activity")
        return CosReflection.objects.create(
            user=self.user,
            content_type=ContentType.objects.get_for_model(CalendarEvent),
            object_id=event.pk,
            text=text,
            activity_date=self.today,
            activity_type=activity_type,
        )

    def test_get_reflections_by_type(self):
        """Filter reflections by activity type."""
        self._create_ref("workout")
        self._create_ref("workout")
        self._create_ref("meeting")
        refs = self.svc.get_reflections_by_type("workout")
        self.assertEqual(len(refs), 2)

    def test_get_active_types(self):
        """Get active activity types with counts."""
        self._create_ref("workout")
        self._create_ref("workout")
        self._create_ref("meeting")
        types = self.svc.get_active_types(days=7)
        self.assertEqual(len(types), 2)
        # Most common first
        self.assertEqual(types[0], ("workout", 2))
        self.assertEqual(types[1], ("meeting", 1))


# ──────────────────────────────────────────────────────────
# Temporal Comparison Tests
# ──────────────────────────────────────────────────────────


class TemporalComparisonTests(TestCase):
    """Test yesterday vs today and week comparisons."""

    def setUp(self):
        self.user = _create_test_user("temporal@example.com")
        self.svc = CosReflectionService(self.user)
        self.today = timezone.now().date()
        self.yesterday = self.today - dt.timedelta(days=1)

    def _create_ref_on_date(self, date, text="Reflection", sentiment=""):
        event = _create_event(self.user, "Activity")
        if not sentiment:
            sentiment = detect_sentiment(text)
        return CosReflection.objects.create(
            user=self.user,
            content_type=ContentType.objects.get_for_model(CalendarEvent),
            object_id=event.pk,
            text=text,
            activity_date=date,
            activity_type="workout",
            sentiment=sentiment,
        )

    def test_yesterday_vs_today_basic(self):
        """Returns yesterday and today reflections."""
        self._create_ref_on_date(self.yesterday, "Tough day", "negative")
        self._create_ref_on_date(self.today, "Better today!", "positive")

        result = self.svc.get_yesterday_vs_today()
        self.assertEqual(len(result["yesterday"]), 1)
        self.assertEqual(len(result["today"]), 1)
        self.assertEqual(result["yesterday_sentiment"], "negative")
        self.assertEqual(result["today_sentiment"], "positive")

    def test_yesterday_vs_today_empty(self):
        """Handles no reflections gracefully."""
        result = self.svc.get_yesterday_vs_today()
        self.assertEqual(len(result["yesterday"]), 0)
        self.assertEqual(len(result["today"]), 0)
        self.assertEqual(result["yesterday_sentiment"], "no_data")
        self.assertEqual(result["today_sentiment"], "no_data")

    def test_this_week_vs_last_week(self):
        """Returns this week and last week reflections."""
        week_start = self.today - dt.timedelta(days=self.today.weekday())
        last_week_day = week_start - dt.timedelta(days=3)

        self._create_ref_on_date(last_week_day, "Last week was great", "positive")
        self._create_ref_on_date(self.today, "This week so far", "neutral")

        result = self.svc.get_this_week_vs_last_week()
        self.assertEqual(len(result["this_week"]), 1)
        self.assertEqual(len(result["last_week"]), 1)
        self.assertIn("this_week_types", result)
        self.assertIn("last_week_types", result)


# ──────────────────────────────────────────────────────────
# Streak Detection Tests
# ──────────────────────────────────────────────────────────


class StreakDetectionTests(TestCase):
    """Test consecutive-day streak detection."""

    def setUp(self):
        self.user = _create_test_user("streak@example.com")
        self.svc = CosReflectionService(self.user)
        self.today = timezone.now().date()

    def _create_ref_on_date(self, date):
        event = _create_event(self.user, "Workout")
        return CosReflection.objects.create(
            user=self.user,
            content_type=ContentType.objects.get_for_model(CalendarEvent),
            object_id=event.pk,
            text="Workout done",
            activity_date=date,
            activity_type="workout",
            sentiment="positive",
        )

    def test_current_streak(self):
        """Detects a current streak ending today."""
        for i in range(5):
            self._create_ref_on_date(self.today - dt.timedelta(days=i))

        result = self.svc.get_streak_reflections("workout")
        self.assertEqual(result["streak_length"], 5)

    def test_streak_from_yesterday(self):
        """Streak starting from yesterday (haven't reflected today yet)."""
        for i in range(3):
            self._create_ref_on_date(self.today - dt.timedelta(days=1+i))

        result = self.svc.get_streak_reflections("workout")
        self.assertEqual(result["streak_length"], 3)

    def test_no_streak(self):
        """No streak when no reflections exist."""
        result = self.svc.get_streak_reflections("workout")
        self.assertEqual(result["streak_length"], 0)

    def test_broken_streak(self):
        """Streak breaks on gap days."""
        # Today and yesterday (streak=2), then gap, then 3 days ago
        self._create_ref_on_date(self.today)
        self._create_ref_on_date(self.today - dt.timedelta(days=1))
        # Skip day 2
        self._create_ref_on_date(self.today - dt.timedelta(days=3))

        result = self.svc.get_streak_reflections("workout")
        self.assertEqual(result["streak_length"], 2)


# ──────────────────────────────────────────────────────────
# Sentiment Trend Tests
# ──────────────────────────────────────────────────────────


class SentimentTrendTests(TestCase):
    """Test sentiment trend analysis."""

    def setUp(self):
        self.user = _create_test_user("trend@example.com")
        self.svc = CosReflectionService(self.user)
        self.today = timezone.now().date()

    def _create_ref(self, days_ago, sentiment):
        event = _create_event(self.user, "Activity")
        return CosReflection.objects.create(
            user=self.user,
            content_type=ContentType.objects.get_for_model(CalendarEvent),
            object_id=event.pk,
            text="Reflection",
            activity_date=self.today - dt.timedelta(days=days_ago),
            activity_type="workout",
            sentiment=sentiment,
        )

    def test_improving_trend(self):
        """Detects improving sentiment trend."""
        # Old: negative, Recent: positive
        for i in range(10, 6, -1):
            self._create_ref(i, "negative")
        for i in range(4, 0, -1):
            self._create_ref(i, "positive")

        result = self.svc.get_sentiment_trend("workout", days=14)
        self.assertEqual(result["trend"], "improving")

    def test_declining_trend(self):
        """Detects declining sentiment trend."""
        # Old: positive, Recent: negative
        for i in range(10, 6, -1):
            self._create_ref(i, "positive")
        for i in range(4, 0, -1):
            self._create_ref(i, "negative")

        result = self.svc.get_sentiment_trend("workout", days=14)
        self.assertEqual(result["trend"], "declining")

    def test_stable_trend(self):
        """Detects stable sentiment (all neutral)."""
        for i in range(8):
            self._create_ref(i, "neutral")

        result = self.svc.get_sentiment_trend("workout", days=14)
        self.assertEqual(result["trend"], "stable")

    def test_no_data(self):
        """Returns no_data when no reflections."""
        result = self.svc.get_sentiment_trend("workout")
        self.assertEqual(result["trend"], "no_data")
        self.assertEqual(result["total"], 0)

    def test_distribution(self):
        """Returns correct sentiment distribution."""
        self._create_ref(1, "positive")
        self._create_ref(2, "positive")
        self._create_ref(3, "negative")

        result = self.svc.get_sentiment_trend("workout", days=7)
        self.assertEqual(result["distribution"]["positive"], 2)
        self.assertEqual(result["distribution"]["negative"], 1)
        self.assertEqual(result["total"], 3)


# ──────────────────────────────────────────────────────────
# Contextual Prompt Enrichment Tests
# ──────────────────────────────────────────────────────────


class ContextualPromptTests(TestCase):
    """Test contextual retrieval for enriching prompts."""

    def setUp(self):
        self.user = _create_test_user("context@example.com")
        self.svc = CosReflectionService(self.user)
        self.today = timezone.now().date()
        self.yesterday = self.today - dt.timedelta(days=1)

    def _create_ref_on_date(self, date, text="Reflection", activity_type="workout"):
        event = _create_event(self.user, "Activity")
        return CosReflection.objects.create(
            user=self.user,
            content_type=ContentType.objects.get_for_model(CalendarEvent),
            object_id=event.pk,
            text=text,
            activity_date=date,
            activity_type=activity_type,
            sentiment=detect_sentiment(text),
        )

    def test_context_with_yesterday_reflection(self):
        """Context includes yesterday's reflection."""
        self._create_ref_on_date(self.yesterday, "Tough workout yesterday")
        event = _create_event(self.user, "Workout")
        ctx = self.svc.get_context_for_prompt(event, activity_type="workout")
        self.assertTrue(ctx["has_context"])
        self.assertIsNotNone(ctx["yesterday_reflection"])
        self.assertIn("Tough workout", ctx["yesterday_reflection"])

    def test_context_without_yesterday(self):
        """Context still works without yesterday's reflection."""
        event = _create_event(self.user, "Workout")
        ctx = self.svc.get_context_for_prompt(event, activity_type="workout")
        self.assertIsNone(ctx["yesterday_reflection"])

    def test_context_includes_streak(self):
        """Context includes streak length."""
        for i in range(5):
            self._create_ref_on_date(self.today - dt.timedelta(days=i))
        event = _create_event(self.user, "Workout")
        ctx = self.svc.get_context_for_prompt(event, activity_type="workout")
        self.assertEqual(ctx["recent_streak"], 5)

    def test_build_contextual_prompt_prefix_with_yesterday(self):
        """Builds prefix referencing yesterday's reflection."""
        self._create_ref_on_date(self.yesterday, "Felt great and strong")
        prefix = self.svc.build_contextual_prompt_prefix("workout")
        self.assertIn("Yesterday you said", prefix)
        self.assertIn("Felt great and strong", prefix)

    def test_build_contextual_prompt_prefix_with_streak(self):
        """Builds prefix referencing a streak."""
        for i in range(5):
            self._create_ref_on_date(self.today - dt.timedelta(days=i))
        prefix = self.svc.build_contextual_prompt_prefix("workout")
        self.assertIn("5 days in a row", prefix)

    def test_build_contextual_prompt_prefix_empty(self):
        """Returns empty string when no context."""
        prefix = self.svc.build_contextual_prompt_prefix("workout")
        self.assertEqual(prefix, "")

    def test_get_related_reflections(self):
        """Get related reflections by activity type."""
        self._create_ref_on_date(self.today, "Today", "workout")
        self._create_ref_on_date(self.yesterday, "Yesterday", "workout")
        self._create_ref_on_date(self.today, "Meeting", "meeting")
        refs = self.svc.get_related_reflections("workout", days_back=7)
        self.assertEqual(len(refs), 2)


# ──────────────────────────────────────────────────────────
# SLCME Integration Tests
# ──────────────────────────────────────────────────────────


class SLCMEIntegrationTests(TestCase):
    """Test SLCME context memory integration."""

    def setUp(self):
        self.user = _create_test_user("slcme@example.com")
        self.svc = CosReflectionService(self.user)

    def test_create_stores_in_slcme(self):
        """Creating a reflection stores context in SLCME."""
        from apps.core.ai_memory.models import ContextSnapshot

        event = _create_event(self.user, "Workout")
        self.svc.create_reflection(
            source_entity=event,
            text="Great workout!",
            activity_type="workout",
        )

        snapshots = ContextSnapshot.objects.filter(
            user=self.user,
            context_type="cos_reflection",
        )
        self.assertEqual(snapshots.count(), 1)
        snap = snapshots.first()
        self.assertIn("Great workout!", snap.metadata["text"])
        self.assertEqual(snap.metadata["sentiment"], "positive")

    def test_get_reflection_memory(self):
        """Retrieve SLCME-stored reflection memory."""
        event = _create_event(self.user, "Workout")
        self.svc.create_reflection(
            source_entity=event,
            text="Strong session",
            activity_type="workout",
        )
        memory = self.svc.get_reflection_memory("workout")
        self.assertIsNotNone(memory)
        self.assertIn("Strong session", memory["text"])

    def test_get_reflection_memory_fallback(self):
        """Falls back to direct DB query when SLCME has no data."""
        # Create reflection without going through service (no SLCME)
        event = _create_event(self.user, "Prayer")
        CosReflection.objects.create(
            user=self.user,
            content_type=ContentType.objects.get_for_model(CalendarEvent),
            object_id=event.pk,
            text="Peaceful time",
            activity_date=timezone.now().date(),
            activity_type="prayer",
            sentiment="positive",
        )
        memory = self.svc.get_reflection_memory("prayer")
        self.assertIsNotNone(memory)
        self.assertEqual(memory["source"], "direct")
        self.assertIn("Peaceful", memory["text"])

    def test_get_reflection_memory_none(self):
        """Returns None when no reflections exist."""
        memory = self.svc.get_reflection_memory("nonexistent")
        self.assertIsNone(memory)


# ──────────────────────────────────────────────────────────
# Stats Tests
# ──────────────────────────────────────────────────────────


class ReflectionStatsTests(TestCase):
    """Test reflection summary statistics."""

    def setUp(self):
        self.user = _create_test_user("stats@example.com")
        self.svc = CosReflectionService(self.user)
        self.today = timezone.now().date()

    def _create_ref(self, days_ago=0, activity_type="workout", sentiment="positive"):
        event = _create_event(self.user, "Activity")
        return CosReflection.objects.create(
            user=self.user,
            content_type=ContentType.objects.get_for_model(CalendarEvent),
            object_id=event.pk,
            text="Reflection",
            activity_date=self.today - dt.timedelta(days=days_ago),
            activity_type=activity_type,
            sentiment=sentiment,
        )

    def test_basic_stats(self):
        """Returns correct basic stats."""
        self._create_ref(0, "workout", "positive")
        self._create_ref(1, "workout", "positive")
        self._create_ref(2, "meeting", "neutral")

        stats = self.svc.get_reflection_stats(days=7)
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["by_type"]["workout"], 2)
        self.assertEqual(stats["by_type"]["meeting"], 1)
        self.assertEqual(stats["by_sentiment"]["positive"], 2)
        self.assertEqual(stats["by_sentiment"]["neutral"], 1)

    def test_active_days(self):
        """Counts active days correctly."""
        self._create_ref(0)
        self._create_ref(0)  # Same day
        self._create_ref(1)
        self._create_ref(3)

        stats = self.svc.get_reflection_stats(days=7)
        self.assertEqual(stats["active_days"], 3)
        self.assertEqual(stats["total"], 4)

    def test_empty_stats(self):
        """Handles no reflections."""
        stats = self.svc.get_reflection_stats(days=7)
        self.assertEqual(stats["total"], 0)
        self.assertEqual(stats["active_days"], 0)
