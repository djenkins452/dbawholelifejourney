"""Beth Trust Validation Suite (2026-06-22).

Guards the Chief-of-Staff trust contract: facts vs assessment, evidence shown,
confidence expressed, milestone (not ultimate) coaching, upstream-driver root
causes, and explicit uncertainty. Deterministic (no LLM).
"""
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai import deterministic_router as dr

User = get_user_model()


def _user(email):
    u = User.objects.create_user(email=email, password="x" * 20)
    from apps.users.models import TermsAcceptance
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u

_SLEEP = {"domain": "sleep", "title": "Sleep consistency slipping",
          "message": "Sleep is trending down.", "direction": "declining",
          "leverage": True, "confidence": "high", "category": "strategic_risk"}
_WIN = {"domain": "medication", "title": "Medication adherence strong",
        "message": "100%.", "direction": "improving", "leverage": False,
        "confidence": "high", "category": "major_win"}
_GP_MILESTONE = {"current": 286.4, "goal": 284.9, "remaining": 1.5,
                 "milestone": True, "target_date": "2026-06-30",
                 "current_pace_lb_wk": 0.9, "ultimate_goal": 240.0,
                 "strategic_objective": "France Ready"}


class FactVsAssessmentRouting(SimpleTestCase):
    def test_fact_question_does_not_hit_assessment(self):
        self.assertFalse(dr._match_weight_assessment_query("what is my weight"))
        self.assertFalse(dr._match_weight_assessment_query("current weight"))

    def test_trend_question_hits_assessment(self):
        for q in ("how is my weight doing", "how's my weight going",
                  "how is my weight trending", "assess my weight"):
            self.assertTrue(dr._match_weight_assessment_query(q), q)


class AnswerContract(TestCase):
    def setUp(self):
        self.user = _user("trust@test.com")

    def _render(self, R, W, gp):
        with patch.object(dr, "_life_state_signals", return_value=(R, [], W)), \
             patch("apps.ai.cos_intelligence.goal_pace", return_value=gp):
            return dr._render_structured_assessment(self.user, "weight")

    def test_trend_answer_has_all_five_sections(self):
        out = self._render([_SLEEP], [_WIN], _GP_MILESTONE)
        for section in ("Facts:", "Evidence:", "Assessment:", "Confidence:",
                        "Recommendation:"):
            self.assertIn(section, out, section)

    def test_facts_use_milestone_not_ultimate(self):
        out = self._render([_SLEEP], [_WIN], _GP_MILESTONE)
        self.assertIn("Next milestone: 284.9 lb", out)
        self.assertNotIn("240", out)            # ultimate never in the facts

    def test_evidence_is_cross_domain(self):
        out = self._render([_SLEEP], [_WIN], _GP_MILESTONE)
        self.assertIn("sleep:", out)
        self.assertIn("medication:", out)

    def test_assessment_names_upstream_driver_with_confidence(self):
        out = self._render([_SLEEP], [_WIN], _GP_MILESTONE)
        self.assertIn("upstream driver is", out.lower().replace("the likely ", ""))
        self.assertIn("Confidence:", out)

    def test_insufficient_evidence_admitted(self):
        # NO drivers at all (no negative AND no positive health signal) → must
        # admit uncertainty, not invent. (A positive driver yields a supportive
        # read instead — covered by test_assessment_positive_when_drivers_healthy.)
        out = self._render([], [], {"current": 286.4, "milestone": False,
                                    "goal": 240.0})
        self.assertIn("insufficient evidence", out.lower())
        self.assertIn("Confidence: Low", out)


