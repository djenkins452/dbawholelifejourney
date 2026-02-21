"""
Vegas Ops Wall v2 — Tests.

Covers:
  - EngineExpectedCadence, EngineHeartbeat, AdminIntervention models
  - OpsAnomaly, OpsNarrativeSnapshot models
  - Heartbeat calculator (OK, LATE, MISSED)
  - SAME engine (anomaly detection + narrative generation)
  - Ops stream endpoint (JSON + incremental cursor)
  - Admin action endpoint (rerun, clear cache, acknowledge)
  - Access control (staff-only)
  - Anomaly reconciliation (activate/resolve)

Project: Whole Life Journey
Path: apps/core/ai_observability/tests_ops_wall_v2.py
"""

import json
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.core.ai_observability.models import (
    AdminIntervention,
    DecisionRecord,
    EngineExpectedCadence,
    EngineHeartbeat,
    EngineRun,
    OpsAnomaly,
    OpsNarrativeSnapshot,
)
from apps.users.models import TermsAcceptance, User


def _staff_user(email="staff@test.com"):
    """Create a staff user with required onboarding."""
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    user.is_staff = True
    user.save()
    return user


def _login_staff(client, user):
    """Force login staff user and set MFA verified in session."""
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True
    session.save()


def _regular_user(email="user@test.com"):
    """Create a non-staff user."""
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


def _create_engine_run(engine, status="success", minutes_ago=0, duration_ms=50):
    """Helper to create an EngineRun."""
    started = timezone.now() - timedelta(minutes=minutes_ago)
    return EngineRun.objects.create(
        trace_id="test-trace-001",
        engine_name=engine,
        phase=3,
        started_at=started,
        ended_at=started + timedelta(milliseconds=duration_ms),
        duration_ms=duration_ms,
        status=status,
    )


# ============================================================
# Model Tests
# ============================================================


