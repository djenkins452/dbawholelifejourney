"""
Tests for Write Together — the dedicated Journal conversation (M2, text).

Covers gating, the opening, a conversation turn, durability (persist + resume),
generation, and the review → save path that produces a canonical JournalEntry
linked back to its source conversation.

Location: apps/journal/tests/test_write_together_conversation.py
"""

import json
from datetime import date
from unittest.mock import patch

from django.test import TestCase, Client
from django.urls import reverse

from apps.journal.models import JournalEntry, JournalConversation
from apps.journal.tests.test_journal_comprehensive import JournalTestMixin


class WriteTogetherConversationTests(JournalTestMixin, TestCase):
    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.page_url = reverse("journal:write_together")
        self.msg_url = reverse("journal:write_together_message")
        self.gen_url = reverse("journal:write_together_generate")

    def _enable(self, pa=True):
        prefs = self.user.preferences
        prefs.journal_features = dict(prefs.journal_features or {})
        prefs.journal_features["write_together"] = True
        prefs.personal_assistant_enabled = pa
        prefs.save()

    # --- gating -------------------------------------------------------------

    def test_page_redirects_when_disabled(self):
        self.login_user()
        resp = self.client.get(self.page_url)
        self.assertEqual(resp.status_code, 302)

    def test_message_404_when_disabled(self):
        self.login_user()
        resp = self.client.post(self.msg_url, data="{}", content_type="application/json")
        self.assertEqual(resp.status_code, 404)

    def test_page_renders_when_enabled(self):
        self._enable()
        self.login_user()
        resp = self.client.get(self.page_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "wt-thread")
        # one active conversation is created for today
        self.assertTrue(
            JournalConversation.objects.filter(user=self.user, state="active").exists()
        )

    def test_voice_controls_render(self):
        # Talk It Through is the SAME page with a voice layer (mic + status bar).
        self._enable()
        self.login_user()
        resp = self.client.get(self.page_url + "?voice=1")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="wt-mic"')
        self.assertContains(resp, 'id="wt-voicebar"')
        self.assertContains(resp, 'data-voice="1"')  # auto-enters voice mode

    def test_conversation_style_controls_render_and_reflect_saved_pref(self):
        # Conversation Style (Quick / Natural / Reflective) + Pause are the user's
        # controls over rhythm — they render, and the page carries the saved style.
        prefs = self.user.preferences
        prefs.journal_features = dict(prefs.journal_features or {})
        prefs.journal_features["write_together"] = True
        prefs.journal_features["conversation_style"] = "reflective"
        prefs.personal_assistant_enabled = True
        prefs.save()
        self.login_user()
        resp = self.client.get(self.page_url + "?voice=1")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'class="wt-styles"')
        self.assertContains(resp, 'data-style="quick"')
        self.assertContains(resp, 'data-style="reflective"')
        self.assertContains(resp, 'id="wt-pause"')
        self.assertContains(resp, 'id="wt-paused"')
        self.assertContains(resp, 'id="wt-resume"')
        # the remembered style is delivered to the client
        self.assertContains(resp, 'data-style="reflective"')

    def test_conversation_style_defaults_to_natural(self):
        self._enable()
        self.login_user()
        resp = self.client.get(self.page_url)
        self.assertEqual(resp.status_code, 200)
        # .wt carries the persisted style; absent any saved value it is 'natural'
        self.assertContains(resp, 'data-style="natural"')

    def test_style_endpoint_persists_choice(self):
        self._enable()
        self.login_user()
        url = reverse("journal:write_together_style")
        resp = self.client.post(url, data=json.dumps({"style": "reflective"}),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("style"), "reflective")
        self.user.preferences.refresh_from_db()
        self.assertEqual(
            self.user.preferences.journal_features.get("conversation_style"), "reflective"
        )

    def test_style_endpoint_rejects_invalid(self):
        self._enable()
        self.login_user()
        url = reverse("journal:write_together_style")
        resp = self.client.post(url, data=json.dumps({"style": "sprint"}),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        self.user.preferences.refresh_from_db()
        self.assertNotIn("conversation_style", self.user.preferences.journal_features or {})

    def test_style_endpoint_404_when_disabled(self):
        self.login_user()
        url = reverse("journal:write_together_style")
        resp = self.client.post(url, data=json.dumps({"style": "quick"}),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 404)

    def test_talk_it_through_chooser_links_to_voice(self):
        from django.urls import reverse as _rev
        prefs = self.user.preferences
        prefs.journal_features = dict(prefs.journal_features or {})
        prefs.journal_features["write_together"] = True
        prefs.personal_assistant_enabled = True
        prefs.save()
        self.login_user()
        resp = self.client.get(_rev("journal:entry_create"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "write-together/?voice=1")  # Talk It Through is live

    # --- opening ------------------------------------------------------------

    @patch("apps.journal.services.journal_conversation.AIService")
    def test_opening_is_deterministic_and_does_not_steer(self, MockAI):
        # The opening is deterministic (no model call) and purpose-neutral — it must
        # never choose a subject or assume why the user is journaling.
        self._enable()
        self.login_user()
        resp = self.client.post(self.msg_url, data=json.dumps({"message": ""}),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("opening"))
        self.assertTrue(data["reply"])
        MockAI.return_value._call_api.assert_not_called()  # no model call for the opening
        self.assertNotIn("remember", data["reply"].lower())  # doesn't assume purpose
        convo = JournalConversation.objects.get(user=self.user)
        self.assertEqual(len(convo.transcript), 1)
        self.assertEqual(convo.transcript[0]["role"], "assistant")

    @patch("apps.ai.cos_services.personal_truth.personal_truth_for_context",
           return_value={"facts": {"health": [{"key": "condition", "value": "diabetes"}]}})
    @patch("apps.ai.cos_services.personal_truth.build_personal_truth", return_value={"status": "ready"})
    @patch("apps.journal.services.journal_conversation.AIService")
    def test_conversation_prompt_always_supplies_and_governs_personal_truth(self, MockAI, _bpt, _ptfc):
        # Personal truth is available EVERY turn (no gate) and the prompt governs it:
        # deepen the current story, never redirect. (Fixes the earlier over-correction.)
        MockAI.return_value._call_api.return_value = "What was that like?"
        self._enable()
        self.login_user()
        self.client.post(
            self.msg_url,
            data=json.dumps({"message": "My blood sugar kept running low today."}),
            content_type="application/json",
        )
        call = MockAI.return_value._call_api.call_args
        system_prompt = call.args[0] if call.args else call.kwargs.get("system", "")
        self.assertIn("diabetes", system_prompt)                       # truth supplied every turn
        self.assertIn("BETTER because of this truth", system_prompt)   # deepen-not-redirect guidance
        self.assertIn("never DIFFERENT because of it", system_prompt)

    # --- a turn + durability ------------------------------------------------

    @patch("apps.journal.services.journal_conversation.AIService")
    def test_turn_persists_and_returns_reply(self, MockAI):
        MockAI.return_value._call_api.return_value = "What was the best part?"
        self._enable()
        self.login_user()
        resp = self.client.post(self.msg_url, data=json.dumps({"message": "We went to the park."}),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["reply"], "What was the best part?")
        convo = JournalConversation.objects.get(user=self.user)
        self.assertEqual([t["role"] for t in convo.transcript], ["user", "assistant"])
        self.assertTrue(convo.has_user_content)

    def test_page_resumes_persisted_conversation(self):
        self._enable()
        self.login_user()
        convo = JournalConversation.objects.create(user=self.user, entry_date=date.today())
        convo.add_turn("assistant", "Hi there.")
        convo.add_turn("user", "We went shoe shopping.")
        convo.save()
        resp = self.client.get(self.page_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "We went shoe shopping.")  # transcript restored

    # --- generation ---------------------------------------------------------

    def test_generate_requires_user_content(self):
        self._enable()
        self.login_user()
        resp = self.client.post(self.gen_url, data="{}", content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "nothing_to_journal")

    @patch("apps.journal.services.journal_conversation.AIService")
    def test_generate_produces_draft_and_redirect(self, MockAI):
        MockAI.return_value._call_api.return_value = "Today I went to the park with the kids."
        self._enable()
        self.login_user()
        convo = JournalConversation.objects.create(user=self.user, entry_date=date.today())
        convo.add_turn("assistant", "How was your day?")
        convo.add_turn("user", "Great — park with the kids.")
        convo.save()
        resp = self.client.post(self.gen_url, data="{}", content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("from_conversation", resp.json()["redirect"])
        convo.refresh_from_db()
        self.assertEqual(convo.state, JournalConversation.STATE_REVIEWING)
        self.assertTrue(convo.generated_draft)

    # --- review → save (canonical JournalEntry) -----------------------------

    def test_review_prefills_editor_and_shows_banner(self):
        self._enable()
        self.login_user()
        convo = JournalConversation.objects.create(
            user=self.user, entry_date=date.today(),
            state=JournalConversation.STATE_REVIEWING,
            generated_draft="Today was a good day at the field.",
        )
        resp = self.client.get(reverse("journal:entry_create") + f"?from_conversation={convo.pk}")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Today was a good day at the field.")
        self.assertContains(resp, "from your conversation")
        # the chooser is hidden in review mode
        self.assertNotContains(resp, 'class="journal-methods"')

    def test_save_creates_entry_and_links_conversation(self):
        self._enable()
        self.login_user()
        convo = JournalConversation.objects.create(
            user=self.user, entry_date=date.today(),
            state=JournalConversation.STATE_REVIEWING,
            generated_draft="Today was a good day.",
        )
        resp = self.client.post(
            reverse("journal:entry_create") + f"?from_conversation={convo.pk}",
            {"title": "", "body": "<p>Today was a good day.</p>", "entry_date": date.today().isoformat()},
        )
        self.assertEqual(resp.status_code, 302)
        entry = JournalEntry.objects.filter(user=self.user).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.created_via, "voice_together")
        convo.refresh_from_db()
        self.assertEqual(convo.state, JournalConversation.STATE_COMPLETED)
        self.assertEqual(convo.resulting_entry_id, entry.id)


class TodaysDraftAwarenessTests(JournalTestMixin, TestCase):
    """M-D1: the Journal knows today's draft is in progress and lets the user resume
    it — the draft quietly travels with the user across the day."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.create_url = reverse("journal:entry_create")
        self.list_url = reverse("journal:entry_list")
        self.finish_url = reverse("journal:write_together_finish")

    def _enable(self):
        prefs = self.user.preferences
        prefs.journal_features = dict(prefs.journal_features or {})
        prefs.journal_features["write_together"] = True
        prefs.personal_assistant_enabled = True
        prefs.save()

    def _make_draft(self, state=JournalConversation.STATE_ACTIVE, with_content=True):
        from apps.core.utils import get_user_today
        convo = JournalConversation.objects.create(
            user=self.user, entry_date=get_user_today(self.user), state=state,
        )
        if with_content:
            convo.add_turn(convo.ROLE_ASSISTANT, "What's on your mind?")
            convo.add_turn(convo.ROLE_USER, "We drove up the coast today.")
            convo.save()
        return convo

    def test_no_draft_shows_chooser_not_card(self):
        self._enable()
        self.login_user()
        resp = self.client.get(self.create_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "How would you like to journal?")
        self.assertNotContains(resp, "Your Journal Draft")

    def test_empty_conversation_is_not_a_draft(self):
        # A conversation with only the opening (no user content) is NOT in progress.
        self._enable()
        self._make_draft(with_content=False)
        self.login_user()
        resp = self.client.get(self.create_url)
        self.assertContains(resp, "How would you like to journal?")
        self.assertNotContains(resp, "Your Journal Draft")

    def test_active_draft_replaces_chooser_with_card(self):
        self._enable()
        self._make_draft()
        self.login_user()
        resp = self.client.get(self.create_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Your Journal Draft")
        self.assertContains(resp, "Finish &amp; Review")
        self.assertContains(resp, "Resume Write Together")
        self.assertContains(resp, "Resume Talk It Through")
        # the fresh chooser is replaced by the draft card
        self.assertNotContains(resp, "How would you like to journal?")

    def test_reviewing_draft_shows_review_action(self):
        self._enable()
        convo = self._make_draft(state=JournalConversation.STATE_REVIEWING)
        self.login_user()
        resp = self.client.get(self.create_url)
        self.assertContains(resp, "Ready to review")
        self.assertContains(resp, f"from_conversation={convo.pk}")

    def test_draft_banner_on_entry_list(self):
        self._enable()
        self._make_draft()
        self.login_user()
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "journal-draft-banner")
        self.assertContains(resp, "Your journal draft is in progress")

    def test_no_draft_no_banner(self):
        self._enable()
        self.login_user()
        resp = self.client.get(self.list_url)
        self.assertNotContains(resp, "journal-draft-banner")

    def test_draft_card_gated_off_when_disabled(self):
        # No flag → no card even if a conversation row somehow exists.
        self._make_draft()
        self.login_user()
        resp = self.client.get(self.create_url)
        self.assertNotContains(resp, "Your Journal Draft")

    @patch("apps.journal.services.journal_conversation.AIService")
    def test_finish_today_generates_and_redirects_to_review(self, MockAI):
        MockAI.return_value._call_api.return_value = "We drove up the coast and it was calm."
        self._enable()
        convo = self._make_draft()
        self.login_user()
        resp = self.client.post(self.finish_url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f"from_conversation={convo.pk}", resp.url)
        convo.refresh_from_db()
        self.assertEqual(convo.state, JournalConversation.STATE_REVIEWING)
        self.assertTrue(convo.generated_draft)

    def test_finish_today_requires_content(self):
        self._enable()
        self._make_draft(with_content=False)
        self.login_user()
        resp = self.client.post(self.finish_url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("journal:write_together"), resp.url)

    def test_finish_today_404s_when_disabled(self):
        self.login_user()
        resp = self.client.post(self.finish_url)
        # disabled → redirected away, never generates
        self.assertEqual(resp.status_code, 302)


class UnifiedDraftTests(JournalTestMixin, TestCase):
    """M-D2/M-D3: all three modes contribute to ONE draft. Just Write autosaves the
    typed channel into today's shared draft; Finish & Review composes both channels."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.create_url = reverse("journal:entry_create")
        self.autosave_url = reverse("journal:draft_autosave")
        self.finish_url = reverse("journal:write_together_finish")

    def _enable(self):
        prefs = self.user.preferences
        prefs.journal_features = dict(prefs.journal_features or {})
        prefs.journal_features["write_together"] = True
        prefs.personal_assistant_enabled = True
        prefs.save()

    def _today(self):
        from apps.core.utils import get_user_today
        return get_user_today(self.user)

    # --- autosave -----------------------------------------------------------

    def test_autosave_creates_and_updates_written_draft(self):
        self._enable()
        self.login_user()
        resp = self.client.post(self.autosave_url,
                                data=json.dumps({"body": "<p>Drove up the coast.</p>"}),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("draft_id"))
        convo = JournalConversation.objects.get(user=self.user, entry_date=self._today())
        self.assertIn("coast", convo.written_body)
        self.assertTrue(convo.has_written_content)
        self.assertTrue(convo.has_content)
        # a second autosave updates the same row (one draft)
        resp2 = self.client.post(self.autosave_url,
                                 data=json.dumps({"body": "<p>Drove up the coast with Dad.</p>"}),
                                 content_type="application/json")
        self.assertEqual(resp2.json()["draft_id"], convo.pk)
        self.assertEqual(JournalConversation.objects.filter(user=self.user).count(), 1)

    def test_autosave_does_not_fabricate_empty_draft(self):
        self._enable()
        self.login_user()
        resp = self.client.post(self.autosave_url,
                                data=json.dumps({"body": "<p><br></p>"}),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json().get("draft_id"))
        self.assertFalse(JournalConversation.objects.filter(user=self.user).exists())

    def test_autosave_sanitizes_html(self):
        self._enable()
        self.login_user()
        self.client.post(self.autosave_url,
                         data=json.dumps({"body": "<p>ok</p><script>alert(1)</script>"}),
                         content_type="application/json")
        convo = JournalConversation.objects.get(user=self.user)
        self.assertNotIn("<script>", convo.written_body)

    def test_autosave_404_when_disabled(self):
        self.login_user()
        resp = self.client.post(self.autosave_url,
                                data=json.dumps({"body": "<p>x</p>"}),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 404)

    # --- draft-aware editor -------------------------------------------------

    def test_editor_prefills_written_body_and_enables_autosave(self):
        self._enable()
        JournalConversation.objects.create(
            user=self.user, entry_date=self._today(),
            written_body="<p>Lunch notes.</p>",
        )
        self.login_user()
        resp = self.client.get(self.create_url)
        self.assertContains(resp, "Lunch notes.")
        self.assertContains(resp, "draft/autosave")  # autosave wired

    def test_just_write_save_completes_written_draft(self):
        self._enable()
        draft = JournalConversation.objects.create(
            user=self.user, entry_date=self._today(),
            written_body="<p>My day.</p>",
        )
        self.login_user()
        resp = self.client.post(self.create_url, {
            "title": "", "body": "<p>My day, saved.</p>",
            "entry_date": self._today().isoformat(),
        })
        self.assertEqual(resp.status_code, 302)
        entry = JournalEntry.objects.get(user=self.user)
        draft.refresh_from_db()
        self.assertEqual(draft.state, JournalConversation.STATE_COMPLETED)
        self.assertEqual(draft.resulting_entry_id, entry.id)

    def test_editor_with_conversation_offers_finish_not_direct_save(self):
        # A draft that also holds a conversation must finish via Finish & Review so the
        # conversation is not dropped — the direct write-only Save is replaced.
        self._enable()
        convo = JournalConversation.objects.create(user=self.user, entry_date=self._today())
        convo.add_turn(convo.ROLE_USER, "We drove up the coast.")
        convo.save()
        self.login_user()
        resp = self.client.get(self.create_url)
        self.assertContains(resp, "jc-finish-form")
        self.assertContains(resp, "combine your notes and your conversation")

    # --- generation composes both channels ----------------------------------

    @patch("apps.journal.services.journal_conversation.AIService")
    def test_generate_composes_transcript_and_written_notes(self, MockAI):
        from apps.journal.services.journal_conversation import generate_entry
        MockAI.return_value._call_api.return_value = "We drove up the coast and fixed the fence."
        self._enable()
        convo = JournalConversation.objects.create(
            user=self.user, entry_date=self._today(),
            written_body="<p>Also: fixed the fence.</p>",
        )
        convo.add_turn(convo.ROLE_USER, "We drove up the coast.")
        convo.save()
        generate_entry(self.user, convo)
        # the model was asked to weave in the typed notes
        call = MockAI.return_value._call_api.call_args
        user_prompt = call.args[1] if len(call.args) > 1 else call.kwargs.get("user_prompt", "")
        self.assertIn("fixed the fence", user_prompt)
        self.assertIn("drove up the coast", user_prompt.lower())

    @patch("apps.journal.services.journal_conversation.AIService")
    def test_pure_written_generate_passes_through_without_rewrite(self, MockAI):
        # Pure Just Write has no conversation → never send the user's prose to be
        # rewritten; it passes straight through to review (fidelity).
        from apps.journal.services.journal_conversation import generate_entry
        self._enable()
        convo = JournalConversation.objects.create(
            user=self.user, entry_date=self._today(),
            written_body="<p>My own words, untouched.</p>",
        )
        draft = generate_entry(self.user, convo)
        self.assertIn("My own words, untouched.", draft)
        MockAI.return_value._call_api.assert_not_called()
        convo.refresh_from_db()
        self.assertEqual(convo.state, JournalConversation.STATE_REVIEWING)

    @patch("apps.journal.services.journal_conversation.AIService")
    def test_conversation_is_aware_of_typed_notes(self, MockAI):
        # §13: type notes, then switch to talking — the CoS "reads what's there".
        from apps.journal.services.journal_conversation import respond
        MockAI.return_value._call_api.return_value = "What was the drive like?"
        self._enable()
        convo = JournalConversation.objects.create(
            user=self.user, entry_date=self._today(),
            written_body="<p>We drove up the coast this morning.</p>",
        )
        respond(self.user, convo, "It was a good day.")
        call = MockAI.return_value._call_api.call_args
        system = call.args[0] if call.args else call.kwargs.get("system", "")
        self.assertIn("ALREADY WRITTEN", system)
        self.assertIn("drove up the coast", system)

    def test_written_only_draft_shows_card(self):
        # A pure-written draft (no conversation) is still an in-progress draft.
        self._enable()
        JournalConversation.objects.create(
            user=self.user, entry_date=self._today(),
            written_body="<p>Started writing.</p>",
        )
        self.login_user()
        resp = self.client.get(reverse("journal:entry_list"))
        self.assertContains(resp, "journal-draft-banner")
