"""Conversation State Management — regression coverage (model_interface runtime).

Conversation State is the deterministic working-state authority ("what are we talking
about / doing / waiting on"), distinct from Current Context ("what page"). These tests
lock the deterministic authority, its integration into the production ModelInterfaceService
standing context, the salient leads (the salience fix), expiry, and fail-closed ambiguity.
The LLM's semantic decisions (does "yes" resolve THIS, does "for a leak?" mean the video)
are validated separately on the real gateway (production gate), not here.
"""
import datetime as dt

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai.models import AssistantConversation
from apps.ai.model_interface import conversation_state as cs
from apps.ai.model_interface import confirmation
from apps.ai.model_interface.service import ModelInterfaceService

User = get_user_model()

_VIDEO = [{"artifact_id": 999, "kind": "video", "filename": "leak.mp4"}]


class ConversationStateAuthorityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="cstate@example.com", password="x")
        self.conv = AssistantConversation.objects.create(user=self.user, session_type="chat")

    # 1. Video remains the active subject across follow-ups -------------------
    def test_uploaded_artifact_becomes_and_persists_as_active_subject(self):
        cs.record_turn(self.conv, attachments=_VIDEO)               # upload turn
        st = cs.read(self.conv)
        self.assertEqual(st["active_subject"]["ref"], 999)
        self.assertEqual(st["active_subject"]["label"], "leak.mp4")
        self.assertEqual(st["active_subject"]["turns_ago"], 0)
        cs.record_turn(self.conv, attachments=None)                 # "For a leak?"
        cs.record_turn(self.conv, attachments=None)                 # "I expected you to say..."
        st = cs.read(self.conv)
        self.assertEqual(st["active_subject"]["ref"], 999, "video must survive follow-ups")
        self.assertEqual(st["active_subject"]["turns_ago"], 2)

    # 2. Page Current Context does not silently override the active artifact ---
    def test_active_subject_lead_asserts_precedence_over_page_context(self):
        cs.record_turn(self.conv, attachments=_VIDEO)
        svc = ModelInterfaceService(self.user)
        ctx = svc.build_standing_context(
            conversation=self.conv, writes_enabled=True,
            page_context={"focus_ref": "summary:faith.prayers", "module": "faith",
                          "url": "/faith/prayers/"})
        self.assertIn("conversation_state", ctx)
        lead = svc._conversation_state_lead(ctx)
        self.assertIn("ACTIVE SUBJECT", lead)
        self.assertIn("leak.mp4", lead)
        self.assertIn("page", lead.lower())            # explicitly names the page-precedence rule
        # The lead is early (salient), before the big JSON dump.
        sp = svc._system_prompt(ctx)
        self.assertLess(sp.find("ACTIVE CONVERSATION STATE"), sp.find("STRUCTURED CONTEXT"))

    # 3./4./5. Pending confirmation is surfaced saliently + resolvable by id ---
    def test_single_pending_confirmation_is_salient_and_bound(self):
        rec = confirmation.create(self.user, "import_journal_entries",
                                  {"records": [{"title": "A day"}]}, "Import 1 journal entry")
        svc = ModelInterfaceService(self.user)
        ctx = svc.build_standing_context(conversation=self.conv, writes_enabled=True)
        lead = svc._conversation_state_lead(ctx)
        self.assertIn("AWAITING YOUR CONFIRMATION", lead)
        self.assertIn(rec["confirmation_id"], lead)     # the id to resolve is present
        self.assertIn("resolve_pending_action", lead)

    def test_confirmation_resolves_only_by_specific_id(self):
        rec = confirmation.create(self.user, "import_journal_entries", {"x": 1}, "Import 1")
        # get() returns the pending record for the real id, None for a bogus id.
        self.assertIsNotNone(confirmation.get(self.user, rec["confirmation_id"]))
        self.assertIsNone(confirmation.get(self.user, "deadbeef"))
        # single-use: consumed → no longer resolvable (models "yes" then a stray "yes").
        confirmation.consume(self.user, rec["confirmation_id"])
        self.assertIsNone(confirmation.get(self.user, rec["confirmation_id"]))

    # 6. Two pending confirmations + a bare "yes" must fail closed ------------
    def test_multiple_pending_confirmations_fail_closed(self):
        confirmation.create(self.user, "import_journal_entries", {"a": 1}, "Import journal A")
        confirmation.create(self.user, "log_body_measurements", {"b": 2}, "Log measurements B")
        svc = ModelInterfaceService(self.user)
        ctx = svc.build_standing_context(conversation=self.conv, writes_enabled=True)
        lead = svc._conversation_state_lead(ctx)
        self.assertIn("MULTIPLE CONFIRMATIONS ARE PENDING", lead)
        self.assertIn("AMBIGUOUS", lead)
        self.assertIn("Fail closed", lead)

    # 7. An explicit new subject supersedes the active subject ----------------
    def test_new_retrieval_supersedes_active_subject(self):
        cs.record_turn(self.conv, attachments=_VIDEO)
        cs.record_turn(self.conv, retrieved_subject={
            "kind": "entity", "ref": "Dad's health", "label": "Dad's health", "domain": "faith"})
        st = cs.read(self.conv)
        self.assertEqual(st["active_subject"]["label"], "Dad's health")
        self.assertEqual(st["active_subject"]["kind"], "entity")

    # 8. Expired state does not contaminate a later conversation --------------
    def test_time_expiry_and_turn_expiry(self):
        cs.record_turn(self.conv, attachments=_VIDEO)
        # Time-based: backdate the state past TTL.
        future = timezone.now() + dt.timedelta(seconds=cs.TTL_SECONDS + 60)
        self.assertIsNone(cs.read(self.conv, now=future))
        # Turn-based: the active SUBJECT ages out after MAX_SUBJECT_TURNS (so the salient
        # lead stops offering it); the bounded artifact list may remain as passive context
        # and clears with the whole-state time expiry above.
        for _ in range(cs.MAX_SUBJECT_TURNS + 1):
            cs.record_turn(self.conv, attachments=None)
        st = cs.read(self.conv) or {}
        self.assertIsNone(st.get("active_subject"), "active subject must age out")
        svc = ModelInterfaceService(self.user)
        ctx = svc.build_standing_context(conversation=self.conv, writes_enabled=True)
        self.assertNotIn("ACTIVE SUBJECT", svc._conversation_state_lead(ctx))

    def test_new_conversation_starts_clean(self):
        cs.record_turn(self.conv, attachments=_VIDEO)
        other = AssistantConversation.objects.create(user=self.user, session_type="chat")
        self.assertIsNone(cs.read(other), "a fresh conversation is never contaminated")

    # 9. State survives the refresh/reconnect boundary (durable in the DB) ----
    def test_state_is_durable_across_reload(self):
        cs.record_turn(self.conv, attachments=_VIDEO)
        reloaded = AssistantConversation.objects.get(pk=self.conv.pk)   # simulate refresh
        st = cs.read(reloaded)
        self.assertEqual(st["active_subject"]["ref"], 999)

    # 10. The production runtime assembles Conversation State -----------------
    def test_generate_records_state_and_standing_context_exposes_it(self):
        # build_standing_context is the production assembly point; prove it includes the
        # authority and the derivation from a get_entity retrieval works.
        svc = ModelInterfaceService(self.user)
        subj = svc._subject_from_entity_result(
            "get_entity", {"domain": "faith", "entity_type": "prayer"},
            {"status": "ready", "entities": [{"identity": "Dad's health", "kind": "prayer"}]})
        self.assertEqual(subj["label"], "Dad's health")
        self.assertEqual(subj["kind"], "entity")
        cs.record_turn(self.conv, retrieved_subject=subj)
        ctx = svc.build_standing_context(conversation=self.conv, writes_enabled=True)
        self.assertEqual(ctx["conversation_state"]["active_subject"]["label"], "Dad's health")

    def test_no_active_state_no_lead(self):
        svc = ModelInterfaceService(self.user)
        ctx = svc.build_standing_context(conversation=self.conv, writes_enabled=True)
        self.assertNotIn("conversation_state", ctx)
        self.assertEqual(svc._conversation_state_lead(ctx), "")
