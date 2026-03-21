"""
Tests for the Routine ↔ Maintenance Bridge feature.

Part A: Routine → Maintenance (completion prompt, redirect, prefill)
Part B: Maintenance → Routine (matching, sync)
"""

from datetime import date, time, timedelta

from django.conf import settings
from django.test import TestCase, RequestFactory
from django.urls import reverse

from apps.users.models import User, TermsAcceptance


def _create_test_user(email='bridge@test.com'):
    """Create a test user with onboarding complete."""
    user = User.objects.create_user(email=email, password='testpass123')
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


class RoutineScheduleBridgeFieldsTest(TestCase):
    """A1-A3: Model fields exist with correct defaults."""

    def test_bridge_fields_exist(self):
        from apps.life.models import RoutineSchedule
        fields = {f.name for f in RoutineSchedule._meta.get_fields()}
        self.assertIn('creates_maintenance_log', fields)
        self.assertIn('maintenance_type', fields)
        self.assertIn('maintenance_area', fields)
        self.assertIn('default_maintenance_title', fields)
        self.assertIn('follow_up_days', fields)

    def test_bridge_defaults(self):
        from apps.life.models import Routine, RoutineSchedule
        user = _create_test_user()
        routine = Routine.objects.create(user=user, name='Test Routine')
        sched = RoutineSchedule.objects.create(
            routine=routine, name='Oil Change', scheduled_time=time(9, 0),
        )
        self.assertFalse(sched.creates_maintenance_log)
        self.assertEqual(sched.maintenance_type, 'maintenance')
        self.assertEqual(sched.maintenance_area, '')
        self.assertIsNone(sched.follow_up_days)

    def test_maintenance_log_matched_schedule_id(self):
        from apps.life.models import MaintenanceLog
        fields = {f.name for f in MaintenanceLog._meta.get_fields()}
        self.assertIn('matched_schedule_id', fields)

    def test_created_via_routine_choice_exists(self):
        from apps.core.models import UserOwnedModel
        choices = dict(UserOwnedModel.CREATED_VIA_CHOICES)
        self.assertIn('routine', choices)


class ToggleViewMaintenanceConfigTest(TestCase):
    """A6: Toggle returns maintenance_config when bridge enabled."""

    def setUp(self):
        from apps.life.models import Routine, RoutineSchedule
        self.user = _create_test_user()
        self.client.login(email='bridge@test.com', password='testpass123')
        self.routine = Routine.objects.create(user=self.user, name='Vehicle')
        self.schedule = RoutineSchedule.objects.create(
            routine=self.routine, name='Oil Change',
            scheduled_time=time(9, 0),
            creates_maintenance_log=True,
            maintenance_type='maintenance',
            maintenance_area='Jeep',
            default_maintenance_title='Oil Change',
            follow_up_days=90,
        )

    def test_toggle_complete_returns_maintenance_config(self):
        resp = self.client.post(
            reverse('life:routine_toggle'),
            {'schedule_id': self.schedule.pk},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['is_completed'])
        self.assertIn('maintenance_config', data)
        mc = data['maintenance_config']
        self.assertEqual(mc['title'], 'Oil Change')
        self.assertEqual(mc['log_type'], 'maintenance')
        self.assertEqual(mc['area'], 'Jeep')
        self.assertTrue(mc['follow_up_date'])  # Should be a date string

    def test_toggle_uncomplete_no_maintenance_config(self):
        # First complete
        self.client.post(
            reverse('life:routine_toggle'),
            {'schedule_id': self.schedule.pk},
        )
        # Then uncomplete
        resp = self.client.post(
            reverse('life:routine_toggle'),
            {'schedule_id': self.schedule.pk},
        )
        data = resp.json()
        self.assertFalse(data['is_completed'])
        self.assertNotIn('maintenance_config', data)

    def test_toggle_no_bridge_no_maintenance_config(self):
        from apps.life.models import RoutineSchedule
        sched_no_bridge = RoutineSchedule.objects.create(
            routine=self.routine, name='Wash Car',
            scheduled_time=time(10, 0),
            creates_maintenance_log=False,
        )
        resp = self.client.post(
            reverse('life:routine_toggle'),
            {'schedule_id': sched_no_bridge.pk},
        )
        data = resp.json()
        self.assertTrue(data['is_completed'])
        self.assertNotIn('maintenance_config', data)


