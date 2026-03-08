"""
Faith Engagement Utility Tests

Tests for apps.faith.engagement — centralised daily engagement check.

Location: apps/faith/tests/test_engagement.py
"""
from datetime import date, timedelta

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.faith.engagement import (
    get_faith_engagement_details,
    is_faith_engaged_today,
)
from apps.faith.models import (
    ReadingPlanDay,
    ReadingPlanTemplate,
    UserReadingPlan,
    UserReadingProgress,
)
from apps.life.models import Task

User = get_user_model()


class FaithEngagementTestCase(TestCase):
    """Base test case with common setup for engagement tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )
        self.today = date.today()

    def _create_reading_progress(self, completed_at=None):
        """Helper to create a completed reading plan day."""
        import uuid
        slug = f"test-plan-{uuid.uuid4().hex[:8]}"
        template = ReadingPlanTemplate.objects.create(
            title="Test Plan",
            slug=slug,
            description="A test reading plan",
            duration_days=7,
        )
        plan_day = ReadingPlanDay.objects.create(
            plan=template,
            day_number=1,
            title="Day 1",
            scripture_references=["John 1:1-5"],
        )
        user_plan = UserReadingPlan.objects.create(
            user=self.user,
            template=template,
            plan_status="active",
        )
        return UserReadingProgress.objects.create(
            user=self.user,
            user_plan=user_plan,
            plan_day=plan_day,
            is_completed=True,
            completed_at=completed_at or timezone.now(),
        )


class IsEngagedTodayTests(FaithEngagementTestCase):
    """Tests for is_faith_engaged_today()."""

    def test_no_activity_returns_false(self):
        """No reading or faith task -> not engaged."""
        self.assertFalse(is_faith_engaged_today(self.user, self.today))

    def test_reading_completed_returns_true(self):
        """Completing a reading plan day counts as engagement."""
        self._create_reading_progress()
        self.assertTrue(is_faith_engaged_today(self.user, self.today))

    def test_faith_task_completed_returns_true(self):
        """Completing a faith-linked task counts as engagement."""
        Task.objects.create(
            user=self.user,
            title="Go to Church",
            module="faith",
            completion_status='completed',
            completed_at=timezone.now(),
        )
        self.assertTrue(is_faith_engaged_today(self.user, self.today))

    def test_non_faith_task_does_not_count(self):
        """Completing a task without module='faith' doesn't count."""
        Task.objects.create(
            user=self.user,
            title="Workout",
            module="health",
            completion_status='completed',
            completed_at=timezone.now(),
        )
        self.assertFalse(is_faith_engaged_today(self.user, self.today))

    def test_task_no_module_does_not_count(self):
        """Completing a task with no module doesn't count."""
        Task.objects.create(
            user=self.user,
            title="Buy groceries",
            module="",
            completion_status='completed',
            completed_at=timezone.now(),
        )
        self.assertFalse(is_faith_engaged_today(self.user, self.today))

    def test_yesterday_activity_does_not_count(self):
        """Activity from yesterday doesn't satisfy today."""
        yesterday = timezone.now() - timedelta(days=1)
        Task.objects.create(
            user=self.user,
            title="Go to Church",
            module="faith",
            completion_status='completed',
            completed_at=yesterday,
        )
        self.assertFalse(is_faith_engaged_today(self.user, self.today))


class GetEngagementDetailsTests(FaithEngagementTestCase):
    """Tests for get_faith_engagement_details()."""

    def test_empty_state(self):
        """No activity returns all-False dict."""
        details = get_faith_engagement_details(self.user, self.today)
        self.assertFalse(details['reading_completed_today'])
        self.assertFalse(details['faith_task_completed_today'])
        self.assertFalse(details['faith_engaged_today'])

    def test_reading_only(self):
        """Reading completed but no task."""
        self._create_reading_progress()

        details = get_faith_engagement_details(self.user, self.today)
        self.assertTrue(details['reading_completed_today'])
        self.assertFalse(details['faith_task_completed_today'])
        self.assertTrue(details['faith_engaged_today'])

    def test_task_only(self):
        """Faith task completed but no reading."""
        Task.objects.create(
            user=self.user,
            title="Go to Church",
            module="faith",
            completion_status='completed',
            completed_at=timezone.now(),
        )

        details = get_faith_engagement_details(self.user, self.today)
        self.assertFalse(details['reading_completed_today'])
        self.assertTrue(details['faith_task_completed_today'])
        self.assertTrue(details['faith_engaged_today'])

    def test_both_sources(self):
        """Both reading and task completed."""
        self._create_reading_progress()
        Task.objects.create(
            user=self.user,
            title="Go to Church",
            module="faith",
            completion_status='completed',
            completed_at=timezone.now(),
        )

        details = get_faith_engagement_details(self.user, self.today)
        self.assertTrue(details['reading_completed_today'])
        self.assertTrue(details['faith_task_completed_today'])
        self.assertTrue(details['faith_engaged_today'])
