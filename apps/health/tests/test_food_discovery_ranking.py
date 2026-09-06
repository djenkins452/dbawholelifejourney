# ==============================================================================
# File: apps/health/tests/test_food_discovery_ranking.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Food discovery ranks by relevance; identity still never substitutes
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-06
# ==============================================================================
"""Production, 2026-09-05/06. Searching "ham and cheese sandwich" led with
`4 Egg Ham and Cheese Sandwich`, and searching "banana" did not surface a plain banana.

Neither was a matching bug — nothing was ranking anything. Saved foods came back ordered
by `-updated_at`, the catalog came back ordered ALPHABETICALLY BY NAME, and the caller
concatenated and sliced. A name beginning with a digit sorts before every letter, so
`4 Egg…` led by arithmetic. And `limit` bounded the pool BEFORE relevance was considered,
so the write path — which asked for one row — could only ever see the most recently
updated saved food containing the query as a substring.

Two things are certified here, and the boundary between them is the point:

    SEARCH may return approximate candidates, best first.
    WRITE identity may never silently substitute one.

No food, brand or category is named in any of the code these tests cover. No provider calls.
"""

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.health.services import food_ranking as fr

User = get_user_model()


class _R:
    def __init__(self, name, source="local"):
        self.name = name
        self.source = source


def _item(name, calories):
    from apps.health.models import FoodItem
    return FoodItem.objects.create(name=name, is_active=True, calories=calories,
                                   serving_size=1, serving_unit="serving")


def _custom(user, name, calories):
    from apps.health.models import CustomFood
    return CustomFood.objects.create(user=user, name=name, calories=calories,
                                     serving_size=1, serving_unit="serving")


def _names(results, query):
    return [r.name for r in fr.rank(results, query)]


class RelevanceOrderTests(SimpleTestCase):
    def test_extra_concepts_do_not_win_on_shared_words(self):
        """The production example, as a class."""
        ranked = _names([_R("4 Egg Ham and Cheese Sandwich"),
                         _R("Ham and Cheese Sandwich")],
                        "ham and cheese sandwich")
        self.assertEqual(ranked[0], "Ham and Cheese Sandwich")

    def test_an_exact_generic_food_leads(self):
        ranked = _names([_R("Oikos Pro Banana", source="custom"), _R("Banana Bread"),
                         _R("Banana")], "banana")
        self.assertEqual(ranked[0], "Banana")

    def test_a_saved_food_wins_only_a_TIE_never_a_tier(self):
        """A person's own food is preferred when equally relevant — and not otherwise."""
        self.assertEqual(_names([_R("Banana"), _R("Banana", source="custom")],
                                "banana")[0:2][0], "Banana")
        self.assertEqual(fr.score("Banana", "banana", source="custom")[3],
                         0, "a saved food should tie-break ahead")
        self.assertLess(fr.score("Banana", "banana", source="local"),
                        fr.score("Oikos Pro Banana", "banana", source="custom"),
                        "a saved product outranked the exact food that was asked for")

    def test_a_branded_product_does_not_outrank_the_generic_food(self):
        ranked = _names([_R("Chobani Greek Yogurt", source="custom"),
                         _R("Greek Yogurt")], "greek yogurt")
        self.assertEqual(ranked[0], "Greek Yogurt")

    def test_fewer_added_concepts_ranks_higher(self):
        ranked = _names([_R("Grilled Chicken Breast with Rice and Broccoli"),
                         _R("Grilled Chicken Breast with Rice"),
                         _R("Grilled Chicken Breast")], "grilled chicken breast")
        self.assertEqual(ranked[0], "Grilled Chicken Breast")
        self.assertEqual(ranked[1], "Grilled Chicken Breast with Rice")

    def test_function_words_do_not_change_identity(self):
        self.assertEqual(fr.score("Ham and Cheese Sandwich", "ham cheese sandwich")[0],
                         fr.TIER_SAME_CONCEPTS)

    def test_a_typo_still_finds_the_food(self):
        ranked = _names([_R("Cottage Cheese"), _R("Bananna Bread"), _R("Banana")],
                        "bannana")
        self.assertEqual(ranked[0], "Banana")

    def test_an_unrelated_candidate_ranks_last(self):
        ranked = _names([_R("Beef Stew"), _R("Banana")], "banana")
        self.assertEqual(ranked[-1], "Beef Stew")

    def test_several_reasonable_candidates_are_all_returned_in_order(self):
        ranked = _names([_R("Banana Bread"), _R("Banana Smoothie"), _R("Banana")],
                        "banana")
        self.assertEqual(ranked[0], "Banana")
        self.assertEqual(set(ranked[1:]), {"Banana Bread", "Banana Smoothie"})

    def test_ranking_is_stable_and_total(self):
        pool = [_R("Banana Bread"), _R("Banana"), _R("Beef Stew")]
        self.assertEqual(_names(pool, "banana"), _names(pool, "banana"))
        self.assertEqual(len(fr.rank(pool, "banana")), 3, "a candidate was dropped")

    def test_empty_input_is_safe(self):
        self.assertEqual(fr.rank([], "banana"), [])
        self.assertEqual(fr.rank(None, "banana"), [])

    def test_the_ranker_names_no_food_or_brand(self):
        import ast
        import pathlib
        tree = ast.parse(pathlib.Path(fr.__file__).read_text(encoding="utf-8"))
        docs = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    docs.add(doc)
        literals = [n.value.lower() for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and n.value not in docs]
        for word in ("banana", "ham", "cheese", "egg", "sandwich", "oikos"):
            for literal in literals:
                self.assertNotIn(word, literal.split(),
                                 f"the ranker hard-codes {word!r}")


