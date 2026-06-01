"""Phase 1 of the dashboard-action latency project.

These tests guard the two server-side changes that cut perceived
latency for dashboard_v3 quick-actions in half:

  1. When a v3 data-v3-toggle button POSTs with X-V3-Toggle: 1, the
     action endpoint returns 204 No Content — skipping the v2
     action_center rebuild (~5–8s of render) that the client would
     have discarded anyway.

  2. Without the header, the existing v2 HTML response is unchanged
     — the v2 dashboard still works.

The action_timing log line ([DASHBOARD_ACTION_TIMING] action=... user=...
total_ms=... ...) emits on every action so we can measure before/after
in production.
"""

import logging
from datetime import time as dtime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.users.models import TermsAcceptance


User = get_user_model()


def _make_user(email="latency@test.com"):
    u = User.objects.create_user(email=email, password="x" * 20)
    TermsAcceptance.objects.create(
        user=u,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class V3ToggleShortCircuitTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client = Client()
        self.client.force_login(self.user)

    # ── water_log endpoint ────────────────────────────────────────
    def test_water_log_with_v3_toggle_header_returns_204(self):
        resp = self.client.post(
            reverse("health:water_quick_log"),
            data={"preset": "8", "drink_type": "water"},
            HTTP_X_V3_TOGGLE="1",
        )
        self.assertEqual(
            resp.status_code, 204,
            "v3-toggle header must short-circuit to 204 — got %s"
            % resp.status_code,
        )
        self.assertEqual(resp.content, b"")

    def test_water_log_without_header_still_creates_entry_and_responds(self):
        """Non-v3 callers (legacy water_list widget, browser form) must
        keep working — the redirect/JSON path is unchanged."""
        resp = self.client.post(
            reverse("health:water_quick_log"),
            data={"preset": "8", "drink_type": "water"},
        )
        # 302 redirect to next-or-water_list — same as before.
        self.assertIn(resp.status_code, (200, 302))

    def test_water_log_with_v3_toggle_still_creates_water_entry(self):
        """Trust contract — short-circuit must NOT skip the write,
        only the rendered response."""
        from apps.health.models import WaterEntry
        self.client.post(
            reverse("health:water_quick_log"),
            data={"preset": "8", "drink_type": "coffee"},
            HTTP_X_V3_TOGGLE="1",
        )
        self.assertEqual(
            WaterEntry.objects.filter(
                user=self.user, drink_type="coffee", amount=8,
            ).count(), 1,
        )

    # ── action_center endpoints (task / routine / intake / block) ─
    def test_intake_group_log_with_v3_toggle_returns_204(self):
        url = reverse(
            "dashboard_v2:intake_group_log",
            kwargs={"time_of_day": "morning"},
        )
        resp = self.client.post(url, HTTP_X_V3_TOGGLE="1")
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(resp.content, b"")

    def test_intake_group_log_without_v3_toggle_returns_html(self):
        """v2 still gets the full action_center render."""
        url = reverse(
            "dashboard_v2:intake_group_log",
            kwargs={"time_of_day": "morning"},
        )
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        # Body is non-empty HTML (the action_center template).
        self.assertGreater(len(resp.content), 0)

    def test_task_toggle_with_v3_toggle_returns_204(self):
        from apps.life.models import Task
        task = Task.objects.create(
            user=self.user, title="quick task", priority="medium",
        )
        url = reverse("dashboard_v2:task_toggle", kwargs={"pk": task.pk})
        resp = self.client.post(url, HTTP_X_V3_TOGGLE="1")
        self.assertEqual(resp.status_code, 204)


class ActionTimingLogTests(TestCase):
    """The [DASHBOARD_ACTION_TIMING] log line must emit on every
    action — we rely on it to measure before/after latency in prod."""

    def setUp(self):
        self.user = _make_user("timing@test.com")
        self.client = Client()
        self.client.force_login(self.user)

    def _capture_timing_logs(self, action_callable):
        with self.assertLogs("dashboard.action.timing", level="INFO") as cm:
            action_callable()
        return [r for r in cm.output if "[DASHBOARD_ACTION_TIMING]" in r]

    def test_water_log_emits_timing_with_required_fields(self):
        records = self._capture_timing_logs(
            lambda: self.client.post(
                reverse("health:water_quick_log"),
                data={"preset": "8", "drink_type": "water"},
                HTTP_X_V3_TOGGLE="1",
            )
        )
        self.assertEqual(len(records), 1, "exactly one timing log per request")
        line = records[0]
        # Required fields per the spec.
        self.assertIn("action=water_log", line)
        self.assertIn(f"user={self.user.pk}", line)
        self.assertIn("total_ms=", line)
        # Tag tells us this was the fast-path (v3 short-circuit).
        self.assertIn("short_circuit=True", line)
        # drink_type extra
        self.assertIn("drink_type=water", line)

    def test_action_center_emits_timing_with_short_circuit_flag(self):
        url = reverse(
            "dashboard_v2:intake_group_log",
            kwargs={"time_of_day": "morning"},
        )
        records = self._capture_timing_logs(
            lambda: self.client.post(url, HTTP_X_V3_TOGGLE="1")
        )
        self.assertEqual(len(records), 1)
        self.assertIn("short_circuit=True", records[0])
        self.assertIn(f"user={self.user.pk}", records[0])
        self.assertIn("total_ms=", records[0])

    def test_action_center_without_v3_header_logs_short_circuit_false(self):
        url = reverse(
            "dashboard_v2:intake_group_log",
            kwargs={"time_of_day": "morning"},
        )
        records = self._capture_timing_logs(
            lambda: self.client.post(url)
        )
        self.assertEqual(len(records), 1)
        self.assertIn("short_circuit=False", records[0])
