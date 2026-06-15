"""Regression tests for the three proven production trust failures (2026-06-15).

F1 — check-in implied ~11 remaining, "how many things do I have left?" said 5
     (LLM guess; no deterministic count route). Now routes deterministically.
F2 — at 1:48 PM, "Start with Prayer Time (5:30 AM)" chosen as next action
     (earliest-overdue with no staleness gate). Now block-gated.
F3 — "How am I doing on calories today?" → "You're at 0 calories today" when
     nothing was logged. Now distinguishes empty-log from a tracked zero.
"""
from datetime import time as dt_time

from django.test import SimpleTestCase


class F1RemainingCountRouting(SimpleTestCase):
    def test_how_many_left_routes_deterministically(self):
        from apps.ai.deterministic_router import (
            is_qualified_status_query, _is_remaining_count_query)
        for q in (
            "how many things do i have left?",
            "how many tasks do i have left",
            "how many items are remaining today",
            "how much do i still have to do",
        ):
            self.assertTrue(_is_remaining_count_query(q), q)
            self.assertTrue(is_qualified_status_query(q), q)

    def test_domain_counts_excluded(self):
        # These have their own deterministic routes; must NOT be hijacked.
        from apps.ai.deterministic_router import _is_remaining_count_query
        for q in (
            "how many calories do i have left today",
            "how many steps remaining",
            "how many workouts left this week",
            "how many doses are remaining",
        ):
            self.assertFalse(_is_remaining_count_query(q), q)

    def test_non_count_questions_excluded(self):
        from apps.ai.deterministic_router import _is_remaining_count_query
        self.assertFalse(_is_remaining_count_query("how many tasks did i finish"))
        self.assertFalse(_is_remaining_count_query("what's the weather"))


class F2NextActionStaleOverdue(SimpleTestCase):
    def _entry(self, label, time_str):
        return {"label": label, "item": {"time_str": time_str}, "sort_time": 0}

    def test_stale_morning_item_skipped_recent_chosen(self):
        from apps.core.execution.active_block import first_eligible_overdue
        stale = self._entry("Prayer Time (5:30 AM)", "5:30 AM")
        recent = self._entry("Lunch Walk (12:30 PM)", "12:30 PM")
        # Active block = lunch (12–14); now 1:48 PM.
        chosen = first_eligible_overdue(
            [stale, recent], {"name": "lunch"}, dt_time(13, 48))
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["label"], "Lunch Walk (12:30 PM)")

    def test_only_stale_item_yields_none(self):
        from apps.core.execution.active_block import first_eligible_overdue
        stale = self._entry("Prayer Time (5:30 AM)", "5:30 AM")
        self.assertIsNone(
            first_eligible_overdue([stale], {"name": "lunch"}, dt_time(13, 48)))

    def test_empty_yields_none(self):
        from apps.core.execution.active_block import first_eligible_overdue
        self.assertIsNone(
            first_eligible_overdue([], {"name": "lunch"}, dt_time(13, 48)))


class F3NutritionEmptyLog(SimpleTestCase):
    def test_empty_log_is_honest_not_zero(self):
        from apps.ai.deterministic_router import _nutrition_fact_response
        nut = {"daily_calories": 0, "daily_protein_g": 0,
               "food_entries_today": 0, "calorie_target": 2000}
        out = _nutrition_fact_response(nut, "how am i doing on calories today")
        self.assertIsNotNone(out)
        self.assertIn("don't see nutrition logged today yet", out)
        self.assertNotIn("at **0** calories", out)

    def test_logged_calories_answered_normally(self):
        from apps.ai.deterministic_router import _nutrition_fact_response
        nut = {"daily_calories": 1560, "daily_protein_g": 90,
               "food_entries_today": 3, "calorie_target": 2000}
        out = _nutrition_fact_response(nut, "how am i doing on calories today")
        self.assertIn("1560", out)
        self.assertIn("under** target", out)
        self.assertNotIn("don't see nutrition logged", out)

    def test_empty_log_protein_is_honest(self):
        from apps.ai.deterministic_router import _nutrition_fact_response
        nut = {"daily_calories": 0, "daily_protein_g": 0,
               "food_entries_today": 0}
        out = _nutrition_fact_response(nut, "protein today")
        self.assertIn("don't see nutrition logged today yet", out)
        self.assertNotIn("at **0g** protein", out)
