# ==============================================================================
# File: apps/ai/tests/test_domain_analysis.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The ANALYSIS truth surface — the deterministic guarantee behind
#   "investigate before concluding". Encodes the BEHAVIORAL CONTRACT as a
#   deterministic, model-free test: when WLJ holds relevant truth for a subject,
#   get_domain_analysis returns it composed in ONE bundle with holds_data=True
#   (so a reasoner cannot truthfully say "insufficient"); only a genuine absence
#   of WLJ truth yields status=empty / holds_data=False. Composition only — it
#   reuses the domain's existing history()/describe() surfaces; no new retrieval.
# ==============================================================================
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_services.domain_analysis import (
    analysis_capability_index,
    analysis_capable_domains,
    get_domain_analysis,
)
from apps.health.models import (
    Exercise, ExerciseSet, WorkoutExercise, WorkoutSession,
)

User = get_user_model()


def _seed_workouts(user, days):
    today = date.today()
    for d in days:
        s = WorkoutSession.objects.create(user=user, date=today - timedelta(days=d),
                                          name=f"Day{d}")
        ex = Exercise.objects.create(name="Standing Calf Raise", category="resistance",
                                     load_type="external", is_active=True)
        we = WorkoutExercise.objects.create(session=s, exercise=ex, order=0)
        ExerciseSet.objects.create(workout_exercise=we, set_number=1,
                                   weight=Decimal("135"), reps=12)


class AnalysisCapabilityTests(TestCase):
    def test_health_advertises_analyzable_subjects(self):
        idx = analysis_capability_index()
        self.assertIn("health", idx)
        for subject in ("workouts", "weight", "sleep", "steps"):
            self.assertIn(subject, idx["health"])
        self.assertIn("health", analysis_capable_domains())


class AnalysisGuaranteeTests(TestCase):
    """THE acceptance criterion, deterministic: truth present → never 'insufficient'."""

    def setUp(self):
        self.user = User.objects.create_user(email="analysis@test.com", password="x")

    def test_present_truth_yields_holds_data_with_the_full_bundle(self):
        # The exact failing scenario: workouts logged this month → "analyze my workout trends"
        _seed_workouts(self.user, days=[1, 3, 6, 9])
        a = get_domain_analysis(self.user, "health", "workouts")

        self.assertEqual(a["status"], "ready")
        self.assertTrue(a["holds_data"])            # ← the reasoner MUST NOT say "insufficient"
        self.assertEqual(a["evidence"], "rich")     # 4 sessions ≥ threshold

        # One call carried the WHOLE investigation:
        self.assertEqual(a["all_time"]["total"], 4)                 # span/count
        self.assertTrue(a["all_time"]["span"]["start"])
        self.assertTrue(any(w.get("present")                        # trailing-window trend
                            for w in a["history"].values()))
        self.assertEqual(a["records"]["count"], 4)                  # record detail present
        # …and the detail is real (exercises/sets/reps/weights), not just a count
        first = a["records"]["records"][0]
        self.assertIn("Calf Raise", str(first))                     # the exercise, in the record

    def test_recent_activity_never_reads_empty_via_a_prior_calendar_window(self):
        # The period-semantics trap that produced the false "insufficient": this-month
        # activity must surface even though a prior calendar window (last_month) is empty.
        _seed_workouts(self.user, days=[0, 2, 5])
        a = get_domain_analysis(self.user, "health", "workouts")
        self.assertEqual(a["status"], "ready")
        self.assertTrue(a["holds_data"])
        self.assertTrue(a["history"]["this_month"]["present"])

    def test_thin_but_present_truth_is_thin_not_absent(self):
        _seed_workouts(self.user, days=[2])          # a single session
        a = get_domain_analysis(self.user, "health", "workouts")
        self.assertEqual(a["status"], "ready")
        self.assertTrue(a["holds_data"])
        self.assertEqual(a["evidence"], "thin")      # present but < threshold — still NOT insufficient

    def test_genuine_absence_is_the_only_insufficient(self):
        # No workouts at all → the ONE honest "insufficient".
        a = get_domain_analysis(self.user, "health", "workouts")
        self.assertEqual(a["status"], "empty")
        self.assertFalse(a["holds_data"])
        self.assertEqual(a["evidence"], "absent")

    def test_subject_without_entity_still_composes_history(self):
        # A history-only subject (weight) has no records but still analyzes.
        from django.utils import timezone
        from apps.health.models import WeightEntry
        now = timezone.now()
        for d in (1, 4, 8):
            WeightEntry.objects.create(user=self.user, value=Decimal("185.0"),
                                       unit="lb", recorded_at=now - timedelta(days=d))
        a = get_domain_analysis(self.user, "health", "weight")
        self.assertEqual(a["status"], "ready")
        self.assertTrue(a["holds_data"])
        self.assertIsNone(a.get("records"))          # no entity surface for weight


class AnalysisHonestStateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="analysis2@test.com", password="x")

    def test_unknown_subject_is_unsupported_not_a_guess(self):
        a = get_domain_analysis(self.user, "health", "quidditch")
        self.assertEqual(a["status"], "unsupported")
        self.assertIn("workouts", a["analyzable_subjects"])

    def test_unknown_domain_is_unsupported_domain(self):
        a = get_domain_analysis(self.user, "atlantis", "workouts")
        self.assertEqual(a["status"], "unsupported_domain")