class NoFalseRootCauses(SimpleTestCase):
    """A root cause must be an upstream driver — never timeline/goal/outcome."""

    def test_no_rule_or_fallback_names_a_non_cause(self):
        banned = ("timeline", "goal date", "target date", "the date")
        for domain, rules in dr._ROOT_CAUSE_RULES.items():
            for r in rules:
                self.assertFalse(any(b in r["cause"].lower() for b in banned),
                                 f"{domain}: {r['cause']}")
        for domain, fb in dr._ROOT_CAUSE_FALLBACK.items():
            if fb[0]:
                self.assertFalse(any(b in fb[0].lower() for b in banned),
                                 f"{domain} fallback: {fb[0]}")

    def test_weight_with_no_driver_is_insufficient_not_timeline(self):
        rc = dr._root_cause("weight", set(), 0)
        self.assertTrue(rc.get("insufficient"))
        self.assertIsNone(rc.get("cause"))

    def test_clause_admits_insufficiency(self):
        clause = dr._root_cause_clause("weight", [{"domain": "weight"}], 0)
        self.assertIn("insufficient evidence", clause.lower())


class LiveValidationRegressions(TestCase):
    """Regressions for the P0 defects found in live production validation."""

    def setUp(self):
        self.user = _user("liveval@test.com")

    # T5 / T6 — causal weight questions must REASON, not return the FACT route.
    def test_causal_weight_questions_route_to_assessment(self):
        for q in ("why has my weight loss slowed",
                  "what is the biggest thing holding back my weight loss",
                  "what's slowing my weight loss"):
            self.assertTrue(dr._match_weight_assessment_query(q), q)
            self.assertFalse(dr._match_weight_assessment_query("what is my weight"))

    # T2 — next milestone has a deterministic route + matcher.
    def test_next_milestone_matcher(self):
        self.assertTrue(dr._match_next_milestone_query("what is my next weight milestone"))
        self.assertTrue(dr._match_next_milestone_query("next milestone"))

    # T3 — evidence is physical-health only (no relationships/faith leakage).
    def test_assessment_evidence_is_health_only(self):
        R = [{"domain": "relationships", "title": "3 drifting", "direction": "declining"}]
        W = [{"domain": "sleep", "title": "Sleep improving", "direction": "improving"},
             {"domain": "faith", "title": "Bible streak 14d", "direction": "improving"}]
        with patch.object(dr, "_life_state_signals", return_value=(R, [], W)), \
             patch("apps.ai.cos_intelligence.goal_pace",
                   return_value={"current": 286.0, "current_pace_lb_wk": 1.0,
                                 "milestone": False, "goal": 240.0}):
            out = dr._render_structured_assessment(self.user, "weight")
        self.assertIn("sleep:", out)
        self.assertNotIn("relationships:", out)   # whole-life excluded
        self.assertNotIn("faith:", out)

    # T3/T4 — losing + healthy drivers ⇒ POSITIVE assessment, not "insufficient".
    def test_assessment_positive_when_drivers_healthy(self):
        W = [{"domain": "sleep", "title": "Sleep improving", "direction": "improving"},
             {"domain": "glucose", "title": "Glucose improving", "direction": "improving"}]
        with patch.object(dr, "_life_state_signals", return_value=([], [], W)), \
             patch("apps.ai.cos_intelligence.goal_pace",
                   return_value={"current": 286.0, "current_pace_lb_wk": 1.0,
                                 "milestone": False, "goal": 240.0}):
            out = dr._render_structured_assessment(self.user, "weight").lower()
        self.assertNotIn("insufficient evidence", out)
        self.assertIn("working", out)            # supportive read (not insufficient)
        self.assertNotIn("confidence: low", out)

    # T7 — health-scoped concern must NOT let a relationship signal lead.
    def test_health_scoped_concern_excludes_relationships(self):
        R = [{"domain": "relationships", "title": "3 drifting", "message": "drift.",
              "direction": "risk", "leverage": False, "confidence": "medium"},
             {"domain": "sleep", "title": "Sleep slipping", "message": "sleep down.",
              "direction": "declining", "leverage": True, "confidence": "high"}]
        with patch.object(dr, "_life_state_signals", return_value=(R, [], [])):
            out = dr._render_cos_mode(self.user, "risk",
                                      "what concerns you most about my health right now")
        self.assertIn("sleep", out.lower())
        self.assertNotIn("relationship", out.lower())   # whole-life can't lead health


