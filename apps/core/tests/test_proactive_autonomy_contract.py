# ==============================================================================
# File: apps/core/tests/test_proactive_autonomy_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Unattended provider calls are gated; detection is not interruption
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-04
# ==============================================================================
"""Two gaps left open after the check-in incident, closed together.

**Attribution.** The gate that stops unattended spend asked "is this marked proactive?"
So a path that simply never classified itself came back "not autonomous" and, in
production, was admitted unconditionally. Check-in authoring was exactly that: real
provider calls, `unattributed`, invisible to the gate. The question is now the other way
round — did anything positively assert a human? — so a future autonomous path that forgets
to classify itself is refused rather than silently spending.

**Detection is not interruption.** WLJ used to rank the signals and write the sentence:
an if-ladder that turned one goal-pace calculation crossing one line into a notification.
WLJ now throttles, detects, and hands over facts. The model weighs them and may decline —
and declining produces no message.

No provider is called anywhere in this file; every model call is mocked.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai import llm_admission as adm
from apps.ai.llm_accounting import (TRAFFIC_BACKGROUND, TRAFFIC_CERTIFICATION,
                                    TRAFFIC_PRODUCTION, TRAFFIC_PROACTIVE,
                                    llm_traffic_context)

User = get_user_model()


class AutonomyDefaultTests(SimpleTestCase):
    """Absence of proof that a human asked is not proof that one did."""

    def test_an_unclassified_call_is_autonomous_in_production(self):
        """Production is where the hole was: the allow there is unconditional, so an
        unattributed call rode straight past the gate."""
        self.assertTrue(adm.current_workload_is_autonomous(adm.ENV_PRODUCTION),
                        "an unattributed provider call is still treated as human")

    def test_unclassified_is_left_alone_outside_production(self):
        """Everywhere else deny-by-default already governs every call. Treating
        unattributed as autonomous there would refuse authorized development and operator
        work BEFORE it reached the gate that authorizes it."""
        self.assertFalse(adm.current_workload_is_autonomous("development"))

    def test_an_asserted_human_turn_is_not_autonomous(self):
        with llm_traffic_context(traffic_class=TRAFFIC_PRODUCTION):
            self.assertFalse(adm.current_workload_is_autonomous(adm.ENV_PRODUCTION))

    def test_proactive_and_background_remain_autonomous_everywhere(self):
        for env in (adm.ENV_PRODUCTION, "development"):
            for traffic in (TRAFFIC_PROACTIVE, TRAFFIC_BACKGROUND):
                with llm_traffic_context(traffic_class=traffic):
                    self.assertTrue(adm.current_workload_is_autonomous(env))

    def test_certification_is_left_for_the_diagnostic_gate(self):
        """It must not be refused here, or the authorized operator path would never
        reach the budget that authorizes it."""
        with llm_traffic_context(traffic_class=TRAFFIC_CERTIFICATION):
            self.assertFalse(adm.current_workload_is_autonomous(adm.ENV_PRODUCTION))

    def test_the_explicit_marker_still_wins_over_any_attribution(self):
        with llm_traffic_context(traffic_class=TRAFFIC_PRODUCTION):
            with adm.autonomous_workload("scheduled"):
                self.assertTrue(adm.current_workload_is_autonomous(adm.ENV_PRODUCTION))


class CostGateTests(SimpleTestCase):
    """A preference may request proactive help. It may never authorize the spend."""

    def _decide(self, **kw):
        return adm.may_real_llm_call(environment=adm.ENV_PRODUCTION, **kw)

    def test_autonomous_work_is_refused_in_production_when_the_gate_is_off(self):
        with mock.patch.object(adm, "proactive_ai_enabled", return_value=False):
            with adm.autonomous_workload("proactive_checkin"):
                decision = self._decide()
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "proactive_ai_disabled")

    def test_the_user_preference_cannot_open_the_gate(self):
        """The preference lives on the user; the authorization lives in the environment.
        Nothing about a preference is consulted here, and that is the point."""
        user = mock.Mock(preferences=mock.Mock(proactive_assistance_enabled=True,
                                               assistant_proactive_checkins=True))
        with mock.patch.object(adm, "proactive_ai_enabled", return_value=False):
            with adm.autonomous_workload("proactive_checkin"):
                decision = self._decide()
        self.assertFalse(decision.allowed)
        self.assertTrue(user.preferences.proactive_assistance_enabled)

    def test_autonomous_work_is_admitted_when_the_gate_is_on(self):
        with mock.patch.object(adm, "proactive_ai_enabled", return_value=True):
            with adm.autonomous_workload("proactive_checkin"):
                decision = self._decide()
        self.assertTrue(decision.allowed)

    def test_a_real_user_turn_is_never_refused_by_the_proactive_gate(self):
        with mock.patch.object(adm, "proactive_ai_enabled", return_value=False):
            with llm_traffic_context(traffic_class=TRAFFIC_PRODUCTION):
                decision = self._decide()
        self.assertTrue(decision.allowed, "a customer's own turn was refused")
        self.assertEqual(decision.reason, "production_runtime")


class InteractivePathsAssertThemselvesTests(SimpleTestCase):
    """Every human-initiated provider seam declares the human — or the new default
    would refuse a real customer."""

    def test_the_certified_runtime_asserts_production(self):
        import inspect

        from apps.ai.model_interface.service import ModelInterfaceService
        src = inspect.getsource(ModelInterfaceService.generate)
        self.assertIn("TRAFFIC_PRODUCTION", src)

    def test_the_legacy_chat_entry_point_asserts_production(self):
        import inspect

        from apps.ai.personal_assistant import PersonalAssistant
        src = inspect.getsource(PersonalAssistant.send_message)
        self.assertIn("TRAFFIC_PRODUCTION", src)
        self.assertIn("llm_traffic_context", src)

    def test_the_legacy_streaming_task_asserts_production(self):
        import pathlib
        src = pathlib.Path("apps/ai/tasks.py").read_text(encoding="utf-8")
        loop = src[src.index("send_message_stream(") - 800:]
        self.assertIn("TRAFFIC_PRODUCTION", loop)

    def test_the_journal_seam_asserts_production(self):
        import inspect

        from apps.journal.services import journal_conversation as jc
        src = inspect.getsource(jc._call)
        self.assertIn("TRAFFIC_PRODUCTION", src)

    def test_an_outer_classification_is_never_overwritten(self):
        """A certification or proactive run that reaches an interactive seam keeps its
        own class — otherwise a diagnostic would launder itself as customer traffic."""
        import inspect

        from apps.journal.services import journal_conversation as jc
        self.assertIn("None if current_traffic_class() else", inspect.getsource(jc._call))


class CheckinAttributionTests(TestCase):
    """Attribution belongs to the WORK, so a new caller cannot reintroduce the hole."""

    def setUp(self):
        self.user = User.objects.create_user(email="auto@contract.test", password="x")

    def _author(self, envelope, reply="a real message", signals=None):
        seen = {}

        def _fake(*a, **kw):
            seen["autonomous"] = adm.current_workload_is_autonomous()
            from apps.ai.llm_accounting import current_source, current_traffic_class
            seen["traffic"] = current_traffic_class()
            seen["source"] = current_source()
            seen["prompt"] = a[1] if len(a) > 1 else kw.get("user_prompt")
            return reply

        from apps.ai import checkin_author as ca
        with mock.patch(
                "apps.ai.model_interface.service.ModelInterfaceService"
                ".build_standing_context", return_value=envelope), \
             mock.patch("apps.ai.services.ai_service._call_api", side_effect=_fake) as call:
            text = ca.author_checkin(self.user, signals=signals)
        return text, seen, call

    LIVE = {"execution_state": {"overdue": [{"title": "x"}], "due_now": [],
                                "coming_up": [], "later": [], "completed": []}}
    QUIET = {"execution_state": {"overdue": [], "due_now": [], "coming_up": [],
                                 "later": [{"title": "later"}], "completed": [1]}}

    def test_the_check_in_call_is_marked_autonomous(self):
        _text, seen, _call = self._author(self.LIVE)
        self.assertTrue(seen["autonomous"],
                        "the check-in provider call was not visible to the cost gate")

    def test_it_carries_proactive_traffic_and_its_own_source(self):
        _text, seen, _call = self._author(self.LIVE)
        self.assertEqual(seen["traffic"], TRAFFIC_PROACTIVE)
        self.assertEqual(seen["source"], "proactive_checkin")

    def test_attribution_holds_however_the_caller_reached_it(self):
        """The renderer entry points are the ones that used to forget."""
        from apps.ai import beth_checkin_renderer as r
        seen = {}

        def _fake(*a, **kw):
            seen["autonomous"] = adm.current_workload_is_autonomous()
            return "msg"

        with mock.patch(
                "apps.ai.model_interface.service.ModelInterfaceService"
                ".build_standing_context", return_value=self.LIVE), \
             mock.patch("apps.ai.services.ai_service._call_api", side_effect=_fake):
            r.render_checkin_for_time(self.user)
        self.assertTrue(seen["autonomous"])

    def test_a_quiet_day_makes_no_provider_call_at_all(self):
        text, _seen, call = self._author(self.QUIET)
        self.assertEqual(text, "")
        call.assert_not_called()


class DetectionIsNotInterruptionTests(TestCase):
    """A detected signal reaches authoring; it does not force a message."""

    def setUp(self):
        self.user = User.objects.create_user(email="sig@contract.test", password="x")

    QUIET = {"execution_state": {"overdue": [], "due_now": [], "coming_up": [],
                                 "later": [], "completed": []}}

    def _author(self, reply, signals):
        from apps.ai import checkin_author as ca
        with mock.patch(
                "apps.ai.model_interface.service.ModelInterfaceService"
                ".build_standing_context", return_value=self.QUIET), \
             mock.patch("apps.ai.services.ai_service._call_api",
                        return_value=reply) as call:
            return ca.author_checkin(self.user, signals=signals), call

    def test_a_signal_reaches_authoring_on_an_otherwise_quiet_day(self):
        text, call = self._author("Worth a look at your pace.", {"goal_pace": {"x": 1}})
        call.assert_called_once()
        self.assertEqual(text, "Worth a look at your pace.")

    def test_the_model_may_decline_and_that_produces_silence(self):
        from apps.ai.checkin_author import SILENCE_TOKEN
        text, call = self._author(SILENCE_TOKEN, {"goal_pace": {"x": 1}})
        call.assert_called_once()
        self.assertEqual(text, "", "a declined check-in still produced text")

    def test_declining_does_not_fall_through_to_the_degraded_directive(self):
        """The failure mode this guards: 'not worth it' quietly becoming a fact line."""
        from apps.ai.checkin_author import SILENCE_TOKEN
        with mock.patch("apps.core.execution.decision_authority"
                        ".current_action_directive", return_value="Next: X.") as directive:
            text, _call = self._author(SILENCE_TOKEN, {"goal_pace": {"x": 1}})
        self.assertEqual(text, "")
        directive.assert_not_called()

    def test_silence_is_recognised_despite_punctuation_or_case(self):
        for reply in ("NO_MESSAGE", "no_message", " NO_MESSAGE. ", '"NO_MESSAGE"'):
            text, _call = self._author(reply, {"goal_pace": {"x": 1}})
            self.assertEqual(text, "", f"{reply!r} was not treated as silence")

    def test_the_prompt_states_that_silence_is_a_correct_outcome(self):
        from apps.ai.checkin_author import SILENCE_TOKEN, _user_prompt
        prompt = _user_prompt({}, "morning", {"goal_pace": {"x": 1}})
        self.assertIn(SILENCE_TOKEN, prompt)
        self.assertIn("worse than silence", prompt)
        self.assertIn("WLJ has NOT decided any of them matters", prompt)

    def test_no_message_is_created_when_authoring_returns_silence(self):
        from apps.ai.proactive_checkins import ProactiveCheckInService
        svc = ProactiveCheckInService(self.user)
        with mock.patch.object(svc.throttler, "can_send", return_value=True), \
             mock.patch("apps.ai.cos_intelligence.build_cos_intelligence",
                        return_value={"goal_pace": {"on_pace": False}}), \
             mock.patch("apps.ai.checkin_author.author_checkin", return_value=""), \
             mock.patch.object(svc, "_create_proactive_message") as create:
            self.assertIsNone(svc.generate_health_trend_check_in())
        create.assert_not_called()

    def test_a_useful_message_is_still_delivered(self):
        from apps.ai.proactive_checkins import ProactiveCheckInService
        svc = ProactiveCheckInService(self.user)
        with mock.patch.object(svc.throttler, "can_send", return_value=True), \
             mock.patch("apps.ai.cos_intelligence.build_cos_intelligence",
                        return_value={"goal_pace": {"on_pace": False}}), \
             mock.patch("apps.ai.checkin_author.author_checkin",
                        return_value="Here is the useful thing."), \
             mock.patch.object(svc, "_create_proactive_message") as create:
            svc.generate_health_trend_check_in()
        self.assertEqual(create.call_args.kwargs["content"], "Here is the useful thing.")

    def test_the_cooldown_still_short_circuits_before_anything_else(self):
        from apps.ai.proactive_checkins import ProactiveCheckInService
        svc = ProactiveCheckInService(self.user)
        with mock.patch.object(svc.throttler, "can_send", return_value=False), \
             mock.patch("apps.ai.cos_intelligence.build_cos_intelligence") as intel:
            self.assertIsNone(svc.generate_health_trend_check_in())
        intel.assert_not_called()

    def test_no_detected_signal_means_no_authoring_call(self):
        from apps.ai.proactive_checkins import ProactiveCheckInService
        svc = ProactiveCheckInService(self.user)
        with mock.patch.object(svc.throttler, "can_send", return_value=True), \
             mock.patch("apps.ai.cos_intelligence.build_cos_intelligence",
                        return_value={}), \
             mock.patch("apps.ai.checkin_author.author_checkin") as author:
            self.assertIsNone(svc.generate_health_trend_check_in())
        author.assert_not_called()


class SignalsAreFactsNotWordsTests(SimpleTestCase):
    """WLJ hands over what it measured, never what it would have said about it."""

    def _signals(self, intel):
        from apps.ai.proactive_checkins import _detected_signals
        return _detected_signals(intel)

    def test_wlj_prose_never_travels_as_a_signal(self):
        out = self._signals({
            "goal_pace": {"on_pace": False, "required_pace_lb_wk": 1.2},
            "goal_pace_narrative": "You are slipping badly.",
            "briefing": "Chief of staff briefing prose.",
        })
        self.assertIn("goal_pace", out)
        self.assertNotIn("goal_pace_narrative", out)
        self.assertNotIn("briefing", out)

    def test_verdicts_are_stripped_from_signals_too(self):
        out = self._signals({"intelligence": {"momentum": "strong", "count": 4}})
        self.assertEqual(out["intelligence"], {"count": 4})

    def test_nothing_detected_returns_empty(self):
        for empty in ({}, None, {"goal_pace_narrative": "words"}, {"goal_pace": {}}):
            self.assertEqual(self._signals(empty), {})

    def test_signals_are_bounded(self):
        import json
        big = {f"block_{i}": {"value": "x" * 500} for i in range(40)}
        self.assertLessEqual(len(json.dumps(self._signals(big), default=str)), 4200)

    def test_the_extractor_names_no_domain(self):
        """The old ladder knew about weight. Its replacement must know about nothing."""
        import inspect

        from apps.ai import proactive_checkins as pc
        src = inspect.getsource(pc._detected_signals).lower()
        for domain_word in ("weight", "lb/week", "pace", "sleep", "workout", "goal"):
            self.assertNotIn(domain_word, src)

    def test_the_hand_written_message_ladder_is_gone(self):
        from apps.ai.proactive_checkins import ProactiveCheckInService
        self.assertFalse(hasattr(ProactiveCheckInService,
                                 "_select_health_trend_message"),
                         "WLJ is still choosing and writing the intervention")
