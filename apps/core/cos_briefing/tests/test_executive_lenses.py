"""Executive lens differentiation (2026-06-19).

Each executive lens is a DISTINCT judgment, not a template around one selected
signal. Fixture: weight win + glucose improvement + sleep decline (leverage) +
faith consistency + relationship drift.
"""
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.core.cos_briefing.executive_state import ExecutiveStateSignal
from apps.core.cos_briefing import executive_state as es_state
from apps.core.cos_briefing.executive_summary import build_executive_lenses


def _sig(domain, lens, direction, conf="high", title=None, leverage=False):
    return ExecutiveStateSignal(
        domain=domain, lens=lens, direction=direction, magnitude=None,
        confidence=conf, title=title or f"{domain} {lens}",
        message=f"{domain} {lens} message", evidence=[], source=f"{domain}_state",
        leverage=leverage)


def _fixture():
    return [
        _sig("weight", "win", "improving", title="Weight down 14.1 lb"),
        _sig("glucose", "improvement", "improving", title="Glucose improving"),
        _sig("sleep", "decline", "declining", leverage=True,
             title="Sleep consistency slipping"),
        _sig("faith", "win", "improving", title="Bible reading streak: 15 days"),
        _sig("relationships", "decline", "declining",
             title="2 relationships drifting"),
    ]


class LensDifferentiation(SimpleTestCase):
    def setUp(self):
        self.L = build_executive_lenses(_fixture())

    def test_win_is_weight(self):
        self.assertEqual(self.L["biggest_win"]["domain"], "weight")

    def test_improvement_is_glucose(self):
        self.assertEqual(self.L["biggest_improvement"]["domain"], "glucose")

    def test_decline_is_sleep(self):
        self.assertEqual(self.L["biggest_decline"]["domain"], "sleep")

    def test_opportunity_is_sleep_with_leverage_framing(self):
        self.assertEqual(self.L["biggest_opportunity"]["domain"], "sleep")
        # Opportunity may share Decline's domain — distinct JUDGMENT, not collapse.
        self.assertEqual(self.L["biggest_decline"]["domain"], "sleep")

    def test_opportunity_string_is_strength_framed_distinct_from_risk(self):
        # A CoS opportunity builds on a proven strength applied to the gap — it
        # must NOT read like the risk ("sleep is the threat"). Leads with the win.
        opp = self.L["opportunity"]
        self.assertIn("leverage you've already built", opp)
        self.assertIn("weight", opp.lower())          # the proven strength (≠ sleep)
        self.assertNotEqual(opp, self.L["biggest_decline"]["message"])

    def test_trend_is_synthesis_not_equal_to_win(self):
        trend = self.L["most_important_trend"]
        self.assertIsInstance(trend, str)
        self.assertIn("gating constraint", trend.lower())
        self.assertNotEqual(trend, self.L["biggest_win"]["message"])
        self.assertNotEqual(trend, self.L["biggest_win"]["title"])
        # references BOTH a positive and the constraint (two-part).
        self.assertIn("weight", trend.lower())
        self.assertIn("sleep", trend.lower())

    def test_protect_is_value_times_vulnerability_includes_faith(self):
        protect = self.L["protect"].lower()
        self.assertIn("protect", protect)
        self.assertIn("faith", protect)          # a valuable standing asset
        self.assertIn("sleep", protect)          # the vulnerability/threat

    def test_story_spans_at_least_three_domains(self):
        story = self.L["story"].lower()
        domains_present = sum(any(k in story for k in keys) for keys in (
            ("weight",), ("glucose",), ("sleep",), ("bible", "faith", "reading"),
            ("relationship",)))
        self.assertGreaterEqual(domains_present, 3)
        self.assertIn("relationship", story)     # drift surfaces in the story

    def test_overall_is_not_win_led(self):
        overall = self.L["overall"]
        self.assertTrue(overall.startswith("Net"))
        self.assertNotEqual(overall, self.L["biggest_win"]["message"])

    def test_briefing_has_all_five_dimensions(self):
        b = self.L["chief_of_staff_briefing"]
        for dim in ("Win:", "Risk:", "Opportunity:", "Protect:", "Action:"):
            self.assertIn(dim, b, dim)

    def test_lenses_are_distinct_judgments(self):
        # Win, Trend, Protect, Overall, Briefing are NOT the same string.
        vals = [
            self.L["biggest_win"]["message"],
            self.L["most_important_trend"],
            self.L["protect"],
            self.L["overall"],
            self.L["chief_of_staff_briefing"],
        ]
        self.assertEqual(len(set(vals)), len(vals))  # all different


