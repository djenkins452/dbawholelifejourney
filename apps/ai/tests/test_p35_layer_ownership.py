# ==============================================================================
# File: apps/ai/tests/test_p35_layer_ownership.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P35 Layer Ownership — every executive OPINION (priorities, leverage,
#   recommendations, the "real challenge", the backlog disposition) is owned by the
#   Executive Interpretation Engine. The Composer is a SPEECHWRITER: it narrates
#   signals and invents nothing. Proven dynamically — change a signal and the brief
#   changes; give empty conclusions and the composer adds no judgment of its own.
# ==============================================================================
from unittest import mock

from django.test import SimpleTestCase

from apps.ai.chatgpt_cos import executive_brief as eb
from apps.ai.chatgpt_cos.executive_interpretation import ExecutiveSignals, interpret

_INTERPRET = "apps.ai.chatgpt_cos.executive_interpretation.interpret"
_AGENDA = "apps.ai.chatgpt_cos.executive_brief._agenda_narrative"


def _brief(sig, **kw):
    with mock.patch(_INTERPRET, return_value=sig), mock.patch(_AGENDA, return_value=""):
        return eb.compose_executive_brief(mock.Mock(), **kw).lower()


class ComposerInventsNothingTests(SimpleTestCase):
    def test_empty_conclusions_yield_no_invented_judgment(self):
        # interpretation concluded nothing beyond a workload band -> the composer must
        # add NO executive opinion of its own.
        sig = ExecutiveSignals(workload="manageable", today_count=0)
        brief = _brief(sig)
        for invented in ("the bigger challenge", "because of that", "the real leverage",
                         "backlog can wait", "keep an eye on", "it's your energy"):
            self.assertNotIn(invented, brief, f"composer invented: {invented!r}")

    def test_no_risk_no_risk_sentence(self):
        sig = ExecutiveSignals(workload="manageable", today_count=1, biggest_risk="")
        self.assertNotIn("keep an eye on", _brief(sig))

    def test_no_backlog_signal_no_backlog_sentence(self):
        sig = ExecutiveSignals(workload="manageable", today_count=1, backlog_can_wait=False)
        self.assertNotIn("backlog can wait", _brief(sig))


class ComposerNarratesTheSignalTests(SimpleTestCase):
    """The conclusion lives in the signal — proven by changing it and watching the
    brief follow."""
    def test_primary_challenge_drives_the_energy_conclusion(self):
        energy = ExecutiveSignals(workload="manageable", primary_challenge="energy",
                                  challenge_reason="more than the open work",
                                  disposition="I'd ease into it", sleep_hours=5,
                                  recommendation_levers=["rest up"])
        none = ExecutiveSignals(workload="manageable", primary_challenge="none",
                                today_count=1)
        self.assertIn("it's your energy", _brief(energy))
        self.assertNotIn("it's your energy", _brief(none))   # composer didn't hardcode it

    def test_challenge_reason_is_narrated_verbatim(self):
        sig = ExecutiveSignals(primary_challenge="energy",
                               challenge_reason="more than any to-do list could")
        self.assertIn("more than any to-do list could", _brief(sig))

    def test_disposition_and_levers_come_from_the_signal(self):
        sig = ExecutiveSignals(primary_challenge="energy",
                               disposition="I'd protect the morning",
                               recommendation_levers=["sleep", "hydrate", "one deep-work block"])
        b = _brief(sig)
        self.assertIn("because of that, i'd protect the morning", b)
        self.assertIn("sleep, hydrate, and one deep-work block", b)

    def test_leverage_comes_from_the_signal_not_the_composer(self):
        a = ExecutiveSignals(workload="manageable", today_count=1,
                             highest_leverage="shipping the investor deck")
        b = ExecutiveSignals(workload="manageable", today_count=1,
                             highest_leverage="closing the hiring loop")
        self.assertIn("shipping the investor deck", _brief(a))
        self.assertIn("closing the hiring loop", _brief(b))
        self.assertNotIn("shipping the investor deck", _brief(b))

    def test_backlog_disposition_comes_from_the_signal(self):
        self.assertIn("backlog can wait",
                      _brief(ExecutiveSignals(workload="manageable", backlog_can_wait=True)))


class JudgmentLivesInInterpretationTests(SimpleTestCase):
    """The interpretation engine OWNS the conclusions — verified directly on the
    signals it produces (no composer involved)."""
    def _interpret(self, low_energy=False, **horizons):
        hz = {"today": 1, "overdue": 0, "soon": 3, "backlog": 18, "total": 22}
        hz.update(horizons)
        with mock.patch("apps.ai.chatgpt_cos.executive_interpretation._task_horizons",
                        return_value=hz), \
             mock.patch("apps.ai.chatgpt_cos.executive_interpretation._exec_summary",
                        return_value={}), \
             mock.patch("apps.ai.chatgpt_cos.executive_interpretation._health_read",
                        return_value={"recovery_needed": False, "read": "stable",
                                      "note": "", "sleep_hours": None}):
            return interpret(mock.Mock(), low_energy=low_energy)

    def test_energy_challenge_is_decided_by_interpretation(self):
        sig = self._interpret(low_energy=True)     # the conversation said "tired"
        self.assertEqual(sig.primary_challenge, "energy")
        self.assertTrue(sig.recommendation_levers)
        self.assertTrue(sig.ease_load)

    def test_no_recovery_means_no_energy_challenge(self):
        sig = self._interpret(low_energy=False)
        self.assertEqual(sig.primary_challenge, "none")
        self.assertFalse(sig.ease_load)

    def test_backlog_disposition_is_decided_by_interpretation(self):
        self.assertTrue(self._interpret(total=22).backlog_can_wait)
        self.assertFalse(self._interpret(total=1, backlog=0, today=1).backlog_can_wait)
