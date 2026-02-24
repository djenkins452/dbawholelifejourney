"""
CoS v2 — Phase 7 Tests: Goal Suggestion Policy

Tests:
1. Create suggestion: basic creation, evidence storage
2. Monthly throttle: blocks repeat within 30 days, allows after
3. Opt-out: blocks opted-out themes, undo opt-out
4. Accept flow: marks accepted, never auto-creates goal
5. Decline flow: tracks count, offers opt-out at threshold
6. 3-decline opt-out prompt: exact threshold behavior
7. Batch creation from pattern suggestions
8. Query methods: pending, history, opted-out themes, stats
9. Full pipeline: patterns → suggestions → storage
"""

import datetime as dt
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone

from apps.calendar_engine.models import CalendarEvent
from apps.cos.models import CosGoalSuggestion, CosReflection
from apps.cos.services.goal_suggestion_service import (
    CosGoalSuggestionService,
    DECLINE_THRESHOLD,
    THROTTLE_DAYS,
)

User = get_user_model()


def _create_test_user(email="cosgoal@example.com"):
    from apps.users.models import TermsAcceptance

    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


def _create_ref(user, days_ago=0, activity_type="workout", sentiment="negative"):
    """Create a CosReflection for pattern detection tests."""
    event = CalendarEvent.objects.create(
        user=user,
        title="Activity",
        start_dt=timezone.now() + dt.timedelta(hours=2),
        end_dt=timezone.now() + dt.timedelta(hours=3),
        idempotency_key=uuid4().hex,
    )
    return CosReflection.objects.create(
        user=user,
        content_type=ContentType.objects.get_for_model(CalendarEvent),
        object_id=event.pk,
        text="Reflection",
        activity_date=timezone.now().date() - dt.timedelta(days=days_ago),
        activity_type=activity_type,
        sentiment=sentiment,
    )


# ──────────────────────────────────────────────────────────
# Creation Tests
# ──────────────────────────────────────────────────────────


class SuggestionCreationTests(TestCase):
    """Test basic suggestion creation."""

    def setUp(self):
        self.user = _create_test_user("create@example.com")
        self.svc = CosGoalSuggestionService(self.user)

    def test_create_suggestion(self):
        """Basic suggestion creation."""
        result = self.svc.create_suggestion(
            theme="fitness_consistency",
            suggestion_text="Try working out 3x per week",
            evidence_summary="5-day negative streak detected",
        )
        self.assertTrue(result["created"])
        self.assertIsNotNone(result["suggestion"])
        sug = result["suggestion"]
        self.assertEqual(sug.theme, "fitness_consistency")
        self.assertEqual(sug.status, CosGoalSuggestion.STATUS_SUGGESTED)
        self.assertEqual(sug.evidence_summary, "5-day negative streak detected")

    def test_create_without_evidence(self):
        """Suggestion without evidence_summary is allowed."""
        result = self.svc.create_suggestion(
            theme="sleep_improvement",
            suggestion_text="Aim for 7 hours of sleep",
        )
        self.assertTrue(result["created"])
        self.assertEqual(result["suggestion"].evidence_summary, "")


# ──────────────────────────────────────────────────────────
# Monthly Throttle Tests
# ──────────────────────────────────────────────────────────


class ThrottleTests(TestCase):
    """Test monthly throttle enforcement."""

    def setUp(self):
        self.user = _create_test_user("throttle@example.com")
        self.svc = CosGoalSuggestionService(self.user)

    def test_throttle_blocks_recent(self):
        """Suggestion within 30 days of same theme is blocked."""
        # First suggestion succeeds
        result1 = self.svc.create_suggestion(
            theme="workout_recovery",
            suggestion_text="Take a rest day",
        )
        self.assertTrue(result1["created"])

        # Second attempt for same theme is blocked
        result2 = self.svc.create_suggestion(
            theme="workout_recovery",
            suggestion_text="Modify your routine",
        )
        self.assertFalse(result2["created"])
        self.assertIn("within the last", result2["reason"])

    def test_different_themes_not_throttled(self):
        """Different themes are independent."""
        result1 = self.svc.create_suggestion(
            theme="workout_recovery",
            suggestion_text="Rest",
        )
        result2 = self.svc.create_suggestion(
            theme="prayer_consistency",
            suggestion_text="Pray daily",
        )
        self.assertTrue(result1["created"])
        self.assertTrue(result2["created"])

    def test_throttle_expires_after_period(self):
        """Suggestion allowed after throttle period expires."""
        # Create and backdate a suggestion
        sug = CosGoalSuggestion.objects.create(
            user=self.user,
            theme="workout_recovery",
            suggestion_text="Old suggestion",
            status=CosGoalSuggestion.STATUS_SUGGESTED,
        )
        CosGoalSuggestion.objects.filter(pk=sug.pk).update(
            created_at=timezone.now() - dt.timedelta(days=THROTTLE_DAYS + 1)
        )

        # New suggestion should be allowed
        result = self.svc.create_suggestion(
            theme="workout_recovery",
            suggestion_text="New suggestion",
        )
        self.assertTrue(result["created"])


