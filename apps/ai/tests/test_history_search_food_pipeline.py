# ==============================================================================
# File: apps/ai/tests/test_history_search_food_pipeline.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Regression coverage for the shared conversational historical-search
#              pipeline repair (URL-rot crash class, domain forwarding, registry
#              drift). Origin: nutrition certification exposed that
#              "When was the last time I ate pizza?" reached the model as an error
#              because SearchService._search_health_food reversed a renamed URL
#              (`health:food_log`) → NoReverseMatch → status="error" (2026-07-19).
# ==============================================================================
"""
These tests certify the SHARED search path, using nutrition/food only as the
domain that SURFACED the defect — they assert generic guarantees:

1. A real food-keyword search with matching FoodEntry rows returns truth and
   does not raise NoReverseMatch.
2. A broken/renamed result URL cannot crash the overall historical-search
   response (url degrades to None; truth is preserved).
3. The Model Interface forwards the requested `domain` to search_history unchanged.
4. Nutrition participates through the ONE shared registration mechanism
   (_SEARCH_DOMAIN_MAP → SUPPORTED_HISTORY_DOMAINS) via a real adapter.
5. "pizza" history returns the most recent matching record in correct date order.
6. A domain with no valid search adapter is advertised honestly (unsupported_domain),
   never accepted-then-crashed.
7. Existing Health historical searches keep working.
8. Journal & Faith search participation is explicitly measured and reported.
"""

from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import NoReverseMatch

from apps.ai.cos_services import search_history
from apps.ai.cos_services.history_search import (
    _SEARCH_DOMAIN_MAP,
    SUPPORTED_HISTORY_DOMAINS,
)
from apps.ai.search_service import SearchService
from apps.health.models import FoodEntry

User = get_user_model()


def _food(user, name, d, *, meal="dinner", cal=285):
    return FoodEntry.objects.create(
        user=user, food_name=name, serving_size="1", serving_unit="slice",
        logged_date=d, meal_type=meal, total_calories=cal,
    )


class FoodHistorySearchPipelineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="food_hist@example.com", password="x")
        # Three pizzas on distinct dates (+ one non-pizza) to prove ordering + filtering.
        _food(cls.user, "Pepperoni Pizza", date(2026, 4, 7))
        _food(cls.user, "Cheese Pizza", date(2026, 3, 1))
        _food(cls.user, "Veggie Pizza", date(2026, 2, 15))
        _food(cls.user, "Oatmeal", date(2026, 4, 6), meal="breakfast", cal=150)

    # 1 — real food search returns truth, never NoReverseMatch -----------------
    def test_food_keyword_search_returns_truth_without_noreversematch(self):
        # Directly exercises _search_health_food (the crash site) with matching rows.
        try:
            results = SearchService(self.user)._search_health_food(["pizza"], None, 40)
        except NoReverseMatch as exc:  # pragma: no cover - the bug we fixed
            self.fail(f"food search raised NoReverseMatch: {exc}")
        self.assertEqual(len(results), 3)
        self.assertTrue(all("Pizza" in r["title"] for r in results))

    # 2 — a broken result URL cannot crash the whole response ------------------
    def test_broken_result_url_degrades_to_none_and_preserves_truth(self):
        # Simulate ANY renamed view: force reverse to fail for the food link.
        with mock.patch("apps.ai.search_service.reverse",
                        side_effect=NoReverseMatch("gone")):
            results = SearchService(self.user)._search_health_food(["pizza"], None, 40)
        # Truth survives; only the presentation URL is absent.
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r["url"] is None for r in results))
        self.assertTrue(all(r["date"] for r in results))  # underlying truth intact

    def test_safe_reverse_returns_none_on_missing_view(self):
        self.assertIsNone(SearchService(self.user)._safe_reverse("health:definitely_gone"))

    # 4 — nutrition registered through the ONE shared mechanism ----------------
    def test_nutrition_registered_via_shared_mechanism(self):
        self.assertIn("nutrition", SUPPORTED_HISTORY_DOMAINS)
        self.assertEqual(_SEARCH_DOMAIN_MAP["nutrition"], "search_nutrition")
        # The adapter actually exists and honors the (keywords=, limit=) contract.
        self.assertTrue(hasattr(SearchService(self.user), "search_nutrition"))
        out = SearchService(self.user).search_nutrition(keywords=["pizza"], limit=10)
        self.assertEqual(out["module"], "nutrition")
        self.assertEqual(out["count"], 3)

    # 5 — pizza history: most recent first, correct date order -----------------
    def test_pizza_history_most_recent_first(self):
        env = search_history(self.user, "pizza", domain="nutrition")
        self.assertEqual(env["status"], "ready")
        self.assertEqual(env["count"], 3)
        dates = [r["date"] for r in env["results"]]
        self.assertEqual(dates, sorted(dates, reverse=True))
        self.assertEqual(env["results"][0]["date"], "2026-04-07")
        self.assertIn("Pepperoni", env["results"][0]["title"])

    # 6 — a domain with no adapter is honest, never an accidental error --------
    def test_domain_without_adapter_is_honest_not_error(self):
        env = search_history(self.user, "anything", domain="legacy")
        self.assertEqual(env["status"], "unsupported_domain")
        self.assertIn("supported_domains", env)
        self.assertNotIn("legacy", env["supported_domains"])

    # 7 — existing Health searches keep working --------------------------------
    def test_health_metric_search_still_works(self):
        # A full health search fans out across ALL metric types (incl. the food
        # sub-search that used to crash). It must complete and surface the food rows.
        out = SearchService(self.user).search_health(keywords=["pizza"], limit=40)
        titles = " ".join(r["title"] for r in out["results"])
        self.assertIn("Pizza", titles)          # food branch survived the fan-out
        env = search_history(self.user, "pizza", domain="health")
        self.assertEqual(env["status"], "ready")

    # 8 — Journal & Faith participation explicitly measured --------------------
    def test_journal_and_faith_participation_reported(self):
        report = {
            d: {
                "registered": d in SUPPORTED_HISTORY_DOMAINS,
                "adapter": _SEARCH_DOMAIN_MAP.get(d),
                "adapter_exists": hasattr(SearchService(self.user),
                                          _SEARCH_DOMAIN_MAP.get(d, "")),
            }
            for d in ("journal", "faith", "nutrition")
        }
        # Journal & Faith already participate with real adapters (their deeper
        # conversational certification is a separate, later milestone).
        for d in ("journal", "faith", "nutrition"):
            self.assertTrue(report[d]["registered"], f"{d} not registered")
            self.assertTrue(report[d]["adapter_exists"], f"{d} adapter missing")


class ModelInterfaceDomainForwardingTests(TestCase):
    """3 — the Model Interface must forward the model's requested domain unchanged."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="mi_fwd@example.com", password="x")

    def test_dispatch_forwards_domain_to_search_history(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        svc = ModelInterfaceService(self.user)
        dispatch = svc._make_dispatch(turn_id="t", surface="chat", tools_called=[])
        with mock.patch("apps.ai.model_interface.service.search_history",
                        return_value={"status": "empty"}) as sh:
            dispatch("search_history", {"query": "pizza", "domain": "nutrition"})
        sh.assert_called_once()
        self.assertEqual(sh.call_args.kwargs.get("domain"), "nutrition")
        self.assertEqual(sh.call_args.args[1], "pizza")
