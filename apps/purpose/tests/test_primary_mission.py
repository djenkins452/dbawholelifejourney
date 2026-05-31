"""Phase 2A — Primary Mission selection.

A Mission is explicit user intent: a goal the user marks via
``is_primary_mission``. At most one active Primary Mission per user, enforced
both at the application layer (atomic make_primary_mission) and the database
layer (partial unique constraint). These tests pin the invariant and the
toggle endpoint.
"""
from django.conf import settings
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.purpose.models import LifeGoal
from apps.purpose.mission_selection import select_active_mission_goal
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


class PrimaryMissionEnforcementTests(TestCase):
    def setUp(self):
        self.user = _make_user("mission-enf@test.com")

    def _goal(self, title, **kw):
        kw.setdefault("status", "active")
        return LifeGoal.objects.create(user=self.user, title=title, **kw)

    def test_make_primary_mission_unsets_previous(self):
        a = self._goal("Goal A", is_primary_mission=True)
        b = self._goal("Goal B")

        b.make_primary_mission()

        a.refresh_from_db()
        b.refresh_from_db()
        self.assertFalse(a.is_primary_mission)
        self.assertTrue(b.is_primary_mission)
        self.assertEqual(
            LifeGoal.objects.filter(
                user=self.user, is_primary_mission=True
            ).count(),
            1,
        )

    def test_clear_primary_mission(self):
        a = self._goal("Goal A", is_primary_mission=True)
        a.clear_primary_mission()
        a.refresh_from_db()
        self.assertFalse(a.is_primary_mission)
        self.assertIsNone(select_active_mission_goal(self.user))

    def test_db_constraint_blocks_two_primaries(self):
        self._goal("Goal A", is_primary_mission=True)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                # Bypassing the helper must still be impossible at the DB.
                self._goal("Goal B", is_primary_mission=True)

    def test_selector_returns_only_active_primary(self):
        self._goal("Foundational decoy", is_foundational=True)
        chosen = self._goal("Chosen", is_primary_mission=True)
        self.assertEqual(select_active_mission_goal(self.user), chosen)

    def test_selector_none_when_primary_not_active(self):
        self._goal("Paused mission", is_primary_mission=True, status="paused")
        self.assertIsNone(select_active_mission_goal(self.user))

    def test_constraint_is_per_user(self):
        # Two different users may each have their own Primary Mission.
        other = _make_user("mission-other@test.com")
        self._goal("Mine", is_primary_mission=True)
        LifeGoal.objects.create(
            user=other, title="Theirs", status="active",
            is_primary_mission=True,
        )
        self.assertEqual(
            LifeGoal.objects.filter(is_primary_mission=True).count(), 2
        )


class PrimaryMissionToggleViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = _make_user("mission-view@test.com")
        self.client.login(email="mission-view@test.com", password="testpass123")

    def _goal(self, title, **kw):
        kw.setdefault("status", "active")
        return LifeGoal.objects.create(user=self.user, title=title, **kw)

    def test_set_primary_mission_via_view(self):
        goal = self._goal("Set Me")
        url = reverse("purpose:goal_primary_mission_toggle", args=[goal.pk])
        resp = self.client.post(url, {"action": "set"})
        self.assertEqual(resp.status_code, 302)
        goal.refresh_from_db()
        self.assertTrue(goal.is_primary_mission)

    def test_set_replaces_existing_via_view(self):
        a = self._goal("A", is_primary_mission=True)
        b = self._goal("B")
        url = reverse("purpose:goal_primary_mission_toggle", args=[b.pk])
        self.client.post(url, {"action": "set"})
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertFalse(a.is_primary_mission)
        self.assertTrue(b.is_primary_mission)

    def test_clear_via_view(self):
        goal = self._goal("Clear Me", is_primary_mission=True)
        url = reverse("purpose:goal_primary_mission_toggle", args=[goal.pk])
        self.client.post(url, {"action": "clear"})
        goal.refresh_from_db()
        self.assertFalse(goal.is_primary_mission)

    def test_cannot_toggle_other_users_goal(self):
        other = _make_user("mission-intruder@test.com")
        their_goal = LifeGoal.objects.create(
            user=other, title="Not yours", status="active",
        )
        url = reverse(
            "purpose:goal_primary_mission_toggle", args=[their_goal.pk]
        )
        resp = self.client.post(url, {"action": "set"})
        self.assertEqual(resp.status_code, 404)
        their_goal.refresh_from_db()
        self.assertFalse(their_goal.is_primary_mission)
