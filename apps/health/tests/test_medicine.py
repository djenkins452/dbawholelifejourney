"""
Medicine Module - Comprehensive Tests

This test file covers:
1. Medicine model tests
2. MedicineSchedule model tests
3. MedicineLog model tests
4. View tests (CRUD, daily tracker)
5. Form validation tests
6. Business logic tests (adherence, overdue detection)
7. Data isolation tests
8. Edge case tests

Location: apps/health/tests/test_medicine.py
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.health.models import Medicine, MedicineSchedule, MedicineLog

User = get_user_model()


# =============================================================================
# TEST HELPERS
# =============================================================================

class MedicineTestMixin:
    """Common setup for medicine tests."""

    def create_user(self, email='test@example.com', password='testpass123'):
        """Create a test user with terms accepted and onboarding completed."""
        user = User.objects.create_user(email=email, password=password)
        self._accept_terms(user)
        self._complete_onboarding(user)
        return user

    def _accept_terms(self, user):
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(user=user, terms_version='1.0')

    def _complete_onboarding(self, user):
        """Mark user onboarding as complete."""
        user.preferences.has_completed_onboarding = True
        user.preferences.save()

    def login_user(self, email='test@example.com', password='testpass123'):
        return self.client.login(email=email, password=password)

    def create_medicine(self, user, name='Test Medicine', dose='10mg', **kwargs):
        """Helper to create a medicine."""
        defaults = {
            'user': user,
            'name': name,
            'dose': dose,
            'frequency': 'daily',
            'start_date': timezone.now().date(),
        }
        defaults.update(kwargs)
        return Medicine.objects.create(**defaults)

    def create_schedule(self, medicine, scheduled_time=None, **kwargs):
        """Helper to create a medicine schedule."""
        if scheduled_time is None:
            scheduled_time = time(8, 0)  # 8:00 AM default
        return MedicineSchedule.objects.create(
            medicine=medicine,
            scheduled_time=scheduled_time,
            **kwargs
        )

    def create_log(self, user, medicine, schedule=None, **kwargs):
        """Helper to create a medicine log."""
        defaults = {
            'user': user,
            'medicine': medicine,
            'scheduled_date': timezone.now().date(),
            'log_status': MedicineLog.STATUS_TAKEN,
        }
        if schedule:
            defaults['schedule'] = schedule
            defaults['scheduled_time'] = schedule.scheduled_time
        defaults.update(kwargs)
        return MedicineLog.objects.create(**defaults)


# =============================================================================
# 1. MEDICINE MODEL TESTS
# =============================================================================

class MedicineModelTest(MedicineTestMixin, TestCase):
    """Tests for the Medicine model."""

    def setUp(self):
        self.user = self.create_user()

    def test_create_medicine(self):
        """Medicine can be created."""
        medicine = self.create_medicine(self.user)
        self.assertEqual(medicine.name, 'Test Medicine')
        self.assertEqual(medicine.dose, '10mg')

    def test_medicine_str(self):
        """Medicine string representation."""
        medicine = self.create_medicine(self.user, name='Aspirin')
        self.assertIn('Aspirin', str(medicine))

    def test_medicine_default_status(self):
        """Medicine defaults to active status."""
        medicine = self.create_medicine(self.user)
        self.assertEqual(medicine.medicine_status, Medicine.STATUS_ACTIVE)

    def test_medicine_is_active_property(self):
        """is_active_medicine property works correctly."""
        medicine = self.create_medicine(self.user)
        self.assertTrue(medicine.is_active_medicine)

        medicine.medicine_status = Medicine.STATUS_PAUSED
        medicine.save()
        self.assertFalse(medicine.is_active_medicine)

    def test_medicine_pause(self):
        """Medicine can be paused."""
        medicine = self.create_medicine(self.user)
        medicine.pause('Side effects')

        self.assertEqual(medicine.medicine_status, Medicine.STATUS_PAUSED)
        self.assertEqual(medicine.paused_reason, 'Side effects')
        self.assertIsNotNone(medicine.paused_at)

    def test_medicine_resume(self):
        """Medicine can be resumed after pausing."""
        medicine = self.create_medicine(self.user)
        medicine.pause('Test')
        medicine.resume()

        self.assertEqual(medicine.medicine_status, Medicine.STATUS_ACTIVE)
        self.assertIsNone(medicine.paused_at)
        self.assertEqual(medicine.paused_reason, '')

    def test_medicine_complete(self):
        """Medicine can be marked as completed."""
        medicine = self.create_medicine(self.user)
        medicine.complete()

        self.assertEqual(medicine.medicine_status, Medicine.STATUS_COMPLETED)

    def test_medicine_needs_refill(self):
        """needs_refill property works correctly."""
        medicine = self.create_medicine(
            self.user,
            current_supply=5,
            refill_threshold=7
        )
        self.assertTrue(medicine.needs_refill)

        medicine.current_supply = 10
        medicine.save()
        self.assertFalse(medicine.needs_refill)

    def test_medicine_needs_refill_none_supply(self):
        """needs_refill returns False when supply is not tracked."""
        medicine = self.create_medicine(self.user, current_supply=None)
        self.assertFalse(medicine.needs_refill)

    def test_medicine_prn_flag(self):
        """PRN medicine flag works."""
        medicine = self.create_medicine(self.user, is_prn=True)
        self.assertTrue(medicine.is_prn)

    def test_medicine_with_purpose(self):
        """Medicine can have a purpose."""
        medicine = self.create_medicine(
            self.user,
            name='Lisinopril',
            purpose='Blood pressure'
        )
        self.assertEqual(medicine.purpose, 'Blood pressure')

    def test_medicine_with_prescription_details(self):
        """Medicine can have prescription details."""
        medicine = self.create_medicine(
            self.user,
            prescribing_doctor='Dr. Smith',
            pharmacy='CVS',
            rx_number='RX123456'
        )
        self.assertEqual(medicine.prescribing_doctor, 'Dr. Smith')
        self.assertEqual(medicine.pharmacy, 'CVS')
        self.assertEqual(medicine.rx_number, 'RX123456')

    def test_medicine_grace_period(self):
        """Medicine has configurable grace period."""
        medicine = self.create_medicine(self.user, grace_period_minutes=30)
        self.assertEqual(medicine.grace_period_minutes, 30)

    def test_medicine_ordering(self):
        """Medicines are ordered by name."""
        self.create_medicine(self.user, name='Zebra')
        self.create_medicine(self.user, name='Alpha')
        self.create_medicine(self.user, name='Beta')

        medicines = Medicine.objects.filter(user=self.user)
        self.assertEqual(medicines[0].name, 'Alpha')
        self.assertEqual(medicines[1].name, 'Beta')
        self.assertEqual(medicines[2].name, 'Zebra')


# =============================================================================
# 2. MEDICINE SCHEDULE MODEL TESTS
# =============================================================================

class MedicineScheduleModelTest(MedicineTestMixin, TestCase):
    """Tests for the MedicineSchedule model."""

    def setUp(self):
        self.user = self.create_user()
        self.medicine = self.create_medicine(self.user)

    def test_create_schedule(self):
        """Schedule can be created."""
        schedule = self.create_schedule(self.medicine, time(9, 0))
        self.assertEqual(schedule.scheduled_time, time(9, 0))

    def test_schedule_str(self):
        """Schedule string representation."""
        schedule = self.create_schedule(self.medicine, time(8, 30))
        self.assertIn('08:30', str(schedule))

    def test_schedule_with_label(self):
        """Schedule can have a label."""
        schedule = self.create_schedule(
            self.medicine,
            time(8, 0),
            label='Morning'
        )
        self.assertEqual(schedule.label, 'Morning')

    def test_schedule_days_of_week_default(self):
        """Schedule defaults to all days."""
        schedule = self.create_schedule(self.medicine)
        self.assertEqual(schedule.days_of_week, '0,1,2,3,4,5,6')

    def test_schedule_days_list(self):
        """days_list property returns list of integers."""
        schedule = self.create_schedule(self.medicine)
        schedule.days_of_week = '0,1,2'
        schedule.save()

        self.assertEqual(schedule.days_list, [0, 1, 2])

    def test_schedule_applies_to_day(self):
        """applies_to_day method works correctly."""
        schedule = self.create_schedule(self.medicine)
        schedule.days_of_week = '0,2,4'  # Mon, Wed, Fri
        schedule.save()

        self.assertTrue(schedule.applies_to_day(0))  # Monday
        self.assertFalse(schedule.applies_to_day(1))  # Tuesday
        self.assertTrue(schedule.applies_to_day(2))  # Wednesday

    def test_schedule_is_active_default(self):
        """Schedule defaults to active."""
        schedule = self.create_schedule(self.medicine)
        self.assertTrue(schedule.is_active)

    def test_schedule_ordering(self):
        """Schedules are ordered by time."""
        self.create_schedule(self.medicine, time(20, 0))
        self.create_schedule(self.medicine, time(8, 0))
        self.create_schedule(self.medicine, time(14, 0))

        schedules = MedicineSchedule.objects.filter(medicine=self.medicine)
        self.assertEqual(schedules[0].scheduled_time, time(8, 0))
        self.assertEqual(schedules[1].scheduled_time, time(14, 0))
        self.assertEqual(schedules[2].scheduled_time, time(20, 0))


# =============================================================================
# 3. MEDICINE LOG MODEL TESTS
# =============================================================================

class MedicineLogModelTest(MedicineTestMixin, TestCase):
    """Tests for the MedicineLog model."""

    def setUp(self):
        self.user = self.create_user()
        self.medicine = self.create_medicine(self.user)
        self.schedule = self.create_schedule(self.medicine)

    def test_create_log(self):
        """Log can be created."""
        log = self.create_log(self.user, self.medicine, self.schedule)
        self.assertEqual(log.log_status, MedicineLog.STATUS_TAKEN)

    def test_log_mark_taken(self):
        """Log can be marked as taken."""
        from datetime import datetime
        log = MedicineLog.objects.create(
            user=self.user,
            medicine=self.medicine,
            schedule=self.schedule,
            scheduled_date=timezone.now().date(),
            scheduled_time=self.schedule.scheduled_time,
        )
        # Mark taken at the scheduled time (within grace period)
        taken_at = timezone.make_aware(
            datetime.combine(log.scheduled_date, log.scheduled_time)
        )
        log.mark_taken(taken_at=taken_at)

        self.assertEqual(log.log_status, MedicineLog.STATUS_TAKEN)
        self.assertIsNotNone(log.taken_at)

    def test_log_mark_skipped(self):
        """Log can be marked as skipped."""
        log = MedicineLog.objects.create(
            user=self.user,
            medicine=self.medicine,
            schedule=self.schedule,
            scheduled_date=timezone.now().date(),
            scheduled_time=self.schedule.scheduled_time,
        )
        log.mark_skipped('Ran out')

        self.assertEqual(log.log_status, MedicineLog.STATUS_SKIPPED)
        self.assertIn('Ran out', log.notes)

    def test_log_mark_missed(self):
        """Log can be marked as missed."""
        log = MedicineLog.objects.create(
            user=self.user,
            medicine=self.medicine,
            schedule=self.schedule,
            scheduled_date=timezone.now().date(),
            scheduled_time=self.schedule.scheduled_time,
        )
        log.mark_missed()

        self.assertEqual(log.log_status, MedicineLog.STATUS_MISSED)

    def test_log_prn_dose(self):
        """PRN dose can be logged."""
        log = MedicineLog.objects.create(
            user=self.user,
            medicine=self.medicine,
            scheduled_date=timezone.now().date(),
            is_prn_dose=True,
            prn_reason='Headache',
            log_status=MedicineLog.STATUS_TAKEN,
            taken_at=timezone.now(),
        )

        self.assertTrue(log.is_prn_dose)
        self.assertEqual(log.prn_reason, 'Headache')

    def test_log_with_notes(self):
        """Log can have notes."""
        log = self.create_log(
            self.user,
            self.medicine,
            self.schedule,
            notes='Felt slightly dizzy'
        )
        self.assertEqual(log.notes, 'Felt slightly dizzy')

    def test_log_ordering(self):
        """Logs are ordered by date and time descending."""
        yesterday = timezone.now().date() - timedelta(days=1)
        today = timezone.now().date()

        self.create_log(self.user, self.medicine, scheduled_date=yesterday)
        self.create_log(self.user, self.medicine, scheduled_date=today)

        logs = MedicineLog.objects.filter(user=self.user)
        self.assertEqual(logs[0].scheduled_date, today)


# =============================================================================
# 4. VIEW TESTS - Basic Loading
# =============================================================================

class MedicineViewBasicTest(MedicineTestMixin, TestCase):
    """Basic view loading tests."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()

    # --- Authentication Required ---

    def test_medicine_home_requires_login(self):
        """Medicine home redirects anonymous users."""
        response = self.client.get(reverse('health:medicine_home'))
        self.assertEqual(response.status_code, 302)

    def test_medicine_list_requires_login(self):
        """Medicine list requires authentication."""
        response = self.client.get(reverse('health:medicine_list'))
        self.assertEqual(response.status_code, 302)

    def test_medicine_create_requires_login(self):
        """Medicine create requires authentication."""
        response = self.client.get(reverse('health:medicine_create'))
        self.assertEqual(response.status_code, 302)

    # --- Authenticated Access ---

    def test_medicine_home_loads(self):
        """Medicine home loads for authenticated user."""
        self.login_user()
        response = self.client.get(reverse('health:medicine_home'))
        self.assertEqual(response.status_code, 200)

    def test_medicine_list_loads(self):
        """Medicine list page loads."""
        self.login_user()
        response = self.client.get(reverse('health:medicine_list'))
        self.assertEqual(response.status_code, 200)

    def test_medicine_create_loads(self):
        """Medicine create page loads."""
        self.login_user()
        response = self.client.get(reverse('health:medicine_create'))
        self.assertEqual(response.status_code, 200)

    def test_medicine_detail_loads(self):
        """Medicine detail page loads."""
        self.login_user()
        medicine = self.create_medicine(self.user)
        response = self.client.get(
            reverse('health:medicine_detail', kwargs={'pk': medicine.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_medicine_schedules_loads(self):
        """Medicine schedules page loads."""
        self.login_user()
        medicine = self.create_medicine(self.user)
        response = self.client.get(
            reverse('health:medicine_schedules', kwargs={'pk': medicine.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_medicine_history_loads(self):
        """Medicine history page loads."""
        self.login_user()
        response = self.client.get(reverse('health:medicine_history'))
        self.assertEqual(response.status_code, 200)

    def test_medicine_adherence_loads(self):
        """Medicine adherence page loads."""
        self.login_user()
        response = self.client.get(reverse('health:medicine_adherence'))
        self.assertEqual(response.status_code, 200)

    def test_medicine_quick_look_loads(self):
        """Medicine quick look page loads."""
        self.login_user()
        response = self.client.get(reverse('health:medicine_quick_look'))
        self.assertEqual(response.status_code, 200)

    def test_prn_log_loads(self):
        """PRN log page loads."""
        self.login_user()
        response = self.client.get(reverse('health:medicine_prn_log'))
        self.assertEqual(response.status_code, 200)


# =============================================================================
# 5. VIEW TESTS - CRUD Operations
# =============================================================================

class MedicineCRUDTest(MedicineTestMixin, TestCase):
    """Tests for CRUD operations."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_create_medicine_post(self):
        """Medicine can be created via POST."""
        response = self.client.post(reverse('health:medicine_create'), {
            'name': 'New Medicine',
            'dose': '25mg',
            'frequency': 'daily',
            'start_date': timezone.now().date().isoformat(),
            'refill_threshold': 7,
            'grace_period_minutes': 60,
        })

        self.assertEqual(response.status_code, 302)  # Redirects on success
        self.assertTrue(
            Medicine.objects.filter(name='New Medicine').exists()
        )

    def test_update_medicine(self):
        """Medicine can be updated."""
        medicine = self.create_medicine(self.user)
        response = self.client.post(
            reverse('health:medicine_update', kwargs={'pk': medicine.pk}),
            {
                'name': 'Updated Medicine',
                'dose': '50mg',
                'frequency': 'twice_daily',
                'start_date': medicine.start_date.isoformat(),
                'refill_threshold': 7,
                'grace_period_minutes': 60,
            }
        )

        self.assertEqual(response.status_code, 302)
        medicine.refresh_from_db()
        self.assertEqual(medicine.name, 'Updated Medicine')
        self.assertEqual(medicine.dose, '50mg')

    def test_delete_medicine(self):
        """Medicine can be deleted (soft delete)."""
        medicine = self.create_medicine(self.user)
        response = self.client.post(
            reverse('health:medicine_delete', kwargs={'pk': medicine.pk})
        )

        self.assertEqual(response.status_code, 302)
        medicine.refresh_from_db()
        self.assertEqual(medicine.status, 'deleted')

    def test_pause_medicine(self):
        """Medicine can be paused."""
        medicine = self.create_medicine(self.user)
        response = self.client.post(
            reverse('health:medicine_pause', kwargs={'pk': medicine.pk}),
            {'reason': 'Side effects'}
        )

        self.assertEqual(response.status_code, 302)
        medicine.refresh_from_db()
        self.assertEqual(medicine.medicine_status, Medicine.STATUS_PAUSED)

    def test_resume_medicine(self):
        """Medicine can be resumed."""
        medicine = self.create_medicine(self.user)
        medicine.pause('Test')

        response = self.client.post(
            reverse('health:medicine_resume', kwargs={'pk': medicine.pk})
        )

        self.assertEqual(response.status_code, 302)
        medicine.refresh_from_db()
        self.assertEqual(medicine.medicine_status, Medicine.STATUS_ACTIVE)

    def test_complete_medicine(self):
        """Medicine can be marked as completed."""
        medicine = self.create_medicine(self.user)
        response = self.client.post(
            reverse('health:medicine_complete', kwargs={'pk': medicine.pk})
        )

        self.assertEqual(response.status_code, 302)
        medicine.refresh_from_db()
        self.assertEqual(medicine.medicine_status, Medicine.STATUS_COMPLETED)


# =============================================================================
# 5.5 AI CAMERA SCAN PREFILL TESTS
# =============================================================================

class MedicineAICameraPrefillTest(MedicineTestMixin, TestCase):
    """Tests for AI Camera scan prefilling medicine form."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_medicine_create_prefills_name_from_query_param(self):
        """Medicine create form prefills name from query parameter."""
        response = self.client.get(
            reverse('health:medicine_create') + '?name=Lisinopril%2010mg'
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Lisinopril 10mg')

    def test_medicine_create_prefills_dose_from_query_param(self):
        """Medicine create form prefills dose from query parameter."""
        response = self.client.get(
            reverse('health:medicine_create') + '?name=Metformin&dose=500mg'
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '500mg')

    def test_medicine_create_prefills_directions_as_notes(self):
        """Medicine create form prefills directions into notes field."""
        response = self.client.get(
            reverse('health:medicine_create') + '?name=Aspirin&directions=Take%20with%20food'
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Take with food')

    def test_medicine_create_prefills_quantity_as_supply(self):
        """Medicine create form extracts quantity into current_supply."""
        response = self.client.get(
            reverse('health:medicine_create') + '?name=Vitamin%20D&quantity=30%20tablets'
        )
        self.assertEqual(response.status_code, 200)
        # Check the form initial data
        form = response.context.get('form')
        self.assertIsNotNone(form)
        self.assertEqual(form.initial.get('current_supply'), 30)

    def test_medicine_create_prefills_all_fields_from_scan(self):
        """Medicine create form prefills all fields from AI Camera scan."""
        url = (
            reverse('health:medicine_create') +
            '?name=Lisinopril&dose=10mg&directions=Take%20once%20daily'
            '&quantity=90%20tablets&source=ai_camera'
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        form = response.context.get('form')
        self.assertIsNotNone(form)
        self.assertEqual(form.initial.get('name'), 'Lisinopril')
        self.assertEqual(form.initial.get('dose'), '10mg')
        self.assertEqual(form.initial.get('notes'), 'Take once daily')
        self.assertEqual(form.initial.get('current_supply'), 90)

    def test_medicine_create_tracks_ai_camera_source(self):
        """Medicine created via AI Camera has created_via set correctly."""
        from apps.core.models import UserOwnedModel

        response = self.client.post(
            reverse('health:medicine_create') + '?source=ai_camera',
            {
                'name': 'AI Scanned Medicine',
                'dose': '50mg',
                'frequency': 'daily',
                'start_date': timezone.now().date().isoformat(),
                'refill_threshold': 7,
                'grace_period_minutes': 60,
            }
        )

        self.assertEqual(response.status_code, 302)
        medicine = Medicine.objects.get(name='AI Scanned Medicine')
        self.assertEqual(medicine.created_via, UserOwnedModel.CREATED_VIA_AI_CAMERA)

    def test_medicine_create_without_source_defaults_to_manual(self):
        """Medicine created without source param has manual created_via."""
        from apps.core.models import UserOwnedModel

        response = self.client.post(
            reverse('health:medicine_create'),
            {
                'name': 'Manual Medicine',
                'dose': '25mg',
                'frequency': 'daily',
                'start_date': timezone.now().date().isoformat(),
                'refill_threshold': 7,
                'grace_period_minutes': 60,
            }
        )

        self.assertEqual(response.status_code, 302)
        medicine = Medicine.objects.get(name='Manual Medicine')
        self.assertEqual(medicine.created_via, UserOwnedModel.CREATED_VIA_MANUAL)

    def test_medicine_create_prefills_purpose_from_query_param(self):
        """Medicine create form prefills purpose from query parameter."""
        response = self.client.get(
            reverse('health:medicine_create') + '?name=Lisinopril&purpose=Blood%20pressure%20control'
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Blood pressure control')
        form = response.context.get('form')
        self.assertIsNotNone(form)
        self.assertEqual(form.initial.get('purpose'), 'Blood pressure control')

    def test_medicine_create_prefills_all_fields_including_purpose(self):
        """Medicine create form prefills all fields including purpose from AI Camera scan."""
        url = (
            reverse('health:medicine_create') +
            '?name=Metformin&dose=500mg&directions=Take%20twice%20daily%20with%20meals'
            '&quantity=60%20tablets&purpose=Diabetes%20management&source=ai_camera'
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        form = response.context.get('form')
        self.assertIsNotNone(form)
        self.assertEqual(form.initial.get('name'), 'Metformin')
        self.assertEqual(form.initial.get('dose'), '500mg')
        self.assertEqual(form.initial.get('notes'), 'Take twice daily with meals')
        self.assertEqual(form.initial.get('current_supply'), 60)
        self.assertEqual(form.initial.get('purpose'), 'Diabetes management')


# =============================================================================
# 6. DAILY TRACKER TESTS
# =============================================================================

class MedicineDailyTrackerTest(MedicineTestMixin, TestCase):
    """Tests for daily medicine tracking."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()
        self.medicine = self.create_medicine(self.user)
        self.schedule = self.create_schedule(self.medicine)

    def test_take_dose(self):
        """Dose can be marked as taken."""
        response = self.client.post(
            reverse('health:medicine_take', kwargs={
                'pk': self.medicine.pk,
                'schedule_pk': self.schedule.pk
            })
        )

        self.assertEqual(response.status_code, 302)
        log = MedicineLog.objects.filter(
            medicine=self.medicine,
            schedule=self.schedule,
            scheduled_date=timezone.now().date(),
        ).first()
        self.assertIsNotNone(log)
        self.assertIn(log.log_status, [MedicineLog.STATUS_TAKEN, MedicineLog.STATUS_LATE])

    def test_skip_dose(self):
        """Dose can be marked as skipped."""
        response = self.client.post(
            reverse('health:medicine_skip', kwargs={
                'pk': self.medicine.pk,
                'schedule_pk': self.schedule.pk
            }),
            {'reason': 'Ran out'}
        )

        self.assertEqual(response.status_code, 302)
        log = MedicineLog.objects.filter(
            medicine=self.medicine,
            schedule=self.schedule,
        ).first()
        self.assertEqual(log.log_status, MedicineLog.STATUS_SKIPPED)

    def test_undo_dose(self):
        """Taken dose can be undone."""
        # First take the dose
        self.client.post(
            reverse('health:medicine_take', kwargs={
                'pk': self.medicine.pk,
                'schedule_pk': self.schedule.pk
            })
        )

        # Then undo
        response = self.client.post(
            reverse('health:medicine_undo', kwargs={
                'pk': self.medicine.pk,
                'schedule_pk': self.schedule.pk
            })
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            MedicineLog.objects.filter(
                medicine=self.medicine,
                schedule=self.schedule,
                scheduled_date=timezone.now().date(),
            ).exists()
        )

    def test_take_dose_decreases_supply(self):
        """Taking dose decreases supply count."""
        self.medicine.current_supply = 10
        self.medicine.save()

        self.client.post(
            reverse('health:medicine_take', kwargs={
                'pk': self.medicine.pk,
                'schedule_pk': self.schedule.pk
            })
        )

        self.medicine.refresh_from_db()
        self.assertEqual(self.medicine.current_supply, 9)

    def test_undo_dose_restores_supply(self):
        """Undoing dose restores supply count."""
        self.medicine.current_supply = 9
        self.medicine.save()

        # Take dose
        self.client.post(
            reverse('health:medicine_take', kwargs={
                'pk': self.medicine.pk,
                'schedule_pk': self.schedule.pk
            })
        )

        # Undo dose
        self.client.post(
            reverse('health:medicine_undo', kwargs={
                'pk': self.medicine.pk,
                'schedule_pk': self.schedule.pk
            })
        )

        self.medicine.refresh_from_db()
        self.assertEqual(self.medicine.current_supply, 9)


# =============================================================================
# 7. PRN MEDICINE TESTS
# =============================================================================

class MedicinePRNTest(MedicineTestMixin, TestCase):
    """Tests for PRN (as-needed) medicines."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()
        self.prn_medicine = self.create_medicine(
            self.user,
            name='Ibuprofen',
            is_prn=True,
            frequency='as_needed'
        )

    def test_prn_medicine_in_form_choices(self):
        """PRN medicine appears in PRN log form."""
        response = self.client.get(reverse('health:medicine_prn_log'))
        self.assertContains(response, 'Ibuprofen')

    def test_log_prn_dose(self):
        """PRN dose can be logged."""
        response = self.client.post(reverse('health:medicine_prn_log'), {
            'medicine': self.prn_medicine.pk,
            'reason': 'Headache',
            'notes': 'Took after lunch',
        })

        self.assertEqual(response.status_code, 302)
        log = MedicineLog.objects.filter(
            medicine=self.prn_medicine,
            is_prn_dose=True,
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.prn_reason, 'Headache')


# =============================================================================
# 8. DATA ISOLATION TESTS
# =============================================================================

class MedicineDataIsolationTest(MedicineTestMixin, TestCase):
    """Tests to ensure users can only see their own medicine data."""

    def setUp(self):
        self.client = Client()
        self.user_a = self.create_user(email='usera@example.com')
        self.user_b = self.create_user(email='userb@example.com')

        self.medicine_a = self.create_medicine(self.user_a, name='Medicine A')
        self.medicine_b = self.create_medicine(self.user_b, name='Medicine B')

    def test_user_sees_only_own_medicines(self):
        """User only sees their own medicines."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(reverse('health:medicine_list'))

        self.assertContains(response, 'Medicine A')
        self.assertNotContains(response, 'Medicine B')

    def test_user_cannot_view_other_medicine_detail(self):
        """User cannot view another user's medicine detail."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(
            reverse('health:medicine_detail', kwargs={'pk': self.medicine_b.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_user_cannot_delete_other_users_medicine(self):
        """User cannot delete another user's medicine."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.post(
            reverse('health:medicine_delete', kwargs={'pk': self.medicine_b.pk})
        )
        self.assertEqual(response.status_code, 404)
        # Medicine should still exist
        self.assertTrue(
            Medicine.objects.filter(pk=self.medicine_b.pk).exists()
        )

    def test_user_cannot_take_other_users_medicine(self):
        """User cannot mark another user's medicine as taken."""
        schedule_b = self.create_schedule(self.medicine_b)

        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.post(
            reverse('health:medicine_take', kwargs={
                'pk': self.medicine_b.pk,
                'schedule_pk': schedule_b.pk
            })
        )
        self.assertEqual(response.status_code, 404)


# =============================================================================
# 9. SCHEDULE MANAGEMENT TESTS
# =============================================================================

class MedicineScheduleManagementTest(MedicineTestMixin, TestCase):
    """Tests for schedule management."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()
        self.medicine = self.create_medicine(self.user)

    def test_add_schedule(self):
        """Schedule can be added to medicine."""
        response = self.client.post(
            reverse('health:medicine_schedules', kwargs={'pk': self.medicine.pk}),
            {
                'scheduled_time': '09:00',
                'label': 'Morning',
                'days': ['0', '1', '2', '3', '4', '5', '6'],
                'is_active': True,
            }
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            MedicineSchedule.objects.filter(medicine=self.medicine).exists()
        )

    def test_delete_schedule(self):
        """Schedule can be deleted."""
        schedule = self.create_schedule(self.medicine)
        response = self.client.post(
            reverse('health:medicine_schedule_delete', kwargs={
                'medicine_pk': self.medicine.pk,
                'schedule_pk': schedule.pk
            })
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            MedicineSchedule.objects.filter(pk=schedule.pk).exists()
        )


# =============================================================================
# 10. ADHERENCE TESTS
# =============================================================================

class MedicineAdherenceTest(MedicineTestMixin, TestCase):
    """Tests for adherence calculations."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()
        self.medicine = self.create_medicine(self.user)
        self.schedule = self.create_schedule(self.medicine)

    def test_adherence_page_shows_stats(self):
        """Adherence page shows statistics."""
        # Create some logs
        for i in range(7):
            date = timezone.now().date() - timedelta(days=i)
            MedicineLog.objects.create(
                user=self.user,
                medicine=self.medicine,
                schedule=self.schedule,
                scheduled_date=date,
                scheduled_time=self.schedule.scheduled_time,
                log_status=MedicineLog.STATUS_TAKEN if i < 5 else MedicineLog.STATUS_MISSED,
            )

        response = self.client.get(reverse('health:medicine_adherence'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('adherence_rate', response.context)

    def test_medicine_detail_shows_week_adherence(self):
        """Medicine detail shows 7-day adherence."""
        # Create logs for the week
        for i in range(7):
            date = timezone.now().date() - timedelta(days=i)
            MedicineLog.objects.create(
                user=self.user,
                medicine=self.medicine,
                schedule=self.schedule,
                scheduled_date=date,
                scheduled_time=self.schedule.scheduled_time,
                log_status=MedicineLog.STATUS_TAKEN,
            )

        response = self.client.get(
            reverse('health:medicine_detail', kwargs={'pk': self.medicine.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('week_adherence', response.context)


# =============================================================================
# 11. SUPPLY TRACKING TESTS
# =============================================================================

class MedicineSupplyTest(MedicineTestMixin, TestCase):
    """Tests for supply tracking."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_update_supply(self):
        """Supply can be updated."""
        medicine = self.create_medicine(self.user, current_supply=10)

        response = self.client.post(
            reverse('health:medicine_update_supply', kwargs={'pk': medicine.pk}),
            {'current_supply': 30}
        )

        self.assertEqual(response.status_code, 302)
        medicine.refresh_from_db()
        self.assertEqual(medicine.current_supply, 30)

    def test_low_supply_shown_on_home(self):
        """Low supply warning appears on medicine home."""
        medicine = self.create_medicine(
            self.user,
            current_supply=5,
            refill_threshold=7
        )

        response = self.client.get(reverse('health:medicine_home'))
        self.assertContains(response, 'low')


# =============================================================================
# 12. EDGE CASE TESTS
# =============================================================================

class MedicineEdgeCaseTest(MedicineTestMixin, TestCase):
    """Tests for edge cases."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_medicine_list_empty(self):
        """Medicine list loads with no medicines."""
        response = self.client.get(reverse('health:medicine_list'))
        self.assertEqual(response.status_code, 200)

    def test_medicine_home_empty(self):
        """Medicine home loads with no medicines."""
        response = self.client.get(reverse('health:medicine_home'))
        self.assertEqual(response.status_code, 200)

    def test_medicine_no_schedules(self):
        """Medicine detail works without schedules."""
        medicine = self.create_medicine(self.user)
        response = self.client.get(
            reverse('health:medicine_detail', kwargs={'pk': medicine.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_quick_look_with_multiple_medicines(self):
        """Quick look handles multiple medicines."""
        for i in range(5):
            med = self.create_medicine(self.user, name=f'Medicine {i}')
            self.create_schedule(med, time(8 + i, 0))

        response = self.client.get(reverse('health:medicine_quick_look'))
        self.assertEqual(response.status_code, 200)

    def test_history_with_date_filter(self):
        """History can be filtered by date."""
        medicine = self.create_medicine(self.user)
        start_date = (timezone.now().date() - timedelta(days=7)).isoformat()
        end_date = timezone.now().date().isoformat()

        response = self.client.get(
            reverse('health:medicine_history'),
            {'start': start_date, 'end': end_date}
        )
        self.assertEqual(response.status_code, 200)

    def test_history_filter_by_medicine(self):
        """History can be filtered by medicine."""
        medicine = self.create_medicine(self.user)
        response = self.client.get(
            reverse('health:medicine_history'),
            {'medicine': medicine.pk}
        )
        self.assertEqual(response.status_code, 200)


# =============================================================================
# 13. CONTEXT TESTS
# =============================================================================

class MedicineContextTest(MedicineTestMixin, TestCase):
    """Tests for view context data."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_medicine_home_has_active_medicines(self):
        """Medicine home includes active medicines in context."""
        self.create_medicine(self.user)
        response = self.client.get(reverse('health:medicine_home'))
        self.assertIn('active_medicines', response.context)

    def test_medicine_home_has_today_schedules(self):
        """Medicine home includes today's schedules."""
        medicine = self.create_medicine(self.user)
        self.create_schedule(medicine)

        response = self.client.get(reverse('health:medicine_home'))
        self.assertIn('today_schedules', response.context)

    def test_medicine_list_has_status_counts(self):
        """Medicine list includes status counts."""
        self.create_medicine(self.user)
        response = self.client.get(reverse('health:medicine_list'))

        self.assertIn('active_count', response.context)
        self.assertIn('paused_count', response.context)
        self.assertIn('completed_count', response.context)

    def test_adherence_page_has_daily_data(self):
        """Adherence page includes daily breakdown."""
        medicine = self.create_medicine(self.user)
        schedule = self.create_schedule(medicine)

        # Create some logs
        for i in range(7):
            MedicineLog.objects.create(
                user=self.user,
                medicine=medicine,
                schedule=schedule,
                scheduled_date=timezone.now().date() - timedelta(days=i),
                scheduled_time=schedule.scheduled_time,
                log_status=MedicineLog.STATUS_TAKEN,
            )

        response = self.client.get(reverse('health:medicine_adherence'))
        self.assertIn('daily_data', response.context)


# =============================================================================
# 14. HEALTH DASHBOARD INTEGRATION TESTS
# =============================================================================

class MedicineHealthDashboardTest(MedicineTestMixin, TestCase):
    """Tests for medicine integration with health dashboard."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_health_home_shows_medicine_count(self):
        """Health home shows medicine count."""
        self.create_medicine(self.user)
        response = self.client.get(reverse('health:home'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('medicine_count', response.context)
        self.assertEqual(response.context['medicine_count'], 1)

    def test_health_home_shows_overdue_count(self):
        """Health home shows overdue medicine count."""
        # Create medicine with schedule in the past
        medicine = self.create_medicine(self.user, grace_period_minutes=0)
        self.create_schedule(medicine, time(0, 1))  # 12:01 AM - almost certainly past

        response = self.client.get(reverse('health:home'))
        self.assertIn('medicine_overdue', response.context)

    def test_health_home_shows_low_supply(self):
        """Health home shows low supply count."""
        self.create_medicine(
            self.user,
            current_supply=3,
            refill_threshold=7
        )

        response = self.client.get(reverse('health:home'))
        self.assertIn('medicine_low_supply', response.context)
        self.assertEqual(response.context['medicine_low_supply'], 1)
