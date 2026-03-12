"""Tests for CelebrationDetectionService."""

from datetime import timedelta

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.dashboard_v2.models import PreparedCelebration
from apps.dashboard_v2.services.celebration_service import (
    COOLDOWNS,
    CelebrationDetectionService,
)
from apps.users.models import TermsAcceptance, User


class CelebrationDetectionServiceTest(TestCase):
    """Tests for celebration detection."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="celebrate@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

    def test_get_ready_celebration_none(self):
        """Returns None when no celebrations exist."""
        service = CelebrationDetectionService(self.user)
        self.assertIsNone(service.get_ready_celebration())

    def test_get_ready_celebration_exists(self):
        """Returns the ready celebration when one exists."""
        PreparedCelebration.objects.create(
            user=self.user,
            celebration_type="streak_milestone",
            celebration_status="ready",
            headline="7-Day Streak!",
            narrative="Great job.",
            expires_at=timezone.now() + timedelta(days=7),
            dedupe_key="test:streak:1:7",
        )

        service = CelebrationDetectionService(self.user)
        result = service.get_ready_celebration()
        self.assertIsNotNone(result)
        self.assertEqual(result.headline, "7-Day Streak!")

    def test_get_ready_celebration_expired(self):
        """Expired celebrations are not returned."""
        PreparedCelebration.objects.create(
            user=self.user,
            celebration_type="streak_milestone",
            celebration_status="ready",
            headline="Old Streak",
            narrative="Expired.",
            expires_at=timezone.now() - timedelta(hours=1),
            dedupe_key="test:expired",
        )

        service = CelebrationDetectionService(self.user)
        self.assertIsNone(service.get_ready_celebration())

    def test_cooldown_prevents_duplicate(self):
        """Cooldown period prevents duplicate celebrations."""
        # Create a recent celebration
        PreparedCelebration.objects.create(
            user=self.user,
            celebration_type="streak_milestone",
            celebration_status="ready",
            headline="Recent Streak",
            narrative="Still fresh.",
            generated_at=timezone.now() - timedelta(days=3),
            expires_at=timezone.now() + timedelta(days=4),
            dedupe_key="test:recent",
        )

        service = CelebrationDetectionService(self.user)
        self.assertTrue(service._is_in_cooldown("streak_milestone", "test:new"))

    def test_cooldown_expired(self):
        """Past cooldown period allows new celebrations."""
        PreparedCelebration.objects.create(
            user=self.user,
            celebration_type="streak_milestone",
            celebration_status="ready",
            headline="Old Streak",
            narrative="Past cooldown.",
            generated_at=timezone.now() - timedelta(days=10),
            expires_at=timezone.now() - timedelta(days=3),
            dedupe_key="test:old",
        )

        service = CelebrationDetectionService(self.user)
        self.assertFalse(service._is_in_cooldown("streak_milestone", "test:new"))

    def test_store_best_expires_old_ready(self):
        """Storing a new celebration expires any existing ready ones."""
        old = PreparedCelebration.objects.create(
            user=self.user,
            celebration_type="weekly_discipline",
            celebration_status="ready",
            headline="Old One",
            narrative="To be replaced.",
            expires_at=timezone.now() + timedelta(days=5),
            dedupe_key="test:old:disc",
        )

        service = CelebrationDetectionService(self.user)
        service._store_best([{
            "type": "goal_milestone",
            "dedupe_key": "test:new:milestone",
            "domain": "health",
            "related_goal": None,
            "headline": "New Milestone!",
            "narrative": "You did it.",
            "evidence": {"milestone_id": 1},
        }])

        old.refresh_from_db()
        self.assertEqual(old.celebration_status, "expired")

        new = PreparedCelebration.objects.filter(celebration_status="ready").first()
        self.assertIsNotNone(new)
        self.assertEqual(new.headline, "New Milestone!")

    def test_reveal_celebration(self):
        """Revealing a celebration sets status and revealed_at."""
        celebration = PreparedCelebration.objects.create(
            user=self.user,
            celebration_type="streak_milestone",
            celebration_status="ready",
            headline="Test",
            narrative="Test.",
            expires_at=timezone.now() + timedelta(days=7),
            dedupe_key="test:reveal",
        )

        celebration.reveal()
        celebration.refresh_from_db()
        self.assertEqual(celebration.celebration_status, "revealed")
        self.assertIsNotNone(celebration.revealed_at)

    def test_dismiss_celebration(self):
        """Dismissing a celebration sets status to dismissed."""
        celebration = PreparedCelebration.objects.create(
            user=self.user,
            celebration_type="streak_milestone",
            celebration_status="ready",
            headline="Test",
            narrative="Test.",
            expires_at=timezone.now() + timedelta(days=7),
            dedupe_key="test:dismiss",
        )

        celebration.dismiss()
        celebration.refresh_from_db()
        self.assertEqual(celebration.celebration_status, "dismissed")
