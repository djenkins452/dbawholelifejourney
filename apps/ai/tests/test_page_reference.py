# ==============================================================================
# File: apps/ai/tests/test_page_reference.py
# Description: PAGE-AWARE CONTEXTUAL CONVERSATION. "Summarize this scripture" on the Faith
#   reading page must bind "this" to the entity in focus — not route to the sandboxed
#   general lane ("I can't see the content") or abandon to a sleep recommendation.
#   Generalizes across modules (scripture / journal / goal / task).
# ==============================================================================
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.chatgpt_cos.page_reference import (
    answer_page_reference, is_page_reference, resolve_page_focus,
)
from apps.ai.chatgpt_cos.lanes import route_message

User = get_user_model()
_CALL_API = "apps.ai.services.ai_service._call_api"

_FAITH_PC = {"module": "faith", "page_title": "Isaiah 6:1-8, Isaiah 53:1-12",
             "url": "/faith/journey/today",
             "page_content": {"type": "scripture_reading",
                              "scripture_text": "In the year that King Uzziah died I saw the Lord..."}}


class IsPageReferenceTests(TestCase):
    def test_recognizes_page_actions_and_short_deixis(self):
        for m in ("Summarize this scripture.", "explain this", "what do you think?",
                  "should I still do this?", "what does this mean", "walk me through it"):
            self.assertTrue(is_page_reference(m), m)

    def test_ignores_long_general_questions_with_this(self):
        self.assertFalse(is_page_reference(
            "what is the capital of the country that hosted the olympics this year"))
        self.assertFalse(is_page_reference("how are my goals looking overall right now"))


class ResolvePageFocusTests(TestCase):
    def test_faith_scripture(self):
        f = resolve_page_focus(_FAITH_PC)
        self.assertEqual(f["module"], "faith")
        self.assertIn("Uzziah", f["content"])

    def test_generalizes_across_modules(self):
        self.assertIn("felt grateful", resolve_page_focus(
            {"module": "journal", "page_content": {"body": "Today I felt grateful."}})["content"])
        self.assertIn("Goal Weight 279.9", resolve_page_focus(
            {"module": "purpose", "page_title": "France 2027",
             "page_content": {"milestones": ["Goal Weight 279.9", "Foundation Phase"]}})["content"])
        self.assertIn("Finish the report", resolve_page_focus(
            {"module": "tasks", "page_content": {"description": "Finish the report"}})["content"])

    def test_none_when_no_focus(self):
        self.assertIsNone(resolve_page_focus({}))
        self.assertIsNone(resolve_page_focus({"module": "faith", "page_content": {}}))


class AnswerPageReferenceTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user(email="pr@x.com", password="x")

    def test_grounded_answer_when_content_present(self):
        with mock.patch(_CALL_API, return_value="Isaiah sees the Lord and is commissioned.") as m:
            out = answer_page_reference(self.u, "Summarize this scripture.", None, _FAITH_PC)
        self.assertEqual(out["lane"], "page_reference")
        self.assertIn("Isaiah sees the Lord", out["answer"])
        # the focused scripture content was handed to the model
        self.assertIn("Uzziah", m.call_args[0][0])

    def test_acknowledges_page_when_content_missing_never_abandons(self):
        pc = {"module": "faith", "page_title": "Today's Reading", "page_content": {}}
        with mock.patch(_CALL_API, side_effect=AssertionError("must not call LLM without content")):
            out = answer_page_reference(self.u, "summarize this", None, pc)
        self.assertEqual(out["lane"], "page_reference")
        self.assertIn("paste it", out["answer"].lower())
        self.assertIn("today's reading", out["answer"].lower())

    def test_declines_non_page_reference(self):
        self.assertIsNone(answer_page_reference(self.u, "who was Abraham Lincoln?", None, _FAITH_PC))

    def test_declines_when_no_page_context(self):
        self.assertIsNone(answer_page_reference(self.u, "summarize this", None, None))


class RoutingTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user(email="prr@x.com", password="x")

    def test_summarize_this_scripture_routes_to_page_reference_not_general(self):
        with mock.patch(_CALL_API, return_value="A summary of Isaiah's vision and call."):
            out = route_message(self.u, "Summarize this scripture.", None, page_context=_FAITH_PC)
        self.assertIsNotNone(out)
        self.assertEqual(out["lane"], "page_reference")
        self.assertIn("Isaiah", out["answer"])

    def test_without_page_context_does_not_hijack(self):
        # No page context → page lane never runs; normal routing proceeds.
        with mock.patch(_CALL_API, return_value="general answer"):
            out = route_message(self.u, "Summarize this scripture.", None)
        self.assertNotEqual((out or {}).get("lane"), "page_reference")
