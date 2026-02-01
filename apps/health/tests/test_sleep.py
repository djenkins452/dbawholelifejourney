"""
Sleep Tracking Tests

Tests for sleep tracking functionality including model, views, and API.

Location: apps/health/tests/test_sleep.py
"""

import json
from datetime import date, timedelta

from django.conf import settings
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.health.models import SleepEntry
from apps.health.serializers import SleepEntrySerializer
from apps.users.models import TermsAcceptance

User = get_user_model()


def create_test_user(email="test@example.com", password="testpass123"):
    """Create a test user with terms accepted and onboarding completed."""
    user = User.objects.create_user(email=email, password=password)
    current_terms_version = settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
    TermsAcceptance.objects.create(user=user, terms_version=current_terms_version)
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


class SleepEntryModelTest(TestCase):
    """Tests for the SleepEntry model."""

    def setUp(self):
        self.user = create_test_user()
        self.now = timezone.now()
        self.bedtime = self.now.replace(hour=22, minute=30, second=0, microsecond=0) - timedelta(days=1)
        self.wake_time = self.now.replace(hour=6, minute=30, second=0, microsecond=0)

    def test_create_sleep_entry(self):
        """Sleep entry can be created with required fields."""
        entry = SleepEntry.objects.create(
            user=self.user,
            sleep_date=date.today() - timedelta(days=1),
            bedtime=self.bedtime,
            wake_time=self.wake_time,
            total_duration_minutes=480
        )
        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.total_duration_minutes, 480)
        self.assertEqual(entry.source, "manual")

    def test_total_hours_property(self):
        """total_hours property returns correct value."""
        entry = SleepEntry.objects.create(
            user=self.user,
            sleep_date=date.today() - timedelta(days=1),
            bedtime=self.bedtime,
            wake_time=self.wake_time,
            total_duration_minutes=480
        )
        self.assertEqual(entry.total_hours, 8.0)

    def test_asleep_hours_property(self):
        """asleep_hours property returns correct value."""
        entry = SleepEntry.objects.create(
            user=self.user,
            sleep_date=date.today() - timedelta(days=1),
            bedtime=self.bedtime,
            wake_time=self.wake_time,
            total_duration_minutes=480,
            asleep_duration_minutes=450
        )
        self.assertEqual(entry.asleep_hours, 7.5)

    def test_asleep_hours_none_when_not_set(self):
        """asleep_hours returns None when asleep_duration_minutes not set."""
        entry = SleepEntry.objects.create(
            user=self.user,
            sleep_date=date.today() - timedelta(days=1),
            bedtime=self.bedtime,
            wake_time=self.wake_time,
            total_duration_minutes=480
        )
        self.assertIsNone(entry.asleep_hours)

    def test_quality_display(self):
        """quality_display property returns correct label."""
        entry = SleepEntry.objects.create(
            user=self.user,
            sleep_date=date.today() - timedelta(days=1),
            bedtime=self.bedtime,
            wake_time=self.wake_time,
            total_duration_minutes=480,
            quality_rating="good"
        )
        self.assertEqual(entry.quality_display, "Good - Felt rested")

    def test_has_stage_data(self):
        """has_stage_data returns True when stage data exists."""
        entry = SleepEntry.objects.create(
            user=self.user,
            sleep_date=date.today() - timedelta(days=1),
            bedtime=self.bedtime,
            wake_time=self.wake_time,
            total_duration_minutes=480,
            stage_deep_minutes=60,
            stage_rem_minutes=90
        )
        self.assertTrue(entry.has_stage_data)

    def test_has_stage_data_false(self):
        """has_stage_data returns False when no stage data."""
        entry = SleepEntry.objects.create(
            user=self.user,
            sleep_date=date.today() - timedelta(days=1),
            bedtime=self.bedtime,
            wake_time=self.wake_time,
            total_duration_minutes=480
        )
        self.assertFalse(entry.has_stage_data)

    def test_source_display(self):
        """source_display returns correct label."""
        entry = SleepEntry.objects.create(
            user=self.user,
            sleep_date=date.today() - timedelta(days=1),
            bedtime=self.bedtime,
            wake_time=self.wake_time,
            total_duration_minutes=480,
            source="apple_health"
        )
        self.assertEqual(entry.source_display, "Apple Health")

    def test_entry_ordering(self):
        """Entries are ordered by most recent sleep_date first."""
        SleepEntry.objects.create(
            user=self.user,
            sleep_date=date.today() - timedelta(days=2),
            bedtime=self.bedtime - timedelta(days=1),
            wake_time=self.wake_time - timedelta(days=1),
            total_duration_minutes=480
        )
        entry2 = SleepEntry.objects.create(
            user=self.user,
            sleep_date=date.today() - timedelta(days=1),
            bedtime=self.bedtime,
            wake_time=self.wake_time,
            total_duration_minutes=480
        )
        entries = SleepEntry.objects.filter(user=self.user)
        self.assertEqual(entries[0], entry2)


