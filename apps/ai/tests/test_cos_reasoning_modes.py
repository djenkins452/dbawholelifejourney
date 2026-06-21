"""CoS reasoning modes — one brain, distinct projections (2026-06-21).

status / trajectory / direction / prioritization / risk / opportunity / decision /
pattern / blind-spot / constraint / progress must each answer a DIFFERENT question
from the SAME unified state — never collapse to one string, and "what to fix"
modes must target the constraint (risk), not a positive trend.
"""
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai import deterministic_router as dr
from apps.ai import cos_event_engine as eng

User = get_user_model()


class ModeClassifier(SimpleTestCase):
    def test_phrase_to_mode(self):
        cases = {
            "what is my trajectory": "trajectory",
            "am i moving in the right direction": "direction",
            "what should i focus on this week": "prioritization",
            "what should i focus on today": "prioritization_today",
            "what concerns you most about me": "risk",
            "what gives you confidence about me": "opportunity_soft",
            "what would you do if you were me": "decision",
            "what patterns do you see": "pattern",
            "what am i ignoring": "blindspot",
            "what is holding me back": "constraint",
            "what is the next bottleneck in my life": "bottleneck",
            "where am i making progress": "progress",
            "what should i stop doing": "stop",
            "give me your honest assessment": "honest",
        }
        for phrase, mode in cases.items():
            self.assertEqual(dr._cos_mode_for(phrase), mode, phrase)

    def test_bare_focus_routes_to_prioritization_not_execution(self):
        # Bug: bare "what should I focus on?" fell to the execution reminder.
        self.assertEqual(dr._cos_mode_for("what should i focus on"), "prioritization")

    def test_doing_well_routes_to_progress(self):
        # Bug: "what am I doing well?" fell to the LLM.
        self.assertEqual(dr._cos_mode_for("what am i doing well"), "progress")

    def test_focus_to_keep_losing_stays_coaching_not_prioritization(self):
        # The broad focus phrase must not steal cross-domain coaching.
        self.assertIsNone(dr._cos_mode_for("what should i focus on to keep losing weight"))

    def test_executive_matcher_accepts_modes(self):
        for phrase in ("what is my trajectory", "what concerns you most",
                       "what would you do if you were me", "what am i ignoring"):
            self.assertTrue(dr._match_executive_query(phrase), phrase)


def _user(email):
    u = User.objects.create_user(email=email, password="x" * 20)
    from apps.users.models import TermsAcceptance
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


_INTEL = {
    "overall": "Net: mostly positive but with real pressure.",
    "goal_pace": {"current_pace_lb_wk": 0.88, "target_passed": True,
                  "remaining": 58.3, "target_date": "2026-06-13"},
    "goal_pace_narrative": "Weight 298 → goal 240 (58 to go) at ~0.88 lb/week; "
                           "target date has passed.",
    "recommendation_effectiveness": "I flagged sleep 3 weeks ago.",
}


