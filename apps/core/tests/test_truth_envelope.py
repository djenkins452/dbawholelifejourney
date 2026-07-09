# ==============================================================================
# File: apps/core/tests/test_truth_envelope.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The canonical truth-tool envelope (Pillar 1 of the model interface).
# ==============================================================================
"""
Tests for apps/core/truth/envelope.py — the single shape every WLJ truth answer wears.

Locks in: deterministic status/confidence derivation, first-class honest-absence
constructors, the CurrentTruth adapter, the integrity gate (impossible withholds the
value; suspect hedges), and JSON-safety.
"""

import json

from django.test import SimpleTestCase

from apps.core.truth import confidence as _conf
from apps.core.truth import freshness as _fresh
from apps.core.truth.current import CurrentTruth
from apps.core.truth import envelope as env


class MakeEnvelopeTests(SimpleTestCase):
    def test_present_value_derives_ok_status_and_confidence(self):
        e = env.make_envelope(6.2, freshness=_fresh.CURRENT, source="Apple Health",
                              as_of="2026-07-09T07:41:00", unit="h")
        self.assertEqual(e["status"], env.STATUS_OK)
        self.assertEqual(e["value"], 6.2)
        self.assertEqual(e["freshness"], _fresh.CURRENT)
        self.assertEqual(e["source"], "Apple Health")
        self.assertEqual(e["unit"], "h")
        self.assertIn(e["confidence"], (_conf.LOW, _conf.MEDIUM, _conf.HIGH))
        json.dumps(e)

    def test_stale_present_is_ok_but_carries_freshness(self):
        e = env.make_envelope(70.1, freshness=_fresh.STALE, source="scale")
        self.assertEqual(e["status"], env.STATUS_OK)
        self.assertEqual(e["freshness"], _fresh.STALE)


class HonestAbsenceTests(SimpleTestCase):
    def test_pending(self):
        e = env.pending(source="Apple Health")
        self.assertEqual(e["status"], env.STATUS_PENDING)
        self.assertIsNone(e["value"])
        self.assertEqual(e["confidence"], _conf.NONE)

    def test_missing(self):
        self.assertEqual(env.missing()["status"], env.STATUS_MISSING)

    def test_insufficient_evidence(self):
        e = env.insufficient_evidence(reason="two sources disagree")
        self.assertEqual(e["status"], env.STATUS_INSUFFICIENT_EVIDENCE)
        self.assertEqual(e["reason"], "two sources disagree")

    def test_empty_is_a_valid_result(self):
        e = env.empty(source="search")
        self.assertEqual(e["status"], env.STATUS_EMPTY)
        self.assertEqual(e["value"], [])
        self.assertEqual(e["confidence"], _conf.HIGH)

    def test_error_reports_failure_not_ai_unavailable(self):
        e = env.error("db timeout", source="finance")
        self.assertEqual(e["status"], env.STATUS_ERROR)
        self.assertEqual(e["reason"], "db timeout")
        self.assertEqual(e["confidence"], _conf.NONE)


class FromCurrentTruthTests(SimpleTestCase):
    def test_present_current_truth_maps_to_ok(self):
        ct = CurrentTruth.found("health", "weight", 182.0, _fresh.CURRENT,
                                unit="lb", as_of="2026-07-09", source="scale")
        e = env.from_current_truth(ct)
        self.assertEqual(e["status"], env.STATUS_OK)
        self.assertEqual(e["value"], 182.0)
        self.assertEqual(e["unit"], "lb")
        self.assertEqual(e["source"], "scale")

    def test_absent_pending_maps_to_pending(self):
        ct = CurrentTruth.absent("health", "sleep", freshness=_fresh.PENDING,
                                 reason="not synced")
        e = env.from_current_truth(ct)
        self.assertEqual(e["status"], env.STATUS_PENDING)
        self.assertIsNone(e["value"])

    def test_absent_missing_maps_to_missing(self):
        ct = CurrentTruth.absent("finance", "payroll", freshness=_fresh.MISSING)
        self.assertEqual(env.from_current_truth(ct)["status"], env.STATUS_MISSING)


class IntegrityGateTests(SimpleTestCase):
    def test_ok_claim_leaves_envelope_unchanged(self):
        e = env.make_envelope(72, freshness=_fresh.CURRENT, source="cgm")
        out = env.apply_integrity(e, {"value": 72, "freshness": _fresh.CURRENT})
        self.assertEqual(out["status"], env.STATUS_OK)
        self.assertNotIn("investigation", out)

    def test_impossible_withholds_value_and_downgrades(self):
        e = env.make_envelope(113, freshness=_fresh.CURRENT, source="cgm",
                              confidence=_conf.HIGH)
        # A future-timestamp claim is IMPOSSIBLE (self-contradictory).
        out = env.apply_integrity(
            e, {"value": 113, "temporal_warning": "future ts dropped",
                "presented_as": "current"})
        self.assertEqual(out["status"], env.STATUS_INSUFFICIENT_EVIDENCE)
        self.assertIsNone(out["value"])
        self.assertEqual(out["confidence"], _conf.NONE)
        self.assertTrue(out["investigation"])
        self.assertEqual(out["integrity"], "impossible")

    def test_suspect_keeps_value_but_hedges_confidence(self):
        e = env.make_envelope(70.0, freshness=_fresh.STALE, source="scale",
                              confidence=_conf.HIGH)
        # stale value presented as current → SUSPECT.
        out = env.apply_integrity(
            e, {"value": 70.0, "freshness": _fresh.STALE, "presented_as": "current"})
        self.assertEqual(out["value"], 70.0)                 # value kept
        self.assertEqual(out["confidence"], _conf.LOW)       # hedged down
        self.assertTrue(out["investigation"])
        self.assertEqual(out["integrity"], "suspect")
