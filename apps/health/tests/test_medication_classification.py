# ==============================================================================
# File: apps/health/tests/test_medication_classification.py
# Description: TRUST CONTRACT (2026-06-30) — Medication Adherence counts PRESCRIPTION
#   medications ONLY. It must never include supplements, vitamins, or wellness products.
#   Permanent regression so prescription adherence and supplement adherence can never be
#   merged again. Classifier: apps/health/medicine_classification.py.
# ==============================================================================
from datetime import date, time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.health.models import Intake, IntakeSchedule, IntakeLog
from apps.health.medicine_classification import (
    classify_intake, classification_q, PRESCRIPTION, SUPPLEMENT, OTC, WELLNESS,
)
from apps.health.medicine_utils import calculate_medicine_adherence
from apps.users.models import TermsAcceptance

User = get_user_model()


class _FakeIntake:
    intake_subtype = None
    category = "other"
    intake_type = "medication"

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class ClassifyIntakeTests(SimpleTestCase):
    def test_prescription_bucket(self):
        self.assertEqual(classify_intake(_FakeIntake(category="prescription")), PRESCRIPTION)
        # Insulin (any subtype) is always prescription, regardless of category.
        self.assertEqual(classify_intake(_FakeIntake(intake_subtype="insulin_basal",
                                                     category="other")), PRESCRIPTION)

    def test_supplement_bucket(self):
        for cat in ("vitamin", "mineral", "amino_acid", "herbal", "probiotic", "hormonal"):
            self.assertEqual(classify_intake(_FakeIntake(category=cat, intake_type="supplement")),
                             SUPPLEMENT, cat)

    def test_wellness_bucket(self):
        for cat in ("performance", "other"):
            self.assertEqual(classify_intake(_FakeIntake(category=cat, intake_type="medication")),
                             WELLNESS, cat)

    def test_otc_is_its_own_bucket(self):
        # OTC is no longer folded into Wellness (4-way business vocabulary).
        self.assertEqual(classify_intake(_FakeIntake(category="otc")), OTC)

    def test_supplements_are_never_prescription(self):
        for cat in ("vitamin", "mineral", "amino_acid", "herbal", "probiotic"):
            self.assertNotEqual(classify_intake(_FakeIntake(category=cat)), PRESCRIPTION, cat)


class AdherenceNeverMergesTests(TestCase):
    """The defining regression: prescription and supplement adherence are disjoint."""

    def setUp(self):
        self.user = User.objects.create_user(email="medclass@test.com", password="x")
        TermsAcceptance.objects.create(
            user=self.user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.start, self.end = date(2026, 2, 1), date(2026, 2, 7)

    def _med(self, name, **kw):
        d = {"user": self.user, "name": name, "dose": "10mg", "frequency": "daily",
             "start_date": date(2026, 1, 1), "intake_status": Intake.STATUS_ACTIVE}
        d.update(kw)
        m = Intake.objects.create(**d)
        IntakeSchedule.objects.create(intake=m, scheduled_time=time(8, 0),
                                      days_of_week="0,1,2,3,4,5,6", is_active=True)
        return m

    def _log_all_taken(self, med):
        d = self.start
        while d <= self.end:
            IntakeLog.objects.create(user=self.user, intake=med, scheduled_date=d,
                                     log_status="taken")
            d = date.fromordinal(d.toordinal() + 1)

    def test_prescription_adherence_excludes_supplements_and_wellness(self):
        # A perfectly-taken prescription, a never-taken vitamin, a never-taken OTC.
        rx = self._med("Metformin", category="prescription", intake_type="medication")
        self._log_all_taken(rx)
        self._med("Vitamin D", category="vitamin", intake_type="supplement")   # 0 logs
        self._med("Ibuprofen", category="otc", intake_type="medication")        # 0 logs

        rx_rate = calculate_medicine_adherence(
            self.user, self.start, self.end, classification="prescription")["adherence_rate"]
        self.assertEqual(rx_rate, 100)   # only the prescription counts → 100%, not dragged down

    def test_supplement_adherence_excludes_prescriptions(self):
        self._med("Metformin", category="prescription", intake_type="medication")  # 0 logs
        vit = self._med("Vitamin D", category="vitamin", intake_type="supplement")
        self._log_all_taken(vit)
        sup_rate = calculate_medicine_adherence(
            self.user, self.start, self.end, classification="supplement")["adherence_rate"]
        self.assertEqual(sup_rate, 100)   # only the supplement counts

    def test_the_two_metrics_are_disjoint(self):
        # Prescription taken 100%, supplement taken 0% → the numbers must differ, proving
        # they're computed over disjoint sets and can never be merged.
        rx = self._med("Metformin", category="prescription")
        self._log_all_taken(rx)
        self._med("Vitamin D", category="vitamin", intake_type="supplement")  # 0 taken
        rx_rate = calculate_medicine_adherence(
            self.user, self.start, self.end, classification="prescription")["adherence_rate"]
        sup_rate = calculate_medicine_adherence(
            self.user, self.start, self.end, classification="supplement")["adherence_rate"]
        routine = calculate_medicine_adherence(self.user, self.start, self.end)["adherence_rate"]
        self.assertEqual(rx_rate, 100)
        self.assertEqual(sup_rate, 0)
        # The mixed "health routine" number is BETWEEN the two — and is never the medication number.
        self.assertNotEqual(routine, rx_rate)
        self.assertTrue(sup_rate <= routine <= rx_rate)