class EngineExpectedCadenceModelTest(TestCase):
    """Test EngineExpectedCadence model."""

    def test_create_cadence(self):
        cadence = EngineExpectedCadence.objects.create(
            engine_name="UAL",
            expected_interval_seconds=300,
            expected_jitter_seconds=120,
        )
        self.assertEqual(str(cadence), "UAL (every 5m)")

    def test_unique_engine_constraint(self):
        EngineExpectedCadence.objects.create(
            engine_name="UAL",
            expected_interval_seconds=300,
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            EngineExpectedCadence.objects.create(
                engine_name="UAL",
                expected_interval_seconds=600,
            )

    def test_str_hourly(self):
        cadence = EngineExpectedCadence.objects.create(
            engine_name="PRIE",
            expected_interval_seconds=3600,
        )
        self.assertEqual(str(cadence), "PRIE (every 1h)")

    def test_str_daily(self):
        cadence = EngineExpectedCadence.objects.create(
            engine_name="DBE",
            expected_interval_seconds=86400,
        )
        self.assertEqual(str(cadence), "DBE (every 1d)")


class EngineHeartbeatModelTest(TestCase):
    """Test EngineHeartbeat model."""

    def test_create_heartbeat(self):
        hb = EngineHeartbeat.objects.create(
            engine_name="UAL",
            observed_at=timezone.now(),
            status="OK",
            lateness_seconds=0,
        )
        self.assertIn("UAL", str(hb))
        self.assertIn("OK", str(hb))

    def test_heartbeat_ordering(self):
        now = timezone.now()
        hb1 = EngineHeartbeat.objects.create(
            engine_name="UAL", observed_at=now - timedelta(hours=1), status="OK",
        )
        hb2 = EngineHeartbeat.objects.create(
            engine_name="UAL", observed_at=now, status="MISSED",
        )
        heartbeats = list(EngineHeartbeat.objects.all())
        self.assertEqual(heartbeats[0].id, hb2.id)  # Newest first


class AdminInterventionModelTest(TestCase):
    """Test AdminIntervention model."""

    def test_create_intervention(self):
        user = _staff_user()
        intervention = AdminIntervention.objects.create(
            admin_user=user,
            action_type="rerun_engine",
            engine_name="UAL",
            trace_id="trace-123",
            result_status="success",
        )
        self.assertIn("rerun_engine", str(intervention))
        self.assertIn("UAL", str(intervention))


class OpsAnomalyModelTest(TestCase):
    """Test OpsAnomaly model."""

    def test_create_anomaly(self):
        anomaly = OpsAnomaly.objects.create(
            severity="P1",
            engine_name="UAL",
            anomaly_type="MISSED_RUN",
            summary="UAL missed expected cadence",
        )
        self.assertTrue(anomaly.is_active)
        self.assertIn("P1", str(anomaly))
        self.assertIn("ACTIVE", str(anomaly))

    def test_resolve_anomaly(self):
        anomaly = OpsAnomaly.objects.create(
            severity="P2",
            engine_name="ICQG",
            anomaly_type="SUPPRESSION_STORM",
            summary="Test",
        )
        anomaly.is_active = False
        anomaly.resolved_at = timezone.now()
        anomaly.save()
        self.assertIn("RESOLVED", str(anomaly))

    def test_active_index_query(self):
        OpsAnomaly.objects.create(
            severity="P1", anomaly_type="MISSED_RUN",
            engine_name="UAL", summary="active", is_active=True,
        )
        OpsAnomaly.objects.create(
            severity="P2", anomaly_type="ERROR_SPIKE",
            engine_name="PIE", summary="resolved",
            is_active=False, resolved_at=timezone.now(),
        )
        active = OpsAnomaly.objects.filter(is_active=True)
        self.assertEqual(active.count(), 1)


class OpsNarrativeSnapshotModelTest(TestCase):
    """Test OpsNarrativeSnapshot model."""

    def test_create_narrative(self):
        snapshot = OpsNarrativeSnapshot.objects.create(
            posture="OK",
            headline="All systems nominal.",
            bullets_now=["All engines running."],
            recommendations=["No action needed."],
            watching_next=["Nothing to watch."],
        )
        self.assertEqual(snapshot.posture, "OK")


# ============================================================
# Heartbeat Calculator Tests
# ============================================================


class HeartbeatCalculatorTest(TestCase):
    """Test heartbeat.py compute functions."""

    def test_heartbeat_ok_when_recent_run(self):
        """Engine with recent run should be OK."""
        _create_engine_run("UAL", minutes_ago=2)

        from apps.core.ai_observability.heartbeat import compute_heartbeats
        heartbeats = compute_heartbeats()

        ual_hb = next((h for h in heartbeats if h.engine_name == "UAL"), None)
        self.assertIsNotNone(ual_hb)
        self.assertEqual(ual_hb.status, "OK")
        self.assertEqual(ual_hb.lateness_seconds, 0)

    def test_heartbeat_missed_when_overdue(self):
        """Engine with very old last run should be MISSED."""
        # UAL cadence = 300s, jitter = 120s → MISSED after 420s
        _create_engine_run("UAL", minutes_ago=30)  # 1800s > 420s

        from apps.core.ai_observability.heartbeat import compute_heartbeats
        heartbeats = compute_heartbeats()

        ual_hb = next((h for h in heartbeats if h.engine_name == "UAL"), None)
        self.assertIsNotNone(ual_hb)
        self.assertEqual(ual_hb.status, "MISSED")
        self.assertGreater(ual_hb.lateness_seconds, 0)

    def test_heartbeat_late_in_jitter_window(self):
        """Engine within jitter window should be LATE."""
        # UAL cadence = 300s (5m), jitter = 120s
        # Run 6 minutes ago → 360s since last run
        # next_expected = run_time + 300s, now = run_time + 360s
        # deadline = next_expected + 120s = run_time + 420s
        # 360s > 300s (next_expected) but < 420s (deadline) → LATE
        _create_engine_run("UAL", minutes_ago=6)

        from apps.core.ai_observability.heartbeat import compute_heartbeats
        heartbeats = compute_heartbeats()

        ual_hb = next((h for h in heartbeats if h.engine_name == "UAL"), None)
        self.assertIsNotNone(ual_hb)
        self.assertEqual(ual_hb.status, "LATE")

    def test_compute_and_save_heartbeats(self):
        """compute_and_save_heartbeats persists to DB."""
        _create_engine_run("UAL", minutes_ago=1)

        from apps.core.ai_observability.heartbeat import compute_and_save_heartbeats
        saved = compute_and_save_heartbeats()

        self.assertGreater(len(saved), 0)
        self.assertTrue(EngineHeartbeat.objects.filter(engine_name="UAL").exists())

    def test_get_latest_heartbeats(self):
        """get_latest_heartbeats returns dict of latest per engine."""
        _create_engine_run("UAL", minutes_ago=1)
        _create_engine_run("PIE", minutes_ago=1)

        from apps.core.ai_observability.heartbeat import (
            compute_and_save_heartbeats,
            get_latest_heartbeats,
        )
        compute_and_save_heartbeats()
        result = get_latest_heartbeats()

        self.assertIn("UAL", result)
        self.assertIn("PIE", result)
        self.assertEqual(result["UAL"]["status"], "OK")

    def test_seed_cadence_config(self):
        """seed_cadence_config creates records from defaults."""
        from apps.core.ai_observability.heartbeat import seed_cadence_config
        seed_cadence_config()

        self.assertTrue(
            EngineExpectedCadence.objects.filter(engine_name="UAL").exists()
        )
        ual = EngineExpectedCadence.objects.get(engine_name="UAL")
        self.assertEqual(ual.expected_interval_seconds, 300)

    def test_db_cadence_overrides_default(self):
        """Database cadence config overrides hardcoded defaults."""
        EngineExpectedCadence.objects.create(
            engine_name="UAL",
            expected_interval_seconds=600,  # Override 300 → 600
            expected_jitter_seconds=60,
        )
        _create_engine_run("UAL", minutes_ago=8)  # 480s

        from apps.core.ai_observability.heartbeat import compute_heartbeats
        heartbeats = compute_heartbeats()

        ual_hb = next((h for h in heartbeats if h.engine_name == "UAL"), None)
        # With 600s interval + 60s jitter, 480s should be OK
        self.assertEqual(ual_hb.status, "OK")


# ============================================================
# SAME Engine Tests
# ============================================================


class SAMEMissedRunTest(TestCase):
    """Test SAME detects missed run anomalies."""

    def test_missed_run_creates_anomaly(self):
        """SAME creates anomaly when heartbeat shows MISSED."""
        # Create old run so UAL is MISSED
        _create_engine_run("UAL", minutes_ago=60)

        from apps.core.ai_observability.same_engine import run_same
        result = run_same()

        self.assertGreater(result["anomalies_created"], 0)
        anomaly = OpsAnomaly.objects.filter(
            engine_name="UAL", anomaly_type="MISSED_RUN", is_active=True
        ).first()
        self.assertIsNotNone(anomaly)
        self.assertIn("missed", anomaly.summary.lower())

    def test_resolved_when_engine_recovers(self):
        """Active anomaly gets resolved when engine starts running again."""
        # First: create missed anomaly
        _create_engine_run("UAL", minutes_ago=60)
        from apps.core.ai_observability.same_engine import run_same
        run_same()

        self.assertTrue(
            OpsAnomaly.objects.filter(
                engine_name="UAL", anomaly_type="MISSED_RUN", is_active=True
            ).exists()
        )

        # Now: create recent run to resolve
        _create_engine_run("UAL", minutes_ago=1)
        run_same()

        # Anomaly should be resolved
        resolved = OpsAnomaly.objects.filter(
            engine_name="UAL", anomaly_type="MISSED_RUN", is_active=False
        )
        self.assertTrue(resolved.exists())


class SAMENarrativeTest(TestCase):
    """Test SAME narrative generation."""

    def test_narrative_created(self):
        """run_same creates a narrative snapshot."""
        _create_engine_run("UAL", minutes_ago=1)
        _create_engine_run("PIE", minutes_ago=1)

        from apps.core.ai_observability.same_engine import run_same
        result = run_same()

        self.assertIsNotNone(result["narrative"])
        snapshot = OpsNarrativeSnapshot.objects.first()
        self.assertIsNotNone(snapshot)
        self.assertIn(snapshot.posture, ["OK", "DEGRADED", "AT_RISK"])
        self.assertTrue(len(snapshot.headline) > 0)

    def test_narrative_posture_ok_when_healthy(self):
        """Narrative posture is OK when all engines healthy."""
        for engine in ["UAL", "SAE", "PIE", "PRIE", "PGE", "ICQG", "DBE", "WIRE", "DNE"]:
            _create_engine_run(engine, minutes_ago=1)

        from apps.core.ai_observability.same_engine import run_same
        result = run_same()

        self.assertEqual(result["narrative"].posture, "OK")

    def test_narrative_references_anomaly(self):
        """Narrative bullets reference detected anomalies."""
        _create_engine_run("UAL", minutes_ago=60)  # Will be MISSED

        from apps.core.ai_observability.same_engine import run_same
        result = run_same()

        snapshot = result["narrative"]
        # Should mention missed cadence
        bullets_text = " ".join(snapshot.bullets_now)
        self.assertTrue(
            "missed" in bullets_text.lower() or "UAL" in bullets_text,
            f"Expected 'missed' or 'UAL' in: {bullets_text}"
        )


class SAMESuppressionStormTest(TestCase):
    """Test ICQG suppression storm detection."""

    def test_suppression_storm_detected(self):
        """SAME detects suppression storm when 30m rate > 3x 7d baseline."""
        now = timezone.now()

        # Create baseline: 10 suppressions over 7 days
        for i in range(10):
            DecisionRecord.objects.create(
                trace_id=f"trace-baseline-{i}",
                engine_name="ICQG",
                decision_type="suppression",
                decision=f"SUPPRESS=old_{i}",
                created_at=now - timedelta(days=i % 7 + 1),
            )

        # Create spike: 10 suppressions in last 30m
        for i in range(10):
            DecisionRecord.objects.create(
                trace_id=f"trace-spike-{i}",
                engine_name="ICQG",
                decision_type="suppression",
                decision=f"SUPPRESS=spike_{i}",
                created_at=now - timedelta(minutes=i),
            )

        from apps.core.ai_observability.same_engine import _detect_suppression_storm
        anomalies = _detect_suppression_storm(now)

        self.assertGreater(len(anomalies), 0)
        self.assertEqual(anomalies[0]["anomaly_type"], "SUPPRESSION_STORM")


class SAMEErrorSpikeTest(TestCase):
    """Test error spike detection."""

    def test_error_spike_detected(self):
        """SAME detects error spike when 30m errors > 3x 24h baseline."""
        now = timezone.now()

        # Baseline: a few errors over 24h
        for i in range(6):
            EngineRun.objects.create(
                trace_id=f"trace-baseline-{i}",
                engine_name="PIE",
                phase=3,
                started_at=now - timedelta(hours=i + 2),
                duration_ms=50,
                status="error",
                error_type="TestError",
            )

        # Spike: many errors in last 30m
        for i in range(5):
            EngineRun.objects.create(
                trace_id=f"trace-spike-{i}",
                engine_name="PIE",
                phase=3,
                started_at=now - timedelta(minutes=i),
                duration_ms=50,
                status="error",
                error_type="TestError",
            )

        from apps.core.ai_observability.same_engine import _detect_error_spikes
        anomalies = _detect_error_spikes(now)

        self.assertGreater(len(anomalies), 0)
        self.assertEqual(anomalies[0]["anomaly_type"], "ERROR_SPIKE")
        self.assertEqual(anomalies[0]["engine_name"], "PIE")


# ============================================================
# Ops Stream Endpoint Tests
# ============================================================


class OpsStreamViewTest(TestCase):
    """Test /admin-console/ops/stream/ endpoint."""

    def setUp(self):
        self.staff = _staff_user()
        self.user = _regular_user(email="regular@test.com")

    def test_stream_returns_json(self):
        """Stream endpoint returns valid JSON with expected keys."""
        _login_staff(self.client, self.staff)
        response = self.client.get("/admin-console/ops/stream/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("server_time", data)
        self.assertIn("posture", data)
        self.assertIn("engine_cards", data)
        self.assertIn("narrative", data)
        self.assertIn("anomalies", data)
        self.assertIn("feed", data)
        self.assertIn("next_since", data)

    def test_stream_incremental_cursor(self):
        """Stream returns next_since for incremental polling."""
        _login_staff(self.client, self.staff)

        response1 = self.client.get("/admin-console/ops/stream/")
        data1 = response1.json()
        next_since = data1["next_since"]

        # Second poll with cursor
        response2 = self.client.get(f"/admin-console/ops/stream/?since={next_since}")
        self.assertEqual(response2.status_code, 200)

    def test_stream_forbidden_for_non_staff(self):
        """Non-staff users get 403."""
        self.client.force_login(self.user)
        response = self.client.get("/admin-console/ops/stream/")
        self.assertEqual(response.status_code, 403)

    def test_stream_engine_cards_structure(self):
        """Engine cards have required fields."""
        _create_engine_run("UAL", minutes_ago=1)

        _login_staff(self.client, self.staff)
        response = self.client.get("/admin-console/ops/stream/")
        data = response.json()

        cards = data["engine_cards"]
        self.assertGreater(len(cards), 0)

        card = cards[0]
        required_fields = [
            "name", "status", "cadence", "last_run_at",
            "miss_count_30m", "error_count_24h", "duration_p95_1h", "sparkline",
        ]
        for field in required_fields:
            self.assertIn(field, card, f"Missing field: {field}")


# ============================================================
# Admin Action Tests
# ============================================================


class OpsActionViewTest(TestCase):
    """Test /admin-console/ops/actions/ endpoint."""

    def setUp(self):
        self.staff = _staff_user()

    def test_action_creates_intervention(self):
        """Admin action creates AdminIntervention record."""
        _login_staff(self.client, self.staff)
        response = self.client.post(
            "/admin-console/ops/actions/",
            json.dumps({"action": "rerun_engine", "engine": "UAL"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("trace_id", data)

        intervention = AdminIntervention.objects.first()
        self.assertIsNotNone(intervention)
        self.assertEqual(intervention.action_type, "rerun_engine")
        self.assertEqual(intervention.engine_name, "UAL")
        self.assertEqual(intervention.admin_user, self.staff)

    def test_action_has_trace_id(self):
        """Admin actions generate unique trace_ids."""
        _login_staff(self.client, self.staff)
        response = self.client.post(
            "/admin-console/ops/actions/",
            json.dumps({"action": "rerun_engine", "engine": "DBE"}),
            content_type="application/json",
        )
        data = response.json()
        self.assertTrue(len(data["trace_id"]) > 0)

    def test_action_forbidden_for_non_staff(self):
        """Non-staff users cannot execute actions."""
        user = _regular_user(email="nope@test.com")
        self.client.force_login(user)
        response = self.client.post(
            "/admin-console/ops/actions/",
            json.dumps({"action": "rerun_engine", "engine": "UAL"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_acknowledge_anomaly_resolves(self):
        """Acknowledge action resolves active anomalies."""
        OpsAnomaly.objects.create(
            severity="P2",
            engine_name="PIE",
            anomaly_type="ERROR_SPIKE",
            summary="test",
            is_active=True,
        )

        _login_staff(self.client, self.staff)
        response = self.client.post(
            "/admin-console/ops/actions/",
            json.dumps({"action": "acknowledge_anomaly", "engine": "PIE"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            OpsAnomaly.objects.filter(engine_name="PIE", is_active=True).exists()
        )

    def test_invalid_action(self):
        """Invalid action returns failure."""
        _login_staff(self.client, self.staff)
        response = self.client.post(
            "/admin-console/ops/actions/",
            json.dumps({"action": "invalid_action", "engine": "UAL"}),
            content_type="application/json",
        )
        data = response.json()
        self.assertFalse(data["success"])


# ============================================================
# View Access Control Tests
# ============================================================


class OpsWallViewAccessTest(TestCase):
    """Test Ops Wall view access control."""

    def setUp(self):
        self.staff = _staff_user()

    def test_ops_wall_loads_for_staff(self):
        """Ops Wall page loads for staff users."""
        _login_staff(self.client, self.staff)
        response = self.client.get("/admin-console/ops/")
        self.assertEqual(response.status_code, 200)

    def test_ops_wall_blocked_for_non_staff(self):
        """Non-staff users get redirected."""
        user = _regular_user(email="nope2@test.com")
        self.client.force_login(user)
        response = self.client.get("/admin-console/ops/")
        self.assertEqual(response.status_code, 302)

    def test_all_engines_loads_for_staff(self):
        """All Engines page loads for staff."""
        _login_staff(self.client, self.staff)
        response = self.client.get("/admin-console/ops/all-engines/")
        self.assertEqual(response.status_code, 200)


# ============================================================
# Anomaly Reconciliation Tests
# ============================================================


class AnomalyReconciliationTest(TestCase):
    """Test anomaly lifecycle (activate/deactivate)."""

    def test_new_anomaly_created(self):
        """New detected anomaly creates OpsAnomaly record."""
        from apps.core.ai_observability.same_engine import _reconcile_anomalies

        detected = [{
            "anomaly_type": "MISSED_RUN",
            "severity": "P1",
            "engine_name": "UAL",
            "summary": "UAL missed cadence",
            "evidence": {"lateness_seconds": 600},
            "suggested_actions": [],
        }]

        stats = _reconcile_anomalies(detected, timezone.now())
        self.assertEqual(stats["created"], 1)
        self.assertTrue(
            OpsAnomaly.objects.filter(
                anomaly_type="MISSED_RUN", engine_name="UAL", is_active=True
            ).exists()
        )

    def test_existing_anomaly_updated(self):
        """Existing active anomaly gets updated, not duplicated."""
        OpsAnomaly.objects.create(
            anomaly_type="MISSED_RUN",
            severity="P2",
            engine_name="UAL",
            summary="old summary",
            is_active=True,
        )

        from apps.core.ai_observability.same_engine import _reconcile_anomalies
        detected = [{
            "anomaly_type": "MISSED_RUN",
            "severity": "P1",
            "engine_name": "UAL",
            "summary": "new summary",
            "evidence": {},
            "suggested_actions": [],
        }]

        stats = _reconcile_anomalies(detected, timezone.now())
        self.assertEqual(stats["created"], 0)

        anomaly = OpsAnomaly.objects.get(
            anomaly_type="MISSED_RUN", engine_name="UAL"
        )
        self.assertEqual(anomaly.summary, "new summary")
        self.assertEqual(anomaly.severity, "P1")  # Updated severity

    def test_stale_anomaly_resolved(self):
        """Anomaly no longer detected gets resolved."""
        OpsAnomaly.objects.create(
            anomaly_type="MISSED_RUN",
            severity="P1",
            engine_name="UAL",
            summary="was missed",
            is_active=True,
        )

        from apps.core.ai_observability.same_engine import _reconcile_anomalies
        # Empty detected list → should resolve existing
        stats = _reconcile_anomalies([], timezone.now())
        self.assertEqual(stats["resolved"], 1)

        anomaly = OpsAnomaly.objects.get(
            anomaly_type="MISSED_RUN", engine_name="UAL"
        )
        self.assertFalse(anomaly.is_active)
        self.assertIsNotNone(anomaly.resolved_at)


# ============================================================
# Confidence Volatility Test
# ============================================================


class SAMEConfidenceVolatilityTest(TestCase):
    """Test UAL confidence volatility detection."""

    def test_volatility_detected(self):
        """High stddev across UAL decisions triggers anomaly."""
        now = timezone.now()

        # Create decisions with high variance
        confidences = [0.1, 0.9, 0.2, 0.8, 0.15, 0.85]
        for i, conf in enumerate(confidences):
            DecisionRecord.objects.create(
                trace_id=f"trace-vol-{i}",
                engine_name="UAL",
                decision_type="arbitration",
                decision=f"SCENARIO=TEST_{i}",
                confidence=conf,
                created_at=now - timedelta(hours=i),
            )

        from apps.core.ai_observability.same_engine import _detect_confidence_volatility
        anomalies = _detect_confidence_volatility(now)

        self.assertGreater(len(anomalies), 0)
        self.assertEqual(anomalies[0]["anomaly_type"], "CONFIDENCE_VOLATILITY")

    def test_no_volatility_when_stable(self):
        """Stable confidence doesn't trigger anomaly."""
        now = timezone.now()

        for i in range(6):
            DecisionRecord.objects.create(
                trace_id=f"trace-stable-{i}",
                engine_name="UAL",
                decision_type="arbitration",
                decision="SCENARIO=STABLE",
                confidence=0.75 + (i * 0.01),  # Very stable
                created_at=now - timedelta(hours=i),
            )

        from apps.core.ai_observability.same_engine import _detect_confidence_volatility
        anomalies = _detect_confidence_volatility(now)
        self.assertEqual(len(anomalies), 0)
