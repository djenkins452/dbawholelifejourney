# ==============================================================================
# File: apps/core/tests/test_interview_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: M4 — Getting to Know You lifecycle contract
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-19
# ==============================================================================
"""Getting to Know You contract (M4).

The governing split, asserted at consumer boundaries:

    WLJ owns what is KNOWN and what the user RULED OUT.
    The model owns what is worth asking.

The failure this file exists to prevent is the one the frozen design names: the interview
decaying into a questionnaire wearing a chat costume — WLJ ordering topics, scoring
coverage, or treating an empty area as a gap to fill.
"""

import ast
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.ai.cos_services import interview as iv
from apps.core.personal_knowledge import service as pk
from apps.core.personal_knowledge.models import (
    PersonalKnowledgeFact, Provenance, ReviewState, Sensitivity,
)

User = get_user_model()
REPO = Path(__file__).resolve().parents[3]


class InterviewHarness(TestCase):
    def setUp(self):
        from apps.ai.models import AssistantConversation
        from apps.users.models import TermsAcceptance
        from django.conf import settings as dj
        self.user = User.objects.create_user(
            email="iv@contract.test", password="x", first_name="IV")
        self.user.has_completed_onboarding = True
        self.user.save()
        TermsAcceptance.objects.get_or_create(
            user=self.user, defaults={"terms_version": dj.WLJ_SETTINGS["TERMS_VERSION"]})
        prefs = self.user.preferences
        prefs.has_completed_onboarding = True
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.personal_assistant_enabled = True
        prefs.personal_assistant_consent = True
        prefs.use_model_interface = True
        prefs.use_model_interface_writes = True
        prefs.ai_coaching_style = "texas_rancher"
        prefs.save()
        self.user = User.objects.get(pk=self.user.pk)
        self.conv = AssistantConversation.get_or_create_active(self.user)
        self.client.force_login(self.user)

    def _fresh(self):
        return User.objects.get(pk=self.user.pk)

    def _prompt(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        svc = ModelInterfaceService(self._fresh())
        return svc._system_prompt(
            svc.build_standing_context(conversation=self.conv, writes_enabled=True))

    def _ctx(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        svc = ModelInterfaceService(self._fresh())
        return svc.build_standing_context(conversation=self.conv, writes_enabled=True)


class StartTests(InterviewHarness):
    def test_opening_the_interview_creates_no_knowledge(self):
        iv.start_or_resume(self.user, self.conv)
        self.assertEqual(pk.active_facts(self.user).count(), 0,
                         "merely opening the interview invented knowledge")

    def test_interview_state_is_absent_until_a_session_exists(self):
        self.assertNotIn("interview", self._ctx())
        self.assertNotIn("GETTING TO KNOW", self._prompt())

    def test_state_appears_once_started(self):
        iv.start_or_resume(self.user, self.conv)
        self.assertIn("interview", self._ctx())
        self.assertIn("GETTING TO KNOW", self._prompt())

    def test_starting_hands_the_user_into_the_conversation(self):
        """"Let's talk" must open the conversation, not return to a page that looks
        like nothing happened."""
        r = self.client.post(reverse("users:get_to_know_me_start"), follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.redirect_chain[-1][0],
                         reverse("users:get_to_know_me") + "?started=1")
        html = r.content.decode()
        self.assertIn("ap-chat-input", html, "the surface never reaches the chat input")
        self.assertIn("get to know me", html)

    def test_the_handoff_uses_no_inline_event_handlers(self):
        """CSP: nonce-based policy silently drops inline handlers."""
        import re
        html = self.client.post(reverse("users:get_to_know_me_start"),
                                follow=True).content.decode()
        page = html[html.index('class="content-container gtky"'):]
        self.assertIsNone(re.search(r"on(click|change|submit|load)\s*=", page))

    def test_the_experience_is_never_mandatory(self):
        """Nothing gates the product on the interview."""
        r = self.client.get(reverse("users:about_me"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(pk.active_facts(self.user).count(), 0)


class DeliberateTeachingTests(InterviewHarness):
    def setUp(self):
        super().setUp()
        self.session = iv.start_or_resume(self.user, self.conv)

    def test_taught_facts_persist_through_the_canonical_service(self):
        recorded, rejected = iv.record_facts(self.session, [
            {"statement": "Heather is my wife.", "topic": "family", "subject": "Heather"},
            {"statement": "We have been married since 1997.", "topic": "family"},
        ])
        self.assertEqual(len(recorded), 2)
        self.assertEqual(rejected, [])
        for fact in recorded:
            self.assertEqual(fact.provenance, Provenance.INTERVIEW)
            self.assertEqual(fact.review_state, ReviewState.USER_AUTHORED)

    def test_taught_facts_reach_the_model_immediately(self):
        iv.record_facts(self.session,
                        [{"statement": "MARKER-IV I ride motorcycles.", "topic": "interests"}])
        self.assertIn("MARKER-IV", self._prompt())

    def test_about_me_reflects_taught_knowledge(self):
        iv.record_facts(self.session,
                        [{"statement": "MARKER-AM Heather is my wife.", "topic": "family"}])
        html = self.client.get(reverse("users:about_me")).content.decode()
        self.assertIn("1 thing I know", html)
        topic_html = self.client.get(
            reverse("users:about_me_topic", kwargs={"topic": "family"})).content.decode()
        self.assertIn("MARKER-AM", topic_html)

    def test_sensitive_material_is_stored_but_kept_out_of_context(self):
        iv.record_facts(self.session, [
            {"statement": "MARKER-SENS a private health matter.",
             "topic": "health_context", "sensitive": True}])
        self.assertEqual(pk.active_facts(self.user).count(), 1)
        self.assertNotIn("MARKER-SENS", self._prompt(),
                         "sensitive material entered routine standing context")

    def test_an_empty_statement_is_ignored_not_stored(self):
        recorded, _ = iv.record_facts(self.session, [{"statement": "   "}])
        self.assertEqual(recorded, [])

    def test_recording_is_bounded_per_turn(self):
        many = [{"statement": f"Fact number {i} about my life.", "topic": "other"}
                for i in range(30)]
        recorded, _ = iv.record_facts(self.session, many)
        self.assertLessEqual(len(recorded), iv.MAX_FACTS_PER_TURN)


class BoundaryControlTests(InterviewHarness):
    def setUp(self):
        super().setUp()
        self.session = iv.start_or_resume(self.user, self.conv)

    def test_declined_area_is_recorded_and_never_offered(self):
        iv.set_topic_state(self.session, "faith", "declined")
        block = iv.read(self.user, self.conv)
        self.assertIn("faith", block["declined_areas"])
        prompt = self._prompt()
        self.assertIn("OFF LIMITS", prompt)
        self.assertIn("faith", prompt)

    def test_parked_and_satisfied_are_distinct_from_declined(self):
        iv.set_topic_state(self.session, "goals", "parked")
        iv.set_topic_state(self.session, "family", "satisfied")
        block = iv.read(self.user, self.conv)
        states = {a["area"]: a["user_state"] for a in block["areas"]}
        self.assertEqual(states["goals"], "parked")
        self.assertEqual(states["family"], "satisfied")
        self.assertEqual(block["declined_areas"], [])

    def test_an_unknown_state_is_rejected(self):
        self.assertFalse(iv.set_topic_state(self.session, "family", "complete"))
        self.assertFalse(iv.set_topic_state(self.session, "family", ""))

    def test_emergent_areas_need_no_deploy(self):
        iv.set_topic_state(self.session, "volunteer_fire_department", "discussed")
        iv.record_facts(self.session, [
            {"statement": "I have volunteered with the fire department for 20 years.",
             "topic": "volunteer_fire_department"}])
        areas = {a["area"]: a for a in iv.read(self.user, self.conv)["areas"]}
        self.assertIn("volunteer_fire_department", areas)
        self.assertEqual(areas["volunteer_fire_department"]["things_known"], 1)


class ResumabilityTests(InterviewHarness):
    def test_stop_then_resume_keeps_state_and_knowledge(self):
        session = iv.start_or_resume(self.user, self.conv)
        iv.record_facts(session, [{"statement": "Heather is my wife.", "topic": "family"}])
        iv.set_topic_state(session, "faith", "declined")
        iv.pause(self.user, self.conv)
        self.assertIsNone(iv.active_session(self.user, self.conv))

        resumed = iv.start_or_resume(self.user, self.conv)
        self.assertEqual(resumed.id, session.id, "resuming started a NEW session")
        self.assertIn("faith", resumed.declined_topics(),
                      "a declined area was forgotten across a stop")
        self.assertEqual(pk.active_facts(self.user).count(), 1)

    def test_stopping_does_not_delete_what_was_taught(self):
        session = iv.start_or_resume(self.user, self.conv)
        iv.record_facts(session, [{"statement": "I ride motorcycles.", "topic": "interests"}])
        iv.pause(self.user, self.conv)
        self.assertEqual(pk.active_facts(self.user).count(), 1)

    def test_stop_endpoint_pauses_without_losing_knowledge(self):
        session = iv.start_or_resume(self.user, self.conv)
        iv.record_facts(session, [{"statement": "Heather is my wife.", "topic": "family"}])
        self.client.post(reverse("users:get_to_know_me_stop"))
        self.assertIsNone(iv.active_session(self._fresh(), self.conv))
        self.assertEqual(pk.active_facts(self.user).count(), 1)


class NotAQuestionnaireTests(InterviewHarness):
    """WLJ reports an inventory. It never scores, orders, or completes."""

    def test_interview_state_exposes_no_agenda_or_score(self):
        iv.start_or_resume(self.user, self.conv)
        block = iv.read(self.user, self.conv)
        for banned in ("next_area", "next_topic", "progress", "percent",
                       "complete", "completion", "score", "required", "remaining"):
            self.assertNotIn(banned, block,
                             f"interview state exposes {banned!r} — that is an agenda")
        for area in block["areas"]:
            self.assertNotIn("priority", area)
            self.assertNotIn("order", area)

    def test_the_service_defines_no_next_question_engine(self):
        src = (REPO / "apps/ai/cos_services/interview.py").read_text(encoding="utf-8")
        names = {n.name.lower() for n in ast.walk(ast.parse(src))
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for banned in ("next_question", "choose_topic", "select_topic", "score",
                       "rank", "prioriti"):
            offenders = sorted(n for n in names if banned in n)
            self.assertEqual(offenders, [],
                             f"{offenders} would make WLJ decide what to ask")

    def test_the_surface_shows_no_progress_or_completion(self):
        html = self.client.get(reverse("users:get_to_know_me")).content.decode()
        body = html[html.index('class="content-container gtky"'):html.index("<style")]
        for banned in ("progress", "% complete", "step 1 of", "required",
                       "incomplete", "you still need"):
            self.assertNotIn(banned, body.lower())


class PersonaTests(InterviewHarness):
    def test_the_existing_persona_projection_shapes_the_interview(self):
        from apps.ai.models import CoachingStyle
        CoachingStyle.objects.get_or_create(
            key="texas_rancher",
            defaults=dict(name="Texas Rancher", description="Plainspoken.",
                          prompt_instructions="Talk like someone who has worked the land.",
                          is_active=True))
        iv.start_or_resume(self.user, self.conv)
        prompt = self._prompt()
        self.assertIn("worked the land", prompt,
                      "the interview does not carry the user's persona voice")
        self.assertIn("GETTING TO KNOW", prompt)

    def test_no_second_persona_system_exists(self):
        src = (REPO / "apps/ai/cos_services/interview.py").read_text(encoding="utf-8")
        for banned in ("prompt_instructions", "CoachingStyle", "voice_attributes",
                       "persona_instructions"):
            self.assertNotIn(banned, src,
                             "the interview must reuse the certified persona projection")


class GatingTests(InterviewHarness):
    """M6 natural learning must NOT arrive because M4 exists."""

    def _dispatch(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        svc = ModelInterfaceService(self._fresh())
        return svc._make_dispatch(
            turn_id="t", surface="test", tools_called=[],
            conversation_id=self.conv.id, conversation=self.conv)

    def test_recording_outside_an_interview_is_a_no_op(self):
        out = self._dispatch()(
            "record_interview_knowledge",
            {"facts": [{"statement": "Sneaky background learning.", "topic": "other"}]})
        self.assertEqual(out.get("status"), "not_in_interview")
        self.assertEqual(pk.active_facts(self.user).count(), 0,
                         "ordinary conversation persisted Personal Knowledge")

    def test_recording_inside_an_interview_goes_through_the_same_dispatch(self):
        iv.start_or_resume(self.user, self.conv)
        out = self._dispatch()("record_interview_knowledge", {
            "facts": [{"statement": "MARKER-DISPATCH Heather is my wife.",
                       "topic": "family"}],
            "area_outcome": {"area": "faith", "state": "declined"},
        })
        self.assertEqual(out.get("status"), "recorded")
        self.assertEqual(len(out.get("remembered") or []), 1)
        self.assertEqual(out.get("not_remembered"), [])
        self.assertTrue(out.get("area_outcome_applied"))
        self.assertIn("MARKER-DISPATCH", self._prompt())
        self.assertIn("faith", iv.read(self._fresh(), self.conv)["declined_areas"])

    def test_the_write_is_audited(self):
        from apps.ai.models import ToolCallLog
        iv.start_or_resume(self.user, self.conv)
        self._dispatch()("record_interview_knowledge", {
            "facts": [{"statement": "Heather is my wife.", "topic": "family"}]})
        self.assertTrue(
            ToolCallLog.objects.filter(
                user=self.user, tool_name="record_interview_knowledge").exists(),
            "a state-changing call left no audit row")

    def test_no_background_or_scheduled_writer_exists(self):
        src = (REPO / "apps/ai/cos_services/interview.py").read_text(encoding="utf-8")
        for marker in ("shared_task", "celery", "safe_enqueue", ".delay("):
            self.assertNotIn(marker, src,
                             "the interview must have no background writer")

    def test_every_personal_knowledge_writer_is_user_deliberate(self):
        """The M6 guard. Personal Knowledge may only be written by a path the user
        deliberately initiated. If a new caller appears here, it must be a deliberate
        surface — not background extraction."""
        import subprocess
        out = subprocess.run(
            ["grep", "-rn", "--include=*.py", "add_fact(", "apps/"],
            cwd=REPO, capture_output=True, text=True).stdout
        callers = {
            line.split(":")[0] for line in out.splitlines()
            if "/tests/" not in line and "def add_fact" not in line
        }
        self.assertEqual(callers, {
            "apps/core/personal_knowledge/service.py",   # correct_fact, internal
            "apps/core/personal_knowledge/legacy_import.py",  # one-time, user-invoked
            "apps/ai/cos_services/interview.py",         # session-gated teaching
            "apps/users/about_me_views.py",              # the user typing it
        }, "a new Personal Knowledge writer appeared — is it user-deliberate?")

    def test_the_legacy_background_extractor_still_does_not_touch_pk(self):
        """Post-response extraction predates M4 and writes the OLD store. M4 must not
        have quietly redirected it into Personal Knowledge."""
        src = (REPO / "apps/core/ai_memory/life_fact_extractor.py").read_text(
            encoding="utf-8")
        self.assertNotIn("personal_knowledge", src)
        self.assertNotIn("PersonalKnowledgeFact", src)

    def test_interview_state_is_not_a_biographical_store(self):
        """Contract 19 — orchestration state must never become a second fact store."""
        from apps.ai.models import InterviewSession
        fields = {f.name for f in InterviewSession._meta.get_fields()}
        for banned in ("statement", "fact_text", "facts", "knowledge", "notes", "summary"):
            self.assertNotIn(banned, fields,
                             f"{banned!r} would make interview state a second PK store")


class HonestFailureTests(InterviewHarness):
    def test_a_rejected_fact_is_reported_not_silently_dropped(self):
        session = iv.start_or_resume(self.user, self.conv)
        from unittest import mock
        with mock.patch("apps.core.personal_knowledge.service.add_fact",
                        side_effect=ValueError("domain-owned")):
            recorded, rejected = iv.record_facts(
                session, [{"statement": "Something durable.", "topic": "other"}])
        self.assertEqual(recorded, [])
        self.assertEqual(len(rejected), 1,
                         "a failed write was silently swallowed — the CoS could then "
                         "claim it remembered something it did not")

    def test_persistence_failure_does_not_break_the_conversation(self):
        session = iv.start_or_resume(self.user, self.conv)
        from unittest import mock
        with mock.patch("apps.core.personal_knowledge.service.add_fact",
                        side_effect=RuntimeError("db down")):
            recorded, rejected = iv.record_facts(
                session, [{"statement": "Something durable.", "topic": "other"}])
        self.assertEqual(recorded, [])
        self.assertTrue(rejected)
        self.assertIsNotNone(iv.active_session(self.user, self.conv),
                             "a failed write ended the session")


class AboutMeAuthorityTests(InterviewHarness):
    def test_correcting_after_the_interview_updates_model_truth(self):
        session = iv.start_or_resume(self.user, self.conv)
        recorded, _ = iv.record_facts(
            session, [{"statement": "MARKER-OLD married since 1996.", "topic": "family"}])
        fact = recorded[0]
        self.client.post(reverse("users:about_me_fact_action",
                                 kwargs={"pk_id": fact.id, "action": "correct"}),
                         {"statement": "MARKER-NEW married since 1997."})
        prompt = self._prompt()
        self.assertNotIn("MARKER-OLD", prompt)
        self.assertIn("MARKER-NEW", prompt)

    def test_deleting_after_the_interview_removes_it_from_model_truth(self):
        session = iv.start_or_resume(self.user, self.conv)
        recorded, _ = iv.record_facts(
            session, [{"statement": "MARKER-DEL forget this.", "topic": "family"}])
        self.client.post(reverse("users:about_me_fact_action",
                                 kwargs={"pk_id": recorded[0].id, "action": "delete"}))
        self.assertNotIn("MARKER-DEL", self._prompt())


class CostAndSafetyTests(SimpleTestCase):
    def test_one_tool_carries_both_facts_and_state(self):
        """No second provider round-trip per interview turn (Contract 15)."""
        from apps.ai.model_interface.constitution import all_tools
        names = [(t.get("function") or {}).get("name")
                 for t in all_tools(writes_enabled=True)]
        self.assertIn("record_interview_knowledge", names)
        self.assertEqual(
            len([n for n in names if n and "interview" in n]), 1,
            "more than one interview tool means an extra extraction call per turn")
        tool = next(t["function"] for t in all_tools(writes_enabled=True)
                    if (t.get("function") or {}).get("name") == "record_interview_knowledge")
        props = tool["parameters"]["properties"]
        self.assertIn("facts", props)
        self.assertIn("area_outcome", props)

    def test_the_write_is_declared_on_the_certified_write_surface(self):
        from apps.core.tests.test_write_surface_safety_contract import WRITE_SURFACE
        self.assertIn("record_interview_knowledge", WRITE_SURFACE)
        spec = WRITE_SURFACE["record_interview_knowledge"]
        self.assertTrue((spec.get("exemption") or "").strip(),
                        "a confirmation exemption must state its governing reason")

    def test_the_tool_forbids_recording_interpretation(self):
        from apps.ai.model_interface.constitution import all_tools
        tool = next(t["function"] for t in all_tools(writes_enabled=True)
                    if (t.get("function") or {}).get("name") == "record_interview_knowledge")
        desc = tool["description"].lower()
        self.assertIn("never record an interpretation", desc)
        self.assertIn("store what they said", desc)

class DiscoverabilityTests(TestCase):
    """The surface is useless if nobody can reach it."""

    fixtures = ["apps/help/fixtures/teaching_destinations.json",
                "apps/help/fixtures/help_topics.json"]

    def test_the_cos_can_take_the_user_to_both_surfaces(self):
        from apps.core.action_router import resolve_route
        cases = {
            "about me": "/user/about-me/",
            "what do you know about me": "/user/about-me/",
            "get to know me": "/user/about-me/get-to-know-me/",
            "getting to know you": "/user/about-me/get-to-know-me/",
        }
        for text, url in cases.items():
            with self.subTest(text=text):
                self.assertEqual(resolve_route(text=text).destination_url, url)

    def test_both_surfaces_declare_their_help_context(self):
        from apps.help.models import HelpTopic
        from apps.users.about_me_views import AboutMeView, GetToKnowMeView
        for view, context_id in ((AboutMeView, "ABOUT_ME"),
                                 (GetToKnowMeView, "GET_TO_KNOW_ME")):
            with self.subTest(view=view.__name__):
                self.assertEqual(view.help_context_id, context_id)
                self.assertTrue(HelpTopic.objects.filter(context_id=context_id).exists(),
                                f"{context_id} has no help topic to show")
