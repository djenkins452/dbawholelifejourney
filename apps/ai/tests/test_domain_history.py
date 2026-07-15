# ==============================================================================
# File: apps/ai/tests/test_domain_history.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Model Interface Pillar 1 — the HISTORY branch. Verifies the
#   catalog-driven get_history truth surface re-fronts the canonical Truth
#   Resolution Layer (DomainTruth.history) with honest statuses, and that the
#   Model Interface tool + capability index are wired.
# ==============================================================================
from datetime import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai.cos_services.domain_history import (
    get_domain_history,
    history_capability_index,
    history_capable_domains,
)

User = get_user_model()


def _weigh(user, y, m, d, value):
    from apps.health.models import WeightEntry
    return WeightEntry.objects.create(
        user=user, value=Decimal(str(value)), unit="lb", status="active",
        recorded_at=timezone.make_aware(datetime(y, m, d, 7, 0)),
    )


class DomainHistoryServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="dh@test.com", password="x")
        _weigh(cls.user, 2026, 7, 4, "285.3")
        _weigh(cls.user, 2026, 6, 15, "289.1")

    # --- the core deterministic retrieval (the milestone's canonical example) ---
    def test_weight_on_a_specific_date(self):
        r = get_domain_history(self.user, "health", "weight",
                               period="custom", start="2026-07-04")
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["count"], 1)
        self.assertEqual(r["points"][0]["value"], 285.3)
        self.assertEqual(r["unit"], "lb")
        # composed series, NOT raw rows
        self.assertNotIn("id", r["points"][0])

    def test_weight_over_a_named_period(self):
        r = get_domain_history(self.user, "health", "weight", period="this_year")
        self.assertEqual(r["status"], "ready")
        self.assertGreaterEqual(r["count"], 2)  # both weigh-ins fall in 2026

    # --- honest empty (no data that day) — NEVER a fabricated value or "error" ---
    def test_no_reading_that_day_is_empty_not_error(self):
        r = get_domain_history(self.user, "health", "weight",
                               period="custom", start="2026-07-10")
        self.assertEqual(r["status"], "empty")
        self.assertIn("no weight data", r["reason"].lower())

    # --- honest unsupported: bad metric lists the answerable ones ---
    def test_unsupported_metric_lists_supported(self):
        r = get_domain_history(self.user, "health", "bogus")
        self.assertEqual(r["status"], "unsupported")
        self.assertIn("weight", r["supported_metrics"])

    # --- honest unsupported_domain: unknown domain lists history-capable ones ---
    def test_unknown_domain(self):
        r = get_domain_history(self.user, "not_a_domain", "x")
        self.assertEqual(r["status"], "unsupported_domain")
        self.assertIn("health", r["history_capable_domains"])

    # --- a registered current-only domain answers no history (journal) ---
    def test_current_only_domain_has_no_history(self):
        r = get_domain_history(self.user, "journal", "anything")
        self.assertEqual(r["status"], "unsupported")

    # --- a bad period is unsupported, listing valid windows ---
    def test_bad_period_is_unsupported(self):
        r = get_domain_history(self.user, "health", "weight", period="last_eon")
        self.assertEqual(r["status"], "unsupported")
        self.assertIn("custom", r["valid_periods"])

    # --- provider declares a history metric but doesn't resolve it → unsupported,
    #     never a generic error (medicine 'adherence' is declared-but-raises today) ---
    def test_declared_but_unimplemented_history_is_unsupported(self):
        idx = history_capability_index()
        if "medicine" in idx and "adherence" in idx["medicine"]:
            r = get_domain_history(self.user, "medicine", "adherence")
            self.assertEqual(r["status"], "unsupported")


class HistoryCatalogTests(TestCase):
    def test_health_participates_via_the_catalog(self):
        idx = history_capability_index()
        self.assertIn("health", idx)
        for m in ("weight", "steps", "sleep", "workouts"):
            self.assertIn(m, idx["health"])
        self.assertIn("health", history_capable_domains())


class ModelInterfaceWiringTests(TestCase):
    """The get_history tool is registered, correctly shaped, and dispatched."""

    def test_get_history_registered_in_truth_tools(self):
        from apps.ai.model_interface.constitution import truth_tools, all_tools
        names = [t["function"]["name"] for t in truth_tools()]
        self.assertIn("get_history", names)
        self.assertIn("get_history",
                      [t["function"]["name"] for t in all_tools(writes_enabled=False)])

    def test_get_history_schema_shape(self):
        from apps.ai.model_interface.constitution import truth_tools
        tool = next(t for t in truth_tools()
                    if t["function"]["name"] == "get_history")
        params = tool["function"]["parameters"]
        self.assertEqual(set(params["required"]), {"domain", "metric"})
        self.assertIn("period", params["properties"])
        self.assertIn("start", params["properties"])
        # domain enum is catalog-driven and includes health
        self.assertIn("health", params["properties"]["domain"].get("enum", []))

    def test_capability_index_advertises_history(self):
        from apps.ai.cos_services.current_context import _capabilities
        caps = _capabilities()
        self.assertIn("truth_history", caps)
        self.assertIn("weight", caps["truth_history"].get("health", []))

    def test_dispatch_wraps_history_in_truth_envelope(self):
        # The MI dispatch routes get_history → get_domain_history → truth envelope.
        from apps.ai.model_interface.service import ModelInterfaceService
        user = User.objects.create_user(email="mi@test.com", password="x")
        _weigh(user, 2026, 7, 4, "285.3")
        svc = ModelInterfaceService(user, ai_service=object())  # AI unused for dispatch
        dispatch = svc._make_dispatch(
            turn_id="t", surface="chat", tools_called=[],
        )
        out = dispatch("get_history", {"domain": "health", "metric": "weight",
                                       "period": "custom", "start": "2026-07-04"})
        # canonical truth envelope with provenance
        self.assertIn("status", out)
        self.assertIn("source", out)
        self.assertEqual(out["source"], "history:health.weight")
