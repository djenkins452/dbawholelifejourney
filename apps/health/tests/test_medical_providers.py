# ==============================================================================
# File: test_medical_providers.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Comprehensive tests for MedicalProvider and ProviderStaff features
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-29
# Last Updated: 2025-12-29
# ==============================================================================

"""
Tests for Medical Providers feature.

Covers:
- MedicalProvider model CRUD operations
- ProviderStaff model CRUD operations
- Provider views (list, detail, create, update, delete)
- Staff views (create, update, delete)
- User isolation (users can only see their own providers)
- AI lookup endpoint
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.health.models import MedicalProvider, ProviderStaff
from apps.users.models import TermsAcceptance

User = get_user_model()


class MedicalProviderTestMixin:
    """Common setup for medical provider tests."""

    def create_user(self, email='test@example.com', password='testpass123'):
        """Create a test user with terms accepted and onboarding completed."""
        user = User.objects.create_user(email=email, password=password)
        self._accept_terms(user)
        self._complete_onboarding(user)
        return user

    def _accept_terms(self, user):
        TermsAcceptance.objects.create(user=user, terms_version='1.0')

    def _complete_onboarding(self, user):
        user.preferences.has_completed_onboarding = True
        user.preferences.save()

    def login_user(self, email='test@example.com', password='testpass123'):
        return self.client.login(email=email, password=password)

    def create_provider(self, user, name='Test Provider', **kwargs):
        """Create a test medical provider."""
        defaults = {
            'user': user,
            'name': name,
            'specialty': 'primary_care',
        }
        defaults.update(kwargs)
        return MedicalProvider.objects.create(**defaults)

    def create_staff(self, provider, user, name='Test Staff', **kwargs):
        """Create a test staff member."""
        defaults = {
            'provider': provider,
            'user': user,
            'name': name,
            'role': 'registered_nurse',
        }
        defaults.update(kwargs)
        return ProviderStaff.objects.create(**defaults)


class MedicalProviderModelTests(MedicalProviderTestMixin, TestCase):
    """Test MedicalProvider model functionality."""

    def test_create_provider(self):
        """Test creating a medical provider."""
        user = self.create_user()
        provider = self.create_provider(user, name='Dr. John Smith')

        self.assertEqual(provider.name, 'Dr. John Smith')
        self.assertEqual(provider.user, user)
        self.assertEqual(provider.specialty, 'primary_care')

    def test_provider_str(self):
        """Test provider string representation."""
        user = self.create_user()
        provider = self.create_provider(user, name='Dr. Smith', credentials='MD')

        self.assertEqual(str(provider), 'Dr. Smith, MD')

    def test_provider_str_no_credentials(self):
        """Test provider string without credentials."""
        user = self.create_user()
        provider = self.create_provider(user, name='Cleveland Clinic')

        self.assertEqual(str(provider), 'Cleveland Clinic')

    def test_full_address_property(self):
        """Test full_address property."""
        user = self.create_user()
        provider = self.create_provider(
            user,
            name='Test Clinic',
            address_line1='123 Main St',
            address_line2='Suite 100',
            city='Cleveland',
            state='OH',
            postal_code='44114',
        )

        address = provider.full_address
        self.assertIn('123 Main St', address)
        self.assertIn('Suite 100', address)
        self.assertIn('Cleveland', address)
        self.assertIn('OH', address)
        self.assertIn('44114', address)

    def test_staff_count_property(self):
        """Test staff_count property."""
        user = self.create_user()
        provider = self.create_provider(user)

        self.assertEqual(provider.staff_count, 0)

        self.create_staff(provider, user, name='Nurse Jane')
        self.create_staff(provider, user, name='PA Mike')

        self.assertEqual(provider.staff_count, 2)

    def test_specialty_choices(self):
        """Test that all specialty choices are valid."""
        user = self.create_user()

        for specialty_code, _ in MedicalProvider.SPECIALTY_CHOICES:
            provider = MedicalProvider.objects.create(
                user=user,
                name=f'Provider for {specialty_code}',
                specialty=specialty_code,
            )
            self.assertEqual(provider.specialty, specialty_code)

    def test_is_primary_flag(self):
        """Test primary provider flag."""
        user = self.create_user()
        provider1 = self.create_provider(user, name='Primary Doc', is_primary=True)
        provider2 = self.create_provider(user, name='Specialist', is_primary=False)

        self.assertTrue(provider1.is_primary)
        self.assertFalse(provider2.is_primary)

    def test_ai_lookup_tracking(self):
        """Test AI lookup tracking fields."""
        user = self.create_user()
        provider = self.create_provider(user)

        self.assertFalse(provider.ai_lookup_completed)
        self.assertIsNone(provider.ai_lookup_at)

        provider.ai_lookup_completed = True
        provider.ai_lookup_at = timezone.now()
        provider.save()

        provider.refresh_from_db()
        self.assertTrue(provider.ai_lookup_completed)
        self.assertIsNotNone(provider.ai_lookup_at)


class ProviderStaffModelTests(MedicalProviderTestMixin, TestCase):
    """Test ProviderStaff model functionality."""

    def test_create_staff(self):
        """Test creating a staff member."""
        user = self.create_user()
        provider = self.create_provider(user)
        staff = self.create_staff(provider, user, name='Jane Doe')

        self.assertEqual(staff.name, 'Jane Doe')
        self.assertEqual(staff.provider, provider)
        self.assertEqual(staff.role, 'registered_nurse')

    def test_staff_str(self):
        """Test staff string representation."""
        user = self.create_user()
        provider = self.create_provider(user, name='Dr. Smith')
        staff = self.create_staff(provider, user, name='Jane Doe', role='physician_assistant')

        str_repr = str(staff)
        self.assertIn('Jane Doe', str_repr)
        self.assertIn('Physician Assistant', str_repr)
        self.assertIn('Dr. Smith', str_repr)

    def test_role_choices(self):
        """Test that all role choices are valid."""
        user = self.create_user()
        provider = self.create_provider(user)

        for role_code, _ in ProviderStaff.ROLE_CHOICES:
            staff = ProviderStaff.objects.create(
                user=user,
                provider=provider,
                name=f'Staff for {role_code}',
                role=role_code,
            )
            self.assertEqual(staff.role, role_code)


class MedicalProviderViewTests(MedicalProviderTestMixin, TestCase):
    """Test Medical Provider views."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_provider_list_view(self):
        """Test provider list view."""
        provider = self.create_provider(self.user, name='Dr. Test')

        response = self.client.get(reverse('health:provider_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dr. Test')

    def test_provider_list_empty(self):
        """Test provider list with no providers."""
        response = self.client.get(reverse('health:provider_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No providers found')

    def test_provider_detail_view(self):
        """Test provider detail view."""
        provider = self.create_provider(
            self.user,
            name='Dr. John Smith',
            specialty='cardiology',
            phone='555-123-4567',
        )

        response = self.client.get(
            reverse('health:provider_detail', kwargs={'pk': provider.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dr. John Smith')
        self.assertContains(response, 'Cardiology')
        self.assertContains(response, '555-123-4567')

    def test_provider_create_view_get(self):
        """Test provider create view GET request."""
        response = self.client.get(reverse('health:provider_create'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Add Medical Provider')
        self.assertContains(response, 'Quick Start with AI')

    def test_provider_create_view_post(self):
        """Test provider create view POST request."""
        data = {
            'name': 'New Provider',
            'specialty': 'dermatology',
            'phone': '555-999-8888',
            'accepts_insurance': True,
            'country': 'USA',
        }

        response = self.client.post(reverse('health:provider_create'), data)

        self.assertEqual(response.status_code, 302)  # Redirect on success
        self.assertTrue(MedicalProvider.objects.filter(name='New Provider').exists())

    def test_provider_update_view_get(self):
        """Test provider update view GET request."""
        provider = self.create_provider(self.user, name='Old Name')

        response = self.client.get(
            reverse('health:provider_update', kwargs={'pk': provider.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Old Name')

    def test_provider_update_view_post(self):
        """Test provider update view POST request."""
        provider = self.create_provider(self.user, name='Old Name')

        data = {
            'name': 'New Name',
            'specialty': 'primary_care',
            'accepts_insurance': True,
            'country': 'USA',
        }

        response = self.client.post(
            reverse('health:provider_update', kwargs={'pk': provider.pk}),
            data,
        )

        self.assertEqual(response.status_code, 302)
        provider.refresh_from_db()
        self.assertEqual(provider.name, 'New Name')

    def test_provider_delete_view(self):
        """Test provider delete view."""
        provider = self.create_provider(self.user, name='To Be Deleted')

        response = self.client.post(
            reverse('health:provider_delete', kwargs={'pk': provider.pk})
        )

        self.assertEqual(response.status_code, 302)
        provider.refresh_from_db()
        self.assertEqual(provider.status, 'deleted')


class ProviderStaffViewTests(MedicalProviderTestMixin, TestCase):
    """Test Provider Staff views."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()
        self.provider = self.create_provider(self.user, name='Test Provider')

    def test_staff_create_view_get(self):
        """Test staff create view GET request."""
        response = self.client.get(
            reverse('health:staff_create', kwargs={'provider_pk': self.provider.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Add Staff Member')
        self.assertContains(response, 'Test Provider')

    def test_staff_create_view_post(self):
        """Test staff create view POST request."""
        data = {
            'name': 'Jane Nurse',
            'role': 'registered_nurse',
            'title': 'Head Nurse',
        }

        response = self.client.post(
            reverse('health:staff_create', kwargs={'provider_pk': self.provider.pk}),
            data,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(ProviderStaff.objects.filter(name='Jane Nurse').exists())

    def test_staff_update_view_get(self):
        """Test staff update view GET request."""
        staff = self.create_staff(self.provider, self.user, name='Old Staff')

        response = self.client.get(
            reverse('health:staff_update', kwargs={'pk': staff.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Old Staff')

    def test_staff_update_view_post(self):
        """Test staff update view POST request."""
        staff = self.create_staff(self.provider, self.user, name='Old Staff')

        data = {
            'name': 'Updated Staff',
            'role': 'physician_assistant',
        }

        response = self.client.post(
            reverse('health:staff_update', kwargs={'pk': staff.pk}),
            data,
        )

        self.assertEqual(response.status_code, 302)
        staff.refresh_from_db()
        self.assertEqual(staff.name, 'Updated Staff')

    def test_staff_delete_view(self):
        """Test staff delete view."""
        staff = self.create_staff(self.provider, self.user, name='To Be Deleted')

        response = self.client.post(
            reverse('health:staff_delete', kwargs={'pk': staff.pk})
        )

        self.assertEqual(response.status_code, 302)
        staff.refresh_from_db()
        self.assertEqual(staff.status, 'deleted')


class UserIsolationTests(MedicalProviderTestMixin, TestCase):
    """Test that users can only see their own providers."""

    def setUp(self):
        self.client = Client()
        self.user1 = self.create_user(email='user1@example.com')
        self.user2 = self.create_user(email='user2@example.com')

    def test_provider_list_isolation(self):
        """Test that users only see their own providers in list."""
        provider1 = self.create_provider(self.user1, name='User1 Provider')
        provider2 = self.create_provider(self.user2, name='User2 Provider')

        # Login as user1
        self.client.login(email='user1@example.com', password='testpass123')
        response = self.client.get(reverse('health:provider_list'))

        self.assertContains(response, 'User1 Provider')
        self.assertNotContains(response, 'User2 Provider')

    def test_provider_detail_isolation(self):
        """Test that users cannot access other users' providers."""
        provider = self.create_provider(self.user1, name='User1 Provider')

        # Login as user2
        self.client.login(email='user2@example.com', password='testpass123')
        response = self.client.get(
            reverse('health:provider_detail', kwargs={'pk': provider.pk})
        )

        self.assertEqual(response.status_code, 404)

    def test_provider_update_isolation(self):
        """Test that users cannot update other users' providers."""
        provider = self.create_provider(self.user1, name='User1 Provider')

        # Login as user2
        self.client.login(email='user2@example.com', password='testpass123')
        response = self.client.get(
            reverse('health:provider_update', kwargs={'pk': provider.pk})
        )

        self.assertEqual(response.status_code, 404)

    def test_provider_delete_isolation(self):
        """Test that users cannot delete other users' providers."""
        provider = self.create_provider(self.user1, name='User1 Provider')

        # Login as user2
        self.client.login(email='user2@example.com', password='testpass123')
        response = self.client.post(
            reverse('health:provider_delete', kwargs={'pk': provider.pk})
        )

        self.assertEqual(response.status_code, 404)

    def test_staff_isolation(self):
        """Test that users cannot access other users' staff."""
        provider = self.create_provider(self.user1)
        staff = self.create_staff(provider, self.user1, name='User1 Staff')

        # Login as user2
        self.client.login(email='user2@example.com', password='testpass123')

        # Try to access staff update
        response = self.client.get(
            reverse('health:staff_update', kwargs={'pk': staff.pk})
        )
        self.assertEqual(response.status_code, 404)

        # Try to delete staff
        response = self.client.post(
            reverse('health:staff_delete', kwargs={'pk': staff.pk})
        )
        self.assertEqual(response.status_code, 404)


class ProviderAILookupTests(MedicalProviderTestMixin, TestCase):
    """Test AI lookup endpoint (mocked)."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_ai_lookup_requires_name(self):
        """Test that AI lookup requires provider name."""
        response = self.client.post(
            reverse('health:provider_ai_lookup'),
            {'name': '', 'city': 'Cleveland', 'state': 'OH'},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('required', data['error'].lower())

    def test_ai_lookup_requires_login(self):
        """Test that AI lookup requires authentication."""
        self.client.logout()

        response = self.client.post(
            reverse('health:provider_ai_lookup'),
            {'name': 'Dr. Test', 'city': 'Cleveland', 'state': 'OH'},
        )

        # Should redirect to login
        self.assertEqual(response.status_code, 302)


class HealthHomeViewProviderTests(MedicalProviderTestMixin, TestCase):
    """Test provider display on health home page."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_health_home_shows_provider_count(self):
        """Test that health home shows provider count."""
        self.create_provider(self.user, name='Provider 1')
        self.create_provider(self.user, name='Provider 2')

        response = self.client.get(reverse('health:home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '2')  # provider count
        self.assertContains(response, 'providers')

    def test_health_home_shows_primary_provider(self):
        """Test that health home shows primary provider."""
        self.create_provider(self.user, name='Regular Doc', is_primary=False)
        self.create_provider(self.user, name='My Primary Care', is_primary=True)

        response = self.client.get(reverse('health:home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My Primary Care')

    def test_health_home_no_providers(self):
        """Test health home with no providers."""
        response = self.client.get(reverse('health:home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Keep track of your doctors')


class MedicalProviderFormTests(MedicalProviderTestMixin, TestCase):
    """Test form validation."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_create_provider_minimal_data(self):
        """Test creating provider with minimal required data."""
        data = {
            'name': 'Simple Provider',
            'specialty': 'other',
            'accepts_insurance': True,
            'country': 'USA',
        }

        response = self.client.post(reverse('health:provider_create'), data)

        self.assertEqual(response.status_code, 302)
        provider = MedicalProvider.objects.get(name='Simple Provider')
        self.assertEqual(provider.user, self.user)

    def test_create_provider_full_data(self):
        """Test creating provider with full data."""
        data = {
            'name': 'Full Provider',
            'specialty': 'cardiology',
            'credentials': 'MD, FACC',
            'phone': '555-123-4567',
            'phone_alt': '555-987-6543',
            'fax': '555-111-2222',
            'email': 'office@provider.com',
            'website': 'https://provider.com',
            'address_line1': '123 Medical Dr',
            'address_line2': 'Suite 200',
            'city': 'Cleveland',
            'state': 'OH',
            'postal_code': '44114',
            'country': 'USA',
            'portal_url': 'https://portal.provider.com',
            'portal_username': 'patient123',
            'npi_number': '1234567890',
            'accepts_insurance': True,
            'insurance_notes': 'Accepts Medicare, Aetna',
            'is_primary': True,
            'notes': 'Great doctor, very thorough',
        }

        response = self.client.post(reverse('health:provider_create'), data)

        self.assertEqual(response.status_code, 302)
        provider = MedicalProvider.objects.get(name='Full Provider')
        self.assertEqual(provider.credentials, 'MD, FACC')
        self.assertEqual(provider.city, 'Cleveland')
        self.assertTrue(provider.is_primary)