class ThinDataDegradesHonestly(SimpleTestCase):
    def test_single_signal_no_fabrication(self):
        L = build_executive_lenses([_sig("weight", "win", "improving",
                                         title="Weight down 14.1 lb")])
        self.assertEqual(L["biggest_win"]["domain"], "weight")
        self.assertIsNone(L["biggest_improvement"])
        self.assertIsNone(L["biggest_decline"])
        self.assertIsNone(L["biggest_opportunity"])
        # Trend still honest (positive-only), no invented constraint.
        self.assertNotIn("gating constraint", (L["most_important_trend"] or ""))
        # Briefing has no fabricated Risk/Opportunity it doesn't have.
        self.assertNotIn("Opportunity:", L["chief_of_staff_briefing"] or "")

    def test_no_signals_all_none(self):
        L = build_executive_lenses([])
        self.assertIsNone(L["biggest_win"])
        self.assertIsNone(L["most_important_trend"])
        self.assertIsNone(L["chief_of_staff_briefing"])

    def test_deterministic(self):
        a = build_executive_lenses(_fixture())
        b = build_executive_lenses(_fixture())
        self.assertEqual(a, b)


class RelationshipSignalGrounding(SimpleTestCase):
    def test_relationship_drift_appears_when_grounded(self):
        contract = {"_contract": {
            "summary": {"neglected_count": 2},
            "alerts": {"neglected": [{"name": "Heather"}, {"name": "Parker"}]}}}
        with patch.object(es_state, "_module", return_value=contract):
            out = es_state._relationship_signals(object())
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].domain, "relationships")
        self.assertEqual(out[0].direction, "declining")
        self.assertIn("Heather", out[0].message)

    def test_relationship_omitted_when_not_grounded(self):
        with patch.object(es_state, "_module",
                          return_value={"_contract": {"summary": {"neglected_count": 0}}}):
            self.assertEqual(es_state._relationship_signals(object()), [])
        with patch.object(es_state, "_module", return_value={}):
            self.assertEqual(es_state._relationship_signals(object()), [])


class BriefingRiskAltitude(SimpleTestCase):
    """Risk line operates at STRATEGIC altitude (2026-06-20 narrow fix)."""

    OP_RISK = {"title": "Wake up", "message": "overdue", "module": "routine_item"}

    def _risk_segment(self, briefing):
        # Extract the text of the Risk / Operational risk line.
        for marker in ("Risk: ", "Operational risk: "):
            if marker in briefing:
                return briefing.split(marker, 1)[1].split(" Opportunity:", 1)[0]
        return ""

    def test_risk_uses_relationship_drift_when_present_opportunity_stays_sleep(self):
        sigs = [
            _sig("weight", "win", "improving", title="Weight down 24 lb"),
            _sig("sleep", "decline", "declining", leverage=True,
                 title="Sleep consistency low"),
            _sig("relationships", "decline", "declining",
                 title="3 relationships drifting"),
        ]
        b = build_executive_lenses(sigs, biggest_risk=self.OP_RISK)[
            "chief_of_staff_briefing"]
        self.assertNotIn("overdue", b.lower())          # operational NOT used
        risk = self._risk_segment(b)
        self.assertIn("relationship", risk.lower())     # strategic risk surfaced
        self.assertNotIn("sleep", risk.lower())         # Risk != Opportunity
        # Opportunity is now STRENGTH-framed (leads with the proven win, applied
        # to the gap) — distinct from Risk, not a restatement of the constraint.
        self.assertIn("Opportunity:", b)
        self.assertIn("leverage you've already built", b)
        self.assertIn("weight", b.split("Opportunity:")[1].lower())  # the proven strength

    def test_risk_falls_back_to_sleep_when_only_strategic_risk(self):
        sigs = [
            _sig("weight", "win", "improving", title="Weight down 24 lb"),
            _sig("sleep", "decline", "declining", leverage=True,
                 title="Sleep consistency low"),
        ]
        b = build_executive_lenses(sigs, biggest_risk=self.OP_RISK)[
            "chief_of_staff_briefing"]
        self.assertNotIn("overdue", b.lower())
        self.assertIn("sleep", self._risk_segment(b).lower())  # sleep is the risk

    def test_operational_fallback_only_when_no_strategic_risk_and_labelled(self):
        sigs = [_sig("weight", "win", "improving", title="Weight down 24 lb"),
                _sig("faith", "win", "improving", title="Faith streak")]
        b = build_executive_lenses(sigs, biggest_risk=self.OP_RISK)[
            "chief_of_staff_briefing"]
        self.assertIn("Operational risk:", b)           # labelled operational
        self.assertIn("Wake up", b)
        self.assertNotIn("Risk: overdue", b)            # never a bare strategic risk
        self.assertNotIn("Risk: ", b)                   # no bare strategic Risk line

    def test_no_risk_line_when_no_strategic_and_no_operational(self):
        sigs = [_sig("weight", "win", "improving", title="Weight down 24 lb")]
        b = build_executive_lenses(sigs, biggest_risk=None)[
            "chief_of_staff_briefing"]
        self.assertNotIn("Risk", b)                     # honest omission

    def test_dashboard_biggest_risk_untouched(self):
        # The lens layer must not emit/alter a 'biggest_risk' key (the dashboard
        # sets that separately) and must not mutate the passed operational dict.
        op = dict(self.OP_RISK)
        L = build_executive_lenses(
            [_sig("sleep", "decline", "declining", leverage=True)], biggest_risk=op)
        self.assertNotIn("biggest_risk", L)             # decoupled from dashboard key
        self.assertEqual(op, self.OP_RISK)              # input not mutated


