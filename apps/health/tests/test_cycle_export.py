"""
Cycle Export API Tests

Tests for the cycle data export API endpoint with rate limiting.

Location: apps/health/tests/test_cycle_export.py
"""

import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.health.models import (
    CycleSettings,
    CycleDailyLog,
    Cycle,
    CyclePrediction,
)
from apps.users.models import TermsAcceptance

User = get_user_model()


class CycleExportAPIViewTest(TestCase):
    """Tests for the CycleExportAPIView endpoint."""

    def setUp(self):
        """Set up test user and cycle data."""
        self.user = self._create_test_user()
        self.client = Client()
        self.client.login(email="test@example.com", password="testpass123")
        self.url = reverse("health:cycle_export_api")

        # Clear cache before each test
        cache.clear()

    def _create_test_user(self, email="test@example.com", password="testpass123"):
        """Create a test user with terms accepted and onboarding completed."""
        from django.conf import settings
        user = User.objects.create_user(email=email, password=password)
        # Accept terms (required by middleware) - use current version
        current_terms_version = settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        TermsAcceptance.objects.create(user=user, terms_version=current_terms_version)
        # Complete onboarding
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user

    def _enable_cycle_tracking(self):
        """Enable cycle tracking for the test user."""
        return CycleSettings.objects.create(
            user=self.user,
            cycle_tracking_enabled=True,
            average_cycle_length=28,
            average_period_length=5,
        )

    def _create_test_data(self):
        """Create test cycle data."""
        settings = self._enable_cycle_tracking()

        # Create a cycle
        cycle = Cycle.objects.create(
            user=self.user,
            start_date=date.today() - timedelta(days=10),
            period_end_date=date.today() - timedelta(days=5),
            cycle_number=1,
        )

        # Create daily logs
        for i in range(5):
            CycleDailyLog.objects.create(
                user=self.user,
                log_date=date.today() - timedelta(days=i),
                flow_level="medium" if i < 3 else "light",
                mood="happy",
                energy_level=3,
            )

        return settings, cycle

    def test_export_requires_authentication(self):
        """Unauthenticated users cannot access export."""
        self.client.logout()
        response = self.client.get(self.url)
        # Should redirect to login
        self.assertEqual(response.status_code, 302)

    def test_export_requires_cycle_tracking_enabled(self):
        """Export requires cycle tracking to be enabled."""
        # No CycleSettings created
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_export_json_format(self):
        """Export returns JSON format when requested."""
        self._create_test_data()
        response = self.client.get(self.url, {"format": "json"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(".json", response["Content-Disposition"])

        # Verify content is valid JSON
        content = response.content.decode("utf-8")
        data = json.loads(content)
        self.assertIn("metadata", data)
        self.assertIn("daily_logs", data)
        self.assertIn("cycles", data)

    def test_export_csv_format(self):
        """Export returns CSV format when requested."""
        self._create_test_data()
        response = self.client.get(self.url, {"format": "csv"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(".csv", response["Content-Disposition"])

        # Verify content has CSV headers
        content = response.content.decode("utf-8")
        self.assertIn("id,log_date,flow_level", content)

    def test_export_default_format_is_json(self):
        """Export defaults to JSON when no format specified."""
        self._create_test_data()
        response = self.client.get(self.url)  # No format param

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_export_invalid_format_returns_400(self):
        """Export returns 400 for invalid format."""
        self._enable_cycle_tracking()
        response = self.client.get(self.url, {"format": "xml"})

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("error", data)
        self.assertIn("Invalid format", data["error"])

    def test_export_empty_data_returns_204(self):
        """Export returns 204 when user has no cycle data."""
        self._enable_cycle_tracking()  # But no daily logs, cycles, etc.
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 204)

    @patch('django.core.cache.cache')
    def test_export_rate_limiting(self, mock_cache):
        """Export is rate limited to 5 per hour per user."""
        self._create_test_data()

        # Simulate cache behavior - increment counter each time
        export_counts = {'count': 0}
        def get_side_effect(key, default=0):
            return export_counts['count']

        def incr_side_effect(key, delta=1, version=None):
            export_counts['count'] += delta
            return export_counts['count']

        def set_side_effect(key, value, timeout=None):
            export_counts['count'] = value

        mock_cache.get.side_effect = get_side_effect
        mock_cache.incr.side_effect = incr_side_effect
        mock_cache.set.side_effect = set_side_effect

        # First 5 requests should succeed
        for i in range(5):
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200, f"Request {i+1} should succeed")
            remaining = int(response.get("X-Exports-Remaining", -1))
            self.assertEqual(remaining, 4 - i)

        # 6th request should be rate limited
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 429)
        data = response.json()
        self.assertIn("error", data)
        self.assertIn("rate limit", data["error"].lower())
        self.assertEqual(data["exports_remaining"], 0)

    @patch('django.core.cache.cache')
    def test_rate_limit_is_per_user(self, mock_cache):
        """Rate limit is tracked per user, not globally."""
        self._create_test_data()

        # Create second user with cycle tracking
        user2 = self._create_test_user(
            email="test2@example.com",
            password="testpass123"
        )
        CycleSettings.objects.create(
            user=user2,
            cycle_tracking_enabled=True,
        )
        CycleDailyLog.objects.create(
            user=user2,
            log_date=date.today(),
            flow_level="medium",
        )

        # Simulate cache - user1 exhausted, user2 fresh
        user_counts = {}
        def get_side_effect(key, default=0):
            return user_counts.get(key, default)

        def incr_side_effect(key, delta=1, version=None):
            user_counts[key] = user_counts.get(key, 0) + delta
            return user_counts[key]

        def set_side_effect(key, value, timeout=None):
            user_counts[key] = value

        mock_cache.get.side_effect = get_side_effect
        mock_cache.incr.side_effect = incr_side_effect
        mock_cache.set.side_effect = set_side_effect

        # Exhaust rate limit for first user
        for _ in range(5):
            self.client.get(self.url)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 429)

        # Second user should still be able to export
        self.client.logout()
        self.client.login(email="test2@example.com", password="testpass123")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_export_includes_remaining_header(self):
        """Export response includes X-Exports-Remaining header."""
        self._create_test_data()
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("X-Exports-Remaining", response)
        remaining = int(response["X-Exports-Remaining"])
        self.assertEqual(remaining, 4)  # 5 - 1 = 4


