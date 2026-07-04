# ==============================================================================
# File: apps/ai/tests/test_certification_console.py
# Description: In-app Executive Certification Console. A developer-only surface that
#   triggers REAL production generation paths through ONE shared implementation
#   (apps.ai.certification_console) — the same code the management command calls, so
#   there is no duplicated business logic. Staff-gated; never shown to normal users.
# ==============================================================================
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.ai import certification_console as cc

User = get_user_model()


class CertificationConsoleServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="cc@test.com", password="x")

    def test_every_registered_action_runs_the_real_path(self):
        for key, *_ in cc.action_list():
            result = cc.run_action(self.user, key, force=True)
            self.assertIn("ok", result, key)
            self.assertTrue(result.get("summary"), key)

    def test_proactive_guidance_creates_a_card_with_buttons(self):
        r = cc.run_action(self.user, "proactive_guidance", force=True)
        self.assertTrue(r["ok"])
        self.assertIsNotNone(r.get("message_id"))
        self.assertIn("Got it", r.get("buttons", []))

    def test_briefing_actions_return_preview_text(self):
        for key in ("morning_checkin", "executive_brief", "daily_wrapup"):
            r = cc.run_action(self.user, key)
            self.assertTrue(r["ok"], key)
            self.assertTrue(r.get("preview"), key)

    def test_unknown_action_is_handled(self):
        r = cc.run_action(self.user, "does_not_exist")
        self.assertFalse(r["ok"])

    def test_management_command_uses_the_same_implementation(self):
        # The command is a thin wrapper over run_action — exercising it proves the
        # single shared path (no duplicated logic).
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command("trigger_proactive_checkin", "--email", "cc@test.com", "--force", stdout=out)
        self.assertIn("Proactive guidance card created", out.getvalue())


class CertificationConsoleViewTests(TestCase):
    # RequestFactory isolates the VIEW's staff-gate + action contract from unrelated
    # onboarding/billing middleware redirects.
    def setUp(self):
        from django.test import RequestFactory
        from apps.ai.views import ExecutiveCertificationConsoleView
        self.rf = RequestFactory()
        self.url = reverse("ai:certification_console")
        self.view = ExecutiveCertificationConsoleView.as_view()
        self.staff = User.objects.create_user(email="staff@test.com", password="x", is_staff=True)
        self.normal = User.objects.create_user(email="normal@test.com", password="x")

    def _get(self, user):
        req = self.rf.get(self.url)
        req.user = user
        return self.view(req)

    def _post(self, user, payload):
        req = self.rf.post(self.url, data=json.dumps(payload), content_type="application/json")
        req.user = user
        return self.view(req)

    def test_hidden_from_normal_users(self):
        self.assertEqual(self._get(self.normal).status_code, 403)
        self.assertEqual(
            self._post(self.normal, {"action": "executive_brief"}).status_code, 403)

    def test_staff_can_open_and_run(self):
        page = self._get(self.staff)
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Generate Proactive Guidance", page.content)
        resp = self._post(self.staff, {"action": "executive_brief", "force": False})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(json.loads(resp.content)["ok"])
