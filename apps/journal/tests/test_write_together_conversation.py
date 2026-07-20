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

    def test_context_is_withheld_until_user_gives_little(self):
        # Personal context (last resort) is only offered after >=2 sparse user turns.
        from apps.journal.services.journal_conversation import _should_offer_context

        class _C:
            def __init__(self, transcript):
                self.transcript = transcript

        self.assertFalse(_should_offer_context(_C([])))
        self.assertFalse(_should_offer_context(_C([{"role": "user", "text": "hi"}])))
        # a rich first answer → keep following the user, no context
        long = " ".join(["word"] * 50)
        self.assertFalse(_should_offer_context(_C([
            {"role": "user", "text": long}, {"role": "user", "text": "more stuff here"}])))
        # two sparse turns → last-resort context is allowed
        self.assertTrue(_should_offer_context(_C([
            {"role": "user", "text": "not much"}, {"role": "user", "text": "i dunno"}])))

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
        self.assertContains(resp, "journal from your conversation")
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
