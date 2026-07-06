"""HealthKit historical reimport capability — user-triggered repair of noon-defaulted
body-composition timestamps, following the server-directive + app-fulfilment pattern."""
import json

from django.conf import settings
from django.test import Client, TestCase

from apps.health.services import healthkit_reimport as svc
from apps.mobile.models import HealthReimportRequest, MobileAPIToken, MobileDevice
from apps.users.models import User


class ReimportServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="ri@x.com", password="x")

    def test_request_creates_pending_body_composition_and_supersedes_prior(self):
        r1 = svc.request_reimport(self.user)
        self.assertEqual(r1.status, "pending")
        self.assertEqual(r1.metrics, ["weight", "body_fat", "lean_body_mass"])
        r2 = svc.request_reimport(self.user)          # newest ask wins
        r1.refresh_from_db()
        self.assertEqual(r1.status, "failed")          # superseded (no duplicate open)
        self.assertEqual(r2.status, "pending")
        self.assertEqual(HealthReimportRequest.objects.filter(
            user=self.user, status="pending").count(), 1)

    def test_pending_directive_marks_in_progress_then_clears_on_complete(self):
        svc.request_reimport(self.user)
        d = svc.pending_directive(self.user)
        self.assertEqual(d["metrics"], ["weight", "body_fat", "lean_body_mass"])
        self.assertEqual(d["status"], "in_progress")
        svc.complete_request(self.user, d["request_id"], scanned=190, updated=188, skipped=2)
        self.assertIsNone(svc.pending_directive(self.user))   # nothing open after completion

    def test_complete_records_counts(self):
        r = svc.request_reimport(self.user)
        svc.pending_directive(self.user)
        svc.complete_request(self.user, r.id, scanned=190, updated=188, skipped=2, failed=0)
        r.refresh_from_db()
        self.assertEqual(r.status, "completed")
        self.assertEqual((r.scanned, r.updated, r.skipped), (190, 188, 2))

    def test_idempotent_no_open_directive_when_none_requested(self):
        self.assertIsNone(svc.pending_directive(self.user))


class ReimportMobileEndpointTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="rie@x.com", password="x")
        self.device = MobileDevice.objects.create(user=self.user, device_id="d-reimport")
        self.token, self.raw = MobileAPIToken.create_token(user=self.user, device=self.device)

    def _h(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw}"}

    def test_sync_status_advertises_pending_directive(self):
        svc.request_reimport(self.user)
        resp = self.client.get("/api/mobile/health/sync-status/", **self._h())
        self.assertEqual(resp.status_code, 200, resp.content)
        directive = resp.json()["reimport"]
        self.assertIsNotNone(directive)
        self.assertIn("weight", directive["metrics"])
        self.assertEqual(directive["status"], "in_progress")

    def test_sync_status_reimport_is_null_when_nothing_requested(self):
        resp = self.client.get("/api/mobile/health/sync-status/", **self._h())
        self.assertIsNone(resp.json()["reimport"])

    def test_complete_endpoint_closes_request_with_counts(self):
        r = svc.request_reimport(self.user)
        resp = self.client.post(
            "/api/mobile/health/reimport/complete/",
            data=json.dumps({"request_id": r.id, "scanned": 5, "updated": 5, "skipped": 0}),
            content_type="application/json", **self._h())
        self.assertEqual(resp.status_code, 200, resp.content)
        r.refresh_from_db()
        self.assertEqual(r.status, "completed")
        self.assertEqual(r.updated, 5)

    def test_complete_endpoint_rejects_unknown_request(self):
        resp = self.client.post(
            "/api/mobile/health/reimport/complete/",
            data=json.dumps({"request_id": 999999, "updated": 1}),
            content_type="application/json", **self._h())
        self.assertEqual(resp.status_code, 404)


class ReimportWebViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="riw@x.com", password="x")
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=self.user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.client.force_login(self.user)

    def test_post_creates_pending_request_and_redirects(self):
        resp = self.client.post("/health/physical/weight/reimport/")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(HealthReimportRequest.objects.filter(
            user=self.user, status="pending").exists())

    def test_get_is_not_allowed(self):
        resp = self.client.get("/health/physical/weight/reimport/")
        self.assertIn(resp.status_code, (405, 302))   # require_POST (405) or auth redirect
