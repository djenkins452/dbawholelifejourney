"""Tests for the HealthBriefingSnapshot persistence model."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from apps.core.health_briefing.models import HealthBriefingSnapshot
from apps.users.models import TermsAcceptance

User = get_user_model()


def _make_user(email: str = "snapshot@test.com"):
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


def _payload_stub():
    """Minimal valid JSON dict; real payload shape is exercised by C8 tests."""
    return {
        "schema_version": 1,
        "overall_status": "stable",
        "overall_confidence": 0.7,
        "risk_level": "none",
        "headline_summary": "Test snapshot.",
    }


class SnapshotPersistenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user()
        cls.now = datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc)

    def _create(self, **overrides):
        defaults = dict(
            briefing_id="a" * 64,
            user=self.user,
            generated_at=self.now,
            composer_version="1.0.0",
            payload=_payload_stub(),
            expires_at=self.now + timedelta(seconds=1800),
        )
        defaults.update(overrides)
        return HealthBriefingSnapshot.objects.create(**defaults)

    def test_snapshot_persists_and_round_trips(self):
        snap = self._create()
        fetched = HealthBriefingSnapshot.objects.get(briefing_id=snap.briefing_id)
        self.assertEqual(fetched.user_id, self.user.id)
        self.assertEqual(fetched.composer_version, "1.0.0")
        self.assertEqual(fetched.payload["overall_status"], "stable")

    def test_briefing_id_is_unique(self):
        self._create()
        with self.assertRaises(IntegrityError):
            self._create()  # same briefing_id default

    def test_created_at_auto_populated(self):
        snap = self._create()
        self.assertIsNotNone(snap.created_at)

    def test_str_includes_truncated_id_and_user_id(self):
        snap = self._create()
        s = str(snap)
        self.assertIn(snap.briefing_id[:12], s)
        self.assertIn(str(self.user.id), s)

    def test_ordering_is_newest_first(self):
        self._create(briefing_id="b" * 64, generated_at=self.now)
        self._create(
            briefing_id="c" * 64,
            generated_at=self.now + timedelta(hours=1),
        )
        self._create(
            briefing_id="d" * 64,
            generated_at=self.now - timedelta(hours=1),
        )
        ordered = list(
            HealthBriefingSnapshot.objects.values_list("briefing_id", flat=True)
        )
        # Newest (c) first, then b, then d.
        self.assertEqual(ordered[0], "c" * 64)
        self.assertEqual(ordered[-1], "d" * 64)

    def test_user_cascade_deletes_snapshots(self):
        self._create()
        self.assertEqual(HealthBriefingSnapshot.objects.count(), 1)
        self.user.delete()
        self.assertEqual(HealthBriefingSnapshot.objects.count(), 0)

    def test_related_name_accessible_from_user(self):
        self._create()
        self.assertEqual(self.user.health_briefing_snapshots.count(), 1)


class SnapshotExpiryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("expiry@test.com")

    def _create(self, expires_at):
        return HealthBriefingSnapshot.objects.create(
            briefing_id="e" * 64,
            user=self.user,
            generated_at=datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc),
            composer_version="1.0.0",
            payload=_payload_stub(),
            expires_at=expires_at,
        )

    def test_is_expired_false_when_future(self):
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        snap = self._create(future)
        self.assertFalse(snap.is_expired)

    def test_is_expired_true_when_past(self):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        snap = self._create(past)
        self.assertTrue(snap.is_expired)

    def test_expired_snapshots_still_queryable(self):
        # Snapshots are NOT auto-deleted on expiry; cleanup is a
        # separate concern. is_expired is a flag, not a filter.
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        self._create(past)
        self.assertEqual(HealthBriefingSnapshot.objects.count(), 1)
        # Filter by expires_at to find candidates for cleanup.
        self.assertEqual(
            HealthBriefingSnapshot.objects.filter(
                expires_at__lt=datetime.now(timezone.utc)
            ).count(),
            1,
        )


class SnapshotIntegrationWithContractTests(TestCase):
    """Smoke test that the snapshot model accepts a real-shaped payload
    serialized from the C1 contract types."""

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("integration@test.com")

    def test_accepts_contract_shaped_payload(self):
        from apps.core.health_briefing.contract import (
            COMPOSER_VERSION,
            DEFAULT_TTL_SECONDS,
            compute_briefing_id,
        )

        generated_at = datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc)
        briefing_id = compute_briefing_id(
            self.user.id, generated_at, COMPOSER_VERSION, "evidence-hash-stub"
        )
        payload = {
            "briefing_id": briefing_id,
            "user_id": self.user.id,
            "generated_at_utc": generated_at.isoformat(),
            "composer_version": COMPOSER_VERSION,
            "composed_over": {
                "start_utc": (generated_at - timedelta(days=7)).isoformat(),
                "end_utc": generated_at.isoformat(),
            },
            "ttl_seconds": DEFAULT_TTL_SECONDS,
            "overall_status": "improving",
            "overall_confidence": 0.82,
            "risk_level": "low",
            "headline_summary": "Metabolic trajectory positive.",
            "glucose_trend_7d": {
                "direction": "down",
                "magnitude": 30,
                "confidence": 0.8,
                "window_days": 7,
            },
            "acute_alerts": [],
            "top_positive_drivers": [],
            "watch_items": [],
            "inputs_used": {"latest_glucose": 132},
            "inputs_missing": [],
            "staleness_flags": [],
            "why": ["7-day glucose average down 12 mg/dL"],
            "positive_recognition_required": True,
            "insufficient_data_flag": False,
        }
        snap = HealthBriefingSnapshot.objects.create(
            briefing_id=briefing_id,
            user=self.user,
            generated_at=generated_at,
            composer_version=COMPOSER_VERSION,
            payload=payload,
            expires_at=generated_at + timedelta(seconds=DEFAULT_TTL_SECONDS),
        )
        fetched = HealthBriefingSnapshot.objects.get(briefing_id=briefing_id)
        self.assertEqual(fetched.payload["overall_status"], "improving")
        self.assertEqual(fetched.payload["glucose_trend_7d"]["magnitude"], 30)
