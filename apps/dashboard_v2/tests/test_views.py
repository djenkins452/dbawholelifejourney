"""Tests for Dashboard V2 views."""

from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse

from apps.users.models import TermsAcceptance, User


class DashboardV2ViewTest(TestCase):
    """Tests for the main Dashboard V2 view."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="dashv2@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.client = Client()
        self.client.login(email="dashv2@test.com", password="testpass123")

    def test_home_renders(self):
        """Dashboard V2 home page returns 200."""
        response = self.client.get(reverse("dashboard_v2:home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard_v2/home.html")

    def test_home_context_keys(self):
        """Dashboard V2 home page has expected context keys."""
        response = self.client.get(reverse("dashboard_v2:home"))
        self.assertIn("greeting", response.context)
        self.assertIn("time_phase", response.context)
        self.assertIn("goal_momentum", response.context)
        self.assertIn("daily_progress", response.context)
        self.assertIn("current_date", response.context)

    def test_home_requires_login(self):
        """Dashboard V2 requires authentication."""
        self.client.logout()
        response = self.client.get(reverse("dashboard_v2:home"))
        self.assertEqual(response.status_code, 302)

    def test_execution_section(self):
        """Execution section HTMX endpoint returns 200."""
        response = self.client.get(reverse("dashboard_v2:section_execution"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard_v2/sections/execution.html")

    def test_state_panel_section(self):
        """State panel HTMX endpoint returns 200."""
        response = self.client.get(reverse("dashboard_v2:section_state"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard_v2/sections/state_panel.html")

    def test_celebration_section(self):
        """Celebration section HTMX endpoint returns 200."""
        response = self.client.get(reverse("dashboard_v2:section_celebration"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard_v2/sections/celebration.html")

    def test_insights_section(self):
        """Insights section HTMX endpoint returns 200."""
        response = self.client.get(reverse("dashboard_v2:section_insights"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard_v2/sections/insights.html")


class TaskToggleActionTest(TestCase):
    """Tests for the task toggle action endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="toggle@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.client = Client()
        self.client.login(email="toggle@test.com", password="testpass123")

    def test_toggle_task_complete(self):
        """POST to task toggle completes a pending task."""
        from apps.core.utils import get_user_today
        from apps.life.models import Task

        today = get_user_today(self.user)
        task = Task.objects.create(
            user=self.user, title="Test Task", due_date=today,
            completion_status="pending",
        )

        response = self.client.post(
            reverse("dashboard_v2:task_toggle", kwargs={"pk": task.pk})
        )
        self.assertEqual(response.status_code, 200)

        task.refresh_from_db()
        self.assertEqual(task.completion_status, "completed")

    def test_toggle_task_uncomplete(self):
        """POST to task toggle uncompletes a completed task."""
        from apps.core.utils import get_user_today
        from apps.life.models import Task

        today = get_user_today(self.user)
        task = Task.objects.create(
            user=self.user, title="Done Task", due_date=today,
            completion_status="completed",
        )

        response = self.client.post(
            reverse("dashboard_v2:task_toggle", kwargs={"pk": task.pk})
        )
        self.assertEqual(response.status_code, 200)

        task.refresh_from_db()
        self.assertEqual(task.completion_status, "pending")

    def test_toggle_other_users_task_404(self):
        """Cannot toggle another user's task."""
        other_user = User.objects.create_user(
            email="other@test.com", password="testpass123"
        )
        from apps.core.utils import get_user_today
        from apps.life.models import Task

        today = get_user_today(other_user)
        task = Task.objects.create(
            user=other_user, title="Not Mine", due_date=today,
            completion_status="pending",
        )

        response = self.client.post(
            reverse("dashboard_v2:task_toggle", kwargs={"pk": task.pk})
        )
        self.assertEqual(response.status_code, 404)


class CelebrationViewTest(TestCase):
    """Tests for celebration reveal/dismiss endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="celeb@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.client = Client()
        self.client.login(email="celeb@test.com", password="testpass123")

    def test_reveal_celebration(self):
        """POST to reveal sets status to revealed."""
        from datetime import timedelta

        from django.utils import timezone

        from apps.dashboard_v2.models import PreparedCelebration

        celebration = PreparedCelebration.objects.create(
            user=self.user,
            celebration_type="streak_milestone",
            celebration_status="ready",
            headline="7-Day Streak!",
            narrative="Well done.",
            expires_at=timezone.now() + timedelta(days=7),
            dedupe_key="test:view:reveal",
        )

        response = self.client.post(
            reverse("dashboard_v2:celebration_reveal", kwargs={"pk": celebration.pk})
        )
        self.assertEqual(response.status_code, 200)

        celebration.refresh_from_db()
        self.assertEqual(celebration.celebration_status, "revealed")

    def test_dismiss_celebration(self):
        """POST to dismiss sets status to dismissed."""
        from datetime import timedelta

        from django.utils import timezone

        from apps.dashboard_v2.models import PreparedCelebration

        celebration = PreparedCelebration.objects.create(
            user=self.user,
            celebration_type="streak_milestone",
            celebration_status="ready",
            headline="Test",
            narrative="Test.",
            expires_at=timezone.now() + timedelta(days=7),
            dedupe_key="test:view:dismiss",
        )

        response = self.client.post(
            reverse("dashboard_v2:celebration_dismiss", kwargs={"pk": celebration.pk})
        )
        self.assertEqual(response.status_code, 200)

        celebration.refresh_from_db()
        self.assertEqual(celebration.celebration_status, "dismissed")