class CycleExportServiceIntegrationTest(TestCase):
    """Integration tests for export service with API endpoint."""

    def setUp(self):
        """Set up test user and data."""
        self.user = self._create_test_user()
        self.client = Client()
        self.client.login(email="test@example.com", password="testpass123")
        self.url = reverse("health:cycle_export_api")
        cache.clear()

    def _create_test_user(self, email="test@example.com", password="testpass123"):
        """Create a test user with terms accepted and onboarding completed."""
        from django.conf import settings
        user = User.objects.create_user(email=email, password=password)
        # Accept terms (required by middleware) - use current version
        current_terms_version = settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        TermsAcceptance.objects.create(user=user, terms_version=current_terms_version)
        # Complete onboarding
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user

    def test_exported_json_structure(self):
        """Exported JSON has correct structure."""
        CycleSettings.objects.create(
            user=self.user,
            cycle_tracking_enabled=True,
            average_cycle_length=28,
            average_period_length=5,
            fertile_window_tracking_enabled=True,
        )

        # Note: cycle_length and period_length are computed properties,
        # derived from start_date/end_date and start_date/period_end_date
        Cycle.objects.create(
            user=self.user,
            start_date=date.today() - timedelta(days=28),
            end_date=date.today() - timedelta(days=1),
            period_end_date=date.today() - timedelta(days=23),
            cycle_number=1,
        )

        CycleDailyLog.objects.create(
            user=self.user,
            log_date=date.today(),
            flow_level="medium",
            symptoms=["cramps", "fatigue"],
            mood="neutral",
            energy_level=2,
        )

        CyclePrediction.objects.create(
            user=self.user,
            predicted_period_start=date.today() + timedelta(days=14),
            predicted_period_end=date.today() + timedelta(days=19),
            prediction_confidence=Decimal("0.75"),
        )

        response = self.client.get(self.url, {"format": "json"})
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content.decode("utf-8"))

        # Check metadata
        self.assertIn("metadata", data)
        self.assertIn("export_version", data["metadata"])
        self.assertIn("exported_at", data["metadata"])

        # Check settings
        self.assertIn("settings", data)
        self.assertEqual(data["settings"]["average_cycle_length"], 28)

        # Check daily logs
        self.assertIn("daily_logs", data)
        self.assertEqual(len(data["daily_logs"]), 1)
        self.assertEqual(data["daily_logs"][0]["flow_level"], "medium")

        # Check cycles
        self.assertIn("cycles", data)
        self.assertGreaterEqual(len(data["cycles"]), 1)
        # Check that cycle data has expected structure
        self.assertIn("cycle_number", data["cycles"][0])

        # Check predictions
        self.assertIn("predictions", data)
        self.assertEqual(len(data["predictions"]), 1)


