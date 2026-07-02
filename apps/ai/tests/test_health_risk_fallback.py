# ==============================================================================
# File: apps/ai/tests/test_health_risk_fallback.py
# Description: Deterministic biggest_health_risk fallback must be a COMPLETE, actionable,
#   evidence-backed answer (top risk + evidence + concrete next action + why) and pass the
#   real acceptance rule `gate_actionable`. Origin: Acceptance Run #62 — the fallback
#   identified the risk but the response failed gate_actionable. No OpenAI involved.
# ==============================================================================
from django.test import SimpleTestCase

from apps.ai.chatgpt_cos.reasoning.stages import _rank_health_concerns, _health_risk_fallback
from apps.ai.chatgpt_cos.acceptance_rules import is_actionable


class HealthRiskFallbackTests(SimpleTestCase):
    def _fallback(self, buckets):
        return _health_risk_fallback({"facts": {"ranked_concerns": _rank_health_concerns(buckets)}})

    def test_sleep_trend_is_actionable_and_evidence_backed(self):
        # The exact Run #62 failure: sleep trending down.
        ans = self._fallback({"major_trends": {"sleep_trend": "decreasing"}})
        self.assertTrue(is_actionable(ans), ans)          # gate_actionable now PASSES
        self.assertIn("worth your attention", ans.lower())  # the top risk
        self.assertIn("evidence", ans.lower())              # the evidence behind it
        self.assertIn("bedtime", ans.lower())               # a concrete next action
        self.assertIn("why it matters", ans.lower())        # why it matters

    def test_every_concern_type_yields_an_actionable_answer(self):
        cases = [
            {"current_status": {"latest_glucose": 200}},                 # glucose high
            {"active_risks": {"glucose_variability_label": "high"}},     # glucose swings
            {"current_status": {"sleep_avg_hours_7d": 5.4}},             # short sleep
            {"major_trends": {"sleep_trend": "decreasing"}},             # sleep trending down
            {"goal_progress": {"weight_goal_on_track": False}},          # weight pace
            {"active_risks": {"plateau_risk_label": "elevated"}},        # plateau
            {"active_risks": {"muscle_loss_risk_level": "elevated"}},    # muscle
            {"nutrition_context": {"protein_g": {"interpretation": "below_typical_for_time_of_day"}}},
        ]
        for b in cases:
            ans = self._fallback(b)
            self.assertTrue(is_actionable(ans), f"{b} -> {ans}")   # every one is actionable
            self.assertIn("worth your attention", ans.lower(), b)

    def test_glucose_evidence_cites_the_value(self):
        ans = self._fallback({"current_status": {"latest_glucose": 195}})
        self.assertIn("195", ans)                           # evidence cites the number
        self.assertIn("evidence", ans.lower())

    def test_no_concern_answer_is_still_actionable(self):
        ans = _health_risk_fallback({"facts": {"ranked_concerns": []}})
        self.assertTrue(is_actionable(ans), ans)

    def test_concern_object_is_complete(self):
        # Every ranked concern carries the four contract parts.
        concerns = _rank_health_concerns({"current_status": {"sleep_avg_hours_7d": 5.0}})
        self.assertTrue(concerns)
        for key in ("concern", "evidence", "action", "why"):
            self.assertIn(key, concerns[0])
            self.assertTrue(concerns[0][key])
