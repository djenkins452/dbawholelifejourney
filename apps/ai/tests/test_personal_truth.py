# ==============================================================================
# File: apps/ai/tests/test_personal_truth.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Personal Truth (Slice 1 — explicit durable facts). A deterministic,
#   read-only PROJECTION of module-owned durable user facts, delivered in standing
#   context AND via get_user_truth (one composer). Verifies the contract + that all
#   protected behaviors are unregressed.
# ==============================================================================
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.ai.cos_services.personal_truth import (
    build_personal_truth, get_user_truth, personal_truth_for_context,
)
from apps.health.models import MedicalCondition, NutritionGoals

User = get_user_model()


def _seed(user):
    today = date.today()
    NutritionGoals.objects.create(
        user=user, status="active", effective_from=today - timedelta(days=5),
        daily_calorie_target=1800, daily_protein_target_g=180,
        daily_carb_target_g=150, daily_fat_target_g=60,
        allergies=["shellfish"], dietary_preferences=["low sugar"])
    MedicalCondition.objects.create(
        user=user, status="active", condition_status="active_condition",
        name="Type 2 Diabetes", diagnosed_date=today - timedelta(days=400))


class PersonalTruthCompositionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="pt@test.com", password="x")
        _seed(self.user)

    def test_1_reads_from_authoritative_module_stores(self):
        p = build_personal_truth(self.user, use_cache=False)
        nut = {f["key"]: f for f in p["sections"]["nutrition"]["facts"]}
        self.assertEqual(nut["nutrition.calorie_target"]["value"], 1800.0)
        self.assertEqual(nut["nutrition.calorie_target"]["source"], "health.NutritionGoals")
        cond = next(f for f in p["sections"]["health"]["facts"]
                    if f["key"] == "health.active_conditions")
        self.assertIn("Type 2 Diabetes", cond["value"])
        self.assertEqual(cond["source"], "health.MedicalCondition")

    def test_2_owns_no_data_and_defines_no_model(self):
        # A projection, not a store: the module declares NO Django model.
        from django.apps import apps
        import apps.ai.cos_services.personal_truth as m
        module_models = [x for x in apps.get_models() if x.__module__ == m.__name__]
        self.assertEqual(module_models, [])
        # every fact points back to an owning module + authoritative source
        for sec in build_personal_truth(self.user, use_cache=False)["sections"].values():
            for f in sec["facts"]:
                self.assertTrue(f["module"] and f["source"])

    def test_3_standing_context_and_tool_use_the_same_composer(self):
        with mock.patch("apps.ai.cos_services.personal_truth.build_personal_truth",
                        wraps=build_personal_truth) as spy:
            personal_truth_for_context(build_personal_truth(self.user, use_cache=False))
            get_user_truth(self.user)
        # both paths route through the one composer
        self.assertGreaterEqual(spy.call_count, 1)
        # and they agree on values
        full = get_user_truth(self.user)
        ctx = personal_truth_for_context(full)
        self.assertEqual(ctx["facts"]["nutrition"][0]["value"],
                         full["sections"]["nutrition"]["facts"][0]["value"])

    def test_4_missing_module_degrades_independently(self):
        # One source failing must NOT erase facts from other modules.
        with mock.patch("apps.ai.cos_services.personal_truth._active_nutrition_goals",
                        side_effect=RuntimeError("nutrition db down")):
            p = build_personal_truth(self.user, use_cache=False)
        self.assertEqual(p["sections"]["nutrition"]["status"], "error")
        self.assertEqual(p["sections"]["health"]["status"], "ready")   # survived
        self.assertTrue(p["sections"]["relationship"]["facts"])

    def test_12_no_llm_used(self):
        # Deterministic: the module never imports/creates an LLM client.
        import apps.ai.cos_services.personal_truth as m
        import inspect
        src = inspect.getsource(m)
        self.assertNotIn("openai", src.lower())
        self.assertNotIn("_call_api", src)
        # runs with no ai_service anywhere in scope
        self.assertEqual(build_personal_truth(self.user, use_cache=False)["status"], "ready")

    def test_13_no_behavioral_inference_all_explicit(self):
        p = build_personal_truth(self.user, use_cache=False)
        self.assertEqual(p["provenance"], "explicit")
        for sec in p["sections"].values():
            for f in sec["facts"]:
                self.assertEqual(f["provenance"], "explicit")
                # no derived/inferred keys in slice 1
                self.assertNotIn("favorite", f["key"])
                self.assertNotIn("preferred", f["key"])
                self.assertNotIn("derived", f["key"])

    def test_data_contract_completeness(self):
        for sec in build_personal_truth(self.user, use_cache=False)["sections"].values():
            for f in sec["facts"]:
                for req in ("key", "value", "module", "source", "provenance",
                            "sensitivity", "standing"):
                    self.assertIn(req, f)

    def test_medical_facts_are_classified_sensitive(self):
        p = build_personal_truth(self.user, use_cache=False)
        cond = next(f for f in p["sections"]["health"]["facts"]
                    if f["key"] == "health.active_conditions")
        self.assertEqual(cond["sensitivity"], "medical")
        allergy = next(f for f in p["sections"]["nutrition"]["facts"]
                       if f["key"] == "nutrition.allergies")
        self.assertEqual(allergy["sensitivity"], "medical")

    def test_14_standing_context_is_bounded(self):
        import json
        ctx = personal_truth_for_context(build_personal_truth(self.user, use_cache=False))
        self.assertLess(len(json.dumps(ctx)), 4000)   # concise, must not inflate prompts


