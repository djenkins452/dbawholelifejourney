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
    answer_page_reference, is_page_reference, resolve_focused_object, resolve_page_focus,
)
from apps.ai.chatgpt_cos.lanes import route_message

User = get_user_model()


class FaithJourneyFocusTests(TestCase):
    """Isolated Faith fix: the PRODUCTION reading system is apps.faith.journey (JourneyDay,
    not the legacy UserReadingPlan). The focused-object resolver must narrate the journey day
    from its own fields. Touches only the Faith branch of resolve_focused_object."""

    def setUp(self):
        self.u = User.objects.create_user(email="fj@x.com", password="x")

    def _day(self):
        from apps.faith.journey.models import JourneyArc, JourneyDay, JourneyPath
        jp = JourneyPath.objects.create(slug="wwg", name="Walking With God Through Scripture",
                                        narrative_overview="", difficulty_default="")
        arc = JourneyArc.objects.create(journey_path=jp, slug="creation", name="Creation",
                                        order=1, opening_note="", closing_note="")
        return JourneyDay.objects.create(
            arc=arc, day_number=3, scripture_refs=["Genesis 1:1-5"],
            scripture_content={"translation": "WEB", "blocks": [
                {"ref": "Genesis 1:1", "text": "In the beginning God created the heavens and the earth."}]},
            context_before="God begins creation.", plain_english_simple="s",
            plain_english_standard="std", plain_english_deeper="d",
            key_insight="God is the origin of all things.",
            reflection_prompt="Where do you see God as your beginning?",
            application_action="Pause and pray.")

    def test_journey_review_day(self):
        self._day()
        f = resolve_focused_object(self.u, "/faith/journey/creation/day/3/", "faith")
        self.assertIn("Day 3", f["title"])
        self.assertIn("In the beginning God created", f["content"])   # scripture text
        self.assertIn("origin of all things", f["content"])           # key insight
        self.assertIn("your beginning", f["content"])                 # reflection
        self.assertEqual(f["kind"], "scripture reading")

    def test_journey_today(self):
        from unittest import mock as _mock
        day = self._day()
        with _mock.patch("apps.faith.journey.services.get_active_journey", return_value=object()), \
             _mock.patch("apps.faith.journey.services.get_current_day", return_value=day):
            f = resolve_focused_object(self.u, "/faith/journey/today/", "faith")
        self.assertIn("In the beginning", f["content"])

    def test_cross_user_no_active_journey_returns_none(self):
        # 'today' is user-scoped via the active journey; a user without one gets nothing.
        self.assertIsNone(resolve_focused_object(self.u, "/faith/journey/today/", "faith"))

    def test_legacy_reading_plan_still_resolves(self):
        from apps.faith.models import ReadingPlanDay, ReadingPlanTemplate, UserReadingPlan
        tpl = ReadingPlanTemplate.objects.create(
            title="Legacy Plan", description="d", category="", difficulty="", source="",
            source_abbreviation="", series="", duration_days=7)
        ReadingPlanDay.objects.create(plan=tpl, day_number=1, title="",
                                      scripture_references=["John 1:1"], scripture_content=[])
        lp = UserReadingPlan.objects.create(user=self.u, template=tpl, current_day=1)
        f = resolve_focused_object(self.u, f"/faith/reading-plans/progress/{lp.pk}/", "faith")
        self.assertIn("John 1:1", f["content"])
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


