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


class SignalScoring(SimpleTestCase):
    """Concern (severity) and focus (leverage) select DIFFERENT signals when the
    board has a high-severity/low-leverage threat AND a high-leverage one."""

    def _sig(self, domain, direction, leverage, conf="high"):
        return {"domain": domain, "direction": direction, "leverage": leverage,
                "confidence": conf, "category": "strategic_risk",
                "title": domain, "message": domain}

    def test_concern_and_focus_can_diverge(self):
        sigs = [self._sig("relationships", "risk", False),   # severe, low leverage
                self._sig("sleep", "declining", True)]       # high leverage
        concern = dr._signal_scores(sigs, "concern")
        focus = dr._signal_scores(sigs, "focus")
        self.assertEqual(concern[0][0]["domain"], "relationships")  # severity wins
        self.assertEqual(focus[0][0]["domain"], "sleep")           # leverage wins

    def test_only_threats_are_scored(self):
        wins = [self._sig("weight", "improving", False)]
        self.assertEqual(dr._signal_scores(wins, "concern"), [])


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

    # Strategic R/O/W now come from the LIVE state (not events) — inject them
    # directly, mirroring the seeded events. OD/REC still read the event stream.
    _STATE = (
        [{"domain": "sleep", "title": "Sleep is trending down",
          "message": "Sleep is trending down (6.7h). It constrains weight loss. "
                     "Protect tonight's sleep.", "category": "strategic_risk",
          "occurrence_count": 1, "direction": "declining", "lens": "decline",
          "leverage": True, "magnitude": None, "confidence": "high"}],
        [{"domain": "medication", "title": "Medication is improving",
          "message": "100% adherence this week.",
          "category": "strategic_opportunity", "occurrence_count": 1,
          "direction": "improving", "lens": "improvement", "leverage": False,
          "magnitude": 1.0, "confidence": "high"}],
        [{"domain": "weight", "title": "Weight down 12.7 lb",
          "message": "Down 12.7 lb.", "category": "major_win",
          "occurrence_count": 1, "direction": "improving", "lens": "win",
          "leverage": False, "magnitude": 12.7, "confidence": "high"}],
    )

    def _render(self, mode):
        with patch("apps.ai.cos_intelligence.build_cos_intelligence",
                   return_value={**_INTEL, "events": eng.recent_cos_events(self.user)}), \
             patch.object(dr, "_life_state_signals", return_value=self._STATE):
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

    def test_decision_is_effort_sequenced_not_constraint_first(self):
        # Decision weighs effort: leads with the cheap high-value move (reset the
        # passed goal date), THEN the hard lever — a DIFFERENT lead than risk.
        out = self._render("decision").lower()
        self.assertIn("sequence", out)
        self.assertTrue(out.index("reset your weight target") < out.index("sleep"),
                        "quick win should be sequenced before the hard lever")

    def test_concerns_reasons_across_multiple_signals(self):
        # Concerns enumerates the concern SET (risk + recurring pattern), not just
        # the top risk. Seed a recurring pattern so there's a 2nd signal.
        item, _ = eng.persist_event(self.user, eng.CoSEvent(
            eng.PAST_DUE, "faith", "Prayer Time", "overdue.", "recover.", "do it.",
            key="op:faith:prayer-recur"))
        meta = item.metadata
        meta["occurrence_count"] = 4
        item.metadata = meta
        item.save(update_fields=["metadata"])
        out = self._render("risk").lower()
        self.assertIn("below that", out)     # surfaces beyond the #1 risk
        self.assertIn("pattern of", out)     # the recurring signal

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


class RootCauseAnalysis(SimpleTestCase):
    """Executive judgment: infer the likely CAUSE of a constraint from other
    negative domains on the board — evidence-based, confidence-rated, graceful."""

    def test_corroborated_cause_is_high_confidence_with_evidence(self):
        rc = dr._root_cause("sleep", {"workouts"}, overdue=3)  # 2 factors
        self.assertEqual(rc["confidence"], "high")
        self.assertIn("competing priorities", rc["cause"])
        self.assertIn("workouts is also down", rc["evidence"])
        self.assertTrue(rc["rec"])

    def test_cross_domain_cause_workouts_from_sleep(self):
        rc = dr._root_cause("workouts", {"sleep"}, overdue=0)
        self.assertEqual(rc["confidence"], "medium")
        self.assertIn("recovery", rc["cause"])
        self.assertIn("sleep is also down", rc["evidence"])

    def test_no_hallucination_rule_needs_real_evidence(self):
        # With NO corroborating negative domains, the specific rule must NOT fire;
        # it degrades to the honest low-confidence fallback, not an invented cause.
        rc = dr._root_cause("sleep", set(), overdue=0)
        self.assertEqual(rc["confidence"], "low")
        self.assertIsNone(rc["evidence"])
        self.assertIn("consistency", rc["cause"])

    def test_degrades_to_insufficient_without_rule_or_fallback(self):
        # P0-4: no rule/driver → explicit insufficiency, NEVER a fabricated cause.
        rc = dr._root_cause("relationships", set(), overdue=0)
        self.assertTrue(rc.get("insufficient"))
        self.assertIsNone(rc.get("cause"))

    def test_clause_admits_insufficiency_when_no_judgment(self):
        clause = dr._root_cause_clause("relationships", [{"domain": "relationships"}], 0)
        self.assertIn("insufficient evidence", clause.lower())

    def test_clause_names_cause_and_confidence(self):
        R = [{"domain": "workouts"}]
        clause = dr._root_cause_clause("sleep", R, overdue=3)
        self.assertIn("likely root cause", clause)
        self.assertIn("confidence", clause)
        self.assertIn("aimed at the cause", clause)


