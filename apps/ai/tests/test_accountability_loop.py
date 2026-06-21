"""Accountability loop — Chief-of-Staff memory of progress (2026-06-21).

"Have we made progress on my sleep / weight / glucose?" compares the metric now
vs ~4 weeks ago from EXISTING history and judges whether the focus is working —
grounded, no new model, plausibility-guarded (noisy/sparse → honest uncertainty).
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.ai import deterministic_router as dr

User = get_user_model()


class AccountabilityMatcher(SimpleTestCase):
    def test_matches_progress_questions(self):
        for q in ("have we made progress on my sleep",
                  "is my weight coming down",
                  "has my glucose improved over the last few weeks",
                  "are we making progress on my weight",
                  "is the sleep focus working"):
            self.assertTrue(dr._match_accountability_query(q), q)

    def test_excludes_plain_status(self):
        for q in ("how did i sleep", "what is my weight",
                  "what was my last glucose reading", "what's my glucose"):
            self.assertFalse(dr._match_accountability_query(q), q)

    def test_domain_extraction(self):
        self.assertEqual(dr._accountability_domain("progress on my sleep"), "sleep")
        self.assertEqual(dr._accountability_domain("is my weight coming down"), "weight")
        self.assertEqual(dr._accountability_domain("has my blood sugar improved"), "glucose")


def _user(email):
    u = User.objects.create_user(email=email, password="x" * 20)
    from apps.users.models import TermsAcceptance
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class AccountabilityAssessment(TestCase):
    def setUp(self):
        self.user = _user("acct@test.com")

    def _sleep(self, hours, days_ago):
        from apps.health.models import SleepEntry
        SleepEntry.objects.create(
            user=self.user,
            sleep_date=(timezone.now() - timedelta(days=days_ago)).date(),
            total_duration_minutes=int(hours * 60),
            bedtime=timezone.now() - timedelta(days=days_ago, hours=8),
            wake_time=timezone.now() - timedelta(days=days_ago))

    def _weigh(self, value, days_ago):
        from apps.health.models import WeightEntry
        WeightEntry.objects.create(
            user=self.user, value=value, unit="lb",
            recorded_at=timezone.now() - timedelta(days=days_ago))

    def test_sleep_improving_verdict(self):
        for d in range(0, 7):
            self._sleep(6.6, d)          # recent week ~6.6h
        for d in range(24, 31):
            self._sleep(5.8, d)          # ~4 weeks ago ~5.8h
        out = dr._accountability_assessment(self.user, "sleep")
        print(f"\n>>>ACCT-sleep: {out}\n<<<")
        self.assertIn("improved", out)
        self.assertIn("5.8h", out)
        self.assertIn("6.6h", out)
        self.assertIn("working", out)

    def test_weight_improving_verdict(self):
        self._weigh(305.0, 30)
        self._weigh(295.0, 0)
        out = dr._accountability_assessment(self.user, "weight")
        print(f"\n>>>ACCT-weight: {out}\n<<<")
        self.assertIn("improved", out)
        self.assertIn("305", out)
        self.assertIn("295", out)

    def test_flat_metric_prompts_different_approach(self):
        for d in range(0, 7):
            self._sleep(6.0, d)
        for d in range(24, 31):
            self._sleep(6.1, d)
        out = dr._accountability_assessment(self.user, "sleep")
        self.assertIn("flat", out.lower())
        self.assertIn("different approach", out.lower())

    def test_worsening_metric_prompts_change(self):
        self._weigh(295.0, 30)
        self._weigh(305.0, 0)            # gained → wrong way
        out = dr._accountability_assessment(self.user, "weight")
        self.assertIn("wrong way", out.lower())
        self.assertIn("change tack", out.lower())

    def test_no_clean_history_is_honest_not_false(self):
        out = dr._accountability_assessment(self.user, "sleep")
        self.assertIn("don't have enough clean sleep history", out.lower())

    def test_noisy_data_is_guarded(self):
        # Sub-3h fragments (HealthKit noise) are excluded → honest uncertainty,
        # never a false "improved from 1.4h".
        for d in range(0, 7):
            self._sleep(1.4, d)
        out = dr._accountability_assessment(self.user, "sleep")
        self.assertIn("don't have enough clean", out.lower())

    def test_routes_deterministically(self):
        for d in range(0, 7):
            self._sleep(6.6, d)
        for d in range(24, 31):
            self._sleep(5.8, d)
        res = dr.classify_and_route("have we made progress on my sleep", self.user)
        self.assertIsNotNone(res)
        self.assertEqual(res.route_name, "accountability_query")
        self.assertIn("improved", res.response)

    def test_no_domain_asks_which(self):
        out = dr._handle_accountability_query(self.user, "are we making progress")
        self.assertIn("which", out.lower())
