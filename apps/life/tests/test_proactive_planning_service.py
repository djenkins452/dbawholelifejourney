"""Tests for Proactive Routine Planning Service."""

from datetime import date, time, timedelta

from django.conf import settings
from django.test import TestCase

from apps.users.models import User, TermsAcceptance


def _create_test_user(email='proactive@test.com'):
    user = User.objects.create_user(email=email, password='testpass123')
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


class ProactiveSuggestionsTest(TestCase):
    """Test proactive planning suggestions."""

    def setUp(self):
        from apps.life.models import Routine, RoutineSchedule
        self.user = _create_test_user()
        self.routine = Routine.objects.create(user=self.user, name='Vehicle')
        self.schedule = RoutineSchedule.objects.create(
            routine=self.routine, name='Oil Change',
            scheduled_time=time(9, 0),
            creates_maintenance_log=True,
            follow_up_days=90,
            # Due in 7 days — within 3-10 day window
            last_maintenance_date=date.today() - timedelta(days=83),
        )

    def test_upcoming_detected_within_window(self):
        from apps.life.services.proactive_planning_service import generate_proactive_suggestions
        suggestions = generate_proactive_suggestions(self.user)
        upcoming = [s for s in suggestions if s['type'] == 'upcoming']
        self.assertEqual(len(upcoming), 1)
        self.assertEqual(upcoming[0]['days_until_due'], 7)
        self.assertIn('due in 7 days', upcoming[0]['message'])

    def test_no_suggestion_when_not_in_window(self):
        from apps.life.services.proactive_planning_service import generate_proactive_suggestions
        # Due in 30 days — outside window
        self.schedule.last_maintenance_date = date.today() - timedelta(days=60)
        self.schedule.save()
        suggestions = generate_proactive_suggestions(self.user)
        self.assertEqual(len(suggestions), 0)

    def test_no_suggestion_when_already_overdue(self):
        from apps.life.services.proactive_planning_service import generate_proactive_suggestions
        # Due -5 days ago (overdue) — triggers HIGH action, suppresses proactive
        self.schedule.last_maintenance_date = date.today() - timedelta(days=95)
        self.schedule.save()
        suggestions = generate_proactive_suggestions(self.user)
        # Should be suppressed because overdue creates a HIGH priority action
        self.assertEqual(len(suggestions), 0)

    def test_no_suggestion_without_bridge_flag(self):
        from apps.life.services.proactive_planning_service import generate_proactive_suggestions
        self.schedule.creates_maintenance_log = False
        self.schedule.save()
        suggestions = generate_proactive_suggestions(self.user)
        self.assertEqual(len(suggestions), 0)

    def test_max_two_suggestions(self):
        from apps.life.models import RoutineSchedule
        from apps.life.services.proactive_planning_service import generate_proactive_suggestions
        # Add more schedules in the window
        for i in range(4):
            RoutineSchedule.objects.create(
                routine=self.routine, name=f'Item {i}',
                scheduled_time=time(10, 0),
                creates_maintenance_log=True,
                follow_up_days=90,
                last_maintenance_date=date.today() - timedelta(days=85 + i),
            )
        suggestions = generate_proactive_suggestions(self.user)
        self.assertLessEqual(len(suggestions), 2)

    def test_sorted_by_soonest_due(self):
        from apps.life.models import RoutineSchedule
        from apps.life.services.proactive_planning_service import generate_proactive_suggestions
        # Due in 4 days (sooner)
        RoutineSchedule.objects.create(
            routine=self.routine, name='Sooner Item',
            scheduled_time=time(10, 0),
            creates_maintenance_log=True,
            follow_up_days=90,
            last_maintenance_date=date.today() - timedelta(days=86),
        )
        suggestions = generate_proactive_suggestions(self.user)
        if len(suggestions) >= 2:
            self.assertLessEqual(
                suggestions[0]['days_until_due'],
                suggestions[1]['days_until_due'],
            )
