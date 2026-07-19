"""
Tests for Write Together — Journal experience redesign, Milestone 1 (text).

Covers flag/CoS gating, graceful degradation, the question endpoint, the
blank-draft simple opener, and — critically — that the classic blank-page
Journal is unchanged when the feature is OFF.

Location: apps/journal/tests/test_write_together.py
"""

import json
from unittest.mock import patch

from django.test import TestCase, Client
from django.urls import reverse

from apps.journal.tests.test_journal_comprehensive import JournalTestMixin


class WriteTogetherTests(JournalTestMixin, TestCase):
    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.url = reverse("journal:write_together_ask")

    def _enable_write_together(self, cos_enabled=True):
        prefs = self.user.preferences
        prefs.journal_features = dict(prefs.journal_features or {})
        prefs.journal_features["write_together"] = True
        prefs.personal_assistant_enabled = cos_enabled
        prefs.save()

    # --- gating -------------------------------------------------------------

    def test_requires_login(self):
        resp = self.client.post(self.url, data="{}", content_type="application/json")
        self.assertIn(resp.status_code, (302, 403))

    def test_flag_off_returns_404(self):
        self.login_user()
        resp = self.client.post(
            self.url, data=json.dumps({"draft": "x"}), content_type="application/json"
        )
        self.assertEqual(resp.status_code, 404)

    def test_cos_disabled_degrades_gracefully(self):
        self._enable_write_together(cos_enabled=False)
        self.login_user()
        resp = self.client.post(
            self.url,
            data=json.dumps({"draft": "A long enough draft about my day here."}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data.get("degraded"))
        self.assertTrue(data["question"])

    # --- happy path ---------------------------------------------------------

    @patch("apps.journal.services.write_together.AIService")
    def test_returns_question_from_model(self, MockAI):
        MockAI.return_value._call_api.return_value = "What was the best part of the game?"
        self._enable_write_together()
        self.login_user()
        resp = self.client.post(
            self.url,
            data=json.dumps(
                {"draft": "Took Parker to his baseball game this afternoon and he did great."}
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["question"], "What was the best part of the game?")
        self.assertFalse(data.get("degraded"))

    @patch("apps.journal.services.write_together.AIService")
    def test_blank_draft_returns_simple_opener_without_model(self, MockAI):
        self._enable_write_together()
        self.login_user()
        resp = self.client.post(
            self.url, data=json.dumps({"draft": ""}), content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["question"])
        MockAI.return_value._call_api.assert_not_called()

    @patch("apps.journal.services.write_together.AIService")
    def test_model_unavailable_returns_fallback(self, MockAI):
        MockAI.return_value._call_api.return_value = None
        self._enable_write_together()
        self.login_user()
        resp = self.client.post(
            self.url,
            data=json.dumps(
                {"draft": "A reasonably long draft about my day and the people in it."}
            ),
            content_type="application/json",
        )
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data.get("degraded"))
        self.assertTrue(data["question"])

    @patch("apps.journal.services.write_together.AIService")
    def test_model_output_is_cleaned(self, MockAI):
        # Multi-line + wrapping quotes should collapse to one clean question line.
        MockAI.return_value._call_api.return_value = '"What did Parker say afterward?"\nAnything else?'
        self._enable_write_together()
        self.login_user()
        resp = self.client.post(
            self.url,
            data=json.dumps({"draft": "A long enough draft to trigger the model path here."}),
            content_type="application/json",
        )
        data = resp.json()
        self.assertEqual(data["question"], "What did Parker say afterward?")

    # --- preservation: classic blank page unchanged when the flag is OFF ----

    def test_entry_form_has_no_method_bar_when_flag_off(self):
        self.login_user()
        resp = self.client.get(reverse("journal:entry_create"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "journal-method-bar")
        self.assertNotContains(resp, "wt-panel")

    def test_entry_form_shows_method_bar_when_enabled(self):
        self._enable_write_together()
        self.login_user()
        resp = self.client.get(reverse("journal:entry_create"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "journal-method-bar")
        self.assertContains(resp, "Write Together")
