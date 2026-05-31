"""Phase 5 — Mission Inspiration / emotional motivation layer.

Covers the new optional, generic motivation assets: hero image removal,
GoalMotivationLink CRUD, and GoalVictoryMilestone CRUD. The standing contract:
victory milestones are a SEPARATE relation and must NEVER affect the major
milestone counts that drive mission phase + ring truth.
"""
from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.purpose.models import (
    LifeGoal,
    GoalMilestone,
    GoalMotivationLink,
    GoalVictoryMilestone,
)
from apps.users.models import TermsAcceptance

User = get_user_model()


def _make_user(email):
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.purpose_enabled = True
    user.preferences.save()
    return user


class MotivationLinkViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = _make_user("links@test.com")
        self.client.login(email="links@test.com", password="testpass123")
        self.goal = LifeGoal.objects.create(
            user=self.user, title="Linked Mission", status="active",
        )

    def test_create_link(self):
        url = reverse("purpose:motivation_link_create", args=[self.goal.pk])
        resp = self.client.post(url, {
            "title": "Race Website", "url": "https://example.com", "icon": "🏁",
        })
        self.assertEqual(resp.status_code, 302)
        link = GoalMotivationLink.objects.get(goal=self.goal)
        self.assertEqual(link.title, "Race Website")
        self.assertEqual(link.icon, "🏁")

    def test_create_link_requires_title_and_url(self):
        url = reverse("purpose:motivation_link_create", args=[self.goal.pk])
        self.client.post(url, {"title": "", "url": "https://example.com"})
        self.assertEqual(self.goal.motivation_links.count(), 0)

    def test_create_link_rejects_invalid_url(self):
        url = reverse("purpose:motivation_link_create", args=[self.goal.pk])
        self.client.post(url, {"title": "Bad", "url": "not-a-url"})
        self.assertEqual(self.goal.motivation_links.count(), 0)

    def test_update_link(self):
        link = GoalMotivationLink.objects.create(
            goal=self.goal, title="Old", url="https://example.com",
        )
        url = reverse("purpose:motivation_link_update", args=[link.pk])
        self.client.post(url, {"title": "New", "url": "https://new.com"})
        link.refresh_from_db()
        self.assertEqual(link.title, "New")
        self.assertEqual(link.url, "https://new.com")

    def test_delete_link(self):
        link = GoalMotivationLink.objects.create(
            goal=self.goal, title="Gone", url="https://example.com",
        )
        url = reverse("purpose:motivation_link_delete", args=[link.pk])
        self.client.post(url)
        self.assertFalse(GoalMotivationLink.objects.filter(pk=link.pk).exists())

    def test_cannot_touch_other_users_link(self):
        other = _make_user("links-other@test.com")
        other_goal = LifeGoal.objects.create(
            user=other, title="Theirs", status="active",
        )
        link = GoalMotivationLink.objects.create(
            goal=other_goal, title="Theirs", url="https://example.com",
        )
        url = reverse("purpose:motivation_link_delete", args=[link.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(GoalMotivationLink.objects.filter(pk=link.pk).exists())


class VictoryMilestoneViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = _make_user("wins@test.com")
        self.client.login(email="wins@test.com", password="testpass123")
        self.goal = LifeGoal.objects.create(
            user=self.user, title="Win Mission", status="active",
        )

    def test_create_win(self):
        url = reverse("purpose:victory_create", args=[self.goal.pk])
        resp = self.client.post(url, {"title": "First 5K", "icon": "🏃"})
        self.assertEqual(resp.status_code, 302)
        win = GoalVictoryMilestone.objects.get(goal=self.goal)
        self.assertEqual(win.title, "First 5K")
        self.assertFalse(win.completed)

    def test_toggle_win(self):
        win = GoalVictoryMilestone.objects.create(goal=self.goal, title="Win")
        url = reverse("purpose:victory_toggle", args=[win.pk])
        self.client.post(url)
        win.refresh_from_db()
        self.assertTrue(win.completed)
        self.assertIsNotNone(win.completed_date)
        self.client.post(url)
        win.refresh_from_db()
        self.assertFalse(win.completed)
        self.assertIsNone(win.completed_date)

    def test_delete_win(self):
        win = GoalVictoryMilestone.objects.create(goal=self.goal, title="Win")
        url = reverse("purpose:victory_delete", args=[win.pk])
        self.client.post(url)
        self.assertFalse(GoalVictoryMilestone.objects.filter(pk=win.pk).exists())

    def test_victories_do_not_affect_milestone_counts(self):
        # The core safety invariant: victory milestones are decoupled from the
        # major GoalMilestone counts that drive mission phase + progress ring.
        GoalMilestone.objects.create(goal=self.goal, title="Major", completed=False)
        GoalVictoryMilestone.objects.create(
            goal=self.goal, title="Win", completed=True,
        )
        self.assertEqual(self.goal.milestone_count, 1)
        self.assertEqual(self.goal.completed_milestone_count, 0)
        self.assertEqual(self.goal.milestone_progress_percent, 0)


class HeroImageRemoveViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = _make_user("hero@test.com")
        self.client.login(email="hero@test.com", password="testpass123")
        self.goal = LifeGoal.objects.create(
            user=self.user, title="Hero Mission", status="active",
        )

    def test_remove_hero_when_absent_is_safe(self):
        url = reverse("purpose:goal_hero_remove", args=[self.goal.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.goal.refresh_from_db()
        self.assertFalse(self.goal.hero_image)


class GoalDetailRenderTests(TestCase):
    """Smoke tests — the Phase 5 template additions must render cleanly."""

    def setUp(self):
        self.client = Client()
        self.user = _make_user("render@test.com")
        self.client.login(email="render@test.com", password="testpass123")
        self.goal = LifeGoal.objects.create(
            user=self.user, title="Render Mission", status="active",
            is_primary_mission=True, motivation_note="Because it matters.",
        )

    def test_detail_renders_with_inspiration_and_wins(self):
        GoalMotivationLink.objects.create(
            goal=self.goal, title="Race", url="https://example.com", icon="🏁",
        )
        GoalVictoryMilestone.objects.create(
            goal=self.goal, title="First 5K", completed=True,
        )
        url = reverse("purpose:goal_detail", args=[self.goal.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Mission Inspiration")
        self.assertContains(resp, "Wins Along the Way")
        self.assertContains(resp, "Race")
        self.assertContains(resp, "First 5K")

    def test_detail_renders_form_page(self):
        url = reverse("purpose:goal_update", args=[self.goal.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Inspiration Image")
        self.assertContains(resp, "Motivation Note")
