# ==============================================================================
# File: apps/core/tests/test_presentation.py
# Description: Human Presentation Standard (apps/core/truth/present.py). The reusable
#   presentation layer every Conversation Object renders through: rounded numbers,
#   collapsed duplicates, grouped bulleted lists, remaining-to-goal. Deterministic.
# ==============================================================================
from django.test import SimpleTestCase

from apps.core.truth.present import (
    humanize_number, collapse_items, bullet_list, present_groups, present_remaining,
)


class HumanizeNumberTests(SimpleTestCase):
    def test_rounds_decimals_for_humans(self):
        self.assertEqual(humanize_number(31.2), "31")
        self.assertEqual(humanize_number(180.0), "180")

    def test_thousands_separator(self):
        self.assertEqual(humanize_number(1850.0), "1,850")
        self.assertEqual(humanize_number(1030), "1,030")

    def test_empty_and_none(self):
        self.assertEqual(humanize_number(None), "")
        self.assertEqual(humanize_number(0), "0")


class CollapseItemsTests(SimpleTestCase):
    def test_collapses_duplicates_preserving_order(self):
        self.assertEqual(collapse_items(["Pizza", "Pizza", "Salad"]),
                         [("Pizza", 2), ("Salad", 1)])

    def test_case_insensitive_keeps_first_spelling(self):
        self.assertEqual(collapse_items(["Eggs", "eggs"]), [("Eggs", 2)])

    def test_bullet_list_servings_suffix_only_when_multiple(self):
        self.assertEqual(bullet_list(["Pizza", "Pizza", "Salad"]),
                         ["• Pizza (2 servings)", "• Salad"])


class PresentGroupsTests(SimpleTestCase):
    def test_grouped_bulleted_collapsed(self):
        out = present_groups(
            [("snack", ["Pistachios", "Cashews"]),
             ("dinner", ["Homemade Pizza", "Homemade Pizza"])],
            lead="Today you've logged:")
        self.assertIn("Today you've logged:", out)
        self.assertIn("Snack", out)
        self.assertIn("• Pistachios", out)
        self.assertIn("Dinner", out)
        self.assertIn("• Homemade Pizza (2 servings)", out)
        # scannable: blank line between the lead and the first group
        self.assertIn("logged:\n\nSnack", out)

    def test_empty_groups_dropped(self):
        self.assertEqual(present_groups([("lunch", [])], lead="x"), "")


class PresentRemainingTests(SimpleTestCase):
    def test_shows_consumed_remaining_and_goal_rounded(self):
        self.assertEqual(present_remaining("Protein", 31.2, 180.0, "g"),
                         "Protein: 31 g consumed · 149 g remaining (goal 180 g)")

    def test_thousands_in_remaining(self):
        self.assertEqual(present_remaining("Calories", 770, 1800),
                         "Calories: 770 consumed · 1,030 remaining (goal 1,800)")

    def test_no_goal_falls_back_to_total(self):
        self.assertEqual(present_remaining("Calories", 770, None), "Calories: 770 so far")

    def test_over_goal_clamps_remaining_to_zero(self):
        self.assertIn("0 g remaining", present_remaining("Protein", 200, 180, "g"))

    def test_deterministic(self):
        a = present_remaining("Protein", 31.2, 180.0, "g")
        b = present_remaining("Protein", 31.2, 180.0, "g")
        self.assertEqual(a, b)