class SleepEntryViewTest(TestCase):
    """Tests for Sleep web views."""

    def setUp(self):
        self.user = create_test_user()
        self.client = Client()
        self.client.login(email="test@example.com", password="testpass123")

        self.now = timezone.now()
        self.bedtime = self.now.replace(hour=22, minute=30, second=0, microsecond=0) - timedelta(days=1)
        self.wake_time = self.now.replace(hour=6, minute=30, second=0, microsecond=0)

    def test_sleep_list_view(self):
        """Sleep list view returns 200."""
        response = self.client.get(reverse("health:sleep_list"))
        self.assertEqual(response.status_code, 200)

    def test_sleep_list_shows_entries(self):
        """Sleep list displays entries."""
        SleepEntry.objects.create(
            user=self.user,
            sleep_date=date.today() - timedelta(days=1),
            bedtime=self.bedtime,
            wake_time=self.wake_time,
            total_duration_minutes=480
        )
        response = self.client.get(reverse("health:sleep_list"))
        self.assertContains(response, "8")

    def test_sleep_create_view(self):
        """Sleep create view returns 200."""
        response = self.client.get(reverse("health:sleep_create"))
        self.assertEqual(response.status_code, 200)

    def test_sleep_quick_create_view(self):
        """Sleep quick create view returns 200."""
        response = self.client.get(reverse("health:sleep_quick"))
        self.assertEqual(response.status_code, 200)

    def test_sleep_quick_create_post(self):
        """Quick sleep form creates entry."""
        response = self.client.post(reverse("health:sleep_quick"), {
            "sleep_date": (date.today() - timedelta(days=1)).isoformat(),
            "hours_slept": "7.5",
            "quality_rating": "good"
        })
        self.assertEqual(response.status_code, 302)  # Redirects on success

        entry = SleepEntry.objects.filter(user=self.user).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.total_duration_minutes, 450)  # 7.5 hours
        self.assertEqual(entry.quality_rating, "good")

    def test_sleep_update_view(self):
        """Sleep update view returns 200."""
        entry = SleepEntry.objects.create(
            user=self.user,
            sleep_date=date.today() - timedelta(days=1),
            bedtime=self.bedtime,
            wake_time=self.wake_time,
            total_duration_minutes=480
        )
        response = self.client.get(reverse("health:sleep_update", args=[entry.pk]))
        self.assertEqual(response.status_code, 200)

    def test_sleep_delete_view(self):
        """Sleep delete removes entry."""
        entry = SleepEntry.objects.create(
            user=self.user,
            sleep_date=date.today() - timedelta(days=1),
            bedtime=self.bedtime,
            wake_time=self.wake_time,
            total_duration_minutes=480
        )
        response = self.client.post(reverse("health:sleep_delete", args=[entry.pk]))
        self.assertEqual(response.status_code, 302)

        # Soft delete - entry still exists but is_deleted=True
        entry.refresh_from_db()
        self.assertTrue(entry.is_deleted)

    def test_cannot_access_other_users_entry(self):
        """Cannot access another user's sleep entry."""
        other_user = create_test_user(
            email="other@example.com",
            password="testpass123"
        )
        entry = SleepEntry.objects.create(
            user=other_user,
            sleep_date=date.today() - timedelta(days=1),
            bedtime=self.bedtime,
            wake_time=self.wake_time,
            total_duration_minutes=480
        )
        response = self.client.get(reverse("health:sleep_update", args=[entry.pk]))
        self.assertEqual(response.status_code, 404)