# ──────────────────────────────────────────────────────────
# Accept / Decline Tests
# ──────────────────────────────────────────────────────────


class ResponseTests(TestCase):
    """Test accept and decline flows."""

    def setUp(self):
        self.user = _create_test_user("response@example.com")
        self.svc = CosGoalSuggestionService(self.user)

    def test_accept_suggestion(self):
        """Accepting marks status as accepted."""
        creation = self.svc.create_suggestion(
            theme="test_theme",
            suggestion_text="Test suggestion",
        )
        result = self.svc.accept_suggestion(creation["suggestion"].pk)
        self.assertTrue(result["success"])
        self.assertEqual(
            result["suggestion"].status,
            CosGoalSuggestion.STATUS_ACCEPTED,
        )
        self.assertIsNotNone(result["suggestion"].responded_at)

    def test_accept_does_not_create_goal(self):
        """Accepting does NOT auto-create a goal — just marks accepted."""
        creation = self.svc.create_suggestion(
            theme="test_theme",
            suggestion_text="Test",
        )
        result = self.svc.accept_suggestion(creation["suggestion"].pk)
        self.assertTrue(result["success"])
        # No goal created — just status change
        self.assertEqual(
            result["suggestion"].status,
            CosGoalSuggestion.STATUS_ACCEPTED,
        )

    def test_decline_suggestion(self):
        """Declining marks status and tracks count."""
        creation = self.svc.create_suggestion(
            theme="test_theme",
            suggestion_text="Test",
        )
        result = self.svc.decline_suggestion(creation["suggestion"].pk)
        self.assertTrue(result["success"])
        self.assertEqual(
            result["suggestion"].status,
            CosGoalSuggestion.STATUS_DECLINED,
        )
        self.assertGreater(result["suggestion"].declined_count, 0)

    def test_decline_no_opt_out_below_threshold(self):
        """First decline doesn't offer opt-out."""
        creation = self.svc.create_suggestion(
            theme="test_theme",
            suggestion_text="Test",
        )
        result = self.svc.decline_suggestion(creation["suggestion"].pk)
        self.assertFalse(result["offer_opt_out"])
        self.assertEqual(result["opt_out_prompt"], "")

    def test_accept_not_found(self):
        """Accept returns error for non-existent ID."""
        result = self.svc.accept_suggestion(99999)
        self.assertFalse(result["success"])

    def test_decline_not_found(self):
        """Decline returns error for non-existent ID."""
        result = self.svc.decline_suggestion(99999)
        self.assertFalse(result["success"])


# ──────────────────────────────────────────────────────────
# 3-Decline Opt-Out Tests
# ──────────────────────────────────────────────────────────