class ContractTests(TestCase):
    """CURRENT CONTEXT CONTRACT — the page DECLARES its focused object via focus_ref
    (<meta name=wlj-context>), and page_reference resolves the content SERVER-SIDE from the
    canonical model. No per-module code in Beth; user-scoped."""

    def setUp(self):
        self.u = User.objects.create_user(email="fo@x.com", password="x")

    def _goal(self, title="Launch WLJ", desc="Ship the app to production"):
        from datetime import date
        from apps.purpose.models import LifeGoal
        return LifeGoal.objects.create(user=self.u, title=title, description=desc,
                                       target_date=date(2027, 1, 1))

    def test_resolve_page_focus_uses_declared_ref(self):
        g = self._goal()
        pc = {"module": "purpose", "url": f"/purpose/goals/{g.pk}/",
              "focus_ref": f"purpose.lifegoal:{g.pk}", "page_content": {}}
        focus = resolve_page_focus(pc, user=self.u)
        self.assertIn("Launch WLJ", focus["content"])
        self.assertIn("Ship the app to production", focus["content"])

    def test_other_users_object_not_leaked(self):
        g = self._goal()
        other = User.objects.create_user(email="other-fo@x.com", password="x")
        pc = {"module": "purpose", "focus_ref": f"purpose.lifegoal:{g.pk}", "page_content": {}}
        self.assertIsNone(resolve_page_focus(pc, user=other))

    def test_explain_this_via_contract_hands_content_to_model(self):
        # The exact production case: client sent NO content, only the declared reference.
        g = self._goal(title="Launch WLJ", desc="Ship the app to production")
        pc = {"module": "purpose", "url": f"/purpose/goals/{g.pk}/",
              "focus_ref": f"purpose.lifegoal:{g.pk}", "page_content": {}}
        with mock.patch(_CALL_API, return_value="This goal is about shipping WLJ.") as m:
            out = answer_page_reference(self.u, "Explain this.", None, pc)
        self.assertEqual(out["lane"], "page_reference")
        self.assertIn("shipping WLJ", out["answer"])
        self.assertIn("Ship the app to production", m.call_args[0][0])   # goal content handed to model

    def test_journal_entry_via_contract(self):
        from apps.journal.models import JournalEntry
        e = JournalEntry.objects.create(user=self.u, title="Gratitude", body="Today I felt grateful.")
        pc = {"module": "journal", "focus_ref": f"journal.journalentry:{e.pk}", "page_content": {}}
        focus = resolve_page_focus(pc, user=self.u)
        self.assertIn("grateful", focus["content"])

    def test_new_page_needs_no_beth_code(self):
        # Any UserOwnedModel with a declared ref is resolvable — no page_reference change.
        from apps.journal.models import JournalEntry
        e = JournalEntry.objects.create(user=self.u, title="X", body="body text here")
        pc = {"focus_ref": f"journal.journalentry:{e.pk}"}
        focus = resolve_page_focus(pc, user=self.u)
        self.assertEqual(focus["title"], "X")


class DegradationTests(TestCase):
    """When the focused object IS resolved but the LLM is unavailable (the worker had no
    OpenAI client — is_available False), page_reference must DEGRADE PAGE-AWARE, never
    return None and fall into the contextless general lane."""

    def setUp(self):
        self.u = User.objects.create_user(email="deg@x.com", password="x")

    def _goal_pc(self, title="France 2027 Family 18K Mission"):
        from datetime import date
        from apps.purpose.models import LifeGoal
        g = LifeGoal.objects.create(user=self.u, title=title, description="Save and train.",
                                    target_date=date(2027, 6, 1))
        return {"module": "purpose", "url": f"/purpose/goals/{g.pk}/",
                "focus_ref": f"purpose.lifegoal:{g.pk}", "page_title": title, "page_content": {}}

    def test_llm_none_degrades_page_aware_not_none(self):
        pc = self._goal_pc()
        with mock.patch(_CALL_API, return_value=None):     # LLM unavailable (worker)
            out = answer_page_reference(self.u, "Explain this.", None, pc)
        self.assertIsNotNone(out)                          # must NOT fall to general lane
        self.assertEqual(out["lane"], "page_reference")
        self.assertTrue(out.get("degraded"))
        self.assertIn("France 2027 Family 18K Mission", out["answer"])   # context preserved
        self.assertIn("temporarily unavailable", out["answer"].lower())

    def test_llm_exception_also_degrades_page_aware(self):
        pc = self._goal_pc()
        with mock.patch(_CALL_API, side_effect=RuntimeError("boom")):
            out = answer_page_reference(self.u, "Explain this.", None, pc)
        self.assertEqual(out["lane"], "page_reference")
        self.assertTrue(out.get("degraded"))
        self.assertIn("France 2027", out["answer"])

    def test_route_message_returns_page_reference_when_llm_down(self):
        # End-to-end through the router: LLM down -> still page_reference, NOT general lane.
        pc = self._goal_pc()
        with mock.patch(_CALL_API, return_value=None):
            routed = route_message(self.u, "Explain this.", None, page_context=pc)
        self.assertIsNotNone(routed)
        self.assertEqual(routed["lane"], "page_reference")
        self.assertNotIn("external knowledge service", routed["answer"].lower())
