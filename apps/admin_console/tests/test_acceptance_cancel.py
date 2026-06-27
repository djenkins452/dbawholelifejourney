# ==============================================================================
# File: apps/admin_console/tests/test_acceptance_cancel.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P34 Acceptance Center — graceful COOPERATIVE cancellation (Cancel
#   Run), restart-after-cancel, delete, and the administrator-control UI. The
#   worker stops cleanly AFTER the current question; no orphaned/ambiguous state.
# ==============================================================================
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.admin_console.models import AcceptanceRun, AcceptanceResult
from apps.ai.chatgpt_cos import acceptance_service as svc
from apps.admin_console.tests.test_admin_console import AdminTestMixin

User = get_user_model()


def _fresh_running(**kw):
    at = timezone.now().isoformat()
    return AcceptanceRun.objects.create(
        suite_name="full", depth="deep", status="running", total_count=80,
        started_at=timezone.now(),
        raw_report_json={"heartbeat": {"at": at, "current_question": "q",
                                       "completed": 10, "total": 80}}, **kw)


def _fake_row(spec, passed=True):
    return {"key": spec["key"], "suite": spec.get("suite", "health"),
            "question": spec.get("text", ""), "expected_intent": "", "expected_lane": "",
            "intent": None, "lane": "personal_reasoning", "answer": "ok", "ms": 50,
            "passed": passed, "fails": [], "required": [], "forbidden": [],
            "openai_called": True, "fallback_used": False}


class CancelRequestTests(TestCase):
    def test_request_cancel_on_live_run_sets_cancelling(self):
        run = _fresh_running()
        self.assertEqual(svc.request_cancel(run), "cancelling")
        run.refresh_from_db()
        self.assertEqual(run.status, "cancelling")

    def test_request_cancel_idempotent(self):
        run = _fresh_running()
        svc.request_cancel(run)
        self.assertEqual(svc.request_cancel(run), "cancelling")  # already requested

    def test_request_cancel_on_stale_run_cancels_immediately(self):
        run = _fresh_running()
        run.raw_report_json = {"heartbeat": {"at": (timezone.now() -
                               timedelta(seconds=600)).isoformat(), "completed": 10,
                               "total": 80}}
        run.save()
        self.assertEqual(svc.request_cancel(run), "cancelled")
        run.refresh_from_db()
        self.assertEqual(run.status, "cancelled")

    def test_request_cancel_on_terminal_returns_none(self):
        run = AcceptanceRun.objects.create(suite_name="full", depth="smoke",
                                           status="completed")
        self.assertIsNone(svc.request_cancel(run))


class CancellationWhileProcessingTests(TestCase):
    """The worker detects cancel BETWEEN questions, finishes the in-flight one, and
    exits cleanly with partial results and NO grade."""
    def setUp(self):
        self.user = User.objects.create_user(email="cxl@example.com", password="x")

    def test_worker_stops_after_current_question(self):
        run = AcceptanceRun.objects.create(suite_name="full", depth="deep",
                                           status="running", target_user=self.user)
        specs = [{"key": "q1", "suite": "health", "text": "a"},
                 {"key": "q2", "suite": "health", "text": "b"},
                 {"key": "q3", "suite": "health", "text": "c"}]

        def fake_run_one(svc_, conv, spec, evening=False):
            # admin clicks Cancel right after the FIRST question completes
            if spec["key"] == "q1":
                AcceptanceRun.objects.filter(pk=run.pk).update(status="cancelling")
            return _fake_row(spec)

        with mock.patch.object(svc, "questions_for", return_value=specs), \
             mock.patch.object(svc, "run_one", side_effect=fake_run_one):
            svc.execute_run(run, evening=False)

        run.refresh_from_db()
        self.assertEqual(run.status, "cancelled")          # clean terminal state
        self.assertEqual(run.grade, "")                    # NO grade for partial run
        self.assertFalse(run.trustworthy)
        self.assertEqual(run.total_count, 3)
        # exactly ONE question completed before the cancel was honored
        self.assertEqual(run.results.count(), 1)
        self.assertEqual(run.pass_count, 1)
        self.assertIn("cancelled by administrator", run.error_message.lower())
        self.assertIsNotNone(run.completed_at)
        self.assertTrue(run.is_terminal)


class StaleCancellingReaperTests(TestCase):
    def test_stale_cancelling_becomes_cancelled(self):
        run = AcceptanceRun.objects.create(
            suite_name="full", depth="deep", status="cancelling", total_count=80,
            started_at=timezone.now() - timedelta(seconds=600),
            raw_report_json={"heartbeat": {"at": (timezone.now() -
                             timedelta(seconds=600)).isoformat(), "completed": 5,
                             "total": 80}})
        self.assertEqual(svc.reap_stale_runs(), 1)
        run.refresh_from_db()
        self.assertEqual(run.status, "cancelled")


class CancelUITests(AdminTestMixin, TestCase):
    def setUp(self):
        self.staff = self.create_admin(email="cxlui@example.com")
        self.client.force_login(self.staff)

    def _detail(self, run):
        return self.client.get(reverse("admin_console:beth_acceptance_run",
                                       kwargs={"pk": run.pk}))

    def test_cancel_button_and_confirmation_visible_on_live_run(self):
        run = _fresh_running()
        resp = self._detail(run)
        self.assertContains(resp, "✕ Cancel run")  # the button renders only when cancellable
        # exact administrator confirmation copy
        self.assertContains(resp, "Cancelling will stop after the current question finishes")
        self.assertContains(resp, "cannot be resumed")

    def test_no_cancel_button_on_finished_run(self):
        run = AcceptanceRun.objects.create(suite_name="full", depth="smoke",
                                           status="completed", score_percent=100)
        resp = self._detail(run)
        self.assertNotContains(resp, "✕ Cancel run")  # no cancel button on a finished run

    def test_cancel_view_marks_cancelling(self):
        run = _fresh_running()
        resp = self.client.post(reverse("admin_console:beth_acceptance_cancel",
                                        kwargs={"pk": run.pk}))
        self.assertEqual(resp.status_code, 302)
        run.refresh_from_db()
        self.assertEqual(run.status, "cancelling")

    def test_cancelled_run_offers_restart(self):
        run = AcceptanceRun.objects.create(suite_name="goals", depth="deep",
                                           status="cancelled", error_message="Cancelled.")
        resp = self._detail(run)
        self.assertContains(resp, "cancelled by administrator")
        self.assertContains(resp, "Start a fresh")          # restart offered

    def test_restart_after_cancel_creates_new_run(self):
        AcceptanceRun.objects.create(suite_name="goals", depth="deep", status="cancelled")
        before = AcceptanceRun.objects.count()
        with mock.patch("apps.ai.chatgpt_cos.tasks.run_beth_acceptance.delay"):
            self.client.post(reverse("admin_console:beth_acceptance_start"),
                             {"suite": "goals", "depth": "deep"})
        self.assertEqual(AcceptanceRun.objects.count(), before + 1)

    def test_delete_terminal_run(self):
        run = AcceptanceRun.objects.create(suite_name="full", depth="smoke",
                                           status="cancelled")
        resp = self.client.post(reverse("admin_console:beth_acceptance_delete",
                                        kwargs={"pk": run.pk}))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(AcceptanceRun.objects.filter(pk=run.pk).exists())

    def test_delete_refuses_active_run(self):
        run = _fresh_running()
        self.client.post(reverse("admin_console:beth_acceptance_delete",
                                 kwargs={"pk": run.pk}))
        self.assertTrue(AcceptanceRun.objects.filter(pk=run.pk).exists())  # not deleted
