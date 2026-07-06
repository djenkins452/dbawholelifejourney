# ==============================================================================
# File: apps/ai/tests/test_goals_checkin_strategic.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: ONE BRAIN — the Goals & Commitments and Whole Life check-ins must consume
#   the SAME executive understanding as the Executive Briefing/Opportunity. The bug: the
#   check-in resolvers returned a hardcoded "_GOALS_GAP" ("I don't have enough active
#   goal information") with ZERO goal read, so Beth denied knowing any goals while the
#   Briefing cited the mission. These tests prove the check-in now reads interpret() +
#   the mission snapshot + the canonical mission pick, and only claims "no goals" when
#   there genuinely are none.
# ==============================================================================
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.chatgpt_cos.lanes import (
    _strategic_summary, _goals_checkin_lane, resolve_clarification_option,
)
from apps.ai.chatgpt_cos.executive_interpretation import ExecutiveSignals

User = get_user_model()

_INTERP = "apps.ai.chatgpt_cos.executive_interpretation.interpret"
_GDS = "apps.ai.cos_services.get_domain_state"
_MISSION = "apps.purpose.mission_selection.select_active_mission_goal"

# The mission the Executive Briefing/Opportunity already see, via interpret().
_SIG = ExecutiveSignals(
    strategic_focus="France 2027",
    highest_leverage="moving France 2027 forward — that's where the leverage is today")
# active_titles are RICH DICTS in production (title + context + evidence + …), not
# strings — this fixture mirrors that so the tests exercise the real shape.
_STATE = {"state": {
    "mission": {"title": "France 2027", "current_focus": "Book the flights",
                "days_remaining": 540, "momentum_trend": "rising"},
    "active_titles": [{"title": "France 2027", "context": {}, "evidence": {}},
                      {"title": "Read 24 books", "context": {}, "evidence": {}}],
    "active_goal_count": 2}}


def _with_mission():
    return (mock.patch(_INTERP, return_value=_SIG),
            mock.patch(_GDS, return_value=_STATE),
            mock.patch(_MISSION, return_value=mock.Mock(title="France 2027")))


class StrategicSummaryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="gc@test.com", password="x")

    def test_summary_consumes_the_one_brain(self):
        a, b, c = _with_mission()
        with a, b, c:
            out = _strategic_summary(self.user)
        self.assertIsNotNone(out)
        self.assertIn("France 2027", out)                       # the mission
        self.assertIn("current milestone", out.lower())         # today's concrete move
        self.assertIn("book the flights", out.lower())          # the actual milestone
        self.assertIn("read 24 books", out.lower())             # other commitment

    def test_matches_interpret_strategic_focus(self):
        # Proof of one brain: the check-in surfaces the SAME mission interpret() holds.
        a, b, c = _with_mission()
        with a, b, c:
            out = _strategic_summary(self.user)
        self.assertIn(_SIG.strategic_focus, out)

    def test_honest_empty_only_when_truly_no_goals(self):
        with mock.patch(_INTERP, return_value=ExecutiveSignals()), \
                mock.patch(_GDS, return_value={"state": {"active_goal_count": 0}}), \
                mock.patch(_MISSION, return_value=None):
            self.assertIsNone(_strategic_summary(self.user))

    def test_dict_shaped_active_titles_never_crash_or_gap(self):
        # PROD REGRESSION: active_titles came back as rich DICTS, `", ".join(dicts)` raised
        # TypeError('sequence item 0: expected str instance, dict found'), the resolver's
        # except returned _GOALS_GAP — falsely telling the user there were no goals.
        prod_state = {"state": {
            "mission": {"title": "France 2027 Family 18K Mission",
                        "current_focus": "Goal Weight 279.9", "momentum_trend": "moderate"},
            "active_titles": [
                {"title": "Launch Whole Life Journey", "context": {"has_milestones": True},
                 "evidence": {"momentum": "moderate"}, "target_date": "2026-12-25"},
                {"title": "Relationship with God", "context": {}, "evidence": {}},
                {"title": "Serve Others"},
                {"title": "France 2027 Family 18K Mission", "is_foundational": True},
            ],
            "active_goal_count": 4}}
        sig = ExecutiveSignals(strategic_focus="France 2027 Family 18K Mission",
                               highest_leverage="moving the mission forward")
        with mock.patch(_INTERP, return_value=sig), \
                mock.patch(_GDS, return_value=prod_state), \
                mock.patch(_MISSION, return_value=mock.Mock(title="France 2027 Family 18K Mission")):
            out = _strategic_summary(self.user)
            # and end-to-end through the resolver (the actual check-in "4" path)
            resolved = resolve_clarification_option(self.user, {"resolver": "goals_gap"})
        self.assertIsNotNone(out)
        self.assertNotIn("don't have enough active goal information", out.lower())
        self.assertIn("France 2027 Family 18K Mission", out)
        self.assertIn("launch whole life journey", out.lower())   # dict title extracted
        self.assertIn("goal weight 279.9", out.lower())           # current milestone move
        self.assertNotIn("don't have enough active goal information", resolved.lower())
        self.assertIn("France 2027 Family 18K Mission", resolved)

    def test_never_empty_when_mission_exists_despite_stale_snapshot(self):
        # Requirement 4: never claim "no goals" while a mission exists — even if the
        # domain snapshot is momentarily empty/pending.
        with mock.patch(_INTERP, return_value=ExecutiveSignals()), \
                mock.patch(_GDS, return_value={"state": {}}), \
                mock.patch(_MISSION, return_value=mock.Mock(title="France 2027")):
            out = _strategic_summary(self.user)
        self.assertIsNotNone(out)
        self.assertIn("France 2027", out)


class CheckinResolverTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="gcr@test.com", password="x")

    def test_goals_option_no_longer_returns_hardcoded_gap(self):
        a, b, c = _with_mission()
        with a, b, c:
            out = resolve_clarification_option(self.user, {"resolver": "goals_gap"})
        self.assertIn("France 2027", out)
        self.assertNotIn("don't have enough active goal information", out.lower())

    def test_full_checkin_includes_strategic_not_gap(self):
        a, b, c = _with_mission()
        with a, b, c, \
                mock.patch("apps.core.cos_briefing.daily_agenda.build_daily_agenda",
                           return_value="Here's today's agenda."), \
                mock.patch("apps.ai.chatgpt_cos.lanes._health_overall_summary", return_value=""):
            out = resolve_clarification_option(self.user, {"resolver": "full_checkin"})
        self.assertIn("On your goals:", out)
        self.assertIn("France 2027", out)
        self.assertNotIn("don't have enough active goal information", out.lower())

    def test_resolvers_fall_to_gap_only_when_truly_empty(self):
        empty = (mock.patch(_INTERP, return_value=ExecutiveSignals()),
                 mock.patch(_GDS, return_value={"state": {"active_goal_count": 0}}),
                 mock.patch(_MISSION, return_value=None))
        with empty[0], empty[1], empty[2]:
            out = resolve_clarification_option(self.user, {"resolver": "goals_gap"})
        self.assertIn("don't have enough active goal information", out.lower())


class GoalsCheckinLaneTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="gcl@test.com", password="x")

    def test_lane_claims_direct_goal_questions_from_the_one_brain(self):
        for q in ("Give me a goals and commitments check-in.",
                  "How are my goals looking today?",
                  "What commitment matters most today?",
                  "What strategic goal should I move forward today?"):
            a, b, c = _with_mission()
            with a, b, c:
                out = _goals_checkin_lane(self.user, q)
            self.assertIsNotNone(out, q)
            self.assertEqual(out["lane"], "goals_checkin")
            self.assertIn("France 2027", out["answer"], q)

    def test_unrelated_message_not_claimed(self):
        self.assertIsNone(_goals_checkin_lane(self.user, "what's my glucose right now?"))
