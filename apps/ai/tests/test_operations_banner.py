"""
Operations Awareness UX — banner translation + delivery contract.

Verifies the customer-language boundary (no infrastructure terminology reaches
the user), the staff-gated request-path-safe status endpoint, and the recovery
delivery model: active incidents produce NO chat message (banner only), while a
recovery produces exactly ONE plain-English "Operations Update" timeline card.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.ai.operations_banner import (
    FORBIDDEN_TERMS,
    OPS_WALL_URL,
    get_customer_operations_status,
)

User = get_user_model()

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                      "LOCATION": "ops-banner-tests"}}
OPS_KEY = "wlj:ops:stream_payload"


def _mk_user(email, staff=False):
    u = User.objects.create_user(email=email, password="x")
    u.is_staff = staff
    u.save()
    from apps.users.models import TermsAcceptance
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS["TERMS_VERSION"]
    )
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _no_jargon(text):
    low = str(text).lower()
    return [t for t in FORBIDDEN_TERMS if t.lower() in low]


@override_settings(CACHES=LOCMEM)
class CustomerStatusTranslationTest(TestCase):
    def setUp(self):
        cache.clear()

    def test_missing_payload_fails_safe_to_healthy(self):
        cache.delete(OPS_KEY)
        s = get_customer_operations_status()
        self.assertEqual(s["state"], "healthy")

    def test_healthy_payload_no_banner(self):
        cache.set(OPS_KEY, {"executive": {"overall_status": "HEALTHY"}}, 60)
        self.assertEqual(get_customer_operations_status()["state"], "healthy")

    def test_degraded_maps_to_customer_language(self):
        cache.set(OPS_KEY, {"executive": {
            "overall_status": "DEGRADED",
            "customer_impact_phrases": ["Reduced insight freshness"],
        }}, 60)
        s = get_customer_operations_status()
        self.assertEqual(s["state"], "degraded")
        self.assertEqual(s["emoji"], "🟡")
        self.assertEqual(s["action_url"], OPS_WALL_URL)
        self.assertTrue(any("reduced reliability" in l.lower() for l in s["lines"]))
        self.assertTrue(any("your information is safe" in l.lower() for l in s["lines"]))

    def test_critical_maps_to_customer_language(self):
        cache.set(OPS_KEY, {"executive": {"overall_status": "CRITICAL"}}, 60)
        s = get_customer_operations_status()
        self.assertEqual(s["state"], "critical")
        self.assertEqual(s["emoji"], "🔴")
        self.assertTrue(any("may affect new activity" in l.lower() for l in s["lines"]))

    def test_no_infrastructure_terms_leak_in_any_state(self):
        for status in ("DEGRADED", "CRITICAL"):
            cache.set(OPS_KEY, {"executive": {
                "overall_status": status,
                # Even if phrases somehow carried jargon, primary copy must be clean.
                "customer_impact_phrases": ["Delayed notifications"],
            }}, 60)
            s = get_customer_operations_status()
            blob = " ".join([s["title"]] + s["lines"])
            leaked = _no_jargon(blob)
            self.assertEqual(leaked, [], f"{status}: leaked infra terms {leaked}")


@override_settings(CACHES=LOCMEM)
class OperationsStatusEndpointTest(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = _mk_user("staff@x.com", staff=True)
        self.regular = _mk_user("user@x.com", staff=False)
        self.url = reverse("ai:api_operations_status")

    def test_non_staff_always_healthy(self):
        cache.set(OPS_KEY, {"executive": {"overall_status": "CRITICAL"}}, 60)
        self.client.force_login(self.regular)
        data = self.client.get(self.url).json()
        self.assertEqual(data["state"], "healthy")
        self.assertFalse(data.get("staff"))

    def test_staff_sees_active_state(self):
        # Drive the view directly: staff users are subject to MFA-enforcement
        # middleware (redirects to /user/mfa-required/ in a bare test env), which
        # is unrelated to this endpoint's contract. RequestFactory exercises the
        # view's staff branch deterministically.
        import json
        from django.test import RequestFactory
        from apps.ai.views import OperationsStatusView

        cache.set(OPS_KEY, {"executive": {"overall_status": "DEGRADED"}}, 60)
        req = RequestFactory().get(self.url)
        req.user = self.staff
        resp = OperationsStatusView.as_view()(req)
        data = json.loads(resp.content)
        self.assertEqual(data["state"], "degraded")
        self.assertTrue(data.get("staff"))
        self.assertEqual(data["action_url"], OPS_WALL_URL)

    def test_anonymous_redirected(self):
        self.assertIn(self.client.get(self.url).status_code, (301, 302))


@override_settings(CACHES=LOCMEM)
class RecoveryDeliveryTest(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = _mk_user("ops@x.com", staff=True)

    def test_recovery_message_is_plain_english(self):
        from apps.core.ai_observability.operational_alerts import _build_recovery_message

        class _A:
            severity = "critical"
        msg = _build_recovery_message("scheduler", 92, _A())
        self.assertEqual(_no_jargon(msg), [])
        self.assertIn("recovered", msg.lower())
        self.assertNotIn("92", msg)  # no score

    def test_recovery_slot_guard_allows_once(self):
        from apps.core.ai_observability.operational_alerts import _claim_recovery_message_slot
        self.assertTrue(_claim_recovery_message_slot())
        self.assertFalse(_claim_recovery_message_slot())

    def test_recovery_injects_one_operations_alert_card(self):
        from apps.core.ai_observability.models import OperationalAlert
        from apps.core.ai_observability.operational_alerts import _inject_admin_alert
        from apps.ai.models import AssistantMessage

        alert = OperationalAlert.objects.create(
            subsystem="overall", severity="critical", status="resolved",
            health_score=92, message="x", dedupe_key="overall_critical",
        )
        _inject_admin_alert("WLJ automatically recovered.", alert, level="recovered")
        msgs = AssistantMessage.objects.filter(
            conversation__user=self.staff, message_type="operations_alert"
        )
        self.assertEqual(msgs.count(), 1)
        m = msgs.first()
        self.assertEqual(m.metadata.get("level"), "recovered")
        self.assertEqual(m.metadata.get("action_url"), "/admin-console/ops/")
        self.assertEqual(_no_jargon(m.content), [])

    def test_active_incident_creates_no_chat_message(self):
        """Regression: active degraded/critical must NOT inject a chat message
        (the pinned banner shows active state). Only recovery writes to the
        timeline."""
        from apps.core.ai_observability.operational_alerts import check_and_alert
        from apps.ai.models import AssistantMessage

        # A critical scheduler score would previously inject an alert message.
        check_and_alert({"scheduler": {"score": 20, "details": {}},
                         "engine": {"score": 100},
                         "freshness": {"score": 100},
                         "overall": {"score": 55, "details": {}}})
        self.assertEqual(
            AssistantMessage.objects.filter(message_type="operations_alert").count(),
            0,
        )
        self.assertFalse(
            AssistantMessage.objects.filter(
                metadata__alert_type="coas"
            ).exists()
        )