class EvidenceUtilizationProfileLeadTests(TestCase):
    """Evidence-UTILIZATION fix (2026-07-17): Personal Truth already reached the model as
    inert opaque-keyed JSON ~90% through the prompt, so the model quoted a 90g carb target
    and still wrote 185g. The profile lead reframes the SAME facts (single source) as HARD
    CONSTRAINTS, up front and readable — no new truth, no re-query."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="lead@test.com", password="x")
        _seed(self.user)
        from apps.ai.model_interface.service import ModelInterfaceService
        self.svc = ModelInterfaceService(self.user, ai_service=object())
        self.sc = self.svc.build_standing_context()

    def test_targets_are_surfaced_as_hard_constraints(self):
        lead = self.svc._profile_lead(self.sc)
        self.assertIn("1800 kcal", lead)
        self.assertIn("protein 180 g", lead)
        self.assertIn("carbs 150 g", lead)   # _seed uses carb 150
        self.assertIn("HARD CONSTRAINTS", lead)
        self.assertIn("NOT exceed the carb or fat targets", lead)
        self.assertIn("check them against these", lead)

    def test_conditions_and_allergies_are_surfaced(self):
        lead = self.svc._profile_lead(self.sc)
        self.assertIn("Type 2 Diabetes", lead)
        self.assertIn("MATERIALLY shape", lead)
        self.assertIn("shellfish", lead)

    def test_lead_reads_from_personal_truth_single_source(self):
        # No re-query: derived purely from the already-composed standing personal_truth.
        empty = self.svc._profile_lead({"personal_truth": {"facts": {}}})
        self.assertEqual(empty, "")
        none = self.svc._profile_lead({})
        self.assertEqual(none, "")

    def test_lead_is_positioned_before_the_buried_json_blob(self):
        prompt = self.svc._system_prompt(self.sc)
        self.assertLess(prompt.find("STANDING PROFILE"), prompt.find("STRUCTURED CONTEXT"))
        self.assertIn("never retrieve these facts and then produce a generic answer", prompt)

    def test_lead_is_bounded(self):
        self.assertLess(len(self.svc._profile_lead(self.sc)), 1600)

    def test_lead_never_raises_on_malformed_input(self):
        for bad in (None, {}, {"personal_truth": None},
                    {"personal_truth": {"facts": {"nutrition": [None, {"key": None}]}}}):
            self.assertEqual(self.svc._profile_lead(bad), "")


class PersonalTruthConflictPolicyTests(TestCase):
    """Conflicting stored targets (NutritionGoals vs meals.DietaryProfile) are surfaced
    as a CONTRADICTION with deterministic precedence — never AI-resolved, never hidden."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="ptc@test.com", password="x")

    def test_disagreeing_targets_surface_a_contradiction(self):
        today = date.today()
        NutritionGoals.objects.create(user=self.user, status="active",
                                      effective_from=today, daily_calorie_target=1800)
        try:
            from apps.meals.models import DietaryProfile
            DietaryProfile.objects.create(user=self.user, status="active",
                                          calorie_target=2200)
        except Exception:
            self.skipTest("DietaryProfile shape differs in this env")
        p = build_personal_truth(self.user, use_cache=False)
        cal = next(c for c in p["contradictions"]
                   if c["key"] == "nutrition.calorie_target")
        self.assertEqual(cal["canonical"]["source"], "health.NutritionGoals")
        self.assertEqual(cal["canonical"]["value"], 1800.0)
        self.assertEqual(cal["conflicting"]["value"], 2200.0)
        # canonical value is what's exposed as the FACT (deterministic precedence)
        fact = next(f for f in p["sections"]["nutrition"]["facts"]
                    if f["key"] == "nutrition.calorie_target")
        self.assertEqual(fact["value"], 1800.0)