class SleepAPITest(TestCase):
    """Tests for Sleep API endpoints."""

    def setUp(self):
        self.user = create_test_user()
        self.client = Client()
        self.client.login(email="test@example.com", password="testpass123")

        self.now = timezone.now()
        self.bedtime = self.now.replace(hour=22, minute=30, second=0, microsecond=0) - timedelta(days=1)
        self.wake_time = self.now.replace(hour=6, minute=30, second=0, microsecond=0)

    def test_api_list_empty(self):
        """API returns empty list when no entries."""
        response = self.client.get(reverse("health:sleep_api_list"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["entries"], [])
        self.assertEqual(data["total"], 0)

    def test_api_list_with_entries(self):
        """API returns entries."""
        SleepEntry.objects.create(
            user=self.user,
            sleep_date=date.today() - timedelta(days=1),
            bedtime=self.bedtime,
            wake_time=self.wake_time,
            total_duration_minutes=480
        )
        response = self.client.get(reverse("health:sleep_api_list"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["entries"]), 1)
        self.assertEqual(data["total"], 1)

    def test_api_create_entry(self):
        """API can create new entry."""
        response = self.client.post(
            reverse("health:sleep_api_list"),
            data=json.dumps({
                "sleep_date": (date.today() - timedelta(days=1)).isoformat(),
                "bedtime": self.bedtime.isoformat(),
                "wake_time": self.wake_time.isoformat(),
                "total_duration_minutes": 480,
                "quality_rating": "good",
                "source": "apple_health",
                "sync_id": "test-123"
            }),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["action"], "created")
        self.assertEqual(data["entry"]["total_hours"], 8.0)

    def test_api_upsert_by_sync_id(self):
        """API updates existing entry with same sync_id."""
        # Create initial entry
        SleepEntry.objects.create(
            user=self.user,
            sleep_date=date.today() - timedelta(days=1),
            bedtime=self.bedtime,
            wake_time=self.wake_time,
            total_duration_minutes=480,
            source="apple_health",
            sync_id="test-123"
        )

        # Post with same sync_id
        response = self.client.post(
            reverse("health:sleep_api_list"),
            data=json.dumps({
                "sleep_date": (date.today() - timedelta(days=1)).isoformat(),
                "bedtime": self.bedtime.isoformat(),
                "wake_time": self.wake_time.isoformat(),
                "total_duration_minutes": 500,  # Updated value
                "source": "apple_health",
                "sync_id": "test-123"
            }),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["action"], "updated")

        # Should still be only 1 entry
        self.assertEqual(SleepEntry.objects.filter(user=self.user).count(), 1)

    def test_api_bulk_sync(self):
        """API can bulk sync multiple entries."""
        entries = [
            {
                "sleep_date": (date.today() - timedelta(days=i)).isoformat(),
                "bedtime": (self.bedtime - timedelta(days=i)).isoformat(),
                "wake_time": (self.wake_time - timedelta(days=i)).isoformat(),
                "total_duration_minutes": 480,
                "source": "apple_health",
                "sync_id": f"bulk-test-{i}"
            }
            for i in range(1, 4)
        ]

        response = self.client.post(
            reverse("health:sleep_api_list"),
            data=json.dumps({"entries": entries}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["created"], 3)
        self.assertEqual(data["failed"], 0)

    def test_api_detail_get(self):
        """API can retrieve single entry."""
        entry = SleepEntry.objects.create(
            user=self.user,
            sleep_date=date.today() - timedelta(days=1),
            bedtime=self.bedtime,
            wake_time=self.wake_time,
            total_duration_minutes=480
        )
        response = self.client.get(reverse("health:sleep_api_detail", args=[entry.pk]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["entry"]["total_hours"], 8.0)

    def test_api_detail_not_found(self):
        """API returns 404 for missing entry."""
        response = self.client.get(reverse("health:sleep_api_detail", args=[99999]))
        self.assertEqual(response.status_code, 404)

    def test_api_detail_update(self):
        """API can update entry."""
        entry = SleepEntry.objects.create(
            user=self.user,
            sleep_date=date.today() - timedelta(days=1),
            bedtime=self.bedtime,
            wake_time=self.wake_time,
            total_duration_minutes=480
        )
        response = self.client.put(
            reverse("health:sleep_api_detail", args=[entry.pk]),
            data=json.dumps({
                "sleep_date": entry.sleep_date.isoformat(),
                "bedtime": self.bedtime.isoformat(),
                "wake_time": self.wake_time.isoformat(),
                "total_duration_minutes": 500,
                "quality_rating": "excellent"
            }),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)

        entry.refresh_from_db()
        self.assertEqual(entry.total_duration_minutes, 500)
        self.assertEqual(entry.quality_rating, "excellent")

    def test_api_detail_delete(self):
        """API can delete entry."""
        entry = SleepEntry.objects.create(
            user=self.user,
            sleep_date=date.today() - timedelta(days=1),
            bedtime=self.bedtime,
            wake_time=self.wake_time,
            total_duration_minutes=480
        )
        response = self.client.delete(reverse("health:sleep_api_detail", args=[entry.pk]))
        self.assertEqual(response.status_code, 200)

        entry.refresh_from_db()
        self.assertTrue(entry.is_deleted)

    def test_api_stats(self):
        """API returns sleep statistics."""
        # Create entries over past week
        for i in range(1, 8):
            SleepEntry.objects.create(
                user=self.user,
                sleep_date=date.today() - timedelta(days=i),
                bedtime=self.bedtime - timedelta(days=i),
                wake_time=self.wake_time - timedelta(days=i),
                total_duration_minutes=450 + (i * 10),  # Varying durations
                quality_rating="good"
            )

        response = self.client.get(reverse("health:sleep_api_stats") + "?days=7")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["entries_count"], 7)
        self.assertIn("avg_duration_hours", data)
        self.assertIn("quality_breakdown", data)
        self.assertEqual(data["quality_breakdown"]["good"], 7)

    def test_api_stats_empty(self):
        """API stats handles no data."""
        response = self.client.get(reverse("health:sleep_api_stats"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["entries_count"], 0)

    def test_api_sync_status(self):
        """API returns sync status per source."""
        SleepEntry.objects.create(
            user=self.user,
            sleep_date=date.today() - timedelta(days=1),
            bedtime=self.bedtime,
            wake_time=self.wake_time,
            total_duration_minutes=480,
            source="apple_health",
            sync_id="test-1"
        )

        response = self.client.get(reverse("health:sleep_api_sync_status"))
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("sources", data)
        self.assertIsNotNone(data["sources"]["apple_health"])
        self.assertEqual(data["sources"]["apple_health"]["entries_count"], 1)


class SleepEntrySerializerTest(TestCase):
    """Tests for SleepEntrySerializer."""

    def setUp(self):
        self.user = create_test_user()
        self.now = timezone.now()
        self.bedtime = self.now.replace(hour=22, minute=30, second=0, microsecond=0) - timedelta(days=1)
        self.wake_time = self.now.replace(hour=6, minute=30, second=0, microsecond=0)

    def test_serialize_entry(self):
        """Serializer correctly serializes entry."""
        entry = SleepEntry.objects.create(
            user=self.user,
            sleep_date=date.today() - timedelta(days=1),
            bedtime=self.bedtime,
            wake_time=self.wake_time,
            total_duration_minutes=480,
            quality_rating="good",
            stage_deep_minutes=60,
            stage_rem_minutes=90
        )
        serializer = SleepEntrySerializer(instance=entry)
        data = serializer.data

        self.assertEqual(data["total_hours"], 8.0)
        self.assertEqual(data["quality_display"], "Good - Felt rested")
        self.assertTrue(data["has_stage_data"])

    def test_deserialize_valid_data(self):
        """Serializer validates correct data."""
        data = {
            "sleep_date": (date.today() - timedelta(days=1)).isoformat(),
            "bedtime": self.bedtime.isoformat(),
            "wake_time": self.wake_time.isoformat(),
            "total_duration_minutes": 480,
            "quality_rating": "good"
        }
        serializer = SleepEntrySerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_deserialize_invalid_quality(self):
        """Serializer rejects invalid quality rating."""
        data = {
            "sleep_date": (date.today() - timedelta(days=1)).isoformat(),
            "bedtime": self.bedtime.isoformat(),
            "wake_time": self.wake_time.isoformat(),
            "total_duration_minutes": 480,
            "quality_rating": "invalid"
        }
        serializer = SleepEntrySerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("quality_rating", serializer.errors)

    def test_deserialize_invalid_duration(self):
        """Serializer rejects duration over 24 hours."""
        data = {
            "sleep_date": (date.today() - timedelta(days=1)).isoformat(),
            "bedtime": self.bedtime.isoformat(),
            "wake_time": self.wake_time.isoformat(),
            "total_duration_minutes": 1500  # Over 24 hours
        }
        serializer = SleepEntrySerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("total_duration_minutes", serializer.errors)

    def test_wake_time_before_bedtime(self):
        """Serializer rejects wake time before bedtime."""
        data = {
            "sleep_date": (date.today() - timedelta(days=1)).isoformat(),
            "bedtime": self.wake_time.isoformat(),  # Swapped
            "wake_time": self.bedtime.isoformat(),  # Swapped
            "total_duration_minutes": 480
        }
        serializer = SleepEntrySerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("wake_time", serializer.errors)