class CycleDeleteAllAPIViewTest(TestCase):
    """Tests for the CycleDeleteAllAPIView endpoint."""

    def setUp(self):
        """Set up test user and cycle data."""
        self.user = self._create_test_user()
        self.client = Client()
        self.client.login(email="test@example.com", password="testpass123")
        self.url = reverse("health:cycle_delete_all_api")

    def _create_test_user(self, email="test@example.com", password="testpass123"):
        """Create a test user with terms accepted and onboarding completed."""
        from django.conf import settings
        user = User.objects.create_user(email=email, password=password)
        # Accept terms (required by middleware) - use current version
        current_terms_version = settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        TermsAcceptance.objects.create(user=user, terms_version=current_terms_version)
        # Complete onboarding
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user

    def _create_test_data(self):
        """Create test cycle data."""
        settings = CycleSettings.objects.create(
            user=self.user,
            cycle_tracking_enabled=True,
            average_cycle_length=28,
            average_period_length=5,
        )

        # Create cycles
        Cycle.objects.create(
            user=self.user,
            start_date=date.today() - timedelta(days=28),
            period_end_date=date.today() - timedelta(days=23),
            cycle_number=1,
        )

        # Create daily logs
        for i in range(3):
            CycleDailyLog.objects.create(
                user=self.user,
                log_date=date.today() - timedelta(days=i),
                flow_level="medium",
            )

        # Create prediction
        CyclePrediction.objects.create(
            user=self.user,
            predicted_period_start=date.today() + timedelta(days=14),
            predicted_period_end=date.today() + timedelta(days=19),
            prediction_confidence=Decimal("0.75"),
            prediction_algorithm_version="v1.0",
        )

        return settings

    def test_delete_requires_authentication(self):
        """Unauthenticated users cannot delete data."""
        self.client.logout()
        response = self.client.post(
            self.url,
            data=json.dumps({"confirmation": "DELETE ALL MY CYCLE DATA"}),
            content_type="application/json",
        )
        # Should redirect to login
        self.assertEqual(response.status_code, 302)

    def test_delete_requires_cycle_tracking_enabled(self):
        """Delete requires cycle tracking to be enabled."""
        # No CycleSettings created
        response = self.client.post(
            self.url,
            data=json.dumps({"confirmation": "DELETE ALL MY CYCLE DATA"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn("not enabled", data["error"])

    def test_delete_requires_confirmation(self):
        """Delete requires correct confirmation text."""
        self._create_test_data()
        response = self.client.post(
            self.url,
            data=json.dumps({"confirmation": "wrong text"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("does not match", data["error"])

    def test_delete_requires_json_body(self):
        """Delete requires valid JSON body."""
        self._create_test_data()
        response = self.client.post(
            self.url,
            data="not json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("Invalid JSON", data["error"])

    def test_soft_delete_success(self):
        """Soft delete marks all records as deleted."""
        self._create_test_data()

        # Verify data exists before deletion
        self.assertEqual(CycleDailyLog.objects.filter(user=self.user).count(), 3)
        self.assertEqual(Cycle.objects.filter(user=self.user).count(), 1)
        self.assertEqual(CyclePrediction.objects.filter(user=self.user).count(), 1)

        response = self.client.post(
            self.url,
            data=json.dumps({"confirmation": "DELETE ALL MY CYCLE DATA"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data["success"])
        self.assertEqual(data["deletion_type"], "soft")
        self.assertEqual(data["counts"]["daily_logs"], 3)
        self.assertEqual(data["counts"]["cycles"], 1)
        self.assertEqual(data["counts"]["predictions"], 1)
        self.assertEqual(data["counts"]["settings"], 1)
        self.assertEqual(data["total_deleted"], 6)  # 3 + 1 + 1 + 1

        # Verify data is soft-deleted (not visible via normal manager)
        self.assertEqual(CycleDailyLog.objects.filter(user=self.user).count(), 0)
        self.assertEqual(Cycle.objects.filter(user=self.user).count(), 0)
        self.assertEqual(CyclePrediction.objects.filter(user=self.user).count(), 0)

        # But still exists via all_objects
        self.assertEqual(CycleDailyLog.all_objects.filter(user=self.user).count(), 3)
        self.assertEqual(Cycle.all_objects.filter(user=self.user).count(), 1)
        self.assertEqual(CyclePrediction.all_objects.filter(user=self.user).count(), 1)

    def test_hard_delete_success(self):
        """Hard delete permanently removes all records."""
        self._create_test_data()

        response = self.client.post(
            self.url,
            data=json.dumps({
                "confirmation": "DELETE ALL MY CYCLE DATA",
                "hard_delete": True,
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data["success"])
        self.assertEqual(data["deletion_type"], "hard")

        # Verify data is completely gone
        self.assertEqual(CycleDailyLog.all_objects.filter(user=self.user).count(), 0)
        self.assertEqual(Cycle.all_objects.filter(user=self.user).count(), 0)
        self.assertEqual(CyclePrediction.all_objects.filter(user=self.user).count(), 0)
        self.assertEqual(CycleSettings.all_objects.filter(user=self.user).count(), 0)

    def test_delete_only_affects_own_data(self):
        """Delete only affects the authenticated user's data."""
        self._create_test_data()

        # Create second user with data
        user2 = self._create_test_user(email="test2@example.com")
        CycleSettings.objects.create(
            user=user2,
            cycle_tracking_enabled=True,
        )
        CycleDailyLog.objects.create(
            user=user2,
            log_date=date.today(),
            flow_level="light",
        )

        # Delete first user's data
        response = self.client.post(
            self.url,
            data=json.dumps({"confirmation": "DELETE ALL MY CYCLE DATA"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        # Second user's data should still exist
        self.assertEqual(CycleDailyLog.objects.filter(user=user2).count(), 1)
        self.assertEqual(CycleSettings.objects.filter(user=user2).count(), 1)
