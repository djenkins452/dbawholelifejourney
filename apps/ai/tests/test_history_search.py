# ==============================================================================
# File: apps/ai/tests/test_history_search.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for the ChatGPT CoS HistorySearchService (Phase 5)
# ==============================================================================
"""
Phase 5 — search_history tests.

Verifies the historical retrieval surface REUSES existing search infrastructure
(SearchService + search_notes_cos), maps domains/aliases correctly, applies
timeframe filtering deterministically, and never fabricates (empty stays empty).
"""

import json
from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_services import search_history
from apps.ai.cos_services.history_search import _parse_timeframe

User = get_user_model()

_SVC = "apps.ai.search_service.SearchService"
_NOTES = "apps.notes.services.search_notes_cos"


def _result(rid, d):
    return {"id": rid, "title": f"t{rid}", "snippet": "s", "date": d,
            "url": f"/x/{rid}/", "metadata": {}}


class TimeframeParseTests(TestCase):
    def test_none(self):
        self.assertIsNone(_parse_timeframe(None))
        self.assertIsNone(_parse_timeframe(""))

    def test_days(self):
        rng = _parse_timeframe("7d")
        self.assertIsNotNone(rng)
        self.assertEqual((rng[1] - rng[0]).days, 7)

    def test_named_window(self):
        rng = _parse_timeframe("year")
        self.assertEqual((rng[1] - rng[0]).days, 365)

    def test_explicit_range(self):
        rng = _parse_timeframe("2026-01-01:2026-03-01")
        self.assertEqual(rng[0], date(2026, 1, 1))
        self.assertEqual(rng[1], date(2026, 3, 1))

    def test_garbage_is_none(self):
        self.assertIsNone(_parse_timeframe("whenever"))


class HistorySearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="cos_hist@example.com", password="x")

    def _svc(self, **method_returns):
        inst = mock.MagicMock()
        for name, val in method_returns.items():
            getattr(inst, name).return_value = val
        return inst

    def test_domain_maps_to_search_method_with_keywords(self):
        inst = self._svc(search_journal={"results": [_result(1, "2026-06-01")]})
        with mock.patch(_SVC, return_value=inst):
            env = search_history(self.user, "anxiety sleep", domain="journal")
        self.assertEqual(env["status"], "ready")
        self.assertEqual(env["count"], 1)
        inst.search_journal.assert_called_once()
        self.assertEqual(inst.search_journal.call_args.kwargs["keywords"],
                         ["anxiety", "sleep"])

    def test_exposure_alias_purpose_to_goals(self):
        inst = self._svc(search_goals={"results": [_result(2, "2026-06-01")]})
        with mock.patch(_SVC, return_value=inst):
            env = search_history(self.user, "habit", domain="purpose")
        self.assertEqual(env["status"], "ready")
        inst.search_goals.assert_called_once()

    def test_default_domain_uses_search_all(self):
        inst = self._svc(search_all={"results": [_result(3, "2026-06-01")]})
        with mock.patch(_SVC, return_value=inst):
            env = search_history(self.user, "discouraged")  # domain=None -> all
        self.assertEqual(env["domain"], "all")
        self.assertEqual(env["status"], "ready")
        inst.search_all.assert_called_once()

    def test_notes_uses_search_notes_cos(self):
        with mock.patch(_NOTES, return_value={"results": [{"id": 9, "title": "n",
                        "date": "2026-06-01"}]}) as notes_fn:
            env = search_history(self.user, "sermon", domain="notes")
        self.assertEqual(env["status"], "ready")
        notes_fn.assert_called_once()
        self.assertEqual(env["_meta"]["source"], "search_notes_cos")

    def test_timeframe_filters_results(self):
        inst = self._svc(search_journal={"results": [
            _result(1, "2026-06-15"),   # in range
            _result(2, "2026-01-01"),   # out of range
            _result(3, None),           # undated -> excluded when timeframe set
        ]})
        with mock.patch(_SVC, return_value=inst):
            env = search_history(self.user, "x", domain="journal",
                                 timeframe="2026-06-01:2026-06-30")
        ids = [r["id"] for r in env["results"]]
        self.assertEqual(ids, [1])

    def test_empty_results_status_empty_no_fabrication(self):
        inst = self._svc(search_journal={"results": []})
        with mock.patch(_SVC, return_value=inst):
            env = search_history(self.user, "nothing", domain="journal")
        self.assertEqual(env["status"], "empty")
        self.assertEqual(env["count"], 0)
        self.assertEqual(env["results"], [])

    def test_unsupported_domain(self):
        env = search_history(self.user, "x", domain="telepathy")
        self.assertEqual(env["status"], "unsupported_domain")
        self.assertIn("supported_domains", env)

    def test_error_is_surfaced_not_swallowed(self):
        with mock.patch(_SVC, side_effect=RuntimeError("db down")):
            env = search_history(self.user, "x", domain="journal")
        self.assertEqual(env["status"], "error")
        self.assertNotIn("results", env)

    def test_output_json_serializable(self):
        inst = self._svc(search_journal={"results": [_result(1, "2026-06-01")]})
        with mock.patch(_SVC, return_value=inst):
            env = search_history(self.user, "x", domain="journal")
        json.dumps(env)


class HistoryToolDispatchTests(TestCase):
    """search_history is reachable through the CoS tool dispatcher (Phase 5 enabled)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="cos_hist2@example.com", password="x")

    def test_dispatch_search_history(self):
        from apps.ai.cos_services import dispatch_tool_call
        inst = mock.MagicMock()
        inst.search_all.return_value = {"results": []}
        with mock.patch(_SVC, return_value=inst):
            env = dispatch_tool_call(self.user, "search_history", {"query": "stress"})
        self.assertTrue(env["ok"])
        self.assertEqual(env["result"]["status"], "empty")
