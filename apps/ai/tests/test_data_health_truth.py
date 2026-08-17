# ==============================================================================
# File: apps/ai/tests/test_data_health_truth.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Proactive Missing-Data Intervention (M3) — the get_data_health truth surface
#   exposes source-sync facts (reusing the single authority), facts-only, and is registered
#   as a CoS truth tool. Deterministic (mocks the underlying authority).
# ==============================================================================
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from apps.ai.cos_services.data_health import get_data_health
from apps.users.models import TermsAcceptance

try:
    from apps.users.models import User
except ImportError:
    from django.contrib.auth import get_user_model
    User = get_user_model()


def _user(email="dh@test.com"):
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    p = u.preferences
    p.has_completed_onboarding = True
    p.timezone = "UTC"
    p.save()
    return u


_RAW = {
    "overall_health": {"status": "healthy", "active_count": 5, "total_count": 9},
    "last_sync": {"at": "2026-08-14T06:00:00+00:00", "status": "completed"},
    "data_types": [
        {"key": "steps", "label": "Steps", "days_since_last_record": 0},
        {"key": "sleep", "label": "Sleep", "days_since_last_record": 5},
        {"key": "hr", "label": "Heart Rate", "days_since_last_record": 4},
        {"key": "weight", "label": "Weight", "days_since_last_record": 1},
    ],
    "issues": [{"summary": "Apple Health stopped delivering Sleep", "action": "Open the app to re-sync"}],
}


class DataHealthTruthTests(TestCase):
    def setUp(self):
        self.user = _user()

    def test_exposes_source_sync_facts_only(self):
        with patch("apps.health.services.health_sync_status.build_health_sync_status",
                   return_value=_RAW):
            out = get_data_health(self.user)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["sync_state"], "healthy")             # plumbing fact, not a life verdict
        self.assertEqual(out["last_sync_at"], "2026-08-14T06:00:00+00:00")
        quiet = {s["source"]: s["days_since_last_record"] for s in out["quiet_sources"]}
        self.assertEqual(quiet, {"Sleep": 5, "Heart Rate": 4})     # only >= threshold, sorted
        self.assertNotIn("Steps", quiet)                            # fresh source not flagged
        self.assertEqual(out["issues"][0]["action"], "Open the app to re-sync")

    def test_authority_failure_is_honest_not_fatal(self):
        with patch("apps.health.services.health_sync_status.build_health_sync_status",
                   side_effect=RuntimeError("db down")):
            out = get_data_health(self.user)
        self.assertEqual(out["status"], "unavailable")

    def test_registered_as_truth_tool(self):
        from apps.ai.model_interface.constitution import truth_tools
        names = {t["function"]["name"] for t in truth_tools()}
        self.assertIn("get_data_health", names)
