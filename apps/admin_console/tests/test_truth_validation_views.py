"""Smoke + behaviour tests for the Truth Validation Center operator views.

Enqueue is patched so the suite never runs live (no OpenAI); we assert the operator
surface: the center renders, starting creates a scoped run + dispatches, override and
approve mutate the right state. Admin-only access is enforced.
"""
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.admin_console.models import AcceptanceResult, AcceptanceRun
from apps.admin_console.tests.test_admin_console import AdminTestMixin


class TruthValidationViewTests(AdminTestMixin, TestCase):
    def setUp(self):
        self.admin = self.create_admin(email="admin_tv@example.com")
        self.plain = self.create_user(email="plain_tv@example.com")
        self.client.force_login(self.admin)

    def test_center_renders(self):
        resp = self.client.get(reverse("admin_console:truth_validation"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Truth Validation Center")
        self.assertContains(resp, "Overall Truth Health")

    def test_non_admin_denied(self):
        self.client.force_login(self.plain)
        resp = self.client.get(reverse("admin_console:truth_validation"))
        self.assertEqual(resp.status_code, 302)   # redirected away

    @patch("apps.core.celery_utils.safe_enqueue", return_value=True)
    def test_start_full_creates_scoped_run(self, mock_enqueue):
        resp = self.client.post(reverse("admin_console:truth_validation_start"),
                                {"scope": "full"})
        self.assertEqual(resp.status_code, 302)
        run = AcceptanceRun.objects.filter(validation_type="truth").latest("id")
        self.assertEqual(run.scope_kind, "full")
        self.assertTrue(mock_enqueue.called)

    @patch("apps.core.celery_utils.safe_enqueue", return_value=True)
    def test_start_domain_scope(self, mock_enqueue):
        self.client.post(reverse("admin_console:truth_validation_start"),
                         {"scope": "domain:health"})
        run = AcceptanceRun.objects.filter(validation_type="truth").latest("id")
        self.assertEqual((run.scope_kind, run.scope_key), ("domain", "health"))

    @patch("apps.core.celery_utils.safe_enqueue", return_value=True)
    def test_rerun_object_scopes_to_one(self, mock_enqueue):
        self.client.post(reverse("admin_console:truth_validation_rerun_object"),
                         {"object_key": "body.weigh_in"})
        run = AcceptanceRun.objects.filter(validation_type="truth").latest("id")
        self.assertEqual((run.scope_kind, run.scope_key), ("object", "body.weigh_in"))

    @patch("apps.core.celery_utils.safe_enqueue", return_value=True)
    def test_rerun_unknown_object_rejected(self, mock_enqueue):
        before = AcceptanceRun.objects.count()
        self.client.post(reverse("admin_console:truth_validation_rerun_object"),
                         {"object_key": "nope.nope"})
        self.assertEqual(AcceptanceRun.objects.count(), before)

    def test_override_updates_check_and_rollup(self):
        run = AcceptanceRun.objects.create(validation_type="truth", status="completed",
                                           scope_kind="object", scope_key="x",
                                           checks_total=1)
        result = AcceptanceResult.objects.create(
            run=run, object_key="x", question_key="x",
            checks=[{"label": "value", "path": "p", "kind": "numeric", "unit": "lb",
                     "expected": "185 lb", "extracted": "", "status": "missing",
                     "is_forbidden": False}],
            check_pass_count=0, check_total=1, passed=False)
        resp = self.client.post(
            reverse("admin_console:truth_validation_override", kwargs={"pk": result.pk}),
            {"check_index": "0", "status": "present", "reason": "said 'about 185'"})
        self.assertEqual(resp.status_code, 302)
        result.refresh_from_db(); run.refresh_from_db()
        self.assertTrue(result.passed)
        self.assertEqual(run.checks_passed, 1)
        self.assertEqual(run.score_percent, 100)

    def test_override_requires_reason(self):
        run = AcceptanceRun.objects.create(validation_type="truth", status="completed")
        result = AcceptanceResult.objects.create(
            run=run, object_key="x", question_key="x",
            checks=[{"label": "v", "status": "missing", "is_forbidden": False}],
            check_total=1)
        self.client.post(
            reverse("admin_console:truth_validation_override", kwargs={"pk": result.pk}),
            {"check_index": "0", "status": "present", "reason": ""})
        result.refresh_from_db()
        self.assertFalse(result.passed)   # unchanged — no reason supplied

    def test_approve_marks_certification(self):
        run = AcceptanceRun.objects.create(validation_type="truth", status="completed")
        resp = self.client.post(
            reverse("admin_console:truth_validation_approve", kwargs={"pk": run.pk}))
        self.assertEqual(resp.status_code, 302)
        run.refresh_from_db()
        self.assertTrue(run.approved)
        self.assertEqual(run.approved_by, self.admin)