class ModeRendering(TestCase):
    def setUp(self):
        self.user = _user("modes@test.com")
        eng.persist_event(self.user, eng.CoSEvent(
            eng.STRATEGIC_RISK, "sleep", "Sleep is trending down",
            "Sleep is trending down (6.7h).", "It constrains weight loss.",
            "Protect tonight's sleep."))
        eng.persist_event(self.user, eng.CoSEvent(
            eng.STRATEGIC_OPPORTUNITY, "medication", "Medication is improving",
            "100% adherence this week.", "Momentum.", "Keep it up."))
        eng.persist_event(self.user, eng.CoSEvent(
            eng.MAJOR_WIN, "weight", "Weight down 12.7 lb",
            "Down 12.7 lb.", "The goal.", "Bank it."))
        eng.persist_event(self.user, eng.CoSEvent(
            eng.PAST_DUE, "health", "Prayer Time",
            "Prayer Time is overdue.", "Recover.", "Do it now.",
            key="op:health:prayer-time"))

    def _render(self, mode):
        with patch("apps.ai.cos_intelligence.build_cos_intelligence",
                   return_value={**_INTEL, "events": eng.recent_cos_events(self.user)}):
            return dr._render_cos_mode(self.user, mode)

    def test_fix_modes_target_constraint_not_positive_trend(self):
        # The bug: "what holds me back / what would you do / start / focus" used
        # the OPPORTUNITY (medication, a positive) as the leverage target.
        for mode in ("constraint", "decision", "start", "prioritization"):
            out = self._render(mode).lower()
            self.assertIn("sleep", out, mode)
            self.assertNotIn("medication", out, f"{mode} wrongly led with medication")

    def test_modes_are_materially_different(self):
        modes = ["trajectory", "direction", "prioritization", "risk",
                 "opportunity_soft", "decision", "pattern", "blindspot",
                 "constraint", "progress", "stop", "start", "honest"]
        outs = [self._render(m) for m in modes]
        # No two modes produce the same string.
        self.assertEqual(len(set(outs)), len(outs))

    def test_trajectory_uses_pace(self):
        self.assertIn("0.88 lb/week", self._render("trajectory"))

    def test_direction_is_a_verdict_with_judgment(self):
        out = self._render("direction").lower()
        self.assertTrue(out.startswith(("overall", "yes", "honestly")))  # verdict
        self.assertIn("proving you can", out)        # capability framing
        self.assertIn("sleep", out)                  # cross-domain concern
        self.assertIn("if i were prioritising", out)  # recommendation/tradeoff

    def test_risk_is_strategic_not_operational(self):
        self.assertIn("concerns me most", self._render("risk").lower())
        self.assertIn("sleep", self._render("risk").lower())

    def test_opportunity_soft_uses_positive(self):
        out = self._render("opportunity_soft").lower()
        self.assertIn("adherence", out)        # the positive trend (medication)
        self.assertIn("confidence", out)       # names what's going well

    def test_progress_lists_wins(self):
        out = self._render("progress").lower()
        self.assertIn("weight down", out)

    def test_decision_is_cross_domain(self):
        out = self._render("decision").lower()
        self.assertIn("sleep", out)          # constraint
        self.assertIn("weight", out)         # + reset the plan (2nd domain)

    def test_blindspot_names_unaddressed_risk(self):
        self.assertIn("sleep", self._render("blindspot").lower())

    def test_modes_carry_judgment_not_just_facts(self):
        # CoS bar: trajectory + progress must add an implication/recommendation,
        # not just report the metric.
        traj = self._render("trajectory").lower()
        self.assertIn("lever is the date", traj)     # judgment, not just the number
        prog = self._render("progress").lower()
        self.assertIn("proves you can", prog)        # what the win means
        self.assertIn("don't let it mask", prog)     # the caveat

    def test_decision_uses_full_reasoning_chain(self):
        # Decision must carry the constraint's WHY (from the event message),
        # not just its title.
        out = self._render("decision").lower()
        self.assertIn("constrains weight loss", out)  # why_it_matters from message

    def test_bottleneck_is_forward_looking_and_distinct(self):
        constraint = self._render("constraint")
        bottleneck = self._render("bottleneck")
        self.assertNotEqual(constraint, bottleneck)
        self.assertIn("right now the bottleneck", bottleneck.lower())

    def test_today_vs_week_are_distinct(self):
        week = self._render("prioritization")
        today = self._render("prioritization_today")
        self.assertNotEqual(week, today)
        self.assertTrue(week.lower().startswith("this week"))
        self.assertTrue(today.lower().startswith("today"))


class RouteIntegration(TestCase):
    def setUp(self):
        self.user = _user("moderoute@test.com")
        eng.persist_event(self.user, eng.CoSEvent(
            eng.STRATEGIC_RISK, "sleep", "Sleep is trending down",
            "Sleep down.", "Constraint.", "Protect it."))

    def test_holding_me_back_routes_to_executive_with_sleep(self):
        res = dr.classify_and_route("what is holding me back", self.user)
        self.assertEqual(res.route_name, "executive_summary_query")
        self.assertIn("sleep", res.response.lower())

    def test_what_would_you_do_not_hijacked_by_execution(self):
        res = dr.classify_and_route("what would you do if you were me", self.user)
        self.assertEqual(res.route_name, "executive_summary_query")
