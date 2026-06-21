"""Unified CoS intelligence — goal pace (Cap 5) + single-brain integration.

Goal-pace trajectory from real weight history, and the standing-read narrative
that gets injected into Beth's normal conversation context (no trigger phrase).
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.ai import cos_intelligence as ci
from apps.ai import deterministic_router as dr

User = get_user_model()


class PaceMatcher(SimpleTestCase):
    def test_matches(self):
        for q in ("am i on pace", "when will i reach my goal",
                  "what pace am i on", "how long until i reach my goal"):
            self.assertTrue(dr._match_goal_pace_query(q), q)

    def test_excludes_plain(self):
        for q in ("what is my weight", "how did i sleep"):
            self.assertFalse(dr._match_goal_pace_query(q), q)


class NarrativeShape(SimpleTestCase):
    def test_pace_narrative_none_safe(self):
        self.assertIsNone(ci.goal_pace_narrative(None))

    def test_standing_read_none_when_empty(self):
        self.assertIsNone(ci.cos_intelligence_narrative({}))

    def test_standing_read_renders_sections(self):
        out = ci.cos_intelligence_narrative({
            "overall": "Net: positive.",
            "goal_pace_narrative": "Weight 298 → 240 (58 to go).",
            "recommendation_effectiveness": "Sleep is working."})
        self.assertIn("CHIEF OF STAFF STANDING READ", out)
        self.assertIn("Net: positive.", out)
        self.assertIn("Goal pace:", out)
        self.assertIn("Recommendation status:", out)


def _user(email):
    u = User.objects.create_user(email=email, password="x" * 20)
    from apps.users.models import TermsAcceptance
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class GoalPace(TestCase):
    def setUp(self):
        self.user = _user("pace@test.com")

    def _weigh(self, value, days_ago):
        from apps.health.models import WeightEntry
        WeightEntry.objects.create(
            user=self.user, value=value, unit="lb",
            recorded_at=timezone.now() - timedelta(days=days_ago))

    def _goal(self, goal, target_days_from_now):
        from apps.health.models import HealthProfile
        hp, _ = HealthProfile.objects.get_or_create(user=self.user)
        hp.weight_goal = goal
        hp.weight_goal_unit = "lb"
        hp.weight_goal_target_date = (
            timezone.now().date() + timedelta(days=target_days_from_now))
        hp.save()
        return hp

    def test_on_pace_projects_completion(self):
        self._weigh(310.0, 60)
        self._weigh(295.0, 0)            # 15 lb / 60d = 1.75 lb/wk
        self._goal(240.0, 365)           # plenty of time → on pace
        p = ci.goal_pace(self.user)
        print(f"\n>>>PACE on: {ci.goal_pace_narrative(p)}\n<<<")
        self.assertEqual(p["direction"], "lose")
        self.assertGreater(p["current_pace_lb_wk"], 1.0)
        self.assertIn("projected_date", p)
        self.assertTrue(p["on_pace"])
        self.assertIn("ON pace", ci.goal_pace_narrative(p))

    def test_behind_pace_prompts_change(self):
        self._weigh(300.0, 60)
        self._weigh(298.0, 0)            # only 2 lb / 60d → slow
        self._goal(240.0, 30)            # 58 lb in 30d → impossible pace
        p = ci.goal_pace(self.user)
        self.assertFalse(p["on_pace"])
        n = ci.goal_pace_narrative(p)
        self.assertIn("behind pace", n)

    def test_target_passed(self):
        self._weigh(310.0, 60)
        self._weigh(298.0, 0)
        self._goal(240.0, -5)            # target 5 days in the past
        p = ci.goal_pace(self.user)
        self.assertTrue(p.get("target_passed"))
        self.assertIn("already passed", ci.goal_pace_narrative(p))

    def test_insufficient_history(self):
        self._weigh(300.0, 2)
        self._weigh(299.0, 0)            # < 7 days span
        self._goal(240.0, 365)
        p = ci.goal_pace(self.user)
        self.assertTrue(p.get("insufficient"))
        self.assertIn("Not enough", ci.goal_pace_narrative(p))

    def test_no_goal_returns_none(self):
        self._weigh(300.0, 10)
        self.assertIsNone(ci.goal_pace(self.user))

    def test_build_intelligence_includes_pace(self):
        self._weigh(310.0, 60)
        self._weigh(295.0, 0)
        self._goal(240.0, 365)
        intel = ci.build_cos_intelligence(self.user)
        self.assertIn("goal_pace", intel)
        self.assertIn("goal_pace_narrative", intel)

    def test_route(self):
        self._weigh(310.0, 60)
        self._weigh(295.0, 0)
        self._goal(240.0, 365)
        res = dr.classify_and_route("am i on pace", self.user)
        self.assertEqual(res.route_name, "goal_pace_query")
        self.assertIn("lb/week", res.response)
