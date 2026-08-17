# ==============================================================================
# File: apps/ai/tests/test_llm_cost_accounting.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Cost-governance milestone (2026-08-16) acceptance tests.
#   (1) Usage accounting — every recorded provider request becomes ONE LLMUsageEvent with
#       provenance (source/traffic_class), cost from the PriceBook, failures represented.
#   (2) Certification traffic is classified distinctly from customer traffic.
#   (3) Proactive cost avoidance — a deterministically-suppressed opportunity makes ZERO
#       model calls, and a duplicate scheduler pass reserves once (no duplicate generation).
#   (4) Operator visibility — the read-only cost-summary endpoint aggregates by class/source/model.
# ==============================================================================
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, Client

from apps.ai.llm_accounting import (llm_traffic_context, record_llm_event,
                                    TRAFFIC_CERTIFICATION, TRAFFIC_PRODUCTION,
                                    SOURCE_INTERACTIVE_CHAT)
from apps.owner_finance.models import (LLMPriceBook, LLMUsageEvent, ThirdPartyVendor)
from apps.users.models import TermsAcceptance

try:
    from apps.users.models import User
except ImportError:
    from django.contrib.auth import get_user_model
    User = get_user_model()


def _user(email="cost@test.com", *, proactive=True):
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    p = u.preferences
    p.has_completed_onboarding = True
    p.personal_assistant_enabled = True
    p.assistant_proactive_checkins = proactive
    p.save()
    return u


class UsageAccountingTests(TestCase):
    def setUp(self):
        self.user = _user()

    def test_records_one_event_with_provenance(self):
        record_llm_event(model="gpt-4o", user=self.user, prompt_tokens=1200,
                         completion_tokens=300, total_tokens=1500, success=True,
                         latency_ms=850, endpoint="model_interface")
        self.assertEqual(LLMUsageEvent.objects.count(), 1)
        ev = LLMUsageEvent.objects.get()
        self.assertEqual(ev.input_tokens, 1200)
        self.assertEqual(ev.output_tokens, 300)
        self.assertEqual(ev.model_name, "gpt-4o")
        self.assertTrue(ev.success)
        self.assertEqual(ev.traffic_class, TRAFFIC_PRODUCTION)      # default
        self.assertEqual(ev.source, SOURCE_INTERACTIVE_CHAT)        # derived from endpoint
        self.assertEqual(ev.latency_ms, 850)

    def test_certification_context_tags_traffic_class(self):
        with llm_traffic_context(traffic_class=TRAFFIC_CERTIFICATION):
            record_llm_event(model="gpt-4o", user=self.user, prompt_tokens=10,
                             completion_tokens=5, success=True, endpoint="model_interface")
        self.assertEqual(LLMUsageEvent.objects.get().traffic_class, TRAFFIC_CERTIFICATION)

    def test_failure_recorded_honestly(self):
        record_llm_event(model="gpt-4o", user=self.user, success=False,
                         endpoint="model_interface", error_class="APITimeoutError")
        ev = LLMUsageEvent.objects.get()
        self.assertFalse(ev.success)
        self.assertEqual(ev.input_tokens, 0)

    def test_cost_computed_from_pricebook(self):
        vendor = ThirdPartyVendor.objects.create(name="OpenAI", category="LLM")
        LLMPriceBook.objects.create(
            vendor=vendor, model_name="gpt-4o", effective_start=date(2020, 1, 1),
            input_cost_per_1m_tokens_usd=Decimal("2.50"),
            output_cost_per_1m_tokens_usd=Decimal("10.00"), is_active=True)
        record_llm_event(model="gpt-4o", user=self.user, prompt_tokens=1_000_000,
                         completion_tokens=1_000_000, success=True, endpoint="model_interface")
        ev = LLMUsageEvent.objects.get()
        # 1M input @ $2.50 + 1M output @ $10.00 = $12.50
        self.assertEqual(ev.cost_usd, Decimal("12.500000"))

    def test_synthesis_source_survives_certification_class(self):
        # A certification broad turn: tool rounds are interactive_chat, synthesis is
        # executive_synthesis, BOTH under traffic_class=certification.
        with llm_traffic_context(traffic_class=TRAFFIC_CERTIFICATION):
            record_llm_event(model="gpt-4o", user=self.user, prompt_tokens=1, success=True,
                             endpoint="model_interface")
            record_llm_event(model="gpt-4o", user=self.user, prompt_tokens=1, success=True,
                             endpoint="model_interface_synthesis")
        classes = set(LLMUsageEvent.objects.values_list("traffic_class", flat=True))
        sources = set(LLMUsageEvent.objects.values_list("source", flat=True))
        self.assertEqual(classes, {TRAFFIC_CERTIFICATION})
        self.assertEqual(sources, {"interactive_chat", "executive_synthesis"})


