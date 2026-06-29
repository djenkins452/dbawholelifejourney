# ==============================================================================
# File: apps/core/ai_state/tests/test_health_state_glucose_timestamp.py
# Description: Defect 2 regression — the glucose TIMESTAMP must survive the REAL SAE
#   build. A swallowed NameError (timezone not imported) silently dropped
#   last_glucose_entry, so "What is my glucose?" → "At what time?" failed in
#   production while mocked unit tests passed. This test runs build_health_state for
#   real so the regression cannot recur.
# ==============================================================================
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_state.state_builder import build_health_state
from apps.health.models import GlucoseEntry

User = get_user_model()


class GlucoseTimestampSurvivesBuildTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="glubuild@test.com", password="x")

    def test_recent_glucose_populates_value_AND_timestamp(self):
        recorded = timezone.now() - timedelta(hours=1)
        GlucoseEntry.objects.create(user=self.user, value=91, unit="mg/dL",
                                    recorded_at=recorded)
        state = build_health_state(self.user)
        self.assertEqual(state.get("latest_glucose"), 91.0)
        # The timestamp must be present (the bug left this None via a swallowed error).
        self.assertTrue(state.get("last_glucose_entry"),
                        "last_glucose_entry missing — the glucose block crashed silently")
        self.assertNotIn("last_glucose_entry_warning", state)   # not future → no warning

    def test_glucose_block_does_not_swallow_into_a_blank_state(self):
        # A present reading must yield BOTH value and timestamp — proving the block ran
        # to completion (not aborted early by an exception after the value was set).
        GlucoseEntry.objects.create(user=self.user, value=120, unit="mg/dL",
                                    recorded_at=timezone.now() - timedelta(minutes=30))
        state = build_health_state(self.user)
        self.assertIsNotNone(state.get("latest_glucose"))
        self.assertIsNotNone(state.get("last_glucose_entry"))
