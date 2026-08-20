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


class ProviderCopyGateTests(SimpleTestCase):
    """Contracts §16c — the release-copy gate is cleared by NOT making the claim.

    WLJ must not put a provider's account configuration into customer-facing copy: that
    copy would silently become false if the provider or the account changed, and it would
    undermine provider-agnosticism (Constitution I.8). If a surface ever wants to say
    "never used for training" or "zero data retention", the OpenAI organisation settings
    must be verified first — so this test is the thing that re-arms the gate.
    """

    SURFACES = [
        "templates/users/get_to_know_me.html",
        "templates/users/about_me.html",
        "templates/users/about_me_topic.html",
        "templates/users/about_me_review.html",
    ]
    CLAIMS = [
        r"never used (for|to) train",
        r"not used (for|to) train",
        r"zero[- ]data[- ]retention",
        r"\bZDR\b",
        r"(is|are) not retained",
        r"deleted (immediately|after)",
        r"\bOpenAI\b",
        r"\bChatGPT\b",
    ]

    def test_no_pk_surface_claims_provider_training_or_retention_behaviour(self):
        import re
        for rel in self.SURFACES:
            path = REPO / rel
            if not path.exists():
                continue
            body = re.sub(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", "",
                          path.read_text(encoding="utf-8"), flags=re.S)
            body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
            for claim in self.CLAIMS:
                with self.subTest(surface=rel, claim=claim):
                    self.assertIsNone(
                        re.search(claim, body, re.I),
                        f"{rel} makes a provider claim ({claim!r}). Verify the OpenAI "
                        f"organisation settings first — see contracts doc §16c.")


class CostAttributionTests(InterviewHarness):
    """M5 §8 — interview cost must be separable from ordinary chat.

    Without this an interview turn is billed as `interactive_chat` and the question
    "what does Getting to Know You actually cost?" has no answer.
    """

    def _run_turn(self):
        """Run one generate() with the provider mocked — no real spend."""
        from unittest import mock
        from apps.ai.llm_accounting import current_source
        from apps.ai.model_interface.service import ModelInterfaceService

        seen = {}
        svc = ModelInterfaceService(self._fresh())

        def _fake_call(*args, **kwargs):
            # captured INSIDE the provider call, which is where the seam reads it
            seen["source"] = current_source()
            return "ok"

        with mock.patch.object(svc.ai, "_call_api_with_tools", side_effect=_fake_call):
            svc.generate(self.conv, "hello", surface="test")
        return seen.get("source")

    def test_an_interview_turn_is_attributed_to_its_own_source(self):
        from apps.ai.llm_accounting import SOURCE_GETTING_TO_KNOW_YOU
        iv.start_or_resume(self.user, self.conv)
        self.assertEqual(self._run_turn(), SOURCE_GETTING_TO_KNOW_YOU)

    def test_an_ordinary_turn_is_not_attributed_to_the_interview(self):
        from apps.ai.llm_accounting import SOURCE_INTERACTIVE_CHAT
        self.assertEqual(self._run_turn(), SOURCE_INTERACTIVE_CHAT)

    def test_the_source_does_not_leak_into_the_next_turn(self):
        """A worker process serves many users; a leaked contextvar would misattribute
        every later turn."""
        from apps.ai.llm_accounting import SOURCE_INTERACTIVE_CHAT, current_source
        iv.start_or_resume(self.user, self.conv)
        self._run_turn()
        self.assertIsNone(current_source(), "accounting source leaked past the turn")
        iv.pause(self.user, self.conv)
        self.assertEqual(self._run_turn(), SOURCE_INTERACTIVE_CHAT)

    def test_an_accounting_probe_failure_never_breaks_the_turn(self):
        from unittest import mock
        with mock.patch("apps.ai.cos_services.interview.active_session",
                        side_effect=RuntimeError("db down")):
            self.assertIsNotNone(self._run_turn())