class RoutineToMaintenanceRedirectTest(TestCase):
    """A7: Redirect view builds correct query params."""

    def setUp(self):
        from apps.life.models import Routine, RoutineSchedule
        self.user = _create_test_user()
        self.client.login(email='bridge@test.com', password='testpass123')
        self.routine = Routine.objects.create(user=self.user, name='Vehicle')
        self.schedule = RoutineSchedule.objects.create(
            routine=self.routine, name='Oil Change',
            scheduled_time=time(9, 0),
            creates_maintenance_log=True,
            maintenance_type='service',
            maintenance_area='Jeep',
            default_maintenance_title='Oil Change Service',
            follow_up_days=90,
        )

    def test_redirect_has_correct_params(self):
        resp = self.client.get(
            reverse('life:routine_to_maintenance', args=[self.schedule.pk]),
        )
        self.assertEqual(resp.status_code, 302)
        url = resp.url
        self.assertIn('title=Oil+Change+Service', url)
        self.assertIn('log_type=service', url)
        self.assertIn('area=Jeep', url)
        self.assertIn('source=routine', url)
        self.assertIn('follow_up_date=', url)

    def test_redirect_rejects_no_bridge(self):
        from apps.life.models import RoutineSchedule
        sched = RoutineSchedule.objects.create(
            routine=self.routine, name='Wash',
            scheduled_time=time(10, 0),
            creates_maintenance_log=False,
        )
        resp = self.client.get(
            reverse('life:routine_to_maintenance', args=[sched.pk]),
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn('routine', resp.url)  # Redirects to routine_list


class MaintenanceRoutineMatcherTest(TestCase):
    """B1: Matching service finds correct matches."""

    def setUp(self):
        from apps.life.models import Routine, RoutineSchedule, MaintenanceLog
        self.user = _create_test_user()
        self.routine = Routine.objects.create(user=self.user, name='Vehicle')
        self.schedule = RoutineSchedule.objects.create(
            routine=self.routine, name='Oil Change',
            scheduled_time=time(9, 0),
            creates_maintenance_log=True,
            maintenance_type='service',
            maintenance_area='Jeep',
            default_maintenance_title='Oil Change',
        )
        self.log = MaintenanceLog.objects.create(
            user=self.user, title='Oil Change', log_type='service',
            area='Jeep', date=date.today(),
        )

    def test_finds_match_on_area_and_type(self):
        from apps.life.services.maintenance_routine_matcher import find_matching_routines
        matches = find_matching_routines(self.log, self.user)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['schedule_id'], self.schedule.pk)
        self.assertGreaterEqual(matches[0]['score'], 70)

    def test_no_match_for_unrelated(self):
        from apps.life.models import MaintenanceLog
        from apps.life.services.maintenance_routine_matcher import find_matching_routines
        unrelated = MaintenanceLog.objects.create(
            user=self.user, title='Roof Repair', log_type='repair',
            area='Home', date=date.today(),
        )
        matches = find_matching_routines(unrelated, self.user)
        self.assertEqual(len(matches), 0)

    def test_only_checks_bridge_enabled(self):
        from apps.life.models import RoutineSchedule, MaintenanceLog
        from apps.life.services.maintenance_routine_matcher import find_matching_routines
        # Create schedule WITHOUT bridge
        RoutineSchedule.objects.create(
            routine=self.routine, name='Tire Rotation',
            scheduled_time=time(10, 0),
            creates_maintenance_log=False,
            maintenance_type='service', maintenance_area='Jeep',
        )
        log = MaintenanceLog.objects.create(
            user=self.user, title='Tire Rotation', log_type='service',
            area='Jeep', date=date.today(),
        )
        matches = find_matching_routines(log, self.user)
        # Should NOT match the non-bridge schedule
        for m in matches:
            self.assertTrue(
                RoutineSchedule.objects.get(pk=m['schedule_id']).creates_maintenance_log
            )