class FullBoardConsumption(TestCase):
    """Reasoning must pool the FULL board (by consider_for/polarity), so a
    neglected/declining steady-state domain — not just notable signals — can
    enter the risk pool and influence answers."""

    def setUp(self):
        self.user = _user("fullboardconsume@test.com")

    def test_neglected_domain_enters_risk_pool(self):
        # A glucose domain with stale history reports 'neglected' (consider_for
        # 'risk'); it must appear in R even though it's not a notable decline.
        from apps.health.models import GlucoseEntry
        from datetime import timedelta
        from django.utils import timezone
        GlucoseEntry.objects.create(
            user=self.user, value=120,
            recorded_at=timezone.now() - timedelta(days=60))
        R, O, W = dr._life_state_signals(self.user)
        self.assertIn("glucose", {s["domain"] for s in R})
        # And it is scoreable as a concern (severity-ranked).
        ranked = {s["domain"] for s, _, _ in dr._signal_scores(R + O + W, "concern")}
        self.assertIn("glucose", ranked)

    def test_strong_domain_enters_positive_pool(self):
        # A healthy/strong domain enters W via polarity, not only 'win' lens.
        from unittest.mock import patch
        from apps.core.cos_briefing.executive_state import ExecutiveStateSignal
        sig = ExecutiveStateSignal(
            domain="glucose", lens="context", direction="steady", magnitude=None,
            confidence="medium", title="Glucose in range", message="healthy",
            evidence=[], source="x", status="strong", polarity="positive",
            consider_for="progress")
        with patch("apps.core.cos_briefing.executive_state."
                   "build_executive_state_signals", return_value=[sig]):
            R, O, W = dr._life_state_signals(self.user)
        self.assertIn("glucose", {s["domain"] for s in W})


class LifeModelNuclearTest(TestCase):
    """Beth must reason from the LIVE STATE even with ZERO events (no alerts):
    if every GuidanceItem disappeared, she still knows the constraint."""

    def setUp(self):
        self.user = _user("nuclear@test.com")  # deliberately NO events persisted

    def _render_no_events(self, mode, state):
        from apps.core.ai_guidance.models import GuidanceItem
        self.assertEqual(GuidanceItem.objects.filter(
            user=self.user, dedupe_key__startswith="cos_event:").count(), 0)
        with patch("apps.ai.cos_intelligence.build_cos_intelligence",
                   return_value={"overall": "net read"}), \
             patch.object(dr, "_life_state_signals", return_value=state):
            return dr._render_cos_mode(self.user, mode)

    def test_concerns_surfaces_constraint_from_state_not_events(self):
        state = ([{"domain": "sleep", "title": "Sleep trending down",
                   "message": "Sleep is your constraint.",
                   "category": "strategic_risk", "occurrence_count": 1,
                   "direction": "declining", "lens": "decline", "leverage": True,
                   "magnitude": None, "confidence": "high"}], [], [])
        out = self._render_no_events("risk", state)
        self.assertIn("sleep", out.lower())          # from STATE, with no events

    def test_doing_well_surfaces_win_from_state_not_events(self):
        state = ([], [], [{"domain": "weight", "title": "Weight down 12 lb",
                           "message": "Down 12 lb.", "category": "major_win",
                           "occurrence_count": 1}])
        out = self._render_no_events("progress", state)
        self.assertIn("weight", out.lower())


class RouteIntegration(TestCase):
    def setUp(self):
        self.user = _user("moderoute@test.com")
        # Strategic reasoning reads the LIVE state — inject a sleep risk signal.
        self._patch = patch.object(dr, "_life_state_signals", return_value=(
            [{"domain": "sleep", "title": "Sleep is trending down",
              "message": "Sleep down. Constraint. Protect it.",
              "category": "strategic_risk", "occurrence_count": 1}], [], []))
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_holding_me_back_routes_to_executive_with_sleep(self):
        res = dr.classify_and_route("what is holding me back", self.user)
        self.assertEqual(res.route_name, "executive_summary_query")
        self.assertIn("sleep", res.response.lower())

    def test_what_would_you_do_not_hijacked_by_execution(self):
        res = dr.classify_and_route("what would you do if you were me", self.user)
        self.assertEqual(res.route_name, "executive_summary_query")