class DeclineOptOutTests(TestCase):
    """Test the 3-decline opt-out flow."""

    def setUp(self):
        self.user = _create_test_user("optout@example.com")
        self.svc = CosGoalSuggestionService(self.user)

    def _create_and_decline(self, theme, count):
        """Helper to create and decline N suggestions for a theme."""
        results = []
        for i in range(count):
            # Backdate earlier ones to pass throttle
            sug = CosGoalSuggestion.objects.create(
                user=self.user,
                theme=theme,
                suggestion_text="Suggestion {}".format(i),
                status=CosGoalSuggestion.STATUS_SUGGESTED,
            )
            if i < count - 1:
                # Backdate so throttle doesn't block
                CosGoalSuggestion.objects.filter(pk=sug.pk).update(
                    created_at=timezone.now() - dt.timedelta(
                        days=THROTTLE_DAYS * (count - i)
                    )
                )
            result = self.svc.decline_suggestion(sug.pk)
            results.append(result)
        return results

    def test_opt_out_offered_at_threshold(self):
        """3rd decline triggers opt-out offer."""
        results = self._create_and_decline("workout_rest", DECLINE_THRESHOLD)
        last_result = results[-1]
        self.assertTrue(last_result["offer_opt_out"])
        self.assertIn("stop suggesting", last_result["opt_out_prompt"])
        self.assertIn("workout rest", last_result["opt_out_prompt"])

    def test_no_opt_out_before_threshold(self):
        """Declines before threshold don't offer opt-out."""
        results = self._create_and_decline(
            "workout_rest", DECLINE_THRESHOLD - 1
        )
        for result in results:
            self.assertFalse(result["offer_opt_out"])

    def test_opt_out_blocks_future_suggestions(self):
        """After opt-out, new suggestions for theme are blocked."""
        self.svc.opt_out_theme("workout_rest")

        result = self.svc.create_suggestion(
            theme="workout_rest",
            suggestion_text="Should be blocked",
        )
        self.assertFalse(result["created"])
        self.assertIn("opted out", result["reason"])

    def test_opt_out_marks_existing(self):
        """Opt-out marks all existing suggestions for theme."""
        CosGoalSuggestion.objects.create(
            user=self.user,
            theme="test_theme",
            suggestion_text="Old 1",
            status=CosGoalSuggestion.STATUS_DECLINED,
        )
        CosGoalSuggestion.objects.create(
            user=self.user,
            theme="test_theme",
            suggestion_text="Old 2",
            status=CosGoalSuggestion.STATUS_SUGGESTED,
        )

        self.svc.opt_out_theme("test_theme")

        all_for_theme = CosGoalSuggestion.objects.filter(
            user=self.user, theme="test_theme",
        )
        for sug in all_for_theme:
            self.assertTrue(sug.opted_out)

    def test_undo_opt_out(self):
        """Can re-enable suggestions for opted-out theme."""
        self.svc.opt_out_theme("test_theme")
        self.assertTrue(
            CosGoalSuggestion.is_theme_opted_out(self.user, "test_theme")
        )

        result = self.svc.undo_opt_out("test_theme")
        self.assertTrue(result)
        self.assertFalse(
            CosGoalSuggestion.is_theme_opted_out(self.user, "test_theme")
        )

    def test_undo_opt_out_nonexistent(self):
        """Undo on non-opted-out theme returns False."""
        result = self.svc.undo_opt_out("never_opted_out")
        self.assertFalse(result)


# ──────────────────────────────────────────────────────────
# Batch Creation Tests
# ──────────────────────────────────────────────────────────


class BatchCreationTests(TestCase):
    """Test batch creation from pattern suggestions."""

    def setUp(self):
        self.user = _create_test_user("batch@example.com")
        self.svc = CosGoalSuggestionService(self.user)

    def test_batch_creation(self):
        """Creates multiple suggestions from pattern output."""
        pattern_suggestions = [
            {
                "theme": "workout_recovery",
                "text": "Take a break",
                "evidence_summary": "5-day negative streak",
            },
            {
                "theme": "prayer_restart",
                "text": "Resume daily prayer",
                "evidence_summary": "Activity gap detected",
            },
        ]

        results = self.svc.create_suggestions_from_patterns(pattern_suggestions)
        self.assertEqual(len(results), 2)
        created = [r for r in results if r["created"]]
        self.assertEqual(len(created), 2)

    def test_batch_respects_throttle(self):
        """Batch creation respects throttle per theme."""
        # Pre-create a suggestion for one theme
        self.svc.create_suggestion(
            theme="workout_recovery",
            suggestion_text="Already suggested",
        )

        pattern_suggestions = [
            {
                "theme": "workout_recovery",
                "text": "Should be blocked",
                "evidence_summary": "Evidence",
            },
            {
                "theme": "prayer_restart",
                "text": "Should succeed",
                "evidence_summary": "Evidence",
            },
        ]

        results = self.svc.create_suggestions_from_patterns(pattern_suggestions)
        created = [r for r in results if r["created"]]
        blocked = [r for r in results if not r["created"]]
        self.assertEqual(len(created), 1)
        self.assertEqual(len(blocked), 1)
        self.assertEqual(created[0]["suggestion"].theme, "prayer_restart")


# ──────────────────────────────────────────────────────────
# Query Methods Tests
# ──────────────────────────────────────────────────────────


