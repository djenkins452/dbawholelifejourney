"""Tests for Signal API views — feedback endpoint + insights endpoint.

Covers:
1. Feedback endpoint accepts yes/no only
2. Invalid fingerprint handled safely
3. Yes triggers feedback + completion
4. No triggers feedback only
5. Insights endpoint returns correct structure
"""

import json
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.users.models import TermsAcceptance, User


@override_settings(ROOT_URLCONF="config.urls")
class TestSignalFeedbackEndpoint(TestCase):
    """Tests for POST /api/signals/feedback/."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="testpass123",
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.client.login(email="test@example.com", password="testpass123")
        self.url = reverse("signals:feedback")

    def _post(self, data):
        return self.client.post(
            self.url,
            json.dumps(data),
            content_type="application/json",
        )

    def test_accepts_yes_response(self):
        resp = self._post({
            "fingerprint": "abc123",
            "response": "yes",
            "type": "possible_completion",
            "domain": "faith",
            "item": "prayer",
            "source": "journal",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["result"]["recorded"])

    def test_accepts_no_response(self):
        resp = self._post({
            "fingerprint": "abc123",
            "response": "no",
            "type": "possible_completion",
            "domain": "faith",
            "item": "prayer",
            "source": "journal",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertFalse(data["result"]["completion_triggered"])

    def test_rejects_invalid_response(self):
        resp = self._post({
            "fingerprint": "abc123",
            "response": "maybe",
        })
        self.assertEqual(resp.status_code, 400)

    def test_rejects_missing_fingerprint(self):
        resp = self._post({
            "response": "yes",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("fingerprint", resp.json()["detail"].lower())

    def test_rejects_empty_response(self):
        resp = self._post({
            "fingerprint": "abc123",
            "response": "",
        })
        self.assertEqual(resp.status_code, 400)

    def test_rejects_invalid_json(self):
        resp = self.client.post(
            self.url, "not json", content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_requires_authentication(self):
        self.client.logout()
        resp = self._post({
            "fingerprint": "abc123",
            "response": "yes",
        })
        # LoginRequiredMixin redirects to login
        self.assertIn(resp.status_code, [302, 403])

    def test_no_response_records_feedback_only(self):
        """'no' on a possible_completion records feedback but no completion."""
        resp = self._post({
            "fingerprint": "abc123",
            "response": "no",
            "type": "possible_completion",
            "domain": "faith",
            "item": "prayer",
            "source": "journal",
        })
        data = resp.json()
        self.assertTrue(data["result"]["recorded"])
        self.assertFalse(data["result"]["completion_triggered"])

    def test_yes_on_completion_records_and_attempts(self):
        """Yes on possible_completion records feedback and attempts completion.
        Without actual routines set up, completion won't succeed but feedback
        is still recorded and the attempt is made (no_matching_schedule).
        """
        resp = self._post({
            "fingerprint": "abc123",
            "response": "yes",
            "type": "possible_completion",
            "domain": "faith",
            "item": "prayer",
            "source": "journal",
        })
        data = resp.json()
        self.assertTrue(data["result"]["recorded"])
        # Without routines, completion attempt fails gracefully
        self.assertFalse(data["result"]["completion_triggered"])
        self.assertIn("completion_detail", data["result"])

    def test_yes_on_non_completion_type_records_only(self):
        """Yes on intent_signal records feedback but no completion attempt."""
        resp = self._post({
            "fingerprint": "abc123",
            "response": "yes",
            "type": "intent_signal",
            "domain": "faith",
            "item": "prayer",
            "source": "journal",
        })
        data = resp.json()
        self.assertTrue(data["result"]["recorded"])
        self.assertFalse(data["result"]["completion_triggered"])


@override_settings(ROOT_URLCONF="config.urls")
class TestSignalInsightsEndpoint(TestCase):
    """Tests for GET /api/signals/insights/."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="testpass123",
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.client.login(email="test@example.com", password="testpass123")
        self.url = reverse("signals:insights")

    def test_returns_structure(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("reinforced", data)
        self.assertIn("suppressed", data)
        self.assertIn("neutral", data)

    def test_empty_when_no_feedback(self):
        resp = self.client.get(self.url)
        data = resp.json()
        self.assertEqual(data["reinforced"], [])
        self.assertEqual(data["suppressed"], [])
        self.assertEqual(data["neutral"], [])

    def test_requires_authentication(self):
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertIn(resp.status_code, [302, 403])