class ProactiveCostAvoidanceTests(TestCase):
    def setUp(self):
        self.user = _user("proactive@test.com")

    def test_suppressed_opportunity_makes_zero_model_calls(self):
        from apps.ai import proactive_checkins as pc
        with patch("apps.ai.affirmation_detector.is_activity_affirmed", return_value=True), \
             patch("apps.ai.beth_checkin_renderer.render_checkin_for_time") as render:
            pc.generate_midday_alignment_for_user(self.user)
        render.assert_not_called()   # deterministic suppression → NO generation
        self.assertEqual(LLMUsageEvent.objects.count(), 0)

    def test_duplicate_scheduler_pass_reserves_once(self):
        svc = pc_service(self.user)
        self.assertTrue(svc._reserve_proactive_slot("evening_wrap"))
        self.assertFalse(svc._reserve_proactive_slot("evening_wrap"))  # 2nd pass blocked

    def test_unsuppressed_generates_once_then_deduped(self):
        from apps.ai import proactive_checkins as pc
        with patch("apps.ai.affirmation_detector.is_activity_affirmed", return_value=False), \
             patch("apps.core.blueprint.conversation_mode.should_suppress_proactive",
                   return_value=False), \
             patch("apps.ai.beth_checkin_renderer.render_checkin_for_time",
                   return_value="Evening focus: your one open item is the report.") as render:
            pc.generate_evening_wrap_for_user(self.user)
            pc.generate_evening_wrap_for_user(self.user)   # duplicate pass, same day
        self.assertEqual(render.call_count, 1)             # reserved once → one generation


def pc_service(user):
    from apps.ai.proactive_checkins import get_proactive_service
    return get_proactive_service(user)


class CostSummaryEndpointTests(TestCase):
    def setUp(self):
        self.user = _user("op@test.com")
        LLMUsageEvent.objects.create(
            user=self.user, feature="COS_CHAT", model_name="gpt-4o",
            source="interactive_chat", traffic_class=TRAFFIC_PRODUCTION,
            input_tokens=1000, output_tokens=200, cost_usd=Decimal("0.0045"), success=True)
        LLMUsageEvent.objects.create(
            user=self.user, feature="COS_CHAT", model_name="gpt-4o",
            source="executive_synthesis", traffic_class=TRAFFIC_CERTIFICATION,
            input_tokens=5000, output_tokens=400, cost_usd=Decimal("0.0165"), success=True)

    def test_endpoint_breaks_down_by_class_source_model(self):
        key = getattr(settings, "CLAUDE_API_KEY", "") or "test-key"
        with self.settings(CLAUDE_API_KEY=key):
            resp = Client().get("/admin-console/api/claude/cost-summary/?days=7",
                                HTTP_X_CLAUDE_API_KEY=key)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        window = data["last_7_days"]
        self.assertEqual(window["calls"], 2)
        classes = {r["key"] for r in window["by_traffic_class"]}
        self.assertEqual(classes, {"production", "certification"})
        sources = {r["key"] for r in window["by_source"]}
        self.assertIn("executive_synthesis", sources)
        self.assertEqual({r["key"] for r in window["by_model"]}, {"gpt-4o"})

    def test_endpoint_requires_api_key(self):
        with self.settings(CLAUDE_API_KEY="secret-key"):
            resp = Client().get("/admin-console/api/claude/cost-summary/")
        self.assertEqual(resp.status_code, 401)
