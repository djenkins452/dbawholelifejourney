"""Ranked Entity Retrieval platform capability — pure-math invariant tests.

Tests the INVARIANT, not the implementation: entities sort by value in both directions,
ties break deterministically on the canonical reference (never row order), a missing value
is EXCLUDED (never zero-filled) while a real 0 is kept, the result is bounded, contribution
percentages are of the whole present population, and the same items always rank the same.
"""
from django.test import SimpleTestCase

from apps.core.truth.ranked_entity import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    RankItem,
    build_ranking,
)


def _it(ref, value):
    return RankItem(ref=ref, name=ref, value=value)


class RankedEntityTests(SimpleTestCase):
    def test_descending_orders_most_first(self):
        r = build_ranking([_it("a", 10), _it("b", 30), _it("c", 20)],
                          measure="carbs", unit="g")
        self.assertEqual([x["name"] for x in r["results"]], ["b", "c", "a"])
        self.assertEqual(r["results"][0]["rank"], 1)

    def test_ascending_orders_least_first(self):
        r = build_ranking([_it("a", 10), _it("b", 30), _it("c", 20)],
                          measure="carbs", unit="g", order="asc")
        self.assertEqual([x["name"] for x in r["results"]], ["a", "c", "b"])

    def test_ties_break_on_reference_deterministically(self):
        # equal values → canonical ref ascending, NEVER input/row order.
        r1 = build_ranking([_it("zebra", 50), _it("apple", 50), _it("mango", 50)],
                           measure="carbs", unit="g")
        r2 = build_ranking([_it("mango", 50), _it("zebra", 50), _it("apple", 50)],
                           measure="carbs", unit="g")
        self.assertEqual([x["name"] for x in r1["results"]], ["apple", "mango", "zebra"])
        self.assertEqual(r1["results"], r2["results"])          # order-independent

    def test_missing_excluded_not_zeroed(self):
        r = build_ranking([_it("a", 40), _it("b", None), _it("c", 20)],
                          measure="carbs", unit="g")
        self.assertEqual([x["name"] for x in r["results"]], ["a", "c"])
        self.assertEqual(r["missing_excluded"], 1)
        self.assertEqual(r["entities_ranked"], 2)
        self.assertNotIn(0.0, [x["value"] for x in r["results"]])   # never a fabricated 0
        self.assertEqual(r["total"], 60.0)                          # missing not summed

    def test_real_zero_is_kept(self):
        r = build_ranking([_it("a", 0.0), _it("b", 5.0)], measure="carbs", unit="g")
        names = [x["name"] for x in r["results"]]
        self.assertIn("a", names)                                   # 0 is a real value
        self.assertEqual(r["entities_ranked"], 2)

    def test_limit_bounds(self):
        items = [_it(f"m{i:02d}", float(i)) for i in range(100)]
        self.assertEqual(len(build_ranking(items, measure="c", unit="g")["results"]),
                         DEFAULT_LIMIT)
        self.assertEqual(len(build_ranking(items, measure="c", unit="g",
                                           limit=999)["results"]), MAX_LIMIT)
        self.assertEqual(len(build_ranking(items, measure="c", unit="g",
                                           limit=3)["results"]), 3)

    def test_contribution_pct_of_present_population(self):
        r = build_ranking([_it("a", 25), _it("b", 75)], measure="carbs", unit="g")
        top = r["results"][0]
        self.assertEqual(top["name"], "b")
        self.assertEqual(top["value"], 75.0)
        self.assertEqual(top["contribution_pct"], 75.0)            # 75 / (25+75)
        self.assertEqual(r["total"], 100.0)

    def test_empty_is_present_false(self):
        self.assertFalse(build_ranking([], measure="carbs", unit="g")["present"])
        # all-missing is also honestly empty (nothing to rank), not zeros.
        allmiss = build_ranking([_it("a", None), _it("b", None)], measure="c", unit="g")
        self.assertFalse(allmiss["present"])
        self.assertEqual(allmiss["missing_excluded"], 2)

    def test_results_carry_reference_for_followup(self):
        r = build_ranking([RankItem("Dinner — 2026-08-10", "Dinner", 90.0,
                                    occurred_on="2026-08-10", meta={"meal_type": "dinner"})],
                          measure="carbs", unit="g")
        top = r["results"][0]
        self.assertEqual(top["ref"], "Dinner — 2026-08-10")       # canonical reference
        self.assertEqual(top["occurred_on"], "2026-08-10")
        self.assertEqual(top["meta"]["meal_type"], "dinner")

    def test_deterministic(self):
        items = [_it("a", 3), _it("b", 9), _it("c", 3), _it("d", 7)]
        self.assertEqual(build_ranking(items, measure="c", unit="g"),
                         build_ranking(items, measure="c", unit="g"))
