# ==============================================================================
# File: apps/health/tests/test_medicine_domain_truth.py
# Description: LAYER 1 — Medication Canonical Truth. The Medicine Domain Truth answers
#   inventory / today-execution / adherence DIRECTLY from the canonical models, so Beth
#   can answer with the SAE DISABLED/STALE/MISSING. "Medicine" = PRESCRIPTION only;
#   Supplement / OTC / Wellness are never medicine. Acceptance + permanent regression.
# ==============================================================================
from datetime import date, time, timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.core.utils import get_user_today
from apps.core.truth.domain import get_domain_truth, registered_domains
from apps.health.models import Intake, IntakeSchedule, IntakeLog
from apps.health.medicine_classification import (
    classify_intake, PRESCRIPTION, SUPPLEMENT, OTC, WELLNESS,
)
from apps.health.services.medicine_queries import MedicineQueries
from apps.ai.chatgpt_cos.foundational_facts import (
    classify_foundational_fact, answer_fact_by_key,
)
from apps.users.models import TermsAcceptance

User = get_user_model()


def _sae_disabled():
    """Patch the SAE so any read raises — proves canonical truth needs no SAE."""
    return mock.patch("apps.core.ai_state.state_engine.get_module_state",
                      side_effect=RuntimeError("SAE DISABLED"))


class _FakeIntake:
    intake_subtype = None
    category = "other"
    intake_type = "medication"

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class FourWayClassificationTests(SimpleTestCase):
    def test_four_canonical_buckets(self):
        self.assertEqual(classify_intake(_FakeIntake(category="prescription")), PRESCRIPTION)
        self.assertEqual(classify_intake(_FakeIntake(intake_subtype="insulin_basal")), PRESCRIPTION)
        self.assertEqual(classify_intake(_FakeIntake(category="vitamin")), SUPPLEMENT)
        self.assertEqual(classify_intake(_FakeIntake(category="otc")), OTC)         # own bucket
        self.assertEqual(classify_intake(_FakeIntake(category="performance")), WELLNESS)
        self.assertEqual(classify_intake(_FakeIntake(category="other")), WELLNESS)

    def test_otc_is_not_medicine_and_not_supplement_and_not_wellness(self):
        c = classify_intake(_FakeIntake(category="otc"))
        self.assertEqual(c, OTC)
        self.assertNotIn(c, (PRESCRIPTION, SUPPLEMENT, WELLNESS))


class MedicineDomainTruthTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="mdt@test.com", password="x")
        TermsAcceptance.objects.create(
            user=self.user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.today = get_user_today(self.user)

    def _med(self, name, category, intake_type="medication", schedule=True):
        m = Intake.objects.create(user=self.user, name=name, dose="10mg", frequency="daily",
                                  start_date=date(2026, 1, 1), intake_status="active",
                                  intake_type=intake_type, category=category)
        if schedule:
            # 00:01 so today's dose is always already "due" (deterministic adherence).
            IntakeSchedule.objects.create(intake=m, scheduled_time=time(0, 1),
                                          days_of_week="0,1,2,3,4,5,6", is_active=True)
        return m

    def _seed(self):
        rx1 = self._med("Metformin", "prescription")
        rx2 = self._med("Lisinopril", "prescription")
        self._med("Vitamin D", "vitamin", intake_type="supplement")   # supplement
        self._med("Ibuprofen", "otc")                                 # OTC
        self._med("Creatine", "performance", intake_type="supplement")  # wellness
        return rx1, rx2

    # -- the medicine domain truth is registered --------------------------------
    def test_medicine_is_a_registered_domain(self):
        self.assertIn("medicine", registered_domains())

    # -- inventory: prescription only -------------------------------------------
    def test_inventory_is_prescription_only(self):
        self._seed()
        names = MedicineQueries.active_names(self.user)
        self.assertEqual(names, ["Lisinopril", "Metformin"])
        self.assertNotIn("Vitamin D", names)      # supplement excluded
        self.assertNotIn("Ibuprofen", names)      # OTC excluded
        self.assertNotIn("Creatine", names)       # wellness excluded

    def test_supplement_and_otc_are_separately_retrievable(self):
        self._seed()
        self.assertEqual(MedicineQueries.active_names(self.user, SUPPLEMENT), ["Vitamin D"])
        self.assertEqual(MedicineQueries.active_names(self.user, OTC), ["Ibuprofen"])

    # -- ACCEPTANCE: SAE disabled, Beth still answers ---------------------------
    def _ask(self, q):
        key = classify_foundational_fact(q)
        with _sae_disabled():
            r = answer_fact_by_key(self.user, key)
        return key, (r or {}).get("answer", "")

    def test_acceptance_with_sae_disabled(self):
        rx1, rx2 = self._seed()
        # Full 90-day coverage so all three windows are cleanly 100%.
        for i in range(91):
            for rx in (rx1, rx2):
                IntakeLog.objects.create(user=self.user, intake=rx,
                                         scheduled_date=self.today - timedelta(days=i),
                                         log_status="taken")

        key, ans = self._ask("What prescription medications am I taking?")
        self.assertEqual(key, "current_medications")
        self.assertIn("Metformin", ans)
        self.assertIn("Lisinopril", ans)
        self.assertNotIn("Vitamin D", ans)        # never medicine
        self.assertNotIn("Ibuprofen", ans)        # never medicine

        key, ans = self._ask("Did I take my prescription medications today?")
        self.assertEqual(key, "meds_today")
        self.assertIn("2", ans)                   # 2 prescription doses today

        for q, k in (("What is my 7-day medication adherence?", "adherence_7d"),
                     ("What is my 30-day medication adherence?", "adherence_30d"),
                     ("What is my 90-day medication adherence?", "adherence_90d")):
            key, ans = self._ask(q)
            self.assertEqual(key, k)
            self.assertIn("100%", ans)            # all prescription doses taken
            self.assertIn("adherence", ans.lower())

    def test_adherence_excludes_supplements_and_otc(self):
        # Prescriptions perfectly taken; supplement + OTC never logged. Medication
        # Adherence must be 100% (supplements/OTC do not drag it down).
        rx1, rx2 = self._seed()
        for i in range(8):     # full 7-day window (today-7 … today)
            for rx in (rx1, rx2):
                IntakeLog.objects.create(user=self.user, intake=rx,
                                         scheduled_date=self.today - timedelta(days=i),
                                         log_status="taken")
        with _sae_disabled():
            truth = get_domain_truth(self.user, "medicine").current("adherence_7d")
        self.assertEqual(truth.value, 100)
        self.assertEqual(truth.detail["scope"], "prescription")

    def test_mistagged_supplements_never_appear_in_prescription_inventory(self):
        # Production trust failure (2026-06-30): Fish Oil + Magnesium glycinate were tagged
        # category='prescription' and appeared under prescription medications. The
        # supplement-name safety net must exclude them everywhere — even mis-tagged.
        from datetime import date

        def mistag(name):
            return Intake.objects.create(user=self.user, name=name, dose="x", frequency="daily",
                                         start_date=date(2026, 1, 1), intake_status="active",
                                         intake_type="medication", category="prescription")
        prod = ["Atorvastatin", "Fish Oil", "Magnesium glycinate",
                "Metformin HCL ER", "Mounjaro", "Valsartan"]
        for nm in prod:
            mistag(nm)
        Intake.objects.create(user=self.user, name="Lantus SoloStar", dose="x",
                              frequency="daily", start_date=date(2026, 1, 1),
                              intake_status="active", intake_type="medication",
                              category="other", intake_subtype="insulin_basal")

        rx = MedicineQueries.active_names(self.user)
        self.assertNotIn("Fish Oil", rx)                  # supplement — never medicine
        self.assertNotIn("Magnesium glycinate", rx)       # supplement — never medicine
        self.assertEqual(rx, ["Atorvastatin", "Lantus SoloStar", "Metformin HCL ER",
                              "Mounjaro", "Valsartan"])    # exactly the 5 real prescriptions
        self.assertIn("Fish Oil", MedicineQueries.active_names(self.user, SUPPLEMENT))

    def test_current_medications_is_deterministic_exactly_the_canonical_list(self):
        # The answer must be EXACTLY the canonical prescription list — the LLM is bypassed
        # so it can never embellish or pull supplements from broader context.
        from apps.ai.chatgpt_cos.foundational_facts import (
            classify_foundational_fact, answer_fact_by_key, _NUMERIC_VALUE_KEYS,
        )
        self.assertIn("current_medications", _NUMERIC_VALUE_KEYS)   # deterministic
        from datetime import date
        Intake.objects.create(user=self.user, name="Fish Oil", dose="x", frequency="daily",
                              start_date=date(2026, 1, 1), intake_status="active",
                              intake_type="medication", category="prescription")
        self._med("Metformin", "prescription")
        key = classify_foundational_fact("List my active prescription medications.")
        with _sae_disabled(), mock.patch(
                "apps.ai.services.ai_service._call_api",
                side_effect=AssertionError("LLM must not be called for current_medications")):
            ans = answer_fact_by_key(self.user, key)["answer"]
        self.assertIn("Metformin", ans)
        self.assertNotIn("Fish Oil", ans)                 # supplement excluded, deterministically

    def test_describe_returns_complete_entities(self):
        # Entity Completeness Contract: each prescription is a CompleteEntity describing
        # itself across ALL business dimensions.
        from apps.core.truth.entity import CompleteEntity
        rx1, rx2 = self._seed()
        for i in range(8):
            for rx in (rx1, rx2):
                IntakeLog.objects.create(user=self.user, intake=rx,
                                         scheduled_date=self.today - timedelta(days=i),
                                         log_status="taken")
        entities = MedicineQueries.describe(self.user)
        self.assertEqual(len(entities), 2)
        self.assertTrue(all(isinstance(e, CompleteEntity) for e in entities))
        e = entities[0]
        self.assertEqual(e.kind, "medication")
        self.assertTrue(e.identity)                         # Identity
        self.assertIn("dose", e.definition)                 # Definition
        self.assertIn("category", e.definition)
        self.assertTrue(e.status)                           # Status
        self.assertIn("schedule", e.plan)                   # Plan
        self.assertIn("today", e.standing)                  # Standing
        self.assertIn("expected", e.standing["today"])
        self.assertIn("adherence", e.performance)           # Performance (per-med)
        self.assertEqual(e.performance["adherence"]["7d"], 100)
        self.assertTrue(e.freshness and e.confidence)       # Layer 1 trust properties
        names = sorted(x.identity for x in entities)
        self.assertEqual(names, ["Lisinopril", "Metformin"])
        self.assertNotIn("Vitamin D", names)                # supplements never described as meds
        # Domain summary (composed inside Layer 1)
        summ = MedicineQueries.summary(self.user)
        self.assertEqual(summ["count"], 2)
        self.assertEqual(set(summ["adherence"]), {"7d", "30d", "90d"})

    def test_describe_pattern_is_on_the_domain_truth(self):
        # The reusable Layer 1 pattern: get_domain_truth(...).describe() → CompleteEntity.
        from apps.core.truth.entity import CompleteEntity
        self._seed()
        entities = get_domain_truth(self.user, "medicine").describe()
        self.assertTrue(entities and all(isinstance(e, CompleteEntity) for e in entities))
        self.assertIn("medication",
                      get_domain_truth(self.user, "medicine").supports()["entities"])

    def test_single_retrieval_answers_the_full_question(self):
        # ACCEPTANCE: the detailed request is one retrieval of the canonical object —
        # the answer naturally contains name, dose, category, status, schedule, taken
        # today, and 7-day adherence. SAE disabled; LLM bypassed (deterministic).
        from apps.ai.chatgpt_cos.foundational_facts import (
            classify_foundational_fact, answer_fact_by_key, _NUMERIC_VALUE_KEYS,
        )
        rx1, rx2 = self._seed()
        for i in range(8):
            for rx in (rx1, rx2):
                IntakeLog.objects.create(user=self.user, intake=rx,
                                         scheduled_date=self.today - timedelta(days=i),
                                         log_status="taken")
        q = ("List all of my active prescription medications. For each one show: Name, "
             "Dose, Category, Status, Schedule, Whether I took it today, "
             "My 7-day medication adherence.")
        key = classify_foundational_fact(q)
        self.assertEqual(key, "medication_profile")          # one canonical retrieval
        self.assertIn("medication_profile", _NUMERIC_VALUE_KEYS)   # deterministic
        with _sae_disabled(), mock.patch(
                "apps.ai.services.ai_service._call_api",
                side_effect=AssertionError("LLM must not be called")):
            ans = answer_fact_by_key(self.user, key)["answer"]
        self.assertIn("Metformin", ans)
        self.assertIn("10mg", ans)                           # dose
        self.assertIn("prescription", ans.lower())           # category
        self.assertIn("active", ans.lower())                 # status
        self.assertIn("taken today", ans.lower())            # whether taken today
        self.assertIn("7-day", ans.lower())                  # 7-day adherence
        self.assertIn("100%", ans)                           # the adherence value

    def test_inventory_is_present_not_unknown_when_empty(self):
        # No prescriptions → a real "0", never the SAE-missing "unknown" failure.
        self._med("Vitamin D", "vitamin", intake_type="supplement")
        with _sae_disabled():
            truth = get_domain_truth(self.user, "medicine").current("current_medications")
        self.assertTrue(truth.present)            # present, confident — not unknown
        self.assertEqual(truth.value, [])
