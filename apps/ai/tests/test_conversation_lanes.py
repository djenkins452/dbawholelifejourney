# ==============================================================================
# File: apps/ai/tests/test_conversation_lanes.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Conversation lane registry — clarification + general lanes.
# ==============================================================================
"""
Proves the framework-first lane registry (P6/P13):
  Foundational Facts -> Personal Reasoning -> Clarification -> General -> (tool loop)

Guarantees under test:
  * 'check in' routes to the Clarification lane with Daily Check-In framing
  * clarification is DETERMINISTIC (no OpenAI) and never reaches the tool loop
  * the General lane is SANDBOXED (no personal data) with a deterministic fallback
  * existing health-intent routing is preserved (new lanes never steal it)
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.chatgpt_cos.lanes import (
    AMBIGUITY_TYPES,
    LANE_REGISTRY,
    _clarification_reply_lane,
    _next_rhythm_lane,
    clarify,
    general_answer,
    parse_clarification_reply,
    route_message,
)
from apps.ai.models import AssistantConversation

User = get_user_model()

_CALL_API = "apps.ai.services.ai_service._call_api"
_CALL_API_TOOLS = "apps.ai.services.ai_service._call_api_with_tools"
_FOUNDATIONAL = "apps.ai.chatgpt_cos.foundational_facts.answer_foundational_fact"
_REASONING = "apps.ai.chatgpt_cos.reasoning.answer_reasoning_question"

_HEALTH_QS = (
    "What is my biggest health risk right now?",
    "How am I doing overall with my health goals?",
    "What should I focus on from a health perspective today?",
    "What are my health concerns?",
)


class ClarificationLaneTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="lane_clar@example.com", password="x")

    def test_daily_checkin_type_registered(self):
        types = {a["type"] for a in AMBIGUITY_TYPES}
        self.assertIn("daily_checkin_candidate", types)

    def test_clarify_check_in_is_deterministic_no_openai(self):
        # clarify() itself must never call OpenAI: mock both APIs to explode.
        with mock.patch(_CALL_API, side_effect=AssertionError("openai")), \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tools")):
            out = clarify("check in")
        self.assertIsNotNone(out)
        self.assertEqual(out["ambiguity_type"], "daily_checkin_candidate")
        self.assertEqual(out["lane"], "clarification")
        self.assertIn("daily check-in", out["answer"].lower())
        for opt in ("coming up today", "do next", "health and energy",
                    "goals and commitments", "whole life check-in"):
            self.assertIn(opt, out["answer"].lower())

    def test_check_in_routes_to_clarification_not_tool_loop_no_openai_required(self):
        # Even with OpenAI DOWN (planner raises), 'check in' still produces the
        # deterministic clarification and NEVER reaches the tool loop.
        with mock.patch(_CALL_API, side_effect=RuntimeError("openai down")), \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tool loop")):
            out = route_message(self.user, "check in")
        self.assertEqual(out["lane"], "clarification")
        self.assertEqual(out["ambiguity_type"], "daily_checkin_candidate")
        self.assertIn("daily check-in", out["answer"].lower())

    def test_help_and_review_clarifications(self):
        self.assertEqual(clarify("help me")["ambiguity_type"], "unspecified_help")
        self.assertEqual(clarify("review this")["ambiguity_type"],
                         "unspecified_review")

    def test_specific_request_not_stolen_into_clarification(self):
        # a specific, longer request is NOT claimed as ambiguous
        self.assertIsNone(clarify("check in on my flight to Denver tomorrow morning"))
        self.assertIsNone(clarify("review my Q3 sales report and summarize risks"))


class GeneralLaneTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="lane_gen@example.com", password="x")

    def test_general_knowledge_routes_to_general(self):
        with mock.patch(_CALL_API,
                        return_value="Abraham Lincoln was the 16th US president."), \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tool loop")), \
             mock.patch(_FOUNDATIONAL, return_value=None):
            out = route_message(self.user, "Who was Abraham Lincoln?")
        self.assertEqual(out["lane"], "general_conversation")
        self.assertIn("Lincoln", out["answer"])

    def test_general_is_sandboxed_no_personal_payload(self):
        captured = {}

        def _spy(system, user_prompt, **kw):
            captured["system"] = system
            captured["user_prompt"] = user_prompt
            return "Photosynthesis converts light into chemical energy."

        with mock.patch(_CALL_API, side_effect=_spy):
            out = general_answer(self.user, "Explain photosynthesis.")
        self.assertEqual(out["lane"], "general_conversation")
        # the prompt carries ONLY the question — no SAE / personal data injected
        self.assertEqual(captured["user_prompt"], "Explain photosynthesis.")
        self.assertIn("do not reference", captured["system"].lower())

    def test_general_deterministic_fallback_on_llm_failure(self):
        with mock.patch(_CALL_API, side_effect=RuntimeError("boom")):
            out = general_answer(self.user, "What is Delphi?")
        self.assertEqual(out["lane"], "general_conversation")
        self.assertTrue(out["answer"].strip())
        low = out["answer"].lower()
        # graceful degradation: acknowledges the outage + invites retry
        self.assertIn("temporarily unavailable", low)
        self.assertIn("try again", low)
        # NO personal-domain leakage on an external-knowledge question
        for leak in ("your goal", "your health", "your schedule", "your faith"):
            self.assertNotIn(leak, low)

    def test_general_declines_personal_questions(self):
        for q in ("what is my weight", "what are my goals",
                  "how am I doing with my health"):
            self.assertIsNone(general_answer(self.user, q), q)


class RoutingPreservationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="lane_route@example.com", password="x")

    def test_registry_order(self):
        self.assertEqual([n for n, _ in LANE_REGISTRY],
                         ["temporal", "why_explainer", "referential",
                          "clarification_reply", "conversation_planner",
                          "decision_support", "accomplishment", "sleep_history", "weight_history", "workout_history", "foundational_facts", "clarification",
                          "general_continuity", "next_rhythm", "priority_now", "executive_risk", "executive_opportunity", "cos_briefing",
                          "personal_reasoning", "general_conversation"])

    def test_health_questions_never_claimed_by_new_lanes(self):
        # The Clarification + General lanes must NEVER claim a health/personal
        # question — they would otherwise lose personalization / contaminate.
        for q in _HEALTH_QS + ("what's my weight", "what is my glucose today"):
            self.assertIsNone(clarify(q), f"clarify stole: {q}")
            self.assertIsNone(general_answer(self.user, q), f"general stole: {q}")

    def test_health_question_routes_to_reasoning(self):
        # A health question is declined by the deterministic lanes (clarification
        # has no trigger; next_rhythm has no signal) and claimed by reasoning.
        # general_answer must NOT be reached (reasoning claims before it).
        with mock.patch(_FOUNDATIONAL, return_value=None), \
             mock.patch(_REASONING,
                        return_value={"answer": "health answer",
                                      "tools_called": [],
                                      "reasoning": {"intent": "biggest_health_risk"}}), \
             mock.patch("apps.ai.chatgpt_cos.lanes.general_answer",
                        side_effect=AssertionError("general reached")):
            out = route_message(self.user, "What is my biggest health risk right now?")
        self.assertEqual(out["lane"], "personal_reasoning")
        self.assertEqual(out["answer"], "health answer")
        self.assertEqual(out["reasoning"]["intent"], "biggest_health_risk")

    def test_all_lanes_decline_returns_none_for_tool_loop(self):
        # Unknown / non-general / non-ambiguous -> route declines so the caller
        # runs the tool-loop terminal fallback (P8). Planner returns None.
        with mock.patch(_FOUNDATIONAL, return_value=None), \
             mock.patch(_CALL_API, return_value=None):
            self.assertIsNone(route_message(self.user, "asdf qwer zxcv"))

    def test_lane_results_carry_answer_and_tools_called(self):
        # contract parity — every lane result is task-compatible.
        c = clarify("check in")
        self.assertIn("answer", c)
        self.assertEqual(c["tools_called"], [])
        with mock.patch(_CALL_API, return_value="x"):
            g = general_answer(self.user, "What is gravity?")
        self.assertIn("answer", g)
        self.assertEqual(g["tools_called"], [])


_RHYTHM = {"current_key": "day", "sections": [
    {"key": "morning", "items": [
        {"title": "Wake up", "completed_today": True, "scheduled_time": "06:00"}]},
    {"key": "day", "items": [
        {"title": "Work on WLJ", "completed_today": False, "scheduled_time": "09:00"},
        {"title": "Prayer Time", "completed_today": False, "scheduled_time": "12:00"}]},
    {"key": "evening", "items": [
        {"title": "Bible Reading", "completed_today": False, "scheduled_time": "19:00"}]},
    {"key": "night", "items": []},
]}
_RHYTHM_PATCH = "apps.core.cos_briefing.rhythm.build_rhythm_sections"


class ClarificationStateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="lane_state@example.com", password="x")

    def setUp(self):
        self.conv = AssistantConversation.objects.create(user=self.user)

    def test_check_in_sets_pending_state(self):
        # planner is attempted then declines; clarification claims (no OpenAI needed)
        with mock.patch(_CALL_API, side_effect=RuntimeError("openai down")), \
             mock.patch(_FOUNDATIONAL, return_value=None):
            out = route_message(self.user, "check in", self.conv)
        self.assertEqual(out["lane"], "clarification")
        self.assertEqual(out["ambiguity_type"], "daily_checkin_candidate")
        self.conv.refresh_from_db()
        pending = (self.conv.metadata or {}).get("pending_clarification")
        self.assertIsNotNone(pending)
        self.assertEqual(pending["ambiguity_type"], "daily_checkin_candidate")
        self.assertEqual(len(pending["options"]), 5)

    def test_reply_1_resolves_deterministically_no_openai_no_tool_loop(self):
        self.conv.metadata = {"pending_clarification": {
            "ambiguity_type": "daily_checkin_candidate",
            "options": [{"n": i, "aliases": [], "resolution": f"R{i}"} for i in range(1, 6)]}}
        self.conv.save(update_fields=["metadata"])
        with mock.patch(_CALL_API, side_effect=AssertionError("openai")), \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tool loop")):
            out = route_message(self.user, "1", self.conv)
        self.assertEqual(out["lane"], "clarification_reply")
        self.assertEqual(out["resolved_option"], 1)
        self.assertEqual(out["answer"], "R1")
        self.conv.refresh_from_db()
        self.assertNotIn("pending_clarification", self.conv.metadata or {})

    def test_reply_alias_and_ordinal(self):
        opts = [{"n": 1, "aliases": ["today"], "resolution": "R1"},
                {"n": 3, "aliases": ["health"], "resolution": "R3"}]
        self.assertEqual(parse_clarification_reply("health", opts)["resolution"], "R3")
        self.assertEqual(parse_clarification_reply("the first one", opts)["resolution"], "R1")
        self.assertIsNone(parse_clarification_reply("what is photosynthesis exactly today", opts))

    def test_non_reply_clears_stale_and_routes_fresh(self):
        self.conv.metadata = {"pending_clarification": {
            "ambiguity_type": "daily_checkin_candidate",
            "options": [{"n": 1, "aliases": [], "resolution": "R1"}]}}
        self.conv.save(update_fields=["metadata"])
        with mock.patch(_FOUNDATIONAL, return_value=None), \
             mock.patch(_CALL_API, return_value="Gravity is a force."):
            out = route_message(self.user, "What is gravity?", self.conv)
        self.assertEqual(out["lane"], "general_conversation")     # routed fresh
        self.conv.refresh_from_db()
        self.assertNotIn("pending_clarification", self.conv.metadata or {})  # stale cleared

    def test_reply_lane_declines_when_no_pending(self):
        self.assertIsNone(_clarification_reply_lane(self.user, "1", self.conv))


class P24RhythmApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="lane_p24@example.com", password="x")

    def test_rhythm_api_derives_from_build_rhythm_sections(self):
        from apps.core.cos_briefing import rhythm_api
        with mock.patch(_RHYTHM_PATCH, return_value=_RHYTHM):
            self.assertEqual(rhythm_api.get_current_rhythm_item(self.user)["title"], "Work on WLJ")
            self.assertEqual(rhythm_api.get_next_rhythm_item(self.user)["title"], "Prayer Time")
            self.assertEqual([i["title"] for i in rhythm_api.get_remaining_rhythm_items(self.user)],
                             ["Work on WLJ", "Prayer Time", "Bible Reading"])
            self.assertEqual(rhythm_api.get_current_rhythm_bucket(self.user)["key"], "day")

    def test_dashboard_and_beth_agree_on_next(self):
        # Dashboard "next" == rhythm engine's current item; Beth must match it.
        from apps.core.cos_briefing import rhythm_api
        with mock.patch(_RHYTHM_PATCH, return_value=_RHYTHM), \
             mock.patch(_FOUNDATIONAL, return_value=None), \
             mock.patch(_CALL_API, return_value=None):              # planner declines
            dashboard_next = rhythm_api.get_current_rhythm_item(self.user)["title"]
            out = route_message(self.user, "What should I do next?", None)
        self.assertEqual(out["lane"], "next_rhythm")
        self.assertEqual(dashboard_next, "Work on WLJ")
        self.assertIn("Work on WLJ", out["answer"])      # Beth == dashboard
        self.assertNotIn("Bible Reading", out["answer"].split("After that")[0])

    def test_next_rhythm_does_not_claim_urgency_focus_now(self):
        # "right now / focus" is the URGENCY fact (get_next_action), NOT rhythm.
        self.assertIsNone(_next_rhythm_lane(self.user, "what should I do right now"))
        self.assertIsNone(_next_rhythm_lane(self.user, "what should I focus on right now"))


class ApprovedRegistryOrderTests(TestCase):
    """The exact approved order (clarification + next_rhythm BEFORE personal
    reasoning; general AFTER it). Issue #1 General ordering is intentionally
    unchanged pending production telemetry."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="lane_appr@example.com", password="x")

    def setUp(self):
        self.conv = AssistantConversation.objects.create(user=self.user)

    def test_order_is_approved(self):
        self.assertEqual(
            [n for n, _ in LANE_REGISTRY],
            ["temporal", "why_explainer", "referential", "clarification_reply",
             "conversation_planner", "decision_support", "accomplishment", "sleep_history", "weight_history", "workout_history", "foundational_facts",
             "clarification", "general_continuity", "next_rhythm", "priority_now", "executive_risk", "executive_opportunity", "cos_briefing",
             "personal_reasoning", "general_conversation"])

    def test_check_in_routes_to_clarification_and_not_personal_reasoning(self):
        # the planner must NEVER run for 'check in' — mock it to explode; the
        # clarification lane claims first, so reasoning is never reached.
        with mock.patch(_CALL_API, side_effect=AssertionError("planner ran")), \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tool loop")), \
             mock.patch(_FOUNDATIONAL, return_value=None):
            out = route_message(self.user, "check in", self.conv)
        self.assertEqual(out["lane"], "clarification")
        self.assertEqual(out["ambiguity_type"], "daily_checkin_candidate")

    def test_check_in_then_1_resolves_state(self):
        with mock.patch(_CALL_API, side_effect=AssertionError("planner")), \
             mock.patch(_FOUNDATIONAL, return_value=None):
            route_message(self.user, "check in", self.conv)
        with mock.patch(_CALL_API, side_effect=AssertionError("openai")), \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tool loop")):
            out = route_message(self.user, "1", self.conv)
        self.assertEqual(out["lane"], "clarification_reply")
        self.assertEqual(out["resolved_option"], 1)
        self.conv.refresh_from_db()
        self.assertNotIn("pending_clarification", self.conv.metadata or {})

    def test_what_should_i_do_next_routes_to_next_rhythm(self):
        # next_rhythm is before reasoning -> the planner never runs for it.
        with mock.patch(_RHYTHM_PATCH, return_value=_RHYTHM), \
             mock.patch(_CALL_API, side_effect=AssertionError("planner")), \
             mock.patch(_FOUNDATIONAL, return_value=None):
            out = route_message(self.user, "what should I do next?", self.conv)
        self.assertEqual(out["lane"], "next_rhythm")
        self.assertIn("Work on WLJ", out["answer"])

    def test_health_question_routes_to_personal_reasoning(self):
        with mock.patch(_FOUNDATIONAL, return_value=None), \
             mock.patch(_REASONING,
                        return_value={"answer": "health read", "tools_called": [],
                                      "reasoning": {"intent": "biggest_health_risk"}}):
            out = route_message(
                self.user, "what is my biggest health risk right now?", self.conv)
        self.assertEqual(out["lane"], "personal_reasoning")

    def test_general_routes_to_general_after_reasoning_declines_no_tool_loop(self):
        # general is AFTER reasoning: the planner runs, declines (non-JSON ->
        # 'other'), then the general lane claims. Tool loop is never reached.
        with mock.patch(_CALL_API,
                        return_value="Lincoln was the 16th US president."), \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tool loop")), \
             mock.patch(_FOUNDATIONAL, return_value=None):
            out = route_message(self.user, "Who was Abraham Lincoln?", self.conv)
        self.assertEqual(out["lane"], "general_conversation")
        self.assertIn("Lincoln", out["answer"])