class HotfixRegressionV2(TestCase):
    """Reproduces the exact post-hotfix live failures (Q1/Q2/Q3/Q6)."""

    def setUp(self):
        self.user = _user("hotfix2@test.com")

    def test_q1_bare_weight_is_fact_only(self):
        from apps.health.models import WeightEntry
        from django.utils import timezone
        WeightEntry.objects.create(user=self.user, value=286.6, unit="lb",
                                   recorded_at=timezone.now())
        self.assertTrue(dr._match_weight_fact_query("what is my current weight"))
        out = dr._handle_weight_fact_query(self.user, "what is my current weight")
        self.assertEqual(out, "Your current weight is 286.6 lbs.")
        self.assertNotIn("trending", out)
        self.assertNotIn("?", out)

    def test_q2_milestone_from_canonical_mission_goal(self):
        from decimal import Decimal
        from datetime import date
        from django.utils import timezone
        from apps.purpose.models import LifeGoal, GoalMilestone
        from apps.health.models import WeightEntry
        from apps.ai import cos_intelligence as ci
        g = LifeGoal.objects.create(user=self.user, title="France 2027")
        GoalMilestone.objects.create(
            goal=g, title="Goal Weight of 289.9", objective_metric="weight_lb",
            objective_target_value=Decimal("289.9"), objective_operator="lte",
            target_date=date(2026, 5, 1), completed=False)
        GoalMilestone.objects.create(
            goal=g, title="Goal Weight of 284.9", objective_metric="weight_lb",
            objective_target_value=Decimal("284.9"), objective_operator="lte",
            target_date=date(2026, 6, 30), completed=False)
        WeightEntry.objects.create(user=self.user, value=286.6, unit="lb",
                                   recorded_at=timezone.now())
        with patch("apps.purpose.mission_selection.select_active_mission_goal",
                   return_value=g):
            m = ci._nearest_weight_milestone(self.user, current_weight=286.6)
        # 289.9 auto-completes (286.6 <= 289.9); next incomplete = 284.9.
        self.assertEqual(m["target_value"], 284.9)
        self.assertEqual(str(m["target_date"]), "2026-06-30")
        self.assertEqual(m["strategic_objective"], "France 2027")

    def test_q3_evidence_deduped(self):
        # A signal in BOTH W and O must appear ONCE (the live duplicate bug).
        g = {"domain": "glucose", "title": "Glucose improving", "direction": "improving"}
        s = {"domain": "sleep", "title": "Sleep improving", "direction": "improving"}
        with patch.object(dr, "_life_state_signals", return_value=([], [g, s], [g, s])), \
             patch("apps.ai.cos_intelligence.goal_pace",
                   return_value={"current": 286.6, "current_pace_lb_wk": 1.0,
                                 "milestone": False, "goal": 240.0}):
            out = dr._render_structured_assessment(self.user, "weight")
        self.assertEqual(out.lower().count("glucose:"), 1)
        self.assertEqual(out.lower().count("sleep:"), 1)

    def test_q3_positive_when_drivers_improving_even_without_pace(self):
        s = {"domain": "sleep", "title": "Sleep improving", "direction": "improving"}
        g = {"domain": "glucose", "title": "Glucose improving", "direction": "improving"}
        with patch.object(dr, "_life_state_signals", return_value=([], [], [s, g])), \
             patch("apps.ai.cos_intelligence.goal_pace",
                   return_value={"current": 286.6, "milestone": False, "goal": 240.0}):
            out = dr._render_structured_assessment(self.user, "weight").lower()
        self.assertNotIn("insufficient evidence", out)
        self.assertIn("working", out)

    def test_q6_health_scope_gives_physical_read_not_relationships(self):
        R = [{"domain": "relationships", "title": "3 drifting", "message": "drift.",
              "direction": "risk", "leverage": False, "confidence": "medium"}]
        W = [{"domain": "weight", "title": "Weight down", "direction": "improving"},
             {"domain": "glucose", "title": "Glucose improving", "direction": "improving"}]
        with patch.object(dr, "_life_state_signals", return_value=(R, [], W)):
            out = dr._render_cos_mode(self.user, "risk",
                                      "what concerns you most about my health right now")
        self.assertIn("physical-health", out.lower())
        self.assertNotIn("relationship", out.lower())
