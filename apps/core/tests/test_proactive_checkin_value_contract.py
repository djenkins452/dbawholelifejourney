# ==============================================================================
# File: apps/core/tests/test_proactive_checkin_value_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: A proactive message needs a concrete reason, and the task must reach the model
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-04
# ==============================================================================
"""Danny woke up to "Hello! How can I assist you today?" — twice.

Not a fallback, and not a canned string: two real provider calls, ~11,600 input tokens and
about nine output tokens each. The check-in prompt was assembled as CONSTITUTION + the
authoring instruction + the whole truth envelope, in the SYSTEM slot, with an EMPTY user
message. The token governor trims a system prompt FROM THE END at a 12,000-token default,
so measured on Danny's real envelope: 122,518 chars in, 29,817 chars kept — 24%. What it
cut was the instruction and every fact. The model was handed two-thirds of a constitution
and nothing to do, so it greeted.

Two structural corrections, no canned rules and no content matching:

  1. The task and the truth move to the USER turn, which the governor never trims, and the
     call passes a budget sized to the model instead of the legacy default.
  2. Silence becomes an available answer. WLJ decides the FACT question — is anything live
     in today's canonical execution truth? — before a single token is generated. Whether
     that thing is worth saying stays the model's judgment.

No domain, metric, task or phrase is special-cased. No provider calls in these tests.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai import checkin_author as ca

User = get_user_model()

LIVE = {"execution_state": {"overdue": [{"title": "X"}], "due_now": [],
                            "coming_up": [], "later": [], "completed": []}}
QUIET = {"execution_state": {"overdue": [], "due_now": [], "coming_up": [],
                             "later": [{"title": "tomorrow"}],
                             "completed": [{"title": "done"}]},
         "current_action": {"primary_action": None}}


class ReasonToInterruptTests(SimpleTestCase):
    """The precondition is a FACT question, so WLJ answers it — generically."""

    def test_something_outstanding_is_a_reason(self):
        for bucket in ("overdue", "due_now", "coming_up"):
            self.assertTrue(
                ca.has_reason_to_interrupt({"execution_state": {bucket: [{"t": 1}]}}),
                f"{bucket} did not count as a live reason")

    def test_a_decided_current_action_is_a_reason(self):
        self.assertTrue(ca.has_reason_to_interrupt(
            {"current_action": {"primary_action": {"title": "X"}}}))

    def test_a_finished_or_future_day_is_not_a_reason(self):
        self.assertFalse(ca.has_reason_to_interrupt(QUIET))

    def test_an_empty_or_failed_envelope_is_not_a_reason(self):
        self.assertFalse(ca.has_reason_to_interrupt({}))
        self.assertFalse(ca.has_reason_to_interrupt(None))

    def test_the_precondition_is_blind_to_what_the_items_are(self):
        """Asserted as BEHAVIOUR, not by scanning for words — the module's own docstrings
        name the incident's domains, and a substring check would fail on the explanation
        while missing a real topic list. Two envelopes identical in SHAPE but from
        completely different domains must decide identically."""
        weightish = {"execution_state": {"overdue": [{"title": "Weigh in",
                                                      "domain": "health"}]}}
        moneyish = {"execution_state": {"overdue": [{"title": "Pay card",
                                                     "domain": "finance"}]}}
        self.assertEqual(ca.has_reason_to_interrupt(weightish),
                         ca.has_reason_to_interrupt(moneyish))
        self.assertTrue(ca.has_reason_to_interrupt(weightish))

    def test_only_bucket_names_decide(self):
        """The live-bucket list is execution vocabulary, never a topic list."""
        self.assertEqual(set(ca._LIVE_BUCKETS), {"overdue", "due_now", "coming_up"})


class SilencePreferredTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="pc@contract.test", password="x")

    def test_a_quiet_day_produces_no_message_and_no_provider_call(self):
        with mock.patch("apps.ai.model_interface.service.ModelInterfaceService"
                        ".build_standing_context", return_value=QUIET), \
             mock.patch("apps.ai.services.ai_service._call_api") as called:
            self.assertEqual(ca.author_checkin(self.user), "")
        called.assert_not_called()

    def test_a_live_day_still_produces_a_message(self):
        with mock.patch("apps.ai.model_interface.service.ModelInterfaceService"
                        ".build_standing_context", return_value=LIVE), \
             mock.patch("apps.ai.services.ai_service._call_api",
                        return_value="Bike ride is still open — 20 minutes now?"):
            self.assertIn("Bike ride", ca.author_checkin(self.user))

    def test_the_degraded_path_is_silent_rather_than_filler(self):
        """When the model is unavailable AND there is no canonical directive, say nothing.
        The old code returned "Here's where things stand — ask me what's on your plate.\""""
        with mock.patch("apps.ai.model_interface.service.ModelInterfaceService"
                        ".build_standing_context", return_value=LIVE), \
             mock.patch("apps.ai.services.ai_service._call_api", return_value=""), \
             mock.patch("apps.core.execution.decision_authority.current_action_directive",
                        side_effect=RuntimeError("down")):
            self.assertEqual(ca.author_checkin(self.user), "")

    def test_the_senders_already_drop_an_empty_message(self):
        """Silence only works if nothing ships an empty string."""
        import pathlib
        src = pathlib.Path("apps/ai/proactive_checkins.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(src.count("if not message or len(message) < 20:"), 2)


class PromptSurvivesTheGovernorTests(TestCase):
    """The measurement that would have caught this on day one."""

    def setUp(self):
        self.user = User.objects.create_user(email="pc2@contract.test", password="x")

    def test_the_task_and_the_truth_are_in_the_user_turn(self):
        user_prompt = ca._user_prompt(LIVE, "morning")
        self.assertIn("PROACTIVE CHECK-IN (author this now)", user_prompt)
        self.assertIn("=== DETERMINISTIC TRUTH ===", user_prompt)
        self.assertNotIn("PROACTIVE CHECK-IN", ca._system_prompt(),
                         "the task is back in the system prompt, where it gets truncated")

    def test_the_user_turn_is_never_empty(self):
        """An empty user turn is what makes a model greet."""
        self.assertTrue(ca._user_prompt({}, None).strip())

    def test_the_governor_cannot_evict_the_task_or_the_truth(self):
        """Runs the REAL governor over the REAL assembled messages."""
        from apps.ai.conversation.token_governor import govern_prompt
        messages = [{"role": "system", "content": ca._system_prompt()},
                    {"role": "user", "content": ca._user_prompt(LIVE, "morning")}]
        governed, _ = govern_prompt(messages, max_budget=ca.CHECKIN_GOVERN_BUDGET)
        survived = governed[-1]["content"]
        self.assertIn("author this now", survived)
        self.assertIn("DETERMINISTIC TRUTH", survived)

    def test_the_user_turn_survives_even_at_the_legacy_budget(self):
        """The governor trims history and then the SYSTEM prompt — never the user turn. So
        even the default that caused the incident can no longer delete the task."""
        from apps.ai.conversation.token_governor import govern_prompt
        messages = [{"role": "system", "content": ca._system_prompt()},
                    {"role": "user", "content": ca._user_prompt(LIVE, "morning")}]
        governed, report = govern_prompt(messages, max_budget=12000)
        self.assertTrue(report.over_budget)
        self.assertIn("author this now", governed[-1]["content"])

    def test_the_call_passes_a_real_budget(self):
        with mock.patch("apps.ai.model_interface.service.ModelInterfaceService"
                        ".build_standing_context", return_value=LIVE), \
             mock.patch("apps.ai.services.ai_service._call_api",
                        return_value="ok") as called:
            ca.author_checkin(self.user)
        self.assertEqual(called.call_args.kwargs["govern_budget"],
                         ca.CHECKIN_GOVERN_BUDGET)
        self.assertGreater(ca.CHECKIN_GOVERN_BUDGET, 12000,
                           "the budget is still the default that truncated the prompt")


class GovernorBudgetIsHonouredTests(SimpleTestCase):
    """`_call_api` ignored its caller's budget entirely — that is why the fix is possible."""

    def test_call_api_accepts_and_forwards_an_explicit_budget(self):
        import inspect
        from apps.ai.services import AIService
        sig = inspect.signature(AIService._call_api)
        self.assertIn("govern_budget", sig.parameters)
        src = inspect.getsource(AIService._call_api)
        self.assertIn("govern_prompt(messages, max_budget=govern_budget)", src,
                      "_call_api still calls the governor with no budget")


class NoCannedResponseRuleTests(SimpleTestCase):
    """The fix is structural. Nothing here matches on the model's words."""

    def test_no_greeting_blocklist_was_added(self):
        """Assert on the CODE, not the file text.

        A raw substring scan fails on this module's own docstring, which quotes the
        greeting to explain the incident. Explaining a failure is not implementing a
        filter. So this walks the AST and inspects only string constants that are NOT
        docstrings — the ones that could actually take part in a comparison.
        """
        import ast
        import pathlib
        tree = ast.parse(pathlib.Path("apps/ai/checkin_author.py")
                         .read_text(encoding="utf-8"))
        # Identify docstring NODES, not their cleaned text: ast.get_docstring() dedents,
        # so comparing values silently fails to exclude them.
        doc_nodes = set()
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and body:
                first = body[0]
                if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                        and isinstance(first.value.value, str)):
                    doc_nodes.add(id(first.value))
        literals = [n.value.lower() for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and id(n) not in doc_nodes]
        for canned in ("how can i assist", "hello", "hi there", "good morning"):
            self.assertFalse(any(canned in lit for lit in literals),
                             f"a greeting phrase became executable text: {canned!r}")

    def test_the_author_never_branches_on_what_the_model_said(self):
        """The only test applied to the model's output is whether there IS any."""
        import inspect
        body = inspect.getsource(ca.author_checkin)
        for content_check in (".lower()", "startswith(", "in text"):
            self.assertNotIn(content_check, body,
                             "the author inspects the model's words instead of its truth")
