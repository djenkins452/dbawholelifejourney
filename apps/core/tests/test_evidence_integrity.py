# ==============================================================================
# File: apps/core/tests/test_evidence_integrity.py
# Description: EVIDENCE INTEGRITY VALIDATION (Layer 1 platform capability). Before
#   Beth presents deterministic truth, the evidence must survive integrity
#   invariants: TEMPORAL (no future timestamp / negative duration), SEQUENCE
#   ("previous" precedes "current"; not a duplicate; not missing), EVIDENCE
#   (not stale-as-current; sources agree). On failure she does NOT confidently
#   present — she transitions to investigation.
#   Origin: Beth reported "current glucose 113 · previous 113 · recorded 11:07 AM"
#   at 10:11 AM — a duplicated predecessor with an impossible future timestamp,
#   presented with full confidence and no investigation.
# ==============================================================================
from datetime import datetime, timedelta, timezone as _tz
from unittest import mock

from django.test import SimpleTestCase

from apps.core.truth import integrity as I


class ValidateEvidenceTests(SimpleTestCase):
    def setUp(self):
        self.now = datetime(2026, 6, 27, 10, 11, tzinfo=_tz.utc)

    def _ts(self, **kw):
        return self.now + timedelta(**kw)

    # ── passes cleanly ────────────────────────────────────────────────────────
    def test_sound_evidence_passes(self):
        v = I.validate_evidence(
            {"value": 113, "recorded_at": self._ts(minutes=-30),
             "presented_as": "current", "freshness": "current"}, self.now)
        self.assertTrue(v["ok"])
        self.assertEqual(v["integrity"], I.OK)
        self.assertEqual(v["violations"], [])
        self.assertEqual(v["investigation"], "")

    # ── TEMPORAL ──────────────────────────────────────────────────────────────
    def test_future_timestamp_is_impossible(self):
        v = I.validate_evidence(
            {"value": 113, "recorded_at": self._ts(minutes=56)}, self.now)  # 11:07
        self.assertEqual(v["integrity"], I.IMPOSSIBLE)
        self.assertFalse(v["ok"])
        self.assertTrue(any(x["code"] == I.FUTURE_TIMESTAMP for x in v["violations"]))
        self.assertIn("doesn't add up", v["investigation"])

    def test_upstream_temporal_warning_is_honored(self):
        # SAE already dropped the impossible time and left a warning — still impossible.
        v = I.validate_evidence(
            {"value": 113, "recorded_at": None,
             "temporal_warning": "future/sync issue"}, self.now)
        self.assertEqual(v["integrity"], I.IMPOSSIBLE)

    def test_negative_duration_is_impossible(self):
        v = I.validate_evidence(
            {"value": 6.1, "start": self._ts(hours=1), "end": self.now}, self.now)
        self.assertTrue(any(x["code"] == I.NEGATIVE_DURATION for x in v["violations"]))

    # ── SEQUENCE ──────────────────────────────────────────────────────────────
    def test_duplicate_predecessor_is_the_production_case(self):
        # current 113 @10:00, "previous" 113 with no earlier timestamp → not a
        # distinct prior reading → investigate.
        v = I.validate_evidence(
            {"value": 113, "recorded_at": self._ts(minutes=-11),
             "predecessor": {"value": 113, "recorded_at": None}}, self.now)
        self.assertFalse(v["ok"])
        self.assertTrue(any(x["code"] == I.DUPLICATE_PREDECESSOR
                            for x in v["violations"]))

    def test_previous_after_current_is_out_of_order(self):
        v = I.validate_evidence(
            {"value": 120, "recorded_at": self._ts(minutes=-60),
             "predecessor": {"value": 100, "recorded_at": self._ts(minutes=-10)}},
            self.now)
        self.assertTrue(any(x["code"] == I.SEQUENCE_OUT_OF_ORDER
                            for x in v["violations"]))
        self.assertEqual(v["integrity"], I.IMPOSSIBLE)

    def test_distinct_ordered_predecessor_passes(self):
        v = I.validate_evidence(
            {"value": 120, "recorded_at": self._ts(minutes=-10),
             "predecessor": {"value": 100, "recorded_at": self._ts(minutes=-70)}},
            self.now)
        self.assertTrue(v["ok"])

    def test_missing_predecessor_when_expected(self):
        v = I.validate_evidence(
            {"value": 113, "recorded_at": self._ts(minutes=-10),
             "predecessor_expected": True}, self.now)
        self.assertTrue(any(x["code"] == I.MISSING_PREDECESSOR
                            for x in v["violations"]))

    # ── EVIDENCE ──────────────────────────────────────────────────────────────
    def test_stale_presented_as_current_is_suspect(self):
        v = I.validate_evidence(
            {"value": 113, "recorded_at": self._ts(hours=-40),
             "presented_as": "current", "freshness": "stale"}, self.now)
        self.assertEqual(v["integrity"], I.SUSPECT)
        self.assertTrue(any(x["code"] == I.STALE_AS_CURRENT for x in v["violations"]))

    def test_source_conflict(self):
        v = I.validate_evidence(
            {"value": 113,
             "sources": [{"source": "dexcom", "value": 113},
                         {"source": "manual", "value": 150}]}, self.now)
        self.assertTrue(any(x["code"] == I.SOURCE_CONFLICT for x in v["violations"]))

    def test_agreeing_sources_pass(self):
        v = I.validate_evidence(
            {"value": 113,
             "sources": [{"source": "dexcom", "value": 113},
                         {"source": "manual", "value": 114}]}, self.now)
        self.assertTrue(v["ok"])


