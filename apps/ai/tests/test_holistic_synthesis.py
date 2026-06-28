# ==============================================================================
# File: apps/ai/tests/test_holistic_synthesis.py
# Description: Defect Class 4 (Holistic Synthesis) — "how am I doing" must SYNTHESIZE
#   across every populated facet (weight, glucose, sleep, activity), not collapse to
#   sleep. Also locks the 3rd instance of the glucose-safety blocker inside the
#   overall_progress fallback. Origin: real Beth conversation.
# ==============================================================================
from django.test import SimpleTestCase

from apps.ai.chatgpt_cos.reasoning.stages import _health_progress_fallback, _H_STATUS


class HolisticSynthesisTests(SimpleTestCase):
    def _wm(self, **status):
        return {"facts": {"current_status": status, "trends": {}, "goal_progress": {},
                          "ranked_concerns": [{"concern": "sleep", "action": "wind down"}]}}

    def test_enumerates_all_facets_not_just_sleep(self):
        wm = self._wm(weight_current=285, weight_unit="lb", latest_glucose=110,
                      latest_glucose_unit="mg/dL", sleep_avg_hours_7d=6.2,
                      steps_avg_7d=8200)
        out = _health_progress_fallback(wm).lower()
        self.assertIn("weight", out)
        self.assertIn("glucose", out)
        self.assertIn("sleep", out)
        self.assertIn("steps", out)            # activity is no longer dropped

    def test_activity_is_curated_into_working_memory(self):
        self.assertIn("steps_avg_7d", _H_STATUS)

    def test_progress_fallback_is_glucose_safe(self):
        # 43 mg/dL must NOT be called "good range" here either (3rd blocker instance).
        wm = self._wm(latest_glucose=43, latest_glucose_unit="mg/dL",
                      sleep_avg_hours_7d=7.5)
        out = _health_progress_fallback(wm).lower()
        self.assertIn("very low", out)
        for word in ("good range", "in a good range", "healthy"):
            self.assertNotIn(word, out)
