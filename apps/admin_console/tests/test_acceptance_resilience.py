# ==============================================================================
# File: apps/admin_console/tests/test_acceptance_resilience.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P33 Acceptance Center operational resilience. An interrupted run
#   (deploy / worker restart / crash / hung OpenAI) must NEVER stay permanently
#   RUNNING: worker heartbeats + a lazy, Celery-free reaper detect staleness and
#   mark the run INTERRUPTED, the UI explains it, and a clean RESTART is offered.
# ==============================================================================
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.admin_console.models import AcceptanceRun
from apps.ai.chatgpt_cos.acceptance_service import (
    reap_stale_runs, running_acceptance_runs, _write_heartbeat,
)
from apps.admin_console.tests.test_admin_console import AdminTestMixin


def _run(status="running", age_seconds=None, completed=5, total=80, **kw):
    rr = {}
    if age_seconds is not None:
        at = (timezone.now() - timedelta(seconds=age_seconds)).isoformat()
        rr = {"heartbeat": {"at": at, "current_question": "goal_x",
                            "completed": completed, "total": total}}
    return AcceptanceRun.objects.create(
        suite_name="full", depth="deep", status=status, total_count=total,
        started_at=timezone.now() - timedelta(seconds=(age_seconds or 0)),
        raw_report_json=rr, **kw)


class HeartbeatModelTests(TestCase):
    def test_fresh_heartbeat_is_not_stale(self):
        r = _run(age_seconds=10)
        self.assertFalse(r.is_stale)
        self.assertEqual(r.questions_completed, 5)
        self.assertEqual(r.heartbeat_total, 80)
        self.assertEqual(r.progress_pct, 6)

    def test_old_heartbeat_is_stale(self):
        r = _run(age_seconds=600)         # 10 min, threshold 180s
        self.assertTrue(r.is_stale)

    def test_terminal_runs_are_never_stale(self):
        for st in ("completed", "failed", "interrupted"):
            r = _run(status=st, age_seconds=99999)
            self.assertFalse(r.is_stale, st)

    def test_running_with_no_heartbeat_falls_back_to_started_at(self):
        # a run dispatched but whose worker died before the first heartbeat
        r = AcceptanceRun.objects.create(
            suite_name="full", depth="smoke", status="running",
            started_at=timezone.now() - timedelta(seconds=600))
        self.assertTrue(r.is_stale)

    def test_write_heartbeat_roundtrip(self):
        r = _run(age_seconds=None)
        _write_heartbeat(r, "health_x", 12, 80)
        r.refresh_from_db()
        self.assertEqual(r.current_question, "health_x")
        self.assertEqual(r.questions_completed, 12)
        self.assertFalse(r.is_stale)      # just written -> fresh


class ReaperTests(TestCase):
    def test_reaper_marks_stale_running_as_interrupted(self):
        stale = _run(age_seconds=600)
        fresh = _run(age_seconds=5)
        done = _run(status="completed", age_seconds=99999)
        n = reap_stale_runs()
        self.assertEqual(n, 1)
        stale.refresh_from_db(); fresh.refresh_from_db(); done.refresh_from_db()
        self.assertEqual(stale.status, "interrupted")
        self.assertIn("interrupted", stale.error_message.lower())
        self.assertIsNotNone(stale.completed_at)
        self.assertEqual(fresh.status, "running")     # healthy run untouched
        self.assertEqual(done.status, "completed")

    def test_reaper_is_idempotent(self):
        _run(age_seconds=600)
        self.assertEqual(reap_stale_runs(), 1)
        self.assertEqual(reap_stale_runs(), 0)        # nothing left to reap

    def test_running_acceptance_runs_excludes_stale(self):
        _run(age_seconds=5)          # active
        _run(age_seconds=600)        # stale
        active = running_acceptance_runs()
        self.assertEqual(len(active), 1)
        self.assertFalse(active[0].is_stale)


class ViewResilienceTests(AdminTestMixin, TestCase):
    def setUp(self):
        self.staff = self.create_admin(email="p33@example.com")
        self.client.force_login(self.staff)

    def test_detail_view_self_heals_and_explains(self):
        run = _run(age_seconds=600)
        resp = self.client.get(reverse("admin_console:beth_acceptance_run",
                                       kwargs={"pk": run.pk}))
        self.assertEqual(resp.status_code, 200)
        run.refresh_from_db()
        self.assertEqual(run.status, "interrupted")   # reaped on view
        self.assertContains(resp, "appears to have been interrupted")
        self.assertContains(resp, "Start a fresh")     # restart offered
        self.assertNotContains(resp, "auto-refreshes")  # no false "still running"

    def test_center_view_reaps_ghost_runs(self):
        ghost = _run(age_seconds=600)
        resp = self.client.get(reverse("admin_console:beth_acceptance"))
        self.assertEqual(resp.status_code, 200)
        ghost.refresh_from_db()
        self.assertEqual(ghost.status, "interrupted")

    def test_restart_starts_a_fresh_run_same_suite(self):
        from unittest import mock
        before = AcceptanceRun.objects.count()
        # dispatch the runner as a no-op so the test never makes live OpenAI calls.
        with mock.patch("apps.ai.chatgpt_cos.tasks.run_beth_acceptance.delay"):
            resp = self.client.post(reverse("admin_console:beth_acceptance_start"),
                                    {"suite": "goals", "depth": "deep"})
        self.assertEqual(resp.status_code, 302)        # redirects to the new run
        self.assertEqual(AcceptanceRun.objects.count(), before + 1)
        newest = AcceptanceRun.objects.order_by("-created_at").first()
        self.assertEqual((newest.suite_name, newest.depth), ("goals", "deep"))
        self.assertEqual(newest.status, "running")

    def test_running_run_still_shows_progress(self):
        run = _run(age_seconds=5, completed=20, total=80)
        resp = self.client.get(reverse("admin_console:beth_acceptance_run",
                                       kwargs={"pk": run.pk}))
        self.assertContains(resp, "Run in progress")
        self.assertContains(resp, "20/80")