class AttachHelperTests(SimpleTestCase):
    def setUp(self):
        self.now = datetime(2026, 6, 27, 10, 11, tzinfo=_tz.utc)

    def test_attach_flags_future_and_drops_time_backcompat(self):
        fact = {"value": 95, "unit": "mg/dL",
                "recorded_at": (self.now + timedelta(hours=1)).isoformat()}
        I.attach(fact, now=self.now)
        self.assertFalse(fact["integrity"]["ok"])
        self.assertIn("temporal_warning", fact)          # legacy contract preserved
        self.assertNotIn("recorded_at", fact)            # impossible time dropped
        self.assertEqual(fact["value"], 95)              # value object still stands

    def test_attach_noop_for_sound_fact(self):
        fact = {"value": 95, "recorded_at": (self.now - timedelta(minutes=5)).isoformat()}
        I.attach(fact, now=self.now)
        # A sound fact stays lean — no integrity key, zero added payload.
        self.assertNotIn("integrity", fact)
        self.assertFalse(I.failed(fact))
        self.assertIn("recorded_at", fact)

    def test_failed_and_investigation_helpers(self):
        bad = {"value": 1, "integrity": {"ok": False, "investigation": "look into it"}}
        good = {"value": 1, "integrity": {"ok": True}}
        self.assertTrue(I.failed(bad))
        self.assertFalse(I.failed(good))
        self.assertEqual(I.investigation_for(bad), "look into it")
        self.assertEqual(I.investigation_for(good), "")


_GMS = "apps.core.ai_state.state_engine.get_module_state"


class PresentationGateTests(SimpleTestCase):
    """A CoS never confidently presents evidence that fails integrity — she
    investigates. Proven end-to-end through the deterministic fact presentation."""

    def test_glucose_future_timestamp_triggers_investigation_not_confident_value(self):
        from django.utils import timezone
        from apps.ai.cos_services.health_facts import get_foundational_health_facts
        from apps.ai.chatgpt_cos.foundational_facts import format_fact_sentence
        future_iso = (timezone.now() + timedelta(hours=1)).isoformat()
        state = {"latest_glucose": 113, "latest_glucose_unit": "mg/dL",
                 "last_glucose_entry": future_iso}
        with mock.patch(_GMS, return_value=state):
            fact = get_foundational_health_facts(
                None, ["last_glucose_reading"])["last_glucose_reading"]
        # composition attached a failing verdict + preserved the legacy warning
        self.assertFalse(fact["integrity"]["ok"])
        self.assertIn("temporal_warning", fact)
        answer = format_fact_sentence("last_glucose_reading", fact).lower()
        # investigation, not a confident "your last glucose reading was 113"
        self.assertIn("doesn't add up", answer)
        self.assertIn("future", answer)
        self.assertNotIn("your last glucose reading was 113", answer)

    def test_sound_glucose_still_presents_normally(self):
        from django.utils import timezone
        from apps.ai.cos_services.health_facts import get_foundational_health_facts
        from apps.ai.chatgpt_cos.foundational_facts import format_fact_sentence
        recent_iso = (timezone.now() - timedelta(minutes=20)).isoformat()
        state = {"latest_glucose": 113, "latest_glucose_unit": "mg/dL",
                 "last_glucose_entry": recent_iso}
        with mock.patch(_GMS, return_value=state):
            fact = get_foundational_health_facts(
                None, ["last_glucose_reading"])["last_glucose_reading"]
        self.assertFalse(I.failed(fact))
        answer = format_fact_sentence("last_glucose_reading", fact).lower()
        self.assertIn("113", answer)
        self.assertNotIn("doesn't add up", answer)


class ConversationFollowupTests(SimpleTestCase):
    """The production follow-up chain: 'what was the previous reading?' must not
    yield a duplicated/impossible comparison — it investigates."""

    def test_duplicate_previous_reading_investigates(self):
        from apps.ai.chatgpt_cos.conversation_memory import compose_comparison
        last = {
            "fact": {"value": 113, "unit": "mg/dL", "recorded_at": None},
            "supporting": {"prior": {"fact": {"value": 113, "recorded_at": None}}},
        }
        out = compose_comparison(last, kind="prior")
        self.assertIsNotNone(out)
        self.assertIn("doesn't add up", out.lower())

    def test_real_distinct_prior_still_compares(self):
        from django.utils import timezone
        from apps.ai.chatgpt_cos.conversation_memory import compose_comparison
        now = timezone.now()
        last = {
            "fact": {"value": 120, "unit": "mg/dL",
                     "recorded_at": (now - timedelta(minutes=10)).isoformat()},
            "supporting": {"prior": {"fact": {
                "value": 100,
                "recorded_at": (now - timedelta(hours=26)).isoformat()}}},
        }
        out = compose_comparison(last, kind="prior")
        self.assertIsNotNone(out)
        self.assertNotIn("doesn't add up", out.lower())
        self.assertIn("20", out)     # 100 -> 120 delta
