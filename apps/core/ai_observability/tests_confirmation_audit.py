"""
OPS-8a — Confirmation-queue & audit-pipeline health tests.

Confirmation health is exercised against real `PendingAction` rows (deterministic);
audit health verifies stream-liveness facts + the synchronous-audit framing. Uses
the real Postgres test DB; each block degrades gracefully and never raises.
"""
import uuid
from datetime import timedelta

from unittest import mock
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_governance.models import PendingAction
from apps.core.ai_observability import confirmation_audit_monitor as cam

User = get_user_model()


def _mk_user(email):
    return User.objects.create(email=email)


def _mk_pending(user, status, created_delta, expires_delta):
    now = timezone.now()
    pa = PendingAction.objects.create(
        user=user,
        action_type="crud",
        intent_type="log_weight",
        status=status,
        expires_at=now + expires_delta,
    )
    # created_at is auto_now_add; backdate deterministically via update().
    PendingAction.objects.filter(pk=pa.pk).update(created_at=now + created_delta)
    return pa


class ConfirmationHealthTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = _mk_user("conf@test.com")

    def test_healthy_when_no_pending(self):
        r = cam._confirmation_health(timezone.now())
        self.assertEqual(r["status"], "HEALTHY")
        self.assertEqual(r["pending_active"], 0)
        self.assertEqual(r["stalled"], 0)

    def test_active_pending_counted(self):
        _mk_pending(self.user, PendingAction.STATUS_PENDING,
                    created_delta=timedelta(minutes=-2), expires_delta=timedelta(minutes=3))
        r = cam._confirmation_health(timezone.now())
        self.assertEqual(r["pending_active"], 1)
        self.assertEqual(r["stalled"], 0)
        self.assertGreaterEqual(r["oldest_pending_age_s"], 100)

    def test_stalled_pending_flagged(self):
        # status still 'pending' but expiry is in the past → orphaned/silently dead.
        for _ in range(2):
            _mk_pending(self.user, PendingAction.STATUS_PENDING,
                        created_delta=timedelta(minutes=-40), expires_delta=timedelta(minutes=-30))
        r = cam._confirmation_health(timezone.now())
        self.assertEqual(r["stalled"], 2)
        self.assertEqual(r["status"], "WARNING")

    def test_many_stalled_is_critical(self):
        for _ in range(5):
            _mk_pending(self.user, PendingAction.STATUS_PENDING,
                        created_delta=timedelta(minutes=-40), expires_delta=timedelta(minutes=-30))
        r = cam._confirmation_health(timezone.now())
        self.assertEqual(r["status"], "CRITICAL")

    def test_old_live_pending_is_warning(self):
        _mk_pending(self.user, PendingAction.STATUS_PENDING,
                    created_delta=timedelta(minutes=-20), expires_delta=timedelta(minutes=10))
        r = cam._confirmation_health(timezone.now())
        self.assertGreater(r["oldest_pending_age_s"], cam.OLDEST_PENDING_WARN_S)
        self.assertEqual(r["status"], "WARNING")

    def test_flow_24h_counts(self):
        _mk_pending(self.user, PendingAction.STATUS_PENDING,
                    created_delta=timedelta(hours=-1), expires_delta=timedelta(minutes=5))
        c = _mk_pending(self.user, PendingAction.STATUS_CONFIRMED,
                        created_delta=timedelta(hours=-2), expires_delta=timedelta(hours=-1))
        PendingAction.objects.filter(pk=c.pk).update(resolved_at=timezone.now() - timedelta(minutes=30))
        r = cam._confirmation_health(timezone.now())
        self.assertEqual(r["flow_24h"]["created"], 2)
        self.assertEqual(r["flow_24h"]["confirmed"], 1)


class AuditHealthTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_audit_stream_liveness_facts(self):
        from apps.core.ai_observability.models import DecisionRecord
        DecisionRecord.objects.create(
            trace_id=str(uuid.uuid4()), engine_name="UAL",
            decision_type="arbitration", decision="SCENARIO=X",
        )
        r = cam._audit_health(timezone.now())
        self.assertEqual(r["status"], "HEALTHY")  # facts-only, informational
        self.assertGreaterEqual(r["decision_records"]["count_1h"], 1)
        self.assertIsNotNone(r["decision_records"]["last_write_age_s"])
        # No writes → age None, not a fabricated verdict.
        self.assertIn("action_metrics", r)

    def test_empty_streams_age_none(self):
        r = cam._audit_health(timezone.now())
        self.assertEqual(r["action_metrics"]["count_1h"], 0)
        self.assertIsNone(r["action_metrics"]["last_write_age_s"])


class TelemetrySectionTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_section_shape_and_cache(self):
        r = cam.get_confirmation_audit_telemetry()
        for key in ("status", "confirmation", "audit", "measured_at"):
            self.assertIn(key, r)
        with mock.patch.object(cam, "_confirmation_health") as m:
            cam.get_confirmation_audit_telemetry()  # cached → no re-probe
            m.assert_not_called()
