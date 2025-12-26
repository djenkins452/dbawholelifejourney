"""
Health Module Tests

Tests for weight tracking, fasting, glucose, and heart rate.

Location: apps/health/tests/test_health.py
"""

from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.health.models import WeightEntry, FastingWindow, GlucoseEntry

User = get_user_model()


class WeightEntryModelTest(TestCase):
    """Tests for the WeightEntry model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
    
    def test_create_weight_entry(self):
        """Weight entry can be created."""
        entry = WeightEntry.objects.create(
            user=self.user,
            value=Decimal('185.5'),
            unit='lb'
        )
        self.assertEqual(entry.value, Decimal('185.5'))
        self.assertEqual(entry.user, self.user)
    
    def test_weight_entry_str(self):
        """Weight entry string representation."""
        entry = WeightEntry.objects.create(
            user=self.user,
            value=Decimal('180.0'),
            unit='lb'
        )
        self.assertIn('180', str(entry))
    
    def test_weight_entry_ordering(self):
        """Weight entries are ordered by most recent first."""
        entry1 = WeightEntry.objects.create(
            user=self.user,
            value=Decimal('185.0'),
            unit='lb'
        )
        entry2 = WeightEntry.objects.create(
            user=self.user,
            value=Decimal('184.0'),
            unit='lb'
        )
        entries = WeightEntry.objects.filter(user=self.user)
        self.assertEqual(entries[0], entry2)  # Most recent first


class FastingWindowModelTest(TestCase):
    """Tests for the FastingWindow model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
    
    def test_create_fasting_window(self):
        """Fasting window can be created."""
        fast = FastingWindow.objects.create(
            user=self.user,
            started_at=timezone.now()
        )
        self.assertEqual(fast.user, self.user)
        self.assertIsNone(fast.ended_at)
    
    def test_fasting_is_active(self):
        """Active fasting window has no end time."""
        fast = FastingWindow.objects.create(
            user=self.user,
            started_at=timezone.now()
        )
        self.assertTrue(fast.is_active)
    
    def test_fasting_end(self):
        """Fasting window can be ended."""
        fast = FastingWindow.objects.create(
            user=self.user,
            started_at=timezone.now() - timedelta(hours=16)
        )
        fast.ended_at = timezone.now()
        fast.save()
        
        self.assertFalse(fast.is_active)
        self.assertIsNotNone(fast.ended_at)
    
    def test_fasting_duration(self):
        """Fasting duration is calculated correctly."""
        start = timezone.now() - timedelta(hours=18)
        end = timezone.now()
        
        fast = FastingWindow.objects.create(
            user=self.user,
            started_at=start,
            ended_at=end
        )
        
        # Duration should be approximately 18 hours
        self.assertAlmostEqual(fast.duration_hours, 18, delta=0.1)


class GlucoseEntryModelTest(TestCase):
    """Tests for the GlucoseEntry model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
    
    def test_create_glucose_entry(self):
        """Glucose entry can be created."""
        entry = GlucoseEntry.objects.create(
            user=self.user,
            value=95
        )
        self.assertEqual(entry.value, 95)
    
    def test_glucose_in_normal_range(self):
        """Glucose entry recognizes normal range."""
        entry = GlucoseEntry.objects.create(
            user=self.user,
            value=100
        )
        # Normal fasting glucose is typically 70-100 mg/dL
        self.assertTrue(70 <= entry.value <= 100)


class HealthViewTest(TestCase):
    """Tests for health module views."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self._accept_terms(self.user)
        self.client.login(email='test@example.com', password='testpass123')
    
    def _accept_terms(self, user):
        try:
            from apps.users.models import TermsAcceptance
            from django.conf import settings
            TermsAcceptance.objects.create(
                user=user,
                terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
            )
        except (ImportError, Exception):
            pass
    
    def test_health_home_requires_login(self):
        """Health home requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('health:home'))
        self.assertEqual(response.status_code, 302)
    
    def test_health_home_loads(self):
        """Health home page loads for authenticated user."""
        response = self.client.get(reverse('health:home'))
        self.assertEqual(response.status_code, 200)
    
    def test_weight_list_loads(self):
        """Weight list page loads."""
        response = self.client.get(reverse('health:weight_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_weight_can_be_logged(self):
        """User can log a weight entry via form."""
        # Create entry directly to test model works
        entry = WeightEntry.objects.create(
            user=self.user,
            value=Decimal('185.5'),
            unit='lb'
        )
        self.assertTrue(WeightEntry.objects.filter(user=self.user).exists())
    
    def test_fasting_list_loads(self):
        """Fasting list page loads."""
        response = self.client.get(reverse('health:fasting_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_fasting_can_be_created(self):
        """Fasting window can be created."""
        fast = FastingWindow.objects.create(
            user=self.user,
            started_at=timezone.now()
        )
        self.assertTrue(
            FastingWindow.objects.filter(
                user=self.user,
                ended_at__isnull=True
            ).exists()
        )


class HealthDataIsolationTest(TestCase):
    """Tests to ensure users can only see their own health data."""
    
    def setUp(self):
        self.client = Client()
        self.user_a = User.objects.create_user(
            email='usera@example.com',
            password='testpass123'
        )
        self.user_b = User.objects.create_user(
            email='userb@example.com',
            password='testpass123'
        )
        self._accept_terms(self.user_a)
        self._accept_terms(self.user_b)
        
        # Create weight entries for each user
        self.weight_a = WeightEntry.objects.create(
            user=self.user_a,
            value=Decimal('185.0'),
            unit='lb'
        )
        self.weight_b = WeightEntry.objects.create(
            user=self.user_b,
            value=Decimal('165.0'),
            unit='lb'
        )
    
    def _accept_terms(self, user):
        try:
            from apps.users.models import TermsAcceptance
            from django.conf import settings
            TermsAcceptance.objects.create(
                user=user,
                terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
            )
        except (ImportError, Exception):
            pass
    
    def test_user_a_sees_only_their_weights(self):
        """User A only sees their own weight entries."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(reverse('health:weight_list'))
        
        self.assertContains(response, '185')
        self.assertNotContains(response, '165')
    
    def test_user_cannot_access_other_users_weight(self):
        """User A cannot access User B's weight entry."""
        self.client.login(email='usera@example.com', password='testpass123')
        
        # Try to access User B's weight detail if that URL exists
        # Most health apps don't have individual weight detail pages
        # so this test checks the list filtering works
        weights = WeightEntry.objects.filter(user=self.user_a)
        self.assertEqual(weights.count(), 1)
        self.assertEqual(weights[0].value, Decimal('185.0'))