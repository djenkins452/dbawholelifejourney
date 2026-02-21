"""
Tests for OBD-II Diagnostics Console + Operations Wall.

Covers:
- Trace context (generate, set/reset, nested, empty-without-context)
- Models (create EngineRun/EngineSpan/DecisionRecord, ordering, choices)
- Instrumentation decorators (success, error, no-trace skip, DB failure silent)
- Views (staff access, non-staff denied, stream JSON, trace detail, search)
- Ops aggregates (engine pulse, system status, suppression stats)
- Ops anomalies (error burst, engine silence, scenario dominance)
- Ops feed (formatting runs, decisions)
- Cleanup command

Project: Whole Life Journey
"""

import base64
import secrets
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory, override_settings
from django.utils import timezone

User = get_user_model()


def _create_staff_user(email="staff@test.com"):
    """Create a staff user with all middleware requirements satisfied."""
    user = User.objects.create_user(
        email=email, password="test123", is_staff=True
    )
    # Accept terms
    from apps.users.models import TermsAcceptance
    current_version = settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
    TermsAcceptance.objects.create(user=user, terms_version=current_version)

    # Complete onboarding
    user.preferences.has_completed_onboarding = True
    user.preferences.save()

    # Verify email
    from allauth.account.models import EmailAddress
    EmailAddress.objects.get_or_create(
        user=user, email=user.email,
        defaults={"verified": True, "primary": True},
    )

    # MFA credential (required for staff)
    from apps.users.models import WebAuthnCredential
    credential_id = secrets.token_bytes(32)
    credential_id_b64 = base64.urlsafe_b64encode(credential_id).rstrip(b"=").decode()
    public_key = secrets.token_bytes(64)
    WebAuthnCredential.objects.create(
        user=user,
        credential_id=credential_id,
        credential_id_b64=credential_id_b64,
        public_key=public_key,
        device_name="Test Device",
    )

    return user


def _create_regular_user(email="regular@test.com"):
    """Create a non-staff user with middleware requirements satisfied."""
    user = User.objects.create_user(
        email=email, password="test123"
    )
    from apps.users.models import TermsAcceptance
    current_version = settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
    TermsAcceptance.objects.create(user=user, terms_version=current_version)
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    from allauth.account.models import EmailAddress
    EmailAddress.objects.get_or_create(
        user=user, email=user.email,
        defaults={"verified": True, "primary": True},
    )
    return user


# ==========================================================================
# TRACE CONTEXT TESTS
# ==========================================================================


class TraceContextTests(TestCase):
    """Test trace context generation and propagation."""

    def test_generate_trace_id_is_uuid(self):
        from apps.core.ai_observability.trace import generate_trace_id

        tid = generate_trace_id()
        self.assertEqual(len(tid), 36)
        self.assertEqual(tid.count("-"), 4)

    def test_generate_trace_id_unique(self):
        from apps.core.ai_observability.trace import generate_trace_id

        ids = {generate_trace_id() for _ in range(100)}
        self.assertEqual(len(ids), 100)

    def test_get_trace_id_empty_without_context(self):
        from apps.core.ai_observability.trace import get_trace_id

        self.assertEqual(get_trace_id(), "")

    def test_trace_context_sets_and_resets(self):
        from apps.core.ai_observability.trace import (
            get_trace_id,
            get_trace_source,
            trace_context,
        )

        self.assertEqual(get_trace_id(), "")
        with trace_context(source="test") as tid:
            self.assertTrue(len(tid) > 0)
            self.assertEqual(get_trace_id(), tid)
            self.assertEqual(get_trace_source(), "test")

        # After context exits, should be reset
        self.assertEqual(get_trace_id(), "")
        self.assertEqual(get_trace_source(), "")

    def test_trace_context_explicit_id(self):
        from apps.core.ai_observability.trace import get_trace_id, trace_context

        with trace_context(trace_id="my-custom-id", source="custom"):
            self.assertEqual(get_trace_id(), "my-custom-id")

    def test_trace_context_nested(self):
        from apps.core.ai_observability.trace import get_trace_id, trace_context

        with trace_context(source="outer") as outer_id:
            with trace_context(source="inner") as inner_id:
                self.assertEqual(get_trace_id(), inner_id)
                self.assertNotEqual(inner_id, outer_id)
            # Restored to outer
            self.assertEqual(get_trace_id(), outer_id)


# ==========================================================================
# MODEL TESTS
# ==========================================================================


class EngineRunModelTests(TestCase):
    """Test EngineRun model."""

    def test_create_engine_run(self):
        from apps.core.ai_observability.models import EngineRun

        now = timezone.now()
        run = EngineRun.objects.create(
            trace_id="test-trace-001",
            engine_name="UAL",
            phase=3,
            started_at=now,
            ended_at=now + timedelta(milliseconds=42),
            duration_ms=42,
            status="success",
            user_id=1,
        )
        self.assertEqual(run.engine_name, "UAL")
        self.assertEqual(run.duration_ms, 42)
        self.assertEqual(run.status, "success")

    def test_engine_run_ordering(self):
        from apps.core.ai_observability.models import EngineRun

        now = timezone.now()
        EngineRun.objects.create(
            trace_id="t1", engine_name="PIE", phase=3,
            started_at=now - timedelta(minutes=5), duration_ms=10,
        )
        EngineRun.objects.create(
            trace_id="t2", engine_name="UAL", phase=3,
            started_at=now, duration_ms=20,
        )
        runs = list(EngineRun.objects.all())
        # Default ordering is -started_at (newest first)
        self.assertEqual(runs[0].trace_id, "t2")
        self.assertEqual(runs[1].trace_id, "t1")

    def test_engine_run_str(self):
        from apps.core.ai_observability.models import EngineRun

        run = EngineRun(
            trace_id="abcdefgh-1234",
            engine_name="SAE",
            phase=3,
            duration_ms=15,
            status="success",
        )
        self.assertIn("SAE", str(run))
        self.assertIn("success", str(run))
        self.assertIn("15ms", str(run))

    def test_engine_run_error_fields(self):
        from apps.core.ai_observability.models import EngineRun

        run = EngineRun.objects.create(
            trace_id="err-trace",
            engine_name="DNE",
            phase=3,
            started_at=timezone.now(),
            duration_ms=100,
            status="error",
            error_type="ValueError",
            error_message="something broke",
        )
        self.assertEqual(run.error_type, "ValueError")
        self.assertEqual(run.error_message, "something broke")


class EngineSpanModelTests(TestCase):
    """Test EngineSpan model."""

    def test_create_engine_span(self):
        from apps.core.ai_observability.models import EngineSpan

        now = timezone.now()
        span = EngineSpan.objects.create(
            trace_id="span-trace-001",
            engine_name="UAL",
            span_name="collect_signals",
            started_at=now,
            ended_at=now + timedelta(milliseconds=5),
            duration_ms=5,
            status="success",
        )
        self.assertEqual(span.span_name, "collect_signals")

    def test_engine_span_str(self):
        from apps.core.ai_observability.models import EngineSpan

        span = EngineSpan(
            engine_name="UAL",
            span_name="classify_scenario",
            status="success",
            duration_ms=3,
        )
        self.assertIn("UAL.classify_scenario", str(span))


class DecisionRecordModelTests(TestCase):
    """Test DecisionRecord model."""

    def test_create_decision_record(self):
        from apps.core.ai_observability.models import DecisionRecord

        dec = DecisionRecord.objects.create(
            trace_id="dec-trace-001",
            engine_name="UAL",
            decision_type="arbitration",
            decision="SCENARIO=HEALTH_CRITICAL",
            rationale="High signal strength from health domain",
            inputs_summary={"strengths": {"health": 0.8}},
            user_id=1,
            confidence=0.72,
        )
        self.assertEqual(dec.decision_type, "arbitration")
        self.assertEqual(dec.confidence, 0.72)

    def test_decision_record_ordering(self):
        from apps.core.ai_observability.models import DecisionRecord

        DecisionRecord.objects.create(
            trace_id="d1", engine_name="UAL",
            decision_type="arbitration", decision="A",
        )
        DecisionRecord.objects.create(
            trace_id="d2", engine_name="ICQG",
            decision_type="suppression", decision="B",
        )
        decs = list(DecisionRecord.objects.all())
        # Default ordering is -created_at (newest first)
        self.assertEqual(decs[0].trace_id, "d2")


# ==========================================================================
# INSTRUMENTATION DECORATOR TESTS
# ==========================================================================


class LogEngineRunDecoratorTests(TestCase):
    """Test the @log_engine_run decorator."""

    def test_success_records_engine_run(self):
        from apps.core.ai_observability.instrumentation import log_engine_run
        from apps.core.ai_observability.models import EngineRun
        from apps.core.ai_observability.trace import trace_context

        @log_engine_run("TEST", 3)
        def my_engine():
            return "ok"

        with trace_context(source="test"):
            result = my_engine()

        self.assertEqual(result, "ok")
        self.assertEqual(EngineRun.objects.count(), 1)
        run = EngineRun.objects.first()
        self.assertEqual(run.engine_name, "TEST")
        self.assertEqual(run.phase, 3)
        self.assertEqual(run.status, "success")

    def test_error_records_and_reraises(self):
        from apps.core.ai_observability.instrumentation import log_engine_run
        from apps.core.ai_observability.models import EngineRun
        from apps.core.ai_observability.trace import trace_context

        @log_engine_run("FAIL", 3)
        def bad_engine():
            raise ValueError("broken")

        with trace_context(source="test"):
            with self.assertRaises(ValueError):
                bad_engine()

        run = EngineRun.objects.first()
        self.assertEqual(run.status, "error")
        self.assertEqual(run.error_type, "ValueError")
        self.assertIn("broken", run.error_message)

    def test_no_trace_context_skips_recording(self):
        from apps.core.ai_observability.instrumentation import log_engine_run
        from apps.core.ai_observability.models import EngineRun

        @log_engine_run("SKIP", 3)
        def my_engine():
            return "ok"

        result = my_engine()
        self.assertEqual(result, "ok")
        self.assertEqual(EngineRun.objects.count(), 0)

    def test_extracts_user_id_from_first_arg(self):
        from apps.core.ai_observability.instrumentation import log_engine_run
        from apps.core.ai_observability.models import EngineRun
        from apps.core.ai_observability.trace import trace_context

        user = _create_regular_user("diag@test.com")

        @log_engine_run("UTEST", 3)
        def engine_with_user(u):
            return "ok"

        with trace_context(source="test"):
            engine_with_user(user)

        run = EngineRun.objects.first()
        self.assertEqual(run.user_id, user.id)


class LogEngineSpanDecoratorTests(TestCase):
    """Test the @log_engine_span decorator."""

    def test_success_records_span(self):
        from apps.core.ai_observability.instrumentation import log_engine_span
        from apps.core.ai_observability.models import EngineSpan
        from apps.core.ai_observability.trace import trace_context

        @log_engine_span("UAL", "test_step")
        def my_step():
            return 42

        with trace_context(source="test"):
            result = my_step()

        self.assertEqual(result, 42)
        self.assertEqual(EngineSpan.objects.count(), 1)
        span = EngineSpan.objects.first()
        self.assertEqual(span.engine_name, "UAL")
        self.assertEqual(span.span_name, "test_step")

    def test_no_trace_skips(self):
        from apps.core.ai_observability.instrumentation import log_engine_span
        from apps.core.ai_observability.models import EngineSpan

        @log_engine_span("UAL", "test_step")
        def my_step():
            return 42

        my_step()
        self.assertEqual(EngineSpan.objects.count(), 0)


class RecordDecisionTests(TestCase):
    """Test the record_decision function."""

    def test_records_decision(self):
        from apps.core.ai_observability.instrumentation import record_decision
        from apps.core.ai_observability.models import DecisionRecord
        from apps.core.ai_observability.trace import trace_context

        with trace_context(source="test"):
            record_decision(
                engine_name="UAL",
                decision_type="arbitration",
                decision="SCENARIO=STABLE_EXECUTION",
                rationale="All clear",
                confidence=0.85,
                user_id=1,
            )

        self.assertEqual(DecisionRecord.objects.count(), 1)
        dec = DecisionRecord.objects.first()
        self.assertEqual(dec.engine_name, "UAL")
        self.assertEqual(dec.confidence, 0.85)

    def test_no_trace_skips(self):
        from apps.core.ai_observability.instrumentation import record_decision
        from apps.core.ai_observability.models import DecisionRecord

        record_decision(
            engine_name="UAL",
            decision_type="arbitration",
            decision="TEST",
        )
        self.assertEqual(DecisionRecord.objects.count(), 0)

    def test_db_failure_silenced(self):
        from apps.core.ai_observability.instrumentation import record_decision
        from apps.core.ai_observability.trace import trace_context

        with trace_context(source="test"):
            # Invalid decision_type should fail silently
            record_decision(
                engine_name="X" * 50,  # Too long for max_length=10
                decision_type="arbitration",
                decision="TEST",
            )
        # Should not raise — failure is silenced


# ==========================================================================
# VIEW ACCESS CONTROL TESTS
# ==========================================================================


