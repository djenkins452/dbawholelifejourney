# ==============================================================================
# File: apps/core/truth/tests/test_capability_semantics.py
# Description: Contract — every truth domain/entity the model can call must carry
#              plain-language semantics, so the conversational model routes by MEANING
#              (not by matching a domain NAME). Origin: nutrition-vs-meals collision.
# ==============================================================================
from django.test import SimpleTestCase

from apps.core.truth.catalog import truth_catalog
from apps.core.truth.semantics import DOMAIN_SEMANTICS, domain_semantics


def _advertised(cat):
    """Domains that advertise at least one entity/history/analysis capability —
    i.e. the model can actually call a tool for them."""
    return {d: s for d, s in cat.items()
            if s.get("entities") or s.get("history") or s.get("analysis")}


class CapabilitySemanticsContractTests(SimpleTestCase):
    def setUp(self):
        self.cat = truth_catalog()
        self.advertised = _advertised(self.cat)

    def test_every_advertised_domain_has_a_purpose(self):
        missing = [d for d in self.advertised
                   if not (domain_semantics(d).get("purpose") or "").strip()]
        self.assertEqual(missing, [],
                         f"advertised domains missing a semantic purpose: {missing}")

    def test_every_advertised_entity_type_has_a_description(self):
        gaps = []
        for d, s in self.advertised.items():
            ents = domain_semantics(d).get("entities", {})
            for et in s.get("entities", ()):
                if not (ents.get(et) or "").strip():
                    gaps.append(f"{d}.{et}")
        self.assertEqual(gaps, [], f"entities missing a description: {gaps}")

    def test_semantics_stay_catalog_driven(self):
        # No semantics for a domain that isn't registered in the truth catalog.
        stray = [d for d in DOMAIN_SEMANTICS if d not in self.cat]
        self.assertEqual(stray, [], f"semantics for unknown domains: {stray}")

    def test_nutrition_meal_is_an_eaten_logged_meal(self):
        meal = domain_semantics("nutrition")["entities"]["meal"].lower()
        self.assertTrue(("ate" in meal) or ("eaten" in meal) or ("logged" in meal),
                        f"nutrition.meal must read as eaten/logged: {meal!r}")

    def test_meals_domain_is_recipe_supply_planning(self):
        purpose = domain_semantics("meals")["purpose"].lower()
        self.assertTrue(any(w in purpose for w in
                            ("recipe", "supply", "plan", "prepar")),
                        f"meals purpose must convey recipe/supply/planning: {purpose!r}")

    def test_collision_pair_carries_explicit_boundaries(self):
        # Names alone are not the only signal: both sides state the boundary.
        self.assertIn("meals", domain_semantics("nutrition").get("boundary", "").lower())
        self.assertIn("nutrition", domain_semantics("meals").get("boundary", "").lower())

    def test_capability_index_exposes_semantics(self):
        from apps.ai.cos_services.current_context import _capabilities
        caps = _capabilities()
        self.assertIn("domain_semantics", caps)
        sem = caps["domain_semantics"]
        # advertised domains are present with meaning
        self.assertIn("nutrition", sem)
        self.assertIn("meals", sem)
        self.assertTrue(sem["nutrition"]["purpose"])
