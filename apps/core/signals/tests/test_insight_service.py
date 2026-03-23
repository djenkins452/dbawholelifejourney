"""Tests for Phase 5 Signal Insight Service.

Covers:
1. Correct categorization (reinforced/suppressed/neutral)
2. 30-day filter applied
3. Ratios correct
4. Empty state handled
"""

from datetime import timedelta

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.core.signals.insight_service import get_signal_insights
from apps.core.signals.models import SignalFeedback
from apps.core.signals.signal_presenter import FEEDBACK_WINDOW_DAYS
from apps.users.models import TermsAcceptance, User


class TestSignalInsightService(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="insight@example.com", password="testpass123",
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )

    def _create_feedback(self, domain="faith", item="prayer", response="yes",
                         created_at=None):
        fb = SignalFeedback.objects.create(
            user=self.user,
            signal_type="possible_completion",
            domain=domain,
            item=item,
            fingerprint=f"test:{domain}:{item}",
            response=response,
            source="journal",
        )
        if created_at:
            # Update created_at after creation (auto_now_add)
            SignalFeedback.objects.filter(pk=fb.pk).update(created_at=created_at)
        return fb

    # -- Empty state --

    def test_empty_when_no_feedback(self):
        result = get_signal_insights(self.user)
        self.assertEqual(result["reinforced"], [])
        self.assertEqual(result["suppressed"], [])
        self.assertEqual(result["neutral"], [])

    # -- Reinforcement --

    def test_reinforced_categorization(self):
        """3 yes, 0 no → reinforced."""
        for _ in range(3):
            self._create_feedback(response="yes")

        result = get_signal_insights(self.user)
        self.assertEqual(len(result["reinforced"]), 1)
        self.assertEqual(result["reinforced"][0]["domain"], "faith")
        self.assertEqual(result["reinforced"][0]["yes"], 3)
        self.assertEqual(result["reinforced"][0]["no"], 0)

    def test_reinforced_ratio_correct(self):
        """4 yes, 1 no → ratio 0.8."""
        for _ in range(4):
            self._create_feedback(response="yes")
        self._create_feedback(response="no")

        result = get_signal_insights(self.user)
        self.assertEqual(len(result["reinforced"]), 1)
        self.assertEqual(result["reinforced"][0]["ratio"], 0.8)

    # -- Suppression --

    def test_suppressed_categorization(self):
        """0 yes, 3 no → suppressed."""
        for _ in range(3):
            self._create_feedback(response="no")

        result = get_signal_insights(self.user)
        self.assertEqual(len(result["suppressed"]), 1)
        self.assertEqual(result["suppressed"][0]["no"], 3)

    # -- Neutral --

    def test_neutral_mixed_feedback(self):
        """2 yes, 2 no → neutral."""
        for _ in range(2):
            self._create_feedback(response="yes")
        for _ in range(2):
            self._create_feedback(response="no")

        result = get_signal_insights(self.user)
        self.assertEqual(len(result["neutral"]), 1)

    def test_neutral_insufficient_data(self):
        """1 yes → neutral (below threshold)."""
        self._create_feedback(response="yes")

        result = get_signal_insights(self.user)
        self.assertEqual(len(result["neutral"]), 1)
        self.assertEqual(len(result["reinforced"]), 0)

    # -- 30-day filter --

    def test_old_feedback_excluded(self):
        """Feedback older than 30 days should not appear."""
        old_date = timezone.now() - timedelta(days=FEEDBACK_WINDOW_DAYS + 5)
        for _ in range(5):
            self._create_feedback(response="yes", created_at=old_date)

        result = get_signal_insights(self.user)
        self.assertEqual(result["reinforced"], [])
        self.assertEqual(result["neutral"], [])

    def test_recent_feedback_included(self):
        """Feedback within 30 days should appear."""
        recent_date = timezone.now() - timedelta(days=FEEDBACK_WINDOW_DAYS - 1)
        for _ in range(3):
            self._create_feedback(response="yes", created_at=recent_date)

        result = get_signal_insights(self.user)
        self.assertEqual(len(result["reinforced"]), 1)

    # -- Multiple domains --

    def test_multiple_domains_categorized_independently(self):
        """Each domain+item is categorized independently."""
        # Faith/prayer → reinforced
        for _ in range(3):
            self._create_feedback(domain="faith", item="prayer", response="yes")
        # Health/workout → suppressed
        for _ in range(3):
            self._create_feedback(domain="health", item="workout", response="no")

        result = get_signal_insights(self.user)
        self.assertEqual(len(result["reinforced"]), 1)
        self.assertEqual(result["reinforced"][0]["domain"], "faith")
        self.assertEqual(len(result["suppressed"]), 1)
        self.assertEqual(result["suppressed"][0]["domain"], "health")

    # -- Label --

    def test_label_uses_item_labels(self):
        for _ in range(3):
            self._create_feedback(domain="faith", item="bible_reading", response="yes")

        result = get_signal_insights(self.user)
        self.assertEqual(result["reinforced"][0]["label"], "Bible reading")