class MaintenanceSyncTest(TestCase):
    """B4: Sync endpoint sets matched_schedule_id."""

    def setUp(self):
        from apps.life.models import Routine, RoutineSchedule, MaintenanceLog
        self.user = _create_test_user()
        self.client.login(email='bridge@test.com', password='testpass123')
        self.routine = Routine.objects.create(user=self.user, name='Vehicle')
        self.schedule = RoutineSchedule.objects.create(
            routine=self.routine, name='Oil Change',
            scheduled_time=time(9, 0), creates_maintenance_log=True,
        )
        self.log = MaintenanceLog.objects.create(
            user=self.user, title='Oil Change', log_type='maintenance',
            area='Jeep', date=date.today(),
        )

    def test_sync_sets_matched_schedule_id(self):
        resp = self.client.post(
            reverse('life:maintenance_sync_routine',
                    args=[self.log.pk, self.schedule.pk]),
        )
        self.assertEqual(resp.status_code, 302)
        self.log.refresh_from_db()
        self.assertEqual(self.log.matched_schedule_id, self.schedule.pk)


class AutoSyncTest(TestCase):
    """Auto-sync: routine sync service updates schedule + log flags."""

    def setUp(self):
        from apps.life.models import Routine, RoutineSchedule, RoutineLog, MaintenanceLog
        self.user = _create_test_user('sync@test.com')
        self.routine = Routine.objects.create(user=self.user, name='Vehicle')
        self.schedule = RoutineSchedule.objects.create(
            routine=self.routine, name='Oil Change',
            scheduled_time=time(9, 0),
            creates_maintenance_log=True,
            maintenance_area='Jeep',
        )
        self.today = date.today()
        self.routine_log = RoutineLog.objects.create(
            user=self.user, schedule=self.schedule,
            scheduled_date=self.today, log_status='completed',
        )
        self.maint_log = MaintenanceLog.objects.create(
            user=self.user, title='Oil Change', log_type='maintenance',
            area='Jeep', date=self.today,
        )

    def test_sync_updates_schedule_last_maintenance_date(self):
        from apps.life.services.routine_sync_service import sync_routine_from_maintenance
        sync_routine_from_maintenance(self.schedule, self.maint_log, self.user)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.last_maintenance_date, self.today)

    def test_sync_marks_routine_log_maintenance_logged(self):
        from apps.life.services.routine_sync_service import sync_routine_from_maintenance
        sync_routine_from_maintenance(self.schedule, self.maint_log, self.user)
        self.routine_log.refresh_from_db()
        self.assertTrue(self.routine_log.maintenance_logged)

    def test_sync_sets_matched_schedule_id_on_maintenance(self):
        from apps.life.services.routine_sync_service import sync_routine_from_maintenance
        sync_routine_from_maintenance(self.schedule, self.maint_log, self.user)
        self.maint_log.refresh_from_db()
        self.assertEqual(self.maint_log.matched_schedule_id, self.schedule.pk)

    def test_duplicate_sync_is_idempotent(self):
        from apps.life.services.routine_sync_service import sync_routine_from_maintenance
        sync_routine_from_maintenance(self.schedule, self.maint_log, self.user)
        sync_routine_from_maintenance(self.schedule, self.maint_log, self.user)
        self.routine_log.refresh_from_db()
        self.assertTrue(self.routine_log.maintenance_logged)

    def test_toggle_suppresses_prompt_after_sync(self):
        """After maintenance_logged=True, toggle should NOT return maintenance_config."""
        from apps.life.services.routine_sync_service import sync_routine_from_maintenance
        sync_routine_from_maintenance(self.schedule, self.maint_log, self.user)
        # Now toggle uncomplete and re-complete
        self.client.login(email='sync@test.com', password='testpass123')
        self.client.post(reverse('life:routine_toggle'), {'schedule_id': self.schedule.pk})
        resp = self.client.post(reverse('life:routine_toggle'), {'schedule_id': self.schedule.pk})
        data = resp.json()
        # Should NOT get maintenance_config since maintenance was already logged
        self.assertNotIn('maintenance_config', data)
