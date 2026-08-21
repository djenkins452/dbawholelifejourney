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


class OwnRecordGroundingContractTests(SimpleTestCase):
    """Contract — CONDITIONAL GUIDANCE MUST BE RESOLVED, NOT HANDED BACK.

    Production friction 2026-08-21 (residual of the medication-deflection fix): the
    certified CoS answered a medication-administration question from general knowledge
    with `tools_called: []`, handing the user a decision tree ("take it if it's not too
    close to your next dose") while WLJ already held the schedule and last-taken that
    decide which branch applies.

    Two proven exposure defects, both asserted here as INVARIANTS — never a drug, a
    question, or a phrase:
      1. a truth surface must DISCLOSE the facts it actually returns, or the model
         cannot select it for a question those facts would answer;
      2. cue/example phrasings must not read as the BOUNDARY of applicability — a
         record is evidence for a judgment, not only the answer to "show me the record".
    """

    def setUp(self):
        self.cat = truth_catalog()

    # -- 1. surfaces disclose what they actually return ----------------------
    def test_medication_entity_discloses_the_facts_it_returns(self):
        """`medicine_queries` returns schedule, instructions, grace period and
        last-taken; the advertisement must say so or the surface is undiscoverable."""
        desc = domain_semantics("medicine")["entities"]["medication"].lower()
        for fact in ("schedule", "instruction", "last taken", "grace period",
                     "dose", "adherence"):
            self.assertIn(fact, desc,
                          f"medication entity must disclose {fact!r}: {desc!r}")

    def test_disclosure_matches_the_real_serialization(self):
        """Guards against drift: every fact the advertisement promises is a key the
        certified entity surface genuinely composes."""
        import inspect

        from apps.health.services import medicine_queries
        src = inspect.getsource(medicine_queries).lower()
        for key in ("instructions", "schedule_detail", "grace_period_minutes",
                    "last_taken", "adherence"):
            self.assertIn(key, src,
                          f"advertised fact {key!r} is not produced by the surface")

    # -- 2. cues are phrasings, not the limit of applicability ---------------
    def test_capability_note_says_cues_are_not_the_boundary(self):
        from apps.ai.cos_services.current_context import _capabilities
        note = _capabilities()["note"].lower()
        self.assertIn("not the boundary of applicability", note)
        self.assertIn("a record is evidence", note)
        # the decision-shaped phrasings the index previously had no route for
        for shape in ("is it ok to", "should", "can i", "is it too late to"):
            self.assertIn(shape, note)
        self.assertIn("which deterministic fact would change your answer", note)

    def test_a_domain_advertises_decision_shaped_cues(self):
        """The index was 100% lookup-shaped ('what did I…', 'my X'). At least the
        domain proven to fail must now advertise that a decision routes here too."""
        cues = " ".join(domain_semantics("medicine").get("cues", ())).lower()
        self.assertTrue(any(s in cues for s in ("is it too late", "am i supposed to",
                                                "when is my next")),
                        f"medicine cues remain purely lookup-shaped: {cues!r}")

    # -- 3. the governing invariant is stated, and it self-limits ------------
    def test_conditional_guidance_invariant_is_governing(self):
        from apps.ai.model_interface.constitution import CONSTITUTION
        low = CONSTITUTION.lower()
        self.assertIn("conditional guidance must be resolved, not handed back", low)
        self.assertIn("does wlj hold the fact that decides which branch applies", low)
        self.assertIn("non-answer", low)

    def test_invariant_does_not_mandate_retrieval_for_its_own_sake(self):
        """Acceptance case 1 — generic knowledge sufficient => no pointless retrieval.
        The rule must cut BOTH ways or it becomes 'always retrieve'."""
        from apps.ai.model_interface.constitution import CONSTITUTION
        low = CONSTITUTION.lower()
        self.assertIn("do not retrieve for its own sake", low)
        self.assertIn("does not turn on anything wlj holds, just answer", low)
        self.assertIn("retrieve what changes the answer; never more, never less", low)

    def test_no_always_retrieve_and_no_hardcoding(self):
        """The fix must not degenerate into forced routing or example-specific rules."""
        from apps.ai.model_interface.constitution import CONSTITUTION
        low = CONSTITUTION.lower()
        for banned in ("mounjaro", "tirzepatide", "always retrieve medications",
                       "forgot my dose"):
            self.assertNotIn(banned, low)
        # model still owns tool selection: the rule is a question to ask, not a router
        self.assertIn("ask yourself one", low)