class DegradedBehaviourTests(InterviewHarness):
    """M5 §9 — what happens when things go wrong."""

    def test_a_provider_failure_leaves_the_session_recoverable(self):
        from unittest import mock
        from apps.ai.model_interface.service import ModelInterfaceService
        session = iv.start_or_resume(self.user, self.conv)
        iv.record_facts(session, [{"statement": "Heather is my wife.", "topic": "family"}])

        svc = ModelInterfaceService(self._fresh())
        with mock.patch.object(svc.ai, "_call_api_with_tools",
                               side_effect=RuntimeError("provider down")):
            with self.assertRaises(RuntimeError):
                svc.generate(self.conv, "tell me more", surface="test")

        self.assertIsNotNone(iv.active_session(self._fresh(), self.conv),
                             "a provider failure ended the interview")
        self.assertEqual(pk.active_facts(self.user).count(), 1,
                         "a provider failure lost knowledge already taught")

    def test_a_partial_write_is_reported_honestly_not_rounded_up(self):
        """The class §9 names: the CoS must not say 'I'll remember that' for a fact
        that was never persisted."""
        from unittest import mock
        iv.start_or_resume(self.user, self.conv)
        real = pk.add_fact
        calls = {"n": 0}

        def _flaky(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("write failed")
            return real(*args, **kwargs)

        with mock.patch("apps.core.personal_knowledge.service.add_fact",
                        side_effect=_flaky):
            out = self._dispatch()("record_interview_knowledge", {"facts": [
                {"statement": "Heather is my wife.", "topic": "family"},
                {"statement": "We married in 1997.", "topic": "family"},
            ]})
        self.assertEqual(len(out["remembered"]), 1)
        self.assertEqual(len(out["not_remembered"]), 1)
        self.assertIn("could not be kept", out["message"])
        self.assertIn("do not say they were", out["message"])

    def test_the_constitution_binds_memory_claims_to_verified_writes(self):
        from apps.ai.model_interface.constitution import CONSTITUTION
        self.assertIn("THIS COVERS MEMORY TOO", CONSTITUTION)
        self.assertIn("`not_remembered`", CONSTITUTION)

    def _dispatch(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        svc = ModelInterfaceService(self._fresh())
        return svc._make_dispatch(
            turn_id="t", surface="test", tools_called=[],
            conversation_id=self.conv.id, conversation=self.conv)

    def test_an_interrupted_session_resumes_rather_than_restarting(self):
        """Session interruption: the row survives; nothing replays from scratch."""
        session = iv.start_or_resume(self.user, self.conv)
        iv.set_topic_state(session, "faith", "declined")
        iv.record_facts(session, [{"statement": "I ride motorcycles.", "topic": "interests"}])
        # simulate an interrupted process: no pause() ever ran
        resumed = iv.start_or_resume(self._fresh(), self.conv)
        self.assertEqual(resumed.id, session.id)
        self.assertIn("faith", resumed.declined_topics())
        self.assertEqual(pk.active_facts(self.user).count(), 1)


class ProjectionDriftTests(InterviewHarness):
    """M5 §5 — certify the whole customer-visible loop, priming the cache first.

    M2 proved this class hides at consumer boundaries: a read POPULATES the projection
    cache, so a later write is only visible if invalidation actually fires. Tests that
    write before ever reading cannot see the bug.
    """

    def test_teaching_after_a_read_is_not_served_stale(self):
        session = iv.start_or_resume(self.user, self.conv)
        self._prompt()  # priming read — populates the projection cache
        iv.record_facts(session,
                        [{"statement": "MARKER-DRIFT Heather is my wife.", "topic": "family"}])
        self.assertIn("MARKER-DRIFT", self._prompt(),
                      "a primed cache hid knowledge taught seconds earlier")

    def test_correction_after_a_read_is_not_served_stale(self):
        session = iv.start_or_resume(self.user, self.conv)
        recorded, _ = iv.record_facts(
            session, [{"statement": "MARKER-A married in 1996.", "topic": "family"}])
        self._prompt()  # priming read
        self.client.post(reverse("users:about_me_fact_action",
                                 kwargs={"pk_id": recorded[0].id, "action": "correct"}),
                         {"statement": "MARKER-B married in 1997."})
        prompt = self._prompt()
        self.assertIn("MARKER-B", prompt)
        self.assertNotIn("MARKER-A", prompt,
                         "the superseded statement survived in model truth")

    def test_deletion_after_a_read_is_not_served_stale(self):
        session = iv.start_or_resume(self.user, self.conv)
        recorded, _ = iv.record_facts(
            session, [{"statement": "MARKER-GONE forget this.", "topic": "family"}])
        self._prompt()  # priming read
        self.client.post(reverse("users:about_me_fact_action",
                                 kwargs={"pk_id": recorded[0].id, "action": "delete"}))
        self.assertNotIn("MARKER-GONE", self._prompt(),
                         "deleted knowledge survived in model truth")

    def test_counts_and_topic_pages_agree_with_model_truth(self):
        """The user's view and the model's view must be the same truth, not two
        independently derived ones."""
        session = iv.start_or_resume(self.user, self.conv)
        self._prompt()  # priming read
        iv.record_facts(session, [
            {"statement": "MARKER-C1 Heather is my wife.", "topic": "family"},
            {"statement": "MARKER-C2 We married in 1997.", "topic": "family"},
            {"statement": "MARKER-C3 I ride motorcycles.", "topic": "interests"},
        ])
        self.assertEqual(pk.topic_counts(self.user).get("family"), 2)
        about = self.client.get(reverse("users:about_me")).content.decode()
        self.assertIn("3 things in total", about)      # the running total
        self.assertIn("2 things I know", about)        # the family card
        self.assertIn("1 thing I know", about)         # the interests card
        topic = self.client.get(
            reverse("users:about_me_topic", kwargs={"topic": "family"})).content.decode()
        prompt = self._prompt()
        for marker in ("MARKER-C1", "MARKER-C2"):
            self.assertIn(marker, topic)
            self.assertIn(marker, prompt)

    def test_a_fresh_process_sees_the_same_truth(self):
        """A later turn is served by a DIFFERENT worker process — it must not depend on
        in-process state left behind by the interview."""
        session = iv.start_or_resume(self.user, self.conv)
        iv.record_facts(session,
                        [{"statement": "MARKER-FRESH I ride motorcycles.", "topic": "interests"}])
        iv.pause(self.user, self.conv)
        from apps.ai.model_interface.service import ModelInterfaceService
        svc = ModelInterfaceService(User.objects.get(pk=self.user.pk))
        prompt = svc._system_prompt(svc.build_standing_context(conversation=self.conv))
        self.assertIn("MARKER-FRESH", prompt)
        self.assertNotIn("GETTING TO KNOW", prompt,
                         "a paused interview still steers ordinary conversation")


class DuplicateStorageTests(InterviewHarness):
    """M5 §2 — production validation showed one turn re-teaching the previous turn's
    facts verbatim, doubling every count in About Me. Storage integrity is WLJ's job,
    so the class is made impossible rather than instructed away.
    """

    def test_teaching_the_same_thing_twice_stores_it_once(self):
        session = iv.start_or_resume(self.user, self.conv)
        iv.record_facts(session, [{"statement": "I'm married to Rachel.", "topic": "family"}])
        iv.record_facts(session, [{"statement": "I'm married to Rachel.", "topic": "family"}])
        self.assertEqual(pk.active_facts(self.user).count(), 1)

    def test_repeat_is_reported_as_remembered_not_as_a_failure(self):
        """It IS remembered — reporting a reject would make the CoS apologise for
        successfully knowing something."""
        session = iv.start_or_resume(self.user, self.conv)
        iv.record_facts(session, [{"statement": "I'm married to Rachel.", "topic": "family"}])
        recorded, rejected = iv.record_facts(
            session, [{"statement": "I'm married to Rachel.", "topic": "family"}])
        self.assertEqual(len(recorded), 1)
        self.assertEqual(rejected, [])

    def test_matching_ignores_only_case_spacing_and_trailing_punctuation(self):
        session = iv.start_or_resume(self.user, self.conv)
        iv.record_facts(session, [{"statement": "I'm married to Rachel.", "topic": "family"}])
        for variant in ("i'm married to rachel", "I'm  married to Rachel!",
                        "  I'm married to Rachel  "):
            iv.record_facts(session, [{"statement": variant, "topic": "family"}])
        self.assertEqual(pk.active_facts(self.user).count(), 1)

    def test_different_wordings_are_NOT_merged(self):
        """Deciding two different sentences mean the same thing is interpretation, which
        WLJ does not do. Only an identical statement is a duplicate."""
        session = iv.start_or_resume(self.user, self.conv)
        iv.record_facts(session, [
            {"statement": "I'm married to Rachel.", "topic": "family"},
            {"statement": "Rachel is my wife.", "topic": "family"},
        ])
        self.assertEqual(pk.active_facts(self.user).count(), 2)

    def test_the_same_sentence_in_a_different_topic_is_kept(self):
        session = iv.start_or_resume(self.user, self.conv)
        iv.record_facts(session, [{"statement": "Family comes first.", "topic": "family"}])
        iv.record_facts(session, [{"statement": "Family comes first.", "topic": "values"}])
        self.assertEqual(pk.active_facts(self.user).count(), 2)

    def test_a_deleted_fact_can_be_taught_again(self):
        """Dedup matches ACTIVE facts only — otherwise removing something would make it
        impossible to tell WLJ again."""
        session = iv.start_or_resume(self.user, self.conv)
        recorded, _ = iv.record_facts(
            session, [{"statement": "I'm married to Rachel.", "topic": "family"}])
        pk.delete_fact(recorded[0])
        iv.record_facts(session, [{"statement": "I'm married to Rachel.", "topic": "family"}])
        self.assertEqual(pk.active_facts(self.user).count(), 1)

    def test_dedup_is_scoped_to_the_user(self):
        other = User.objects.create_user(email="other@contract.test", password="x")
        pk.add_fact(other, "I'm married to Rachel.", topic="family")
        pk.add_fact(self.user, "I'm married to Rachel.", topic="family")
        self.assertEqual(pk.active_facts(self.user).count(), 1)
        self.assertEqual(pk.active_facts(other).count(), 1)


class BoundaryPersistenceInstructionTests(InterviewHarness):
    """M5 §3 — the run showed the CoS agreeing to a decline in prose while recording
    nothing, so the boundary evaporated. WLJ cannot detect a decline without a text
    classifier, so the instruction must make the requirement unmissable.
    """

    def test_the_lead_requires_recording_a_boundary_not_just_agreeing(self):
        iv.start_or_resume(self.user, self.conv)
        prompt = self._prompt()
        self.assertIn("RECORDING WHAT THEY RULE OUT", prompt)
        self.assertIn("a promise you cannot keep", prompt)

    def test_the_tool_states_it_accepts_an_area_outcome_alone(self):
        from apps.ai.model_interface.constitution import all_tools
        tool = next(t["function"] for t in all_tools(writes_enabled=True)
                    if t["function"]["name"] == "record_interview_knowledge")
        self.assertIn("`area_outcome` ALONE", tool["description"])
        self.assertNotIn("facts", tool["parameters"].get("required", []),
                         "facts must stay optional or a boundary-only call is impossible")

    def test_an_area_outcome_with_no_facts_is_accepted_and_persisted(self):
        iv.start_or_resume(self.user, self.conv)
        out = self._dispatch()("record_interview_knowledge",
                               {"area_outcome": {"area": "faith", "state": "declined"}})
        self.assertTrue(out.get("area_outcome_applied"))
        self.assertIn("faith", iv.read(self._fresh(), self.conv)["declined_areas"])
        self.assertIn("OFF LIMITS", self._prompt())

    def test_the_lead_tells_it_to_lead_rather_than_offer_a_menu(self):
        iv.start_or_resume(self.user, self.conv)
        prompt = self._prompt()
        self.assertIn("LEAD THE CONVERSATION", prompt)
        self.assertIn("Do NOT open with an acknowledgement", prompt)

    def test_the_lead_forbids_converting_what_they_said(self):
        iv.start_or_resume(self.user, self.conv)
        self.assertIn("do not convert it", self._prompt().lower())

    def _dispatch(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        svc = ModelInterfaceService(self._fresh())
        return svc._make_dispatch(
            turn_id="t", surface="test", tools_called=[],
            conversation_id=self.conv.id, conversation=self.conv)


class TemporalAnchorTests(InterviewHarness):
    """M5 §2 — a point-in-time detail must not silently become false as it ages.

    WLJ knows when it was told something; that is WLJ's own truth. The model must NOT
    derive a birth year from an age, because it does not know the birthday.
    """

    def test_every_interview_fact_is_stamped_with_the_date_it_was_taught(self):
        from django.utils import timezone
        session = iv.start_or_resume(self.user, self.conv)
        recorded, _ = iv.record_facts(
            session, [{"statement": "Tom is 14.", "topic": "family"}])
        self.assertEqual(recorded[0].as_of, timezone.localdate())

    def test_the_lead_forbids_deriving_a_birth_year(self):
        iv.start_or_resume(self.user, self.conv)
        prompt = self._prompt()
        self.assertIn("do not know his birthday", prompt)
        self.assertIn("Record what they SAID", prompt)


class CaptureCompletenessTests(InterviewHarness):
    """M5 §3 — production validation showed the model choosing a follow-up question
    INSTEAD of recording, then sounding like it knew the fact (from chat history) when
    nothing had been stored. The fact was gone by the next visit.
    """

    def test_the_lead_forbids_choosing_a_question_over_recording(self):
        iv.start_or_resume(self.user, self.conv)
        prompt = self._prompt()
        self.assertIn("recording and replying are NOT alternatives", prompt)
        self.assertIn("Asking instead of recording is how a fact is lost", prompt)

    def test_the_lead_forbids_a_numbered_menu_of_subjects(self):
        iv.start_or_resume(self.user, self.conv)
        self.assertIn("a numbered list of subjects is an intake form", self._prompt())

    def test_conversation_history_is_not_a_substitute_for_storage(self):
        """The structural reason the above matters: a later visit carries no chat
        history, so anything not persisted is simply gone."""
        session = iv.start_or_resume(self.user, self.conv)
        iv.record_facts(session, [{"statement": "MARKER-KEPT I run a landscaping business.",
                                   "topic": "work"}])
        iv.pause(self.user, self.conv)
        from apps.ai.model_interface.service import ModelInterfaceService
        svc = ModelInterfaceService(User.objects.get(pk=self.user.pk))
        prompt = svc._system_prompt(svc.build_standing_context(conversation=self.conv))
        self.assertIn("MARKER-KEPT", prompt)
        self.assertNotIn("MARKER-UNSAID", prompt)
