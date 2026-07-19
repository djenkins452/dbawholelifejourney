"""
Tests for the Journal "How would you like to journal today?" methods chooser
(the pivot away from the retired editor-conversation model).

Covers flag gating of the chooser, that the classic blank page is unchanged when
off, that Just Write still saves a normal JournalEntry, and that the retired
one-question endpoint is fully removed.

Location: apps/journal/tests/test_journal_methods.py
"""

from datetime import date

from django.test import TestCase, Client
from django.urls import reverse, NoReverseMatch

from apps.journal.models import JournalEntry
from apps.journal.tests.test_journal_comprehensive import JournalTestMixin


class JournalMethodsChooserTests(JournalTestMixin, TestCase):
    def setUp(self):
        self.client = Client()
        self.user = self.create_user()

    def _enable_methods(self):
        prefs = self.user.preferences
        prefs.journal_features = dict(prefs.journal_features or {})
        prefs.journal_features["write_together"] = True
        prefs.save()

    # --- chooser gating ---

    def test_chooser_hidden_when_flag_off(self):
        self.login_user()
        resp = self.client.get(reverse("journal:entry_create"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "How would you like to journal today?")
        self.assertNotContains(resp, "journal-methods")

    def test_chooser_shown_when_flag_on(self):
        self._enable_methods()
        self.login_user()
        resp = self.client.get(reverse("journal:entry_create"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "How would you like to journal today?")
        self.assertContains(resp, "Just Write")
        self.assertContains(resp, "Write Together")
        self.assertContains(resp, "Talk It Through")

    # --- Just Write still works (the classic path is untouched) ---

    def test_just_write_still_saves_entry(self):
        self.login_user()
        resp = self.client.post(reverse("journal:entry_create"), {
            "title": "A quiet day",
            "body": "Wrote a few lines before bed.",
            "entry_date": date.today().isoformat(),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            JournalEntry.objects.filter(user=self.user, title="A quiet day").exists()
        )

    # --- the retired one-question interaction is fully gone ---

    def test_retired_write_together_endpoint_is_removed(self):
        with self.assertRaises(NoReverseMatch):
            reverse("journal:write_together_ask")
