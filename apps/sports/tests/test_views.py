"""Tests for Sports domain views.

Architecture rule: All views gated on sports_enabled preference.
"""
from django.conf import settings
from django.test import TestCase, Client
from django.urls import reverse

from apps.sports.models import League, Sport, Team, UserTeamFollow
from apps.users.models import TermsAcceptance, User


def _create_test_user(email, password="testpass123"):
    """Create a test user with terms accepted and onboarding complete."""
    user = User.objects.create_user(email=email, password=password)
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    prefs = user.preferences
    prefs.has_completed_onboarding = True
    prefs.save()
    return user


class SportsViewGatingTest(TestCase):
    """Verify module gating — disabled sports redirects to preferences."""

    def setUp(self):
        self.user = _create_test_user(
            email="gating@example.com")
        self.client = Client()
        self.client.force_login(self.user)

    def test_hub_redirects_when_disabled(self):
        """Sports hub redirects to preferences when module is disabled."""
        response = self.client.get(reverse("sports:hub"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("preferences", response.url)

    def test_team_select_redirects_when_disabled(self):
        """Team select redirects to preferences when module is disabled."""
        response = self.client.get(reverse("sports:team_select"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("preferences", response.url)

    def test_hub_loads_when_enabled(self):
        """Sports hub loads when module is enabled."""
        prefs = self.user.preferences
        prefs.sports_enabled = True
        prefs.save()
        response = self.client.get(reverse("sports:hub"))
        self.assertEqual(response.status_code, 200)

    def test_team_select_loads_when_enabled(self):
        """Team select loads when module is enabled."""
        prefs = self.user.preferences
        prefs.sports_enabled = True
        prefs.save()
        response = self.client.get(reverse("sports:team_select"))
        self.assertEqual(response.status_code, 200)


class SportsHubViewTest(TestCase):
    def setUp(self):
        self.user = _create_test_user(
            email="hub@example.com")
        prefs = self.user.preferences
        prefs.sports_enabled = True
        prefs.save()
        self.client = Client()
        self.client.force_login(self.user)

    def test_empty_state_no_teams(self):
        """Hub shows empty state when no teams are followed."""
        response = self.client.get(reverse("sports:hub"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["has_teams"])

    def test_has_teams_context(self):
        """Hub sets has_teams=True when teams are followed."""
        sport = Sport.objects.create(name="Football", slug="football")
        league = League.objects.create(
            sport=sport, name="NFL", slug="nfl", abbreviation="NFL"
        )
        team = Team.objects.create(
            league=league, name="Chiefs", location="Kansas City", abbreviation="KC"
        )
        UserTeamFollow.objects.create(user=self.user, team=team, priority=1)

        response = self.client.get(reverse("sports:hub"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["has_teams"])


class FollowTeamViewTest(TestCase):
    def setUp(self):
        self.user = _create_test_user(
            email="follow@example.com")
        prefs = self.user.preferences
        prefs.sports_enabled = True
        prefs.save()
        self.client = Client()
        self.client.force_login(self.user)

        sport = Sport.objects.create(name="Football", slug="football")
        league = League.objects.create(
            sport=sport, name="NFL", slug="nfl", abbreviation="NFL"
        )
        self.team = Team.objects.create(
            league=league, name="Chiefs", location="Kansas City", abbreviation="KC"
        )

    def test_follow_team(self):
        """POST to follow_team creates UserTeamFollow."""
        response = self.client.post(
            reverse("sports:follow_team"),
            {"team_id": str(self.team.id), "priority": "1"},
        )
        # Check redirect destination
        redirect_url = response.get("Location", "")
        follow_exists = UserTeamFollow.objects.filter(
            user=self.user, team=self.team, is_active=True
        ).exists()
        self.assertTrue(
            follow_exists,
            f"Follow not created. Status: {response.status_code}, redirect: {redirect_url}"
        )

    def test_follow_team_idempotent(self):
        """Following same team twice updates rather than duplicates."""
        self.client.post(
            reverse("sports:follow_team"),
            {"team_id": self.team.id, "priority": "2"},
        )
        self.client.post(
            reverse("sports:follow_team"),
            {"team_id": self.team.id, "priority": "1"},
        )
        follows = UserTeamFollow.objects.filter(user=self.user, team=self.team)
        self.assertEqual(follows.count(), 1)
        self.assertEqual(follows.first().priority, 1)


class UnfollowTeamViewTest(TestCase):
    def setUp(self):
        self.user = _create_test_user(
            email="unfollow@example.com")
        prefs = self.user.preferences
        prefs.sports_enabled = True
        prefs.save()
        self.client = Client()
        self.client.force_login(self.user)

        sport = Sport.objects.create(name="Football", slug="football")
        league = League.objects.create(
            sport=sport, name="NFL", slug="nfl", abbreviation="NFL"
        )
        team = Team.objects.create(
            league=league, name="Chiefs", location="Kansas City", abbreviation="KC"
        )
        self.follow = UserTeamFollow.objects.create(
            user=self.user, team=team, priority=1
        )

    def test_unfollow_team(self):
        """POST to unfollow deactivates the follow."""
        response = self.client.post(
            reverse("sports:unfollow_team", kwargs={"pk": self.follow.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.follow.refresh_from_db()
        self.assertFalse(self.follow.is_active)
