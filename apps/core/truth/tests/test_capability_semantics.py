# ==============================================================================
# File: apps/core/truth/tests/test_capability_semantics.py
# Description: Contract — every truth domain/entity the model can call must carry
#              plain-language semantics, so the conversational model routes by MEANING
#              (not by matching a domain NAME). Origin: nutrition-vs-meals collision.
# ==============================================================================
from django.test import SimpleTestCase, TestCase

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
    def test_invariant_does_not_mandate_retrieval_for_its_own_sake(self):
        """Acceptance case 1 — generic knowledge sufficient => no pointless retrieval.
        The rule must cut BOTH ways or it becomes 'always retrieve'."""
        from apps.ai.model_interface.constitution import CONSTITUTION
        low = CONSTITUTION.lower()
        self.assertIn("do not go looking", low)
        self.assertIn("retrieving to seem thorough wastes their turn", low)
        self.assertIn("retrieve what changes the answer; never more, never less", low)

    def test_no_always_retrieve_and_no_hardcoding(self):
        """The fix must not degenerate into forced routing or example-specific rules."""
        from apps.ai.model_interface.constitution import CONSTITUTION
        low = CONSTITUTION.lower()
        for banned in ("mounjaro", "tirzepatide", "always retrieve medications",
                       "forgot my dose"):
            self.assertNotIn(banned, low)
        # model still owns tool selection: the rule is a question it asks itself
        self.assertIn("this is your judgment to make on every turn", low)
        self.assertIn("wlj never decides for you which truth you need", low)


class EarliestDecisionAnchorContractTests(SimpleTestCase):
    """Contract — the own-record grounding invariant lives in the model's EARLIEST
    decision block, and nowhere else as a competing authority.

    Proven 2026-08-21 across three deployed Tier-2 smokes: stating the rule late in
    the prompt changed the prose and never changed `tools_called: []`. The model
    anchors on its opening instructions, so the invariant must be part of the first
    question it asks itself — before it decides whether tools are needed at all.
    """

    ANCHOR = "AND THEN THE SECOND QUESTION"

    def setUp(self):
        from apps.ai.model_interface.constitution import CONSTITUTION
        self.c = CONSTITUTION
        self.low = CONSTITUTION.lower()

    def _idx(self, needle):
        i = self.c.find(needle)
        self.assertNotEqual(i, -1, f"missing from the governing prompt: {needle!r}")
        return i

    # -- it is INSIDE the opening first-question block ------------------------
    def test_invariant_sits_inside_the_first_internal_question_block(self):
        start = self._idx("HOW A CHIEF OF STAFF BEGINS")
        end = self._idx("You are the user's personal assistant")
        anchor = self._idx(self.ANCHOR)
        self.assertTrue(start < anchor < end,
                        "the grounding invariant must live inside the opening "
                        f"first-internal-question block (start={start}, "
                        f"anchor={anchor}, end={end})")

    def test_invariant_precedes_grounding_and_medical_policy(self):
        """It must be read BEFORE the sections that previously carried it."""
        anchor = self._idx(self.ANCHOR)
        for later in ("ANSWER GROUNDING", "MEDICAL INFORMATION POLICY",
                      "CONDITIONAL GUIDANCE"):
            self.assertLess(anchor, self._idx(later),
                            f"{later} must come AFTER the anchoring invariant")

    # -- it tests the ANSWER being formed, not the topic named ---------------
    def test_the_test_is_on_the_answer_not_the_question_topic(self):
        self.assertIn("this one asks what you are about to say", self.low)
        self.assertIn("does any part of this depend on a fact about this person", self.low)
        # the materially-changes triggers, stated as kinds of answer — not phrases
        for trigger in ("a branch", "an assumption", "a recommendation", "a timing call",
                        "a prioritisation", "a comparison", "a conclusion"):
            self.assertIn(trigger, self.low)
        self.assertIn("would come out differently if you knew their own record", self.low)

    def test_both_failure_modes_are_named(self):
        """Handing back the fork AND silently picking a side are one mistake."""
        self.assertIn("two failures that look different and are the same mistake", self.low)
        self.assertIn("quietly picking a side yourself", self.low)
        self.assertIn("correct general information plus an unchecked assumption", self.low)

    # -- the later sections DEFER; they do not duplicate ---------------------
    def test_later_sections_defer_to_the_anchor(self):
        for section in ("CONDITIONAL GUIDANCE", "ANSWER GROUNDING",
                        "MEDICAL INFORMATION POLICY"):
            i = self._idx(section)
            # each downstream mention points back at the one authority
            tail = self.c[i:i + 6000].lower()
            self.assertIn("second internal question", tail,
                          f"{section} must cross-reference the anchoring question "
                          "rather than restate the rule")

    def test_the_rule_is_stated_exactly_once(self):
        """No competing/duplicated authority: the operative sentence appears once."""
        self.assertEqual(
            self.low.count("retrieve what changes the answer; never more, never less"), 1)
        self.assertEqual(self.low.count("does any part of this depend on a fact"), 1)

    def test_later_block_no_longer_restates_the_decision_test(self):
        i = self._idx("CONDITIONAL GUIDANCE")
        block = self.c[i:self.c.find("\n", i + 200)].lower()
        self.assertNotIn("does any part of this depend", block)
        self.assertIn("the grounding consequence of", block)

    # -- still a reasoning instruction, never routing ------------------------
    def test_no_deterministic_routing_was_introduced(self):
        """Option B only: no forced tool choice, no evidence plan, no WLJ routing."""
        for banned in ("tool_choice", "required_tool", "evidence plan",
                       "wlj will tell you which tool", "wlj decides which tool"):
            self.assertNotIn(banned, self.low)

    # -- the self-limit must live INSIDE the anchor, not drift away ----------
    def test_the_self_limit_lives_inside_the_same_anchor_block(self):
        """Side 2 of the invariant, positionally.

        The mandate ("retrieve when it changes the answer") and the limiter ("don't
        when it doesn't") are ONE rule. If a later edit keeps the mandate at the
        anchor but relocates or drops the limiter, the invariant silently degrades
        into "always retrieve" — the exact failure the brief forbids. Assert they are
        in the same block, in that order.
        """
        anchor = self._idx(self.ANCHOR)
        end = self._idx("You are the user's personal assistant")
        for limiter in ("BUT HOLD THE OPPOSITE JUST AS FIRMLY",
                        "do NOT go looking",
                        "RETRIEVE WHAT CHANGES THE ANSWER; NEVER MORE, NEVER LESS"):
            i = self._idx(limiter)
            self.assertTrue(anchor < i < end,
                            f"the self-limit {limiter!r} must stay inside the anchor "
                            f"block (anchor={anchor}, limiter={i}, end={end})")