class ExternalLookupGateTests(SimpleTestCase):
    """Quantity is not quality."""

    def test_three_irrelevant_rows_no_longer_stop_the_search(self):
        junk = [_R("Banana Bread"), _R("Banana Smoothie"), _R("Banana Chips")]
        self.assertFalse(fr.has_strong_match(junk, "banana"))

    def test_a_genuinely_good_match_stops_it(self):
        self.assertTrue(fr.has_strong_match([_R("Banana")], "banana"))
        self.assertTrue(fr.has_strong_match([_R("Ham and Cheese Sandwich")],
                                            "ham cheese sandwich"))


class SearchIntegrationTests(TestCase):
    """The shared authority both the Nutrition UI and the CoS call."""

    def setUp(self):
        self.user = User.objects.create_user(email="fs@contract.test", password="x")
        self.other = User.objects.create_user(email="fs2@contract.test", password="x")
        _item("Banana", 105)
        _item("4 Egg Ham and Cheese Sandwich", 480)
        _item("Ham and Cheese Sandwich", 350)
        _custom(self.user, "Oikos Pro Banana", 130)
        _custom(self.other, "Someone Elses Banana", 99)

    def _search(self, q, **kw):
        from apps.health.services.food_search import food_search_service
        return food_search_service.search(query=q, user=self.user, limit=10,
                                          use_fatsecret=False, use_ai=False, **kw)

    def test_the_generic_food_is_found_and_leads(self):
        self.assertEqual(self._search("banana")[0].name, "Banana")

    def test_the_saved_product_is_still_offered(self):
        self.assertIn("Oikos Pro Banana", [r.name for r in self._search("banana")])

    def test_another_users_saved_food_is_never_returned(self):
        self.assertNotIn("Someone Elses Banana",
                         [r.name for r in self._search("banana")])

    def test_the_added_concept_candidate_no_longer_leads(self):
        self.assertEqual(self._search("ham and cheese sandwich")[0].name,
                         "Ham and Cheese Sandwich")

    def test_no_match_returns_nothing_rather_than_the_closest_thing(self):
        self.assertEqual(self._search("zzzzqqqx"), [])


class IdentityStillNeverSubstitutesTests(TestCase):
    """Wider discovery must not loosen the write boundary."""

    def setUp(self):
        self.user = User.objects.create_user(email="fw@contract.test", password="x")
        _item("Banana", 105)
        _custom(self.user, "Oikos Pro Banana", 130)

    def test_the_exact_food_is_now_reachable_by_the_write_path(self):
        """`limit=1` used to make this impossible."""
        from apps.ai.action_handlers import ActionHandler
        from apps.health.models import FoodEntry
        out = ActionHandler(self.user).handle_log_food(
            food_name="banana", meal_type="breakfast")
        self.assertTrue(out.success)
        entry = FoodEntry.objects.filter(user=self.user).latest("id")
        self.assertEqual(entry.food_name, "Banana")
        self.assertEqual(float(entry.total_calories), 105.0)

    def test_a_near_match_is_still_never_adopted(self):
        from apps.ai.action_handlers import ActionHandler
        from apps.health.models import FoodEntry
        ActionHandler(self.user).handle_log_food(
            food_name="oikos banana", meal_type="breakfast")
        entry = FoodEntry.objects.filter(user=self.user).latest("id")
        self.assertEqual(entry.food_name, "oikos banana")
        self.assertEqual(entry.data_source_used, FoodEntry.DATA_SOURCE_UNKNOWN)
