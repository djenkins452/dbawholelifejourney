# ==============================================================================
# File: apps/core/tests/test_proactive_silence_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: If OpenAI cannot be asked, nobody speaks — and nobody speaks twice
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-04
# ==============================================================================
"""Production, 2026-09-04. Three unwanted proactive messages, and the gate was working.

"Hello! How can I assist you today?" at 7:40. "Next: Prayer Time. Do this now." twice at
12:16. The cost ledger shows two proactive-classified provider calls that day with zero
tokens and a failure each: the autonomous gate REFUSED them, exactly as designed.

Then WLJ published something anyway. `author_checkin` caught the refusal as a generic
error and fell through to the canonical next-action directive — WLJ-authored, never
offered to the model, not subject to the silence the model had just been denied the chance
to choose, and byte-identical between producers, so two producers sent the same sentence in
the same minute.

A refusal became an interruption, and a cost control became a message generator.

Two structural consequences, both certified here:

  1. If OpenAI cannot be asked, nobody has decided whether speaking is worthwhile — and
     WLJ does not get to decide instead. Silence.
  2. Cooldowns were keyed to a check-in TYPE. The person being interrupted does not
     experience types.

No provider calls anywhere; every model call is mocked.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.ai import checkin_author as ca
from apps.ai.llm_admission import RealLLMCallDenied

User = get_user_model()

LIVE = {"execution_state": {"overdue": [{"title": "Prayer Time"}], "due_now": [],
                            "coming_up": [], "later": [], "completed": []},
        "current_action": {"primary_action": {"title": "Prayer Time"}}}
QUIET = {"execution_state": {"overdue": [], "due_now": [], "coming_up": [],
                             "later": [], "completed": []}}


class Harness(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="silence@contract.test", password="x")
        cache.clear()

    def _author(self, *, envelope=LIVE, reply=None, side_effect=None, signals=None):
        kw = {"side_effect": side_effect} if side_effect else {"return_value": reply}
        with mock.patch("apps.ai.model_interface.service.ModelInterfaceService"
                        ".build_standing_context", return_value=envelope), \
             mock.patch("apps.ai.services.ai_service._call_api", **kw):
            return ca.author_checkin(self.user, signals=signals)


class ARefusalIsNotAMessageTests(Harness):
    """The exact production sequence."""

    def test_a_refused_call_produces_silence(self):
        text = self._author(side_effect=RealLLMCallDenied("proactive_ai_disabled"))
        self.assertEqual(text, "", "the cost gate refused, and WLJ spoke anyway")

    def test_the_next_action_directive_is_never_published_as_a_check_in(self):
        """"Next: Prayer Time. Do this now." — WLJ's words, not the model's."""
        with mock.patch("apps.core.execution.decision_authority"
                        ".current_action_directive",
                        return_value="Next: Prayer Time. Do this now.") as directive:
            text = self._author(side_effect=RealLLMCallDenied("nope"))
        self.assertEqual(text, "")
        directive.assert_not_called()

    def test_an_unavailable_model_produces_silence_too(self):
        self.assertEqual(self._author(side_effect=RuntimeError("provider down")), "")

    def test_an_empty_response_produces_silence(self):
        self.assertEqual(self._author(reply=""), "")
        self.assertEqual(self._author(reply=None), "")

    def test_a_real_authored_message_is_still_delivered(self):
        """Silence everywhere would be its own failure."""
        self.assertEqual(self._author(reply="Prayer Time is still open — 10 minutes?"),
                         "Prayer Time is still open — 10 minutes?")

    def test_the_model_may_still_decline_explicitly(self):
        self.assertEqual(self._author(reply=ca.SILENCE_TOKEN), "")


class EveryDecisionIsAuditedTests(Harness):
    """The investigation that could not be run: the proactive path wrote no audit row."""

    def _rows(self):
        from apps.ai.models import ToolCallLog
        return list(ToolCallLog.objects.filter(user=self.user, kind="checkin"))

    def test_an_authored_check_in_is_recorded(self):
        self._author(reply="something useful")
        row = self._rows()[-1]
        self.assertEqual(row.result_status, "authored")
        self.assertEqual(row.surface, "proactive")

    def test_a_refusal_is_recorded_as_a_refusal(self):
        self._author(side_effect=RealLLMCallDenied("proactive_ai_disabled"))
        self.assertEqual(self._rows()[-1].result_status, "refused")

    def test_a_decline_is_distinguishable_from_a_refusal(self):
        """Two different silences: the model said no, versus never being asked."""
        self._author(reply=ca.SILENCE_TOKEN)
        self.assertEqual(self._rows()[-1].result_status, "declined")

    def test_a_quiet_day_is_recorded_without_a_provider_call(self):
        with mock.patch("apps.ai.model_interface.service.ModelInterfaceService"
                        ".build_standing_context", return_value=QUIET), \
             mock.patch("apps.ai.services.ai_service._call_api") as call:
            ca.author_checkin(self.user)
        call.assert_not_called()
        self.assertEqual(self._rows()[-1].result_status, "quiet")

    def test_the_row_carries_the_envelope_evidence(self):
        self._author(reply="msg")
        digest = self._rows()[-1].result_digest
        self.assertEqual(digest["envelope"]["execution_buckets"]["overdue"], 1)
        self.assertEqual(digest["envelope"]["verdict_keys_present"], [])

    def test_the_row_never_carries_the_message_or_a_signal_value(self):
        import json
        self._author(reply="SECRET MESSAGE TEXT",
                     signals={"goal_pace": {"note": "SECRET SIGNAL VALUE"}})
        blob = json.dumps(self._rows()[-1].result_digest)
        self.assertNotIn("SECRET MESSAGE TEXT", blob)
        self.assertNotIn("SECRET SIGNAL VALUE", blob)
        self.assertIn("goal_pace", blob, "the signal's NAME is useful and safe")

    def test_auditing_never_breaks_the_check_in(self):
        with mock.patch("apps.ai.cos_services.audit.record_tool_call",
                        side_effect=RuntimeError("audit down")):
            self.assertEqual(self._author(reply="still fine"), "still fine")


class OneInterruptionAtATimeTests(TestCase):
    """Cooldowns were per TYPE. The person is not."""

    def setUp(self):
        self.user = User.objects.create_user(email="cool@contract.test", password="x")
        cache.clear()
        from apps.ai.proactive_checkins import get_proactive_service
        self.svc = get_proactive_service(self.user)

    def _send(self, check_in_type):
        return self.svc._create_proactive_message(
            content="A message long enough to ship.", quick_replies=[],
            message_type="nudge", metadata={"check_in_type": check_in_type})

    def test_two_producers_cannot_both_interrupt_in_the_same_window(self):
        self.assertIsNotNone(self._send("midday_alignment"))
        self.assertIsNone(self._send("health_trend"),
                          "a second producer interrupted within the cooldown")

    def test_the_same_producer_is_also_held_off(self):
        self.assertIsNotNone(self._send("midday_alignment"))
        self.assertIsNone(self._send("midday_alignment"))

    def test_the_claim_is_atomic_so_a_race_cannot_double_send(self):
        self.assertTrue(self.svc._claim_interruption_slot("a"))
        self.assertFalse(self.svc._claim_interruption_slot("b"))

    def test_a_clinical_prompt_keeps_its_existing_bypass(self):
        self.assertIsNotNone(self._send("midday_alignment"))
        self.assertIsNotNone(self._send("medication"),
                             "a medication reminder was suppressed as chatter")

    def test_the_cooldown_expires(self):
        from apps.ai import proactive_checkins as pc
        self.assertIsNotNone(self._send("midday_alignment"))
        cache.delete(f"wlj:proactive:interrupt:{self.user.pk}")   # simulate expiry
        self.assertIsNotNone(self._send("health_trend"))
        self.assertGreaterEqual(pc.INTERRUPTION_COOLDOWN_SECONDS, 600)

    def test_a_degraded_cache_never_silences_a_genuine_check_in(self):
        with mock.patch("apps.ai.proactive_checkins.cache.add",
                        side_effect=RuntimeError("redis down")):
            self.assertTrue(self.svc._claim_interruption_slot("midday_alignment"))

    def test_the_cooldown_is_content_blind_and_domain_agnostic(self):
        import inspect

        from apps.ai import proactive_checkins as pc
        src = inspect.getsource(pc.ProactiveCheckInService._claim_interruption_slot).lower()
        for banned in ("prayer", "weight", "hello", "greeting", "content"):
            self.assertNotIn(banned, src)


class NoCannedRuleWasAddedTests(TestCase):
    """The fix removes an authoring path; it does not add a filter."""

    def test_wlj_no_longer_authors_a_check_in_anywhere(self):
        import inspect
        src = inspect.getsource(ca.author_checkin)
        self.assertNotIn("current_action_directive", src,
                         "WLJ can still write the message when the model is absent")

    def test_no_phrase_filter_was_introduced(self):
        """Asserts on CODE, not on prose.

        The incident phrases legitimately appear in this module's comments — that is the
        record of why the code looks the way it does. What must not exist is a string
        LITERAL the code matches against. A first draft of this test grepped the raw
        source and failed on its own explanation, which is the same mistake as banning a
        capability's name to prove a verdict was removed.
        """
        import ast
        import pathlib
        tree = ast.parse(pathlib.Path(ca.__file__).read_text(encoding="utf-8"))
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    docstrings.add(doc)
        literals = [n.value.lower() for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and n.value not in docstrings]
        for banned in ("how can i assist", "prayer time", "hello!"):
            for literal in literals:
                self.assertNotIn(
                    banned, literal,
                    f"a canned-phrase filter was added instead of a structural fix: "
                    f"{banned!r}")