class ProtectedBehaviorsUnregressedTests(TestCase):
    """Requirements 5-11: nothing Personal Truth touches is weakened."""

    def setUp(self):
        self.user = User.objects.create_user(email="prot@test.com", password="x")

    def test_5_ai_relationship_intact(self):
        from apps.ai.cos_services.ai_relationship import get_ai_relationship
        rel = get_ai_relationship(self.user)
        self.assertIn("assistant", rel)

    def test_6_foundational_health_facts_intact(self):
        from apps.ai.cos_services import get_foundational_health_facts
        r = get_foundational_health_facts(self.user, keys=["daily_calories"])
        self.assertIsInstance(r, dict)

    def test_7_domain_truth_surfaces_intact(self):
        from apps.ai.cos_services.domain_entity import entity_capability_index
        from apps.ai.cos_services.domain_analysis import analysis_capability_index
        idx = entity_capability_index()
        self.assertIn("workout", idx.get("health", ()))
        self.assertIn("entry", idx.get("journal", ()))
        self.assertIn("food", idx.get("nutrition", ()))
        self.assertIn("workouts", analysis_capability_index().get("health", ()))

    def test_8_journal_entry_and_mood_retrieval_intact(self):
        from apps.journal.models import JournalEntry
        from apps.ai.cos_services.domain_entity import get_domain_entity
        JournalEntry.objects.create(user=self.user, entry_date=date.today(),
                                    title="t", body="<p>calm day</p>", mood="calm")
        r = get_domain_entity(self.user, "journal", entity_type="entry")
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["entities"][0]["definition"]["mood"], "calm")

    def test_9_nutrition_food_retrieval_intact(self):
        from apps.health.models import FoodEntry
        from apps.ai.cos_services.domain_entity import get_domain_entity
        FoodEntry.objects.create(user=self.user, logged_date=date.today(),
            meal_type=FoodEntry.MEAL_BREAKFAST, food_name="Eggs", quantity=Decimal("2"),
            serving_size=Decimal("1"), serving_unit="unit", status="active",
            total_calories=Decimal("140"), total_protein_g=Decimal("12"))
        r = get_domain_entity(self.user, "nutrition", entity_type="food")
        self.assertEqual(r["status"], "ready")

    def test_10_weight_retrieval_intact(self):
        from apps.ai.cos_services.domain_analysis import get_domain_analysis
        r = get_domain_analysis(self.user, "health", "weight")
        self.assertIn(r["status"], ("ready", "empty"))   # a valid deterministic state

    def test_11_tool_loop_budgets_and_timeout_unchanged(self):
        from apps.ai.services import resolve_tool_loop_budgets, get_timeout_for_endpoint
        self.assertEqual(resolve_tool_loop_budgets("model_interface"), (3500, 7))
        self.assertEqual(get_timeout_for_endpoint("model_interface"), 45)

    def test_truth_tool_set_is_the_approved_set(self):
        from apps.ai.model_interface.constitution import truth_tools
        names = {t["function"]["name"] for t in truth_tools()}
        from apps.ai.tests.truth_tool_contract import APPROVED_TRUTH_TOOLS
        self.assertEqual(names, APPROVED_TRUTH_TOOLS)