class DailyCheckinResolutionTests(TestCase):
    """check in -> option resolutions are synthesized (no deflection)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="lane_ckres@example.com", password="x")

    def setUp(self):
        self.conv = AssistantConversation.objects.create(user=self.user)

    def _pending(self, options):
        self.conv.metadata = {"pending_clarification": {
            "ambiguity_type": "daily_checkin_candidate", "options": options}}
        self.conv.save(update_fields=["metadata"])

    def test_option1_returns_synthesized_agenda_no_deflection_no_openai(self):
        self._pending([{"n": 1, "aliases": ["today"], "resolver": "agenda",
                        "resolution": "fallback"}])
        ps = [
            mock.patch("apps.core.cos_briefing.rhythm_api.get_remaining_rhythm_items",
                       return_value=[{"title": "Prayer Time", "scheduled_time": "05:30",
                                      "completed_today": False}]),
            mock.patch("apps.core.cos_briefing.rhythm_api.get_current_rhythm_item",
                       return_value={"title": "Prayer Time", "scheduled_time": "05:30"}),
            mock.patch("apps.core.execution.execution_state.build_execution_state",
                       return_value={}),
            mock.patch("apps.core.execution.selectors.get_next_action",
                       return_value={"primary_action": {"title": "Work on WLJ"}}),
            mock.patch("apps.core.cos_briefing.rhythm.build_rhythm_sections",
                       return_value={"totals": {"overdue": 0, "at_risk": 0}}),
            mock.patch(_CALL_API, side_effect=AssertionError("no openai")),
            mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("no tool loop")),
        ]
        for p in ps:
            p.start()
        try:
            out = route_message(self.user, "1", self.conv)
        finally:
            for p in ps:
                p.stop()
        self.assertEqual(out["lane"], "clarification_reply")
        self.assertIn("Prayer Time", out["answer"])
        self.assertIn("Work on WLJ", out["answer"])
        low = out["answer"].lower()
        for bad in ("dashboard", "ask me", "goals area", "go to", "look at your"):
            self.assertNotIn(bad, low)

    def test_option4_goals_returns_honest_gap_not_deflection(self):
        # full 5-option set — the reply parser selects by position (1..N).
        self._pending([
            {"n": 1, "aliases": [], "resolver": "agenda", "resolution": "f"},
            {"n": 2, "aliases": [], "resolver": "next", "resolution": "f"},
            {"n": 3, "aliases": [], "resolver": "health", "resolution": "f"},
            {"n": 4, "aliases": ["goals"], "resolver": "goals_gap", "resolution": "f"},
            {"n": 5, "aliases": [], "resolver": "full_checkin", "resolution": "f"},
        ])
        with mock.patch(_CALL_API, side_effect=AssertionError("no openai")):
            out = route_message(self.user, "4", self.conv)
        self.assertEqual(out["resolved_option"], 4)
        self.assertIn("active goal information", out["answer"].lower())
        self.assertNotIn("goals area", out["answer"].lower())
        for dev in ("composed", "daily brief"):
            self.assertNotIn(dev, out["answer"].lower())


class NoDeflectionLanguageTests(TestCase):
    def test_no_static_resolution_contains_deflection(self):
        from apps.ai.chatgpt_cos.lanes import AMBIGUITY_TYPES
        bad = ("dashboard", "goals area", "faith area", "open your tasks",
               "ask me", "go to your", "look at your", "check your dashboard",
               "visit the")
        for spec in AMBIGUITY_TYPES:
            for opt in spec.get("options", []):
                low = (opt.get("resolution") or "").lower()
                for phrase in bad:
                    self.assertNotIn(phrase, low,
                                     f"{spec['type']} opt{opt['n']}: {phrase!r}")


class GeneralLaneReliabilityTests(TestCase):
    """Issue #1: a clearly-general question must NOT invoke the health planner."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="lane_genrel@example.com", password="x")

    def test_reasoning_lane_skips_planner_for_general(self):
        from apps.ai.chatgpt_cos.lanes import _reasoning_lane
        # planner would call _call_api; for a general question it must be skipped.
        with mock.patch(_CALL_API, side_effect=AssertionError("planner ran")):
            self.assertIsNone(_reasoning_lane(self.user, "Who was Abraham Lincoln?"))
            self.assertIsNone(_reasoning_lane(self.user, "Explain photosynthesis."))

    def test_general_question_makes_only_one_call_no_planner(self):
        with mock.patch(_CALL_API, return_value="Lincoln was the 16th US president.") as ca, \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tool loop")), \
             mock.patch(_FOUNDATIONAL, return_value=None):
            out = route_message(self.user, "Who was Abraham Lincoln?")
        self.assertEqual(out["lane"], "general_conversation")
        self.assertEqual(ca.call_count, 1)   # general only — planner was skipped