class BriefingThesisLayer(SimpleTestCase):
    """Briefing leads with a one-sentence thesis from existing overall/trend."""

    def test_briefing_leads_with_thesis_from_overall(self):
        sigs = [
            _sig("weight", "win", "improving", title="Weight down 24 lb"),
            _sig("sleep", "decline", "declining", leverage=True,
                 title="Sleep consistency low"),
            _sig("faith", "win", "improving", title="Bible reading streak"),
        ]
        L = build_executive_lenses(sigs, biggest_risk=None)
        b = L["chief_of_staff_briefing"]
        self.assertTrue(b.startswith("Bottom line:"), b)   # thesis leads
        # thesis is the already-computed overall, and the 5 lines still follow
        self.assertIn(L["overall"], b)
        self.assertIn("Win:", b)
        self.assertIn("Risk:", b)
        self.assertIn("Opportunity:", b)
        # thesis precedes Win
        self.assertLess(b.index("Bottom line:"), b.index("Win:"))

    def test_thesis_falls_back_to_trend_when_no_overall(self):
        from apps.core.cos_briefing.executive_summary import _synthesize_briefing
        win = _sig("weight", "win", "improving", title="Weight down 24 lb")
        b = _synthesize_briefing(win, None, None, None, None,
                                 state_signals=[], overall=None,
                                 trend="Weight improving but sleep is the constraint.")
        self.assertTrue(b.startswith("Bottom line: Weight improving but sleep"))

    def test_thesis_omitted_when_no_overall_and_no_trend(self):
        from apps.core.cos_briefing.executive_summary import _synthesize_briefing
        win = _sig("weight", "win", "improving", title="Weight down 24 lb")
        b = _synthesize_briefing(win, None, None, None, None,
                                 state_signals=[], overall=None, trend=None)
        self.assertNotIn("Bottom line:", b)               # honest omission
        self.assertTrue(b.startswith("Win:"))

    def test_thesis_does_not_replace_the_five_lines(self):
        sigs = [
            _sig("weight", "win", "improving", title="Weight down 24 lb"),
            _sig("sleep", "decline", "declining", leverage=True,
                 title="Sleep low"),
            _sig("relationships", "decline", "declining",
                 title="3 relationships drifting"),
        ]
        b = build_executive_lenses(sigs, biggest_risk=None)["chief_of_staff_briefing"]
        for marker in ("Bottom line:", "Win:", "Risk:", "Opportunity:",
                       "Protect:", "Action:"):
            self.assertIn(marker, b, marker)