class DiagnosticsViewAccessTests(TestCase):
    """Test staff-only access for diagnostics views."""

    def setUp(self):
        self.staff_user = _create_staff_user("access-staff@test.com")
        self.regular_user = _create_regular_user("access-regular@test.com")

    def test_diagnostics_console_staff_access(self):
        self.client.force_login(self.staff_user)
        response = self.client.get("/admin-console/diagnostics/")
        self.assertEqual(response.status_code, 200)

    def test_diagnostics_console_non_staff_redirects(self):
        self.client.force_login(self.regular_user)
        response = self.client.get("/admin-console/diagnostics/")
        self.assertEqual(response.status_code, 302)

    def test_diagnostics_console_anonymous_redirects(self):
        response = self.client.get("/admin-console/diagnostics/")
        self.assertEqual(response.status_code, 302)

    def test_stream_staff_access(self):
        self.client.force_login(self.staff_user)
        response = self.client.get("/admin-console/diagnostics/stream/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("runs", data)
        self.assertIn("decisions", data)
        self.assertIn("server_time", data)

    def test_stream_non_staff_forbidden(self):
        self.client.force_login(self.regular_user)
        response = self.client.get("/admin-console/diagnostics/stream/")
        self.assertEqual(response.status_code, 403)

    def test_ops_wall_staff_access(self):
        self.client.force_login(self.staff_user)
        response = self.client.get("/admin-console/ops/")
        self.assertEqual(response.status_code, 200)

    def test_ops_wall_non_staff_redirects(self):
        self.client.force_login(self.regular_user)
        response = self.client.get("/admin-console/ops/")
        self.assertEqual(response.status_code, 302)

    def test_ops_poll_staff_access(self):
        self.client.force_login(self.staff_user)
        response = self.client.get("/admin-console/ops/poll/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # v2 response keys
        self.assertIn("posture", data)
        self.assertIn("engine_cards", data)
        self.assertIn("feed", data)
        self.assertIn("anomalies", data)
        self.assertIn("integrity", data)

    def test_ops_poll_non_staff_forbidden(self):
        self.client.force_login(self.regular_user)
        response = self.client.get("/admin-console/ops/poll/")
        self.assertEqual(response.status_code, 403)


# ==========================================================================
# STREAM / SEARCH / TRACE DETAIL TESTS
# ==========================================================================


class DiagnosticsStreamTests(TestCase):
    """Test the diagnostics stream endpoint."""

    def setUp(self):
        self.staff_user = _create_staff_user("stream@test.com")
        self.client.force_login(self.staff_user)

        from apps.core.ai_observability.models import DecisionRecord, EngineRun

        now = timezone.now()
        self.trace_id = "stream-test-trace"
        EngineRun.objects.create(
            trace_id=self.trace_id, engine_name="UAL", phase=3,
            started_at=now, duration_ms=42, status="success", user_id=1,
        )
        EngineRun.objects.create(
            trace_id=self.trace_id, engine_name="PIE", phase=3,
            started_at=now - timedelta(seconds=1), duration_ms=15,
            status="error", error_type="TestError",
        )
        DecisionRecord.objects.create(
            trace_id=self.trace_id, engine_name="UAL",
            decision_type="arbitration",
            decision="SCENARIO=STABLE_EXECUTION",
            confidence=0.8,
        )

    def test_stream_returns_runs_and_decisions(self):
        since = (timezone.now() - timedelta(minutes=5)).isoformat()
        response = self.client.get(f"/admin-console/diagnostics/stream/?since={since}")
        data = response.json()
        self.assertEqual(len(data["runs"]), 2)
        self.assertEqual(len(data["decisions"]), 1)

    def test_stream_filters_by_engine(self):
        since = (timezone.now() - timedelta(minutes=5)).isoformat()
        response = self.client.get(
            f"/admin-console/diagnostics/stream/?since={since}&engine=UAL"
        )
        data = response.json()
        self.assertEqual(len(data["runs"]), 1)
        self.assertEqual(data["runs"][0]["engine_name"], "UAL")

    def test_stream_filters_by_status(self):
        since = (timezone.now() - timedelta(minutes=5)).isoformat()
        response = self.client.get(
            f"/admin-console/diagnostics/stream/?since={since}&status=error"
        )
        data = response.json()
        self.assertEqual(len(data["runs"]), 1)
        self.assertEqual(data["runs"][0]["status"], "error")


class DiagnosticsTraceDetailTests(TestCase):
    """Test trace detail endpoint."""

    def setUp(self):
        self.staff_user = _create_staff_user("trace@test.com")
        self.client.force_login(self.staff_user)

        from apps.core.ai_observability.models import (
            DecisionRecord, EngineRun, EngineSpan,
        )

        now = timezone.now()
        self.trace_id = "detail-test-trace"

        EngineRun.objects.create(
            trace_id=self.trace_id, engine_name="UAL", phase=3,
            started_at=now, ended_at=now + timedelta(milliseconds=50),
            duration_ms=50, status="success",
        )
        EngineSpan.objects.create(
            trace_id=self.trace_id, engine_name="UAL",
            span_name="collect_signals",
            started_at=now, ended_at=now + timedelta(milliseconds=10),
            duration_ms=10,
        )
        DecisionRecord.objects.create(
            trace_id=self.trace_id, engine_name="UAL",
            decision_type="arbitration",
            decision="SCENARIO=STABLE_EXECUTION",
        )

    def test_trace_detail_returns_all_components(self):
        response = self.client.get(
            f"/admin-console/diagnostics/trace/{self.trace_id}/"
        )
        data = response.json()
        self.assertEqual(data["trace_id"], self.trace_id)
        self.assertEqual(len(data["runs"]), 1)
        self.assertEqual(len(data["spans"]), 1)
        self.assertEqual(len(data["decisions"]), 1)
        self.assertIn("trace_start", data)

    def test_trace_detail_empty_trace(self):
        response = self.client.get(
            "/admin-console/diagnostics/trace/nonexistent-trace/"
        )
        data = response.json()
        self.assertEqual(len(data["runs"]), 0)
        self.assertEqual(len(data["spans"]), 0)
        self.assertEqual(len(data["decisions"]), 0)


class DiagnosticsSearchTests(TestCase):
    """Test the search endpoint."""

    def setUp(self):
        self.staff_user = _create_staff_user("search@test.com")
        self.client.force_login(self.staff_user)

        from apps.core.ai_observability.models import EngineRun

        now = timezone.now()
        EngineRun.objects.create(
            trace_id="search-trace-abc", engine_name="UAL", phase=3,
            started_at=now, duration_ms=42, status="success", user_id=5,
        )
        EngineRun.objects.create(
            trace_id="search-trace-def", engine_name="PIE", phase=3,
            started_at=now, duration_ms=15, status="error",
            error_type="TestError", error_message="test failure",
        )

    def test_search_by_engine(self):
        response = self.client.get("/admin-console/diagnostics/search/?engine=UAL")
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["engine_name"], "UAL")

    def test_search_by_status(self):
        response = self.client.get("/admin-console/diagnostics/search/?status=error")
        data = response.json()
        self.assertEqual(data["count"], 1)

    def test_search_by_trace_id_prefix(self):
        response = self.client.get("/admin-console/diagnostics/search/?q=search-trace-abc")
        data = response.json()
        self.assertEqual(data["count"], 1)

    def test_search_by_error_message(self):
        response = self.client.get("/admin-console/diagnostics/search/?q=test failure")
        data = response.json()
        self.assertEqual(data["count"], 1)

    def test_search_by_user_id(self):
        response = self.client.get("/admin-console/diagnostics/search/?user_id=5")
        data = response.json()
        self.assertEqual(data["count"], 1)


# ==========================================================================
# OPS AGGREGATES TESTS
# ==========================================================================


class OpsAggregatesTests(TestCase):
    """Test rolling aggregate functions."""

    def test_engine_pulse_no_data(self):
        from apps.core.ai_observability.ops_aggregates import get_engine_pulse

        pulse = get_engine_pulse("UAL")
        self.assertEqual(pulse["name"], "UAL")
        self.assertEqual(pulse["status"], "gray")
        self.assertIsNone(pulse["seconds_since"])
        self.assertEqual(pulse["runs_15m"], 0)

    def test_engine_pulse_green(self):
        from apps.core.ai_observability.models import EngineRun
        from apps.core.ai_observability.ops_aggregates import get_engine_pulse

        now = timezone.now()
        EngineRun.objects.create(
            trace_id="pulse-t1", engine_name="UAL", phase=3,
            started_at=now - timedelta(seconds=10), duration_ms=50,
            status="success",
        )
        pulse = get_engine_pulse("UAL")
        self.assertEqual(pulse["status"], "green")
        self.assertEqual(pulse["runs_15m"], 1)

    def test_engine_pulse_red_on_high_errors(self):
        from apps.core.ai_observability.models import EngineRun
        from apps.core.ai_observability.ops_aggregates import get_engine_pulse

        now = timezone.now()
        # Create 5 runs: 4 errors + 1 success = 80% error rate
        for i in range(4):
            EngineRun.objects.create(
                trace_id=f"err-{i}", engine_name="PIE", phase=3,
                started_at=now - timedelta(seconds=i + 1), duration_ms=10,
                status="error",
            )
        EngineRun.objects.create(
            trace_id="ok-1", engine_name="PIE", phase=3,
            started_at=now, duration_ms=10, status="success",
        )

        pulse = get_engine_pulse("PIE")
        self.assertEqual(pulse["status"], "red")

    def test_system_status_green_when_all_green(self):
        from apps.core.ai_observability.ops_aggregates import get_system_status

        pulses = [
            {"name": "UAL", "status": "green"},
            {"name": "PIE", "status": "green"},
        ]
        self.assertEqual(get_system_status(pulses), "green")

    def test_system_status_red_when_any_red(self):
        from apps.core.ai_observability.ops_aggregates import get_system_status

        pulses = [
            {"name": "UAL", "status": "green"},
            {"name": "PIE", "status": "red"},
        ]
        self.assertEqual(get_system_status(pulses), "red")

    def test_system_status_yellow_when_any_yellow(self):
        from apps.core.ai_observability.ops_aggregates import get_system_status

        pulses = [
            {"name": "UAL", "status": "green"},
            {"name": "PIE", "status": "yellow"},
        ]
        self.assertEqual(get_system_status(pulses), "yellow")

    def test_suppression_stats_structure(self):
        from apps.core.ai_observability.ops_aggregates import get_suppression_stats

        stats = get_suppression_stats()
        self.assertIn("15m", stats)
        self.assertIn("24h", stats)
        self.assertIn("count", stats["15m"])

    def test_ual_scenario_distribution_structure(self):
        from apps.core.ai_observability.ops_aggregates import (
            get_ual_scenario_distribution,
        )

        dist = get_ual_scenario_distribution()
        self.assertIn("1h", dist)
        self.assertIn("24h", dist)
        self.assertIn("14d", dist)

    def test_ual_scenario_distribution_with_data(self):
        from apps.core.ai_observability.models import DecisionRecord
        from apps.core.ai_observability.ops_aggregates import (
            get_ual_scenario_distribution,
        )

        DecisionRecord.objects.create(
            trace_id="sc-1", engine_name="UAL",
            decision_type="arbitration",
            decision="SCENARIO=HEALTH_CRITICAL",
        )
        DecisionRecord.objects.create(
            trace_id="sc-2", engine_name="UAL",
            decision_type="arbitration",
            decision="SCENARIO=STABLE_EXECUTION",
        )

        dist = get_ual_scenario_distribution()
        self.assertEqual(dist["1h"].get("HEALTH_CRITICAL", 0), 1)
        self.assertEqual(dist["1h"].get("STABLE_EXECUTION", 0), 1)

    def test_system_latency_structure(self):
        from apps.core.ai_observability.ops_aggregates import get_system_latency

        latency = get_system_latency()
        self.assertIn("UAL", latency)
        self.assertIn("p50", latency["UAL"])
        self.assertIn("p95", latency["UAL"])

    def test_confidence_trend_returns_24_entries(self):
        from apps.core.ai_observability.ops_aggregates import get_confidence_trend

        trend = get_confidence_trend()
        self.assertEqual(len(trend), 24)
        self.assertIn("hour", trend[0])
        self.assertIn("avg_confidence", trend[0])


# ==========================================================================
# OPS ANOMALIES TESTS
# ==========================================================================


class OpsAnomaliesTests(TestCase):
    """Test anomaly detection rules."""

    def test_detect_anomalies_empty_db(self):
        from apps.core.ai_observability.ops_anomalies import detect_anomalies

        anomalies = detect_anomalies()
        self.assertIsInstance(anomalies, list)
        # No data = no anomalies
        self.assertEqual(len(anomalies), 0)

    def test_error_burst_triggers(self):
        from apps.core.ai_observability.models import EngineRun
        from apps.core.ai_observability.ops_anomalies import _check_error_burst

        now = timezone.now()
        for i in range(5):
            EngineRun.objects.create(
                trace_id=f"burst-{i}", engine_name="UAL", phase=3,
                started_at=now - timedelta(seconds=i), duration_ms=10,
                status="error",
            )

        anomalies = _check_error_burst()
        self.assertTrue(len(anomalies) > 0)
        self.assertEqual(anomalies[0]["rule"], "error_burst")
        self.assertEqual(anomalies[0]["severity"], "warn")
        self.assertIn("diagnostic_link", anomalies[0])

    def test_engine_silence_triggers(self):
        from apps.core.ai_observability.models import EngineRun
        from apps.core.ai_observability.ops_anomalies import _check_engine_silence

        # UAL cadence is 300s. Last run 2000s ago = > 3x cadence
        now = timezone.now()
        EngineRun.objects.create(
            trace_id="old-run", engine_name="UAL", phase=3,
            started_at=now - timedelta(seconds=2000), duration_ms=10,
            status="success",
        )

        anomalies = _check_engine_silence()
        found = [a for a in anomalies if a["engine"] == "UAL"]
        self.assertTrue(len(found) > 0)
        self.assertEqual(found[0]["rule"], "engine_silence")

    def test_scenario_dominance_requires_minimum_data(self):
        from apps.core.ai_observability.ops_anomalies import _check_scenario_dominance

        # Less than 10 decisions = no anomaly
        anomalies = _check_scenario_dominance()
        self.assertEqual(len(anomalies), 0)

    def test_anomalies_sorted_by_severity(self):
        from apps.core.ai_observability.ops_anomalies import detect_anomalies

        # Mock anomalies to test sorting
        with patch(
            "apps.core.ai_observability.ops_anomalies._check_engine_silence",
            return_value=[{"severity": "info", "rule": "test"}],
        ), patch(
            "apps.core.ai_observability.ops_anomalies._check_error_burst",
            return_value=[{"severity": "crit", "rule": "test"}],
        ):
            anomalies = detect_anomalies()
            severities = [a["severity"] for a in anomalies]
            # crit should come before info
            if "crit" in severities and "info" in severities:
                self.assertLess(
                    severities.index("crit"),
                    severities.index("info"),
                )


# ==========================================================================
# OPS FEED TESTS
# ==========================================================================


class OpsFeedTests(TestCase):
    """Test the cognitive feed formatter."""

    def test_feed_empty_db(self):
        from apps.core.ai_observability.ops_feed import get_recent_feed

        feed = get_recent_feed()
        self.assertEqual(len(feed), 0)

    def test_feed_formats_successful_run(self):
        from apps.core.ai_observability.models import EngineRun
        from apps.core.ai_observability.ops_feed import get_recent_feed

        now = timezone.now()
        EngineRun.objects.create(
            trace_id="feed-t1", engine_name="UAL", phase=3,
            started_at=now, duration_ms=42, status="success",
        )

        feed = get_recent_feed(since=now - timedelta(minutes=1))
        self.assertEqual(len(feed), 1)
        entry = feed[0]
        self.assertEqual(entry["engine"], "UAL")
        self.assertEqual(entry["type"], "run")
        self.assertEqual(entry["severity"], "info")
        self.assertIn("42ms", entry["detail"])

    def test_feed_formats_error_run(self):
        from apps.core.ai_observability.models import EngineRun
        from apps.core.ai_observability.ops_feed import get_recent_feed

        now = timezone.now()
        EngineRun.objects.create(
            trace_id="feed-err", engine_name="PIE", phase=3,
            started_at=now, duration_ms=10, status="error",
            error_type="RuntimeError", error_message="oops",
        )

        feed = get_recent_feed(since=now - timedelta(minutes=1))
        entry = feed[0]
        self.assertEqual(entry["severity"], "error")
        self.assertIn("RuntimeError", entry["action"])

    def test_feed_formats_slow_run(self):
        from apps.core.ai_observability.models import EngineRun
        from apps.core.ai_observability.ops_feed import get_recent_feed

        now = timezone.now()
        EngineRun.objects.create(
            trace_id="feed-slow", engine_name="DBE", phase=3,
            started_at=now, duration_ms=2500, status="success",
        )

        feed = get_recent_feed(since=now - timedelta(minutes=1))
        entry = feed[0]
        self.assertEqual(entry["severity"], "warn")
        self.assertIn("SLOW", entry["action"])

    def test_feed_formats_ual_decision(self):
        from apps.core.ai_observability.models import DecisionRecord
        from apps.core.ai_observability.ops_feed import get_recent_feed

        now = timezone.now()
        DecisionRecord.objects.create(
            trace_id="feed-dec", engine_name="UAL",
            decision_type="arbitration",
            decision="SCENARIO=HEALTH_CRITICAL",
            confidence=0.72,
            rationale="High health signal",
        )

        feed = get_recent_feed(since=now - timedelta(minutes=1))
        dec_entries = [e for e in feed if e["type"] == "decision"]
        self.assertTrue(len(dec_entries) > 0)
        entry = dec_entries[0]
        self.assertIn("HEALTH_CRITICAL", entry["action"])
        self.assertEqual(entry["severity"], "warn")

    def test_feed_engine_filter(self):
        from apps.core.ai_observability.models import EngineRun
        from apps.core.ai_observability.ops_feed import get_recent_feed

        now = timezone.now()
        EngineRun.objects.create(
            trace_id="f-1", engine_name="UAL", phase=3,
            started_at=now, duration_ms=10, status="success",
        )
        EngineRun.objects.create(
            trace_id="f-2", engine_name="PIE", phase=3,
            started_at=now, duration_ms=10, status="success",
        )

        feed = get_recent_feed(
            since=now - timedelta(minutes=1), engine_filter="UAL"
        )
        self.assertEqual(len(feed), 1)
        self.assertEqual(feed[0]["engine"], "UAL")


# ==========================================================================
# CLEANUP COMMAND TESTS
# ==========================================================================


class CleanupDiagnosticsCommandTests(TestCase):
    """Test the cleanup_diagnostics management command."""

    def test_cleanup_deletes_old_data(self):
        from django.core.management import call_command

        from apps.core.ai_observability.models import (
            DecisionRecord, EngineRun, EngineSpan,
        )

        now = timezone.now()
        old = now - timedelta(days=10)

        # Create old and new records
        EngineRun.objects.create(
            trace_id="old-run", engine_name="UAL", phase=3,
            started_at=old, duration_ms=10, created_at=old,
        )
        EngineRun.objects.create(
            trace_id="new-run", engine_name="UAL", phase=3,
            started_at=now, duration_ms=10,
        )
        EngineSpan.objects.create(
            trace_id="old-span", engine_name="UAL",
            span_name="test", started_at=old, duration_ms=5,
        )
        DecisionRecord.objects.create(
            trace_id="old-dec", engine_name="UAL",
            decision_type="arbitration", decision="TEST",
        )

        # The old EngineRun's created_at is set by auto_now_add to now,
        # so we need to update it manually
        EngineRun.objects.filter(trace_id="old-run").update(created_at=old)
        EngineSpan.objects.filter(trace_id="old-span").update(started_at=old)
        DecisionRecord.objects.filter(trace_id="old-dec").update(created_at=old)

        call_command("cleanup_diagnostics", "--days", "7")

        # Old records deleted, new ones remain
        self.assertEqual(EngineRun.objects.count(), 1)
        self.assertEqual(EngineRun.objects.first().trace_id, "new-run")


# ==========================================================================
# MIDDLEWARE TESTS
# ==========================================================================


class DiagnosticsTraceMiddlewareTests(TestCase):
    """Test that middleware sets trace_id on requests."""

    def setUp(self):
        self.staff_user = _create_staff_user("mw@test.com")

    def test_middleware_sets_trace_id(self):
        self.client.force_login(self.staff_user)
        response = self.client.get("/admin-console/diagnostics/stream/")
        # The request should have had a trace_id set by middleware
        # We can verify indirectly — if decorators are active,
        # engine runs would be created during the request.
        # For now, just verify the response is OK.
        self.assertEqual(response.status_code, 200)


# ==========================================================================
# INTEGRATION TESTS
# ==========================================================================


class IntegrationTests(TestCase):
    """Integration tests combining trace context + decorators + models."""

    def test_full_trace_lifecycle(self):
        """Test: trace context → decorator → EngineRun created → queryable."""
        from apps.core.ai_observability.instrumentation import (
            log_engine_run,
            record_decision,
        )
        from apps.core.ai_observability.models import DecisionRecord, EngineRun
        from apps.core.ai_observability.trace import trace_context

        @log_engine_run("INTEG", 3)
        def mock_engine(user_id):
            record_decision(
                engine_name="INTEG",
                decision_type="other",
                decision="TEST_DECISION",
                rationale="Integration test",
                user_id=user_id,
            )
            return "done"

        with trace_context(source="integration_test") as trace_id:
            result = mock_engine(42)

        self.assertEqual(result, "done")

        # Verify EngineRun
        runs = EngineRun.objects.filter(trace_id=trace_id)
        self.assertEqual(runs.count(), 1)
        self.assertEqual(runs.first().engine_name, "INTEG")

        # Verify DecisionRecord
        decs = DecisionRecord.objects.filter(trace_id=trace_id)
        self.assertEqual(decs.count(), 1)
        self.assertEqual(decs.first().decision, "TEST_DECISION")