class DecidingFactsAreConsultableContractTests(TestCase):
    """Side 1 of the earliest-decision invariant, proven FUNCTIONALLY rather than as
    prompt text: the personal truth that materially changes the answer must actually
    be RETRIEVABLE from the medicine entity surface.

    The instruction to ground is worthless if the surface cannot resolve the fork.
    The 2026-08-21 Tier-2 smoke resolved the missed-dose question using exactly three
    facts off this surface — the schedule (which days/times), the grace period, and
    when it was last taken — so a regression in any of them silently re-opens the
    class while every prompt-text assertion above still passes.

    Deliberately NOT medication-specific: it asserts the SHAPE of the entity contract
    (plan/performance dimensions), never a drug, a question, or a route.
    """

    def setUp(self):
        from datetime import date, time
        from django.conf import settings
        from django.contrib.auth import get_user_model
        from apps.health.models import Intake, IntakeSchedule
        from apps.users.models import TermsAcceptance
        user_model = get_user_model()
        self.user = user_model.objects.create_user(email="deciding@test.com", password="x")
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.med = Intake.objects.create(
            user=self.user, name="TestWeekly", dose="10mg", frequency="weekly",
            start_date=date(2026, 1, 1), intake_status="active",
            intake_type="medication", category="prescription",
            grace_period_minutes=60, instructions="Take with food.")
        IntakeSchedule.objects.create(intake=self.med, scheduled_time=time(7, 0),
                                      days_of_week="0", is_active=True)

    def _entity(self):
        from apps.health.services.medicine_queries import MedicineQueries
        ents = [e for e in MedicineQueries.describe(self.user) if e.identity == "TestWeekly"]
        self.assertEqual(len(ents), 1, "the medicine entity surface lost the record")
        return ents[0].to_dict()

    def test_the_surface_returns_the_facts_that_resolve_a_timing_fork(self):
        d = self._entity()
        plan = d.get("plan") or {}
        # WHEN it is due — times AND days, not a collapsed time list
        self.assertTrue(plan.get("schedule"), "no schedule times exposed")
        detail = plan.get("schedule_detail") or []
        self.assertTrue(detail, "no schedule_detail exposed — 'which days' is unanswerable")
        self.assertEqual(detail[0].get("days_of_week"), "0")
        # HOW LATE still counts, and HOW it is taken
        self.assertEqual(plan.get("grace_period_minutes"), 60)
        self.assertEqual(plan.get("instructions"), "Take with food.")
        # WHEN it was last taken — the other half of a missed-dose decision
        self.assertIn("last_taken", (d.get("performance") or {}))

    def test_the_advertisement_discloses_those_facts(self):
        """A retrievable fact the model is never told exists is not consultable.
        The advertisement must name the deciding facts, not just 'your medications'."""
        text = (domain_semantics("medicine").get("entities", {})
                .get("medication", "")).lower()
        for fact in ("schedule", "grace period", "instructions", "last taken"):
            self.assertIn(fact, text,
                          f"the medicine entity advertisement hides {fact!r}: {text!r}")
