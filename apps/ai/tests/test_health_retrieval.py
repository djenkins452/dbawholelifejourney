"""Sleep + Workout deterministic retrieval fixes, and the Phase 0 probe.

Sleep: "how did I sleep?" must lead with last night (not only 7-day average);
"how has my sleep been this week?" may use the 7-day average.
Workout: "what was my last workout?" returns canonical latest workout
(name/date/exercise/set count) with NO memory/journal filler.
"""

from unittest import mock

from django.test import SimpleTestCase

from apps.ai import deterministic_router as dr
from apps.ai.cognitive_mode import health_retrieval_probe as probe


_HEALTH_STATE = {
    "sleep_last_night_hours": 6.7,
    "sleep_last_night_quality": 90,
    "sleep_last_night_date": "2026-06-08",
    "sleep_avg_duration_7d": 378,   # minutes → 6.3 h
    "sleep_avg_hours_7d": 6.3,
    "sleep_trend": "stable",
}

_FITNESS_STATE = {
    "workouts_7d": 4,
    "last_workout": {
        "name": "Adjusted Upper Body",
        "type": "strength",
        "date": "2026-06-05",
        "minutes": 45,
        "exercise_count": 4,
        "set_count": 12,
    },
}


def _patch_state(health=None, fitness=None):
    def _fake(user, module, *a, **k):
        return {"health": health or {}, "fitness": fitness or {}}.get(module, {})
    return mock.patch("apps.core.ai_state.state_engine.get_module_state", side_effect=_fake)


class SleepRetrievalTests(SimpleTestCase):
    def test_how_did_i_sleep_leads_with_last_night(self):
        with _patch_state(health=_HEALTH_STATE):
            out = dr._handle_sleep_query(object(), "how did i sleep?")
        self.assertIn("6.7", out)            # last night
        self.assertIn("90", out)             # quality
        self.assertIn("6.3", out)            # 7-day avg as context
        # Must NOT be the average-only sentence:
        self.assertNotIn("You're averaging", out)

    def test_this_week_uses_average(self):
        with _patch_state(health=_HEALTH_STATE):
            out = dr._handle_sleep_query(object(), "how has my sleep been this week?")
        self.assertIn("6.3", out)
        self.assertIn("averaging", out)
        # Should be the summary path, not last-night lead.
        self.assertNotIn("last night", out)

    def test_missing_last_night_falls_back_to_avg(self):
        state = dict(_HEALTH_STATE)
        state["sleep_last_night_hours"] = None
        with _patch_state(health=state):
            out = dr._handle_sleep_query(object(), "how did i sleep?")
        self.assertIn("6.3", out)
        self.assertIn("don't have last night", out)

    def test_no_data_falls_through(self):
        with _patch_state(health={}):
            self.assertIsNone(dr._handle_sleep_query(object(), "how did i sleep?"))


class WorkoutRetrievalTests(SimpleTestCase):
    def test_last_workout_matcher_matches(self):
        self.assertTrue(dr._match_last_workout_query("what was my last workout?"))
        self.assertTrue(dr._match_last_workout_query("my last workout"))
        self.assertTrue(dr._match_last_workout_query("most recent workout"))

    def test_last_workout_matcher_excludes_logging(self):
        self.assertFalse(dr._match_last_workout_query("log my last workout"))
        self.assertFalse(dr._match_last_workout_query("start a workout"))

    def test_aggregate_matcher_ignores_last_workout(self):
        # The aggregate route must NOT swallow the event query.
        self.assertFalse(dr._match_workout_query("what was my last workout?"))

    def test_handler_returns_canonical_detail_no_memory(self):
        with _patch_state(fitness=_FITNESS_STATE):
            out = dr._handle_last_workout_query(object())
        self.assertIn("Adjusted Upper Body", out)
        self.assertIn("Jun 5", out)
        self.assertIn("4 exercise", out)
        self.assertIn("12 set", out)
        # No journal/conversation contamination:
        for bad in ("mentioned", "getting up early", "you said", "journal"):
            self.assertNotIn(bad, out.lower())

    def test_handler_no_data_falls_through(self):
        with _patch_state(fitness={}):
            self.assertIsNone(dr._handle_last_workout_query(object()))


class ProbeTests(SimpleTestCase):
    def test_classify_domains_and_class(self):
        self.assertEqual(probe.classify("what was my last glucose reading and when?"),
                         ("glucose", "latest"))
        self.assertEqual(probe.classify("how many calories today?"),
                         ("nutrition", "today"))
        self.assertEqual(probe.classify("how has my sleep been this week?"),
                         ("sleep", "summary"))
        self.assertEqual(probe.classify("what was my last workout?"),
                         ("workout", "latest"))

    def test_classify_non_health_returns_none(self):
        self.assertEqual(probe.classify("what's on my calendar?"), (None, None))

    def test_log_never_raises(self):
        with _patch_state(health=_HEALTH_STATE, fitness=_FITNESS_STATE):
            probe.log_health_retrieval(
                type("U", (), {"id": 1})(),
                "what was my last glucose reading?",
                route_name="glucose_latest_query", route_fired=False,
                handler="glucose_latest_query",
                response="Your last reading was 119 mg/dL",
                memory_injected=False,
                llm_context="glucose_summary_avg_7d: 119",
            )

    def test_hash_opaque(self):
        h = probe._hash("how did i sleep?")
        self.assertEqual(len(h), 16)
        self.assertNotIn("sleep", h)

    def test_probe_disabled_is_silent(self):
        with self.settings(WLJ_BETH_HEALTH_PROBE_ENABLED=False):
            probe.log_health_retrieval(
                type("U", (), {"id": 1})(), "how many calories today?",
                route_name=None, route_fired=False, handler=None,
                response="1355", memory_injected=False, llm_context="")