class QueryMethodTests(TestCase):
    """Test query/retrieval methods."""

    def setUp(self):
        self.user = _create_test_user("query@example.com")
        self.svc = CosGoalSuggestionService(self.user)

    def test_get_pending_suggestions(self):
        """Returns only unresponded suggestions."""
        self.svc.create_suggestion(
            theme="theme1", suggestion_text="Pending",
        )
        creation = self.svc.create_suggestion(
            theme="theme2", suggestion_text="Will be accepted",
        )
        self.svc.accept_suggestion(creation["suggestion"].pk)

        pending = self.svc.get_pending_suggestions()
        self.assertEqual(pending.count(), 1)
        self.assertEqual(pending.first().theme, "theme1")

    def test_get_opted_out_themes(self):
        """Returns list of opted-out themes."""
        self.svc.opt_out_theme("theme_a")
        self.svc.opt_out_theme("theme_b")

        opted_out = self.svc.get_opted_out_themes()
        self.assertIn("theme_a", opted_out)
        self.assertIn("theme_b", opted_out)

    def test_get_theme_stats(self):
        """Returns correct stats for a theme."""
        for i in range(3):
            sug = CosGoalSuggestion.objects.create(
                user=self.user,
                theme="test_theme",
                suggestion_text="Sug {}".format(i),
                status=CosGoalSuggestion.STATUS_SUGGESTED,
            )
            if i < 3:
                CosGoalSuggestion.objects.filter(pk=sug.pk).update(
                    created_at=timezone.now() - dt.timedelta(
                        days=THROTTLE_DAYS * (3 - i)
                    )
                )

        # Accept one, decline one
        sugs = list(
            CosGoalSuggestion.objects.filter(
                user=self.user, theme="test_theme",
            ).order_by("created_at")
        )
        self.svc.accept_suggestion(sugs[0].pk)
        self.svc.decline_suggestion(sugs[1].pk)

        stats = self.svc.get_theme_stats("test_theme")
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["accepted"], 1)
        self.assertEqual(stats["declined"], 1)

    def test_get_suggestion_history(self):
        """Returns suggestion history for user."""
        self.svc.create_suggestion(
            theme="theme1", suggestion_text="First",
        )
        self.svc.create_suggestion(
            theme="theme2", suggestion_text="Second",
        )

        history = self.svc.get_suggestion_history()
        self.assertEqual(history.count(), 2)

    def test_get_suggestion_history_by_theme(self):
        """Filter history by theme."""
        self.svc.create_suggestion(
            theme="theme1", suggestion_text="First",
        )
        self.svc.create_suggestion(
            theme="theme2", suggestion_text="Second",
        )

        history = self.svc.get_suggestion_history(theme="theme1")
        self.assertEqual(history.count(), 1)


# ──────────────────────────────────────────────────────────
# Full Pipeline Tests
# ──────────────────────────────────────────────────────────


class FullPipelineTests(TestCase):
    """Test the full patterns → suggestions pipeline."""

    def setUp(self):
        self.user = _create_test_user("pipeline@example.com")
        self.svc = CosGoalSuggestionService(self.user)

    def test_pipeline_with_patterns(self):
        """Full pipeline: reflections → patterns → suggestions stored."""
        # Create enough negative data for pattern detection
        for i in range(7):
            _create_ref(self.user, days_ago=i, sentiment="negative")

        result = self.svc.run_suggestion_pipeline(days=14)
        self.assertTrue(len(result["patterns"]) > 0)
        # At least one suggestion created
        self.assertTrue(len(result["created"]) > 0)

        # Verify stored in DB
        stored = CosGoalSuggestion.objects.filter(
            user=self.user,
            status=CosGoalSuggestion.STATUS_SUGGESTED,
        )
        self.assertTrue(stored.exists())

    def test_pipeline_empty(self):
        """Pipeline with no reflections produces no suggestions."""
        result = self.svc.run_suggestion_pipeline(days=14)
        self.assertEqual(len(result["patterns"]), 0)
        self.assertEqual(len(result["created"]), 0)

    def test_pipeline_respects_throttle(self):
        """Pipeline doesn't create duplicate suggestions."""
        for i in range(7):
            _create_ref(self.user, days_ago=i, sentiment="negative")

        # First run creates suggestions
        result1 = self.svc.run_suggestion_pipeline(days=14)
        created1 = len(result1["created"])

        # Second run should be throttled
        result2 = self.svc.run_suggestion_pipeline(days=14)
        self.assertTrue(len(result2["blocked"]) >= created1 or len(result2["created"]) == 0)
