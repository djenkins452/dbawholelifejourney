# ==============================================================================
# File: apps/ai/tests/test_executive_filtering.py
# Description: EXECUTIVE FILTERING (Phase 2) — Beth decides not just what is true but
#   what is worth SAYING. Regressions for: (1) internal reasoning artifacts leaking
#   ("Consolidated from 3 readings into one concern", raw "range 49–55%, average 52%");
#   (2) routine items (supplements, "log X") getting equal airtime with real
#   commitments; (3) endings that read as optionality ("it's your call") instead of
#   executive judgment; (4) recommendations phrased as a nutrient ("get protein")
#   instead of a concrete action ("start with eggs").
# ==============================================================================
from unittest import mock

from django.test import SimpleTestCase

from apps.ai.chatgpt_cos.naturalize import naturalize
from apps.ai.chatgpt_cos import executive_brief as EB
from apps.ai.chatgpt_cos.executive_interpretation import ExecutiveSignals

_RHYTHM = "apps.core.cos_briefing.rhythm_api.get_remaining_rhythm_items"
_NOW = "apps.core.utils.get_user_now"
_PLANNED = "apps.ai.chatgpt_cos.day_truth.todays_planned_workout"
_PROTEIN = "apps.ai.chatgpt_cos.day_truth.protein_options"


# ── #1 Internal artifacts never reach the customer ────────────────────────────
class NoInternalArtifactsTests(SimpleTestCase):
    def test_naturalize_strips_the_consolidation_artifact_and_raw_stats(self):
        leak = ("Protein intake has been below target for 3 days — range 49–55%, "
                "average 52%. Consolidated from 3 readings into one concern.")
        out = naturalize(leak)
        self.assertNotIn("consolidated from", out.lower())
        self.assertNotIn("average 52%", out.lower())
        self.assertNotIn("range 49", out.lower())
        self.assertIn("below target", out.lower())
        # (The consolidation SOURCE message is verified natural in
        # apps/core/cos_briefing/tests/test_executive_summary_phase_a.py.)


# ── #4 (endings with judgment) + #2/#3 (filter routine) ───────────────────────
class AgendaFilteringTests(SimpleTestCase):
    def test_routine_items_are_filtered_meaningful_kept(self):
        self.assertFalse(EB._agenda_worth_surfacing(
            {"title": "Fish Oil", "source_type": "supplement_dose"}))
        self.assertFalse(EB._agenda_worth_surfacing(
            {"title": "Log Nutrition", "source_type": "routine_item"}))
        self.assertTrue(EB._agenda_worth_surfacing(
            {"title": "Pick up motorcycle", "source_type": "task"}))
        self.assertTrue(EB._agenda_worth_surfacing(
            {"title": "Dentist", "source_type": "task", "domain": "appointment"}))

    def _agenda(self, items, hour=9):
        import datetime
        now = datetime.datetime(2026, 7, 3, hour, 0, tzinfo=datetime.timezone.utc)
        with mock.patch(_RHYTHM, return_value=items), mock.patch(_NOW, return_value=now):
            return EB._agenda_narrative(None, recovery=False)

    def test_agenda_drops_routine_and_surfaces_the_commitment(self):
        items = [
            {"title": "Fish Oil", "source_type": "supplement_dose", "scheduled_time": "09:30"},
            {"title": "Log Nutrition", "source_type": "routine_item", "scheduled_time": "10:00"},
            {"title": "Pick up motorcycle", "source_type": "task", "scheduled_time": "14:00"},
            {"title": "THORNE Creatine", "source_type": "supplement_dose", "scheduled_time": "08:00"},
        ]
        out = self._agenda(items).lower()
        self.assertIn("motorcycle", out)              # the real commitment surfaces
        self.assertNotIn("fish oil", out)             # routine supplements filtered
        self.assertNotIn("creatine", out)
        self.assertNotIn("log nutrition", out)

    def test_agenda_ends_with_judgment_not_optionality(self):
        # A past (overdue) meaningful item is raised with a recommendation, never
        # "it's your call".
        items = [{"title": "Pick up motorcycle", "source_type": "task",
                  "scheduled_time": "07:00"}]
        out = self._agenda(items, hour=12).lower()
        self.assertNotIn("your call", out)
        self.assertIn("worth closing", out)


# ── #5 Recommendations are concrete actions, not nutrients ────────────────────
class ActionRecommendationTests(SimpleTestCase):
    def test_next_move_leads_with_a_concrete_food(self):
        sig = ExecutiveSignals(sleep_hours=6.0)
        with mock.patch(_PLANNED, return_value={"type": "cardio", "time": "6:00 PM",
                                                "completed": False}), \
             mock.patch(_PROTEIN, return_value="eggs, Greek yogurt, or a protein shake"):
            out = EB._next_move_story(sig, None).lower()
        self.assertIn("start with eggs", out)         # the action, not the nutrient
        self.assertNotIn("getting protein in early so you're fuelled for your", out)


# ── biggest_risk narrated naturally (no over-drama, no raw artifact) ──────────
class RiskNarrationTests(SimpleTestCase):
    def test_risk_is_natural_and_not_over_dramatized(self):
        sig = ExecutiveSignals(
            today_count=0, biggest_risk="protein has been below target across the last 3 days")
        out = EB._priority_story(sig)
        self.assertIn("worth staying on top of today", out)
        self.assertNotIn("derail the day", out)
        self.assertNotIn("Consolidated", out)
