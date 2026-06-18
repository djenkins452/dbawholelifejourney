"""Phase 1 — Goals/Life PLANNING route (2026-06-18).

Long-range planning questions ("what should I focus on next month / this
quarter / be building toward?") are PLANNING, not EXECUTION. They must be
answered from grounded goal strategy (active Primary Mission + next milestone +
nightly momentum snapshot) — NEVER from today's overdue task list. The route
intercepts planning-category questions ahead of the next-step / decision /
focus execution gates.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai import deterministic_router as dr

User = get_user_model()


class PlanningMatcher(SimpleTestCase):
    def test_general_planning_questions_match(self):
        for q in (
            "what should i focus on next month",
            "what should i work on over the next few weeks",
            "what should i prioritize this quarter",
            "what should i be building toward",
        ):
            self.assertTrue(dr._match_planning_query(q), q)

    def test_execution_questions_do_not_match(self):
        # No future horizon → not planning → left to the execution gates.
        for q in (
            "what should i do next",
            "what should i focus on",
            "what should i fix first",
            "am i behind",
            "what's my biggest risk",
        ):
            self.assertFalse(dr._match_planning_query(q), q)

    def test_domain_scoped_planning_is_excluded(self):
        # Planning horizon but scoped to a tracked domain → NOT goal planning
        # (out of Phase 1 scope); handled elsewhere, not by goal strategy.
        for q in (
            "how can i improve my sleep next month",
            "what should my glucose look like next quarter",
            "what's my weight plan for the next few weeks",
        ):
            self.assertFalse(dr._match_planning_query(q), q)


def _user(email):
    u = User.objects.create_user(email=email, password="x" * 20)
    from apps.users.models import TermsAcceptance
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.purpose_enabled = True
    u.preferences.save()
    return u


class PlanningHandler(TestCase):
    def setUp(self):
        self.user = _user("plan@test.com")
        from apps.core.utils import get_user_today
        self.today = get_user_today(self.user)

    def _mission(self, **kw):
        from apps.purpose.models import LifeGoal
        kw.setdefault("status", "active")
        kw.setdefault("is_primary_mission", True)
        return LifeGoal.objects.create(user=self.user, **kw)

    def test_four_part_grounded_plan(self):
        goal = self._mission(
            title="Reach 185 lbs and run a half marathon",
            why_it_matters="So I can keep up with my kids without getting winded.",
            target_date=self.today + timedelta(days=90),
        )
        goal.milestones.create(
            title="Run 5 miles without stopping",
            description="Build base mileage to 5 miles at an easy pace.",
            target_date=self.today + timedelta(days=20),
        )
        out = dr._handle_planning_query(self.user, "what should i focus on next month")
        print(f"\n>>>PLAN: {out}\n<<<")
        # 1) strategic priority — the mission
        self.assertIn("Reach 185 lbs", out)
        # 2) why it matters — the user's OWN words
        self.assertIn("keep up with my kids", out)
        # 3) near-term milestone (+ its date)
        self.assertIn("Run 5 miles without stopping", out)
        # 4) next practical step — tied to the milestone, not today's tasks
        self.assertIn("Practical next step", out)
        self.assertIn("Build base mileage", out)

    def test_momentum_trend_when_snapshot_exists(self):
        goal = self._mission(title="Launch the side business",
                             target_date=self.today + timedelta(days=120))
        goal.milestones.create(title="Validate the idea with 10 customers")
        from apps.dashboard_v2.models import GoalMomentumSnapshot
        GoalMomentumSnapshot.objects.create(
            user=self.user, goal=goal, snapshot_date=self.today,
            momentum_score=70, progress_score=30, momentum_trend="rising")
        out = dr._handle_planning_query(self.user, "what should i prioritize this quarter")
        self.assertIn("building", out)            # rising → "building"
        self.assertIn("Validate the idea", out)

    def test_no_mission_is_honest_not_today_tasks(self):
        out = dr._handle_planning_query(self.user, "what should i focus on next month")
        self.assertIn("Primary Mission", out)
        self.assertIn("Goals", out)
        # Must NOT fabricate a direction or reach for today's task list.
        self.assertNotIn("overdue", out.lower())

    def test_target_date_framing_when_no_why(self):
        self._mission(title="Finish writing the book",
                     target_date=self.today + timedelta(days=60))
        out = dr._handle_planning_query(self.user, "what should i be building toward")
        self.assertIn("Finish writing the book", out)
        self.assertIn("target date", out.lower())


class PlanningRouting(TestCase):
    def setUp(self):
        self.user = _user("planroute@test.com")
        from apps.core.utils import get_user_today
        self.today = get_user_today(self.user)

    def test_planning_routes_not_to_execution(self):
        from apps.purpose.models import LifeGoal
        LifeGoal.objects.create(
            user=self.user, title="Get to a sustainable weight",
            status="active", is_primary_mission=True,
            target_date=self.today + timedelta(days=90))
        res = dr.classify_and_route("what should i focus on next month", self.user)
        self.assertIsNotNone(res)
        self.assertEqual(res.route_name, "planning_query")
        # The core bug: a planning question must NOT be answered by the
        # execution engines (next_action / decision / focus).
        self.assertNotIn(res.route_name,
                         ("next_action_canonical", "focus_query"))
        self.assertNotIn("next_action", res.route_name)

    def test_planning_intercepts_even_with_no_mission(self):
        # Even without a mission, a planning question is owned by the planning
        # route (honest answer) — it never falls through to today's tasks.
        res = dr.classify_and_route("what should i prioritize this quarter", self.user)
        self.assertIsNotNone(res)
        self.assertEqual(res.route_name, "planning_query")
        self.assertIn("Primary Mission", res.response)

    def test_execution_question_still_routes_to_execution(self):
        # Guard: a pure next-step question is unaffected by the planning gate.
        res = dr.classify_and_route("what should i do next", self.user)
        # Either next_action_canonical or a decision/focus route — never planning.
        route = getattr(res, "route_name", None) if res is not None else None
        if route is not None:
            self.assertNotEqual(route, "planning_query")
