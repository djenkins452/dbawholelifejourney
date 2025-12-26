"""
Purpose Module Tests

Tests for goals, annual direction, and reflections.

Location: apps/purpose/tests/test_purpose.py
"""

from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.purpose.models import AnnualDirection, LifeGoal, Reflection

User = get_user_model()


class AnnualDirectionModelTest(TestCase):
    """Tests for the AnnualDirection model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
    
    def test_create_annual_direction(self):
        """Annual direction can be created."""
        direction = AnnualDirection.objects.create(
            user=self.user,
            year=2025,
            word_of_year='Growth'
        )
        self.assertEqual(direction.year, 2025)
        self.assertEqual(direction.word_of_year, 'Growth')
    
    def test_annual_direction_str(self):
        """Annual direction string representation."""
        direction = AnnualDirection.objects.create(
            user=self.user,
            year=2025,
            word_of_year='Focus'
        )
        # Check string contains year
        self.assertIn('2025', str(direction))


class LifeGoalModelTest(TestCase):
    """Tests for the LifeGoal model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
    
    def test_create_goal(self):
        """Goal can be created."""
        goal = LifeGoal.objects.create(
            user=self.user,
            title='Learn Spanish',
            description='Become conversational in Spanish'
        )
        self.assertEqual(goal.title, 'Learn Spanish')
    
    def test_goal_str(self):
        """Goal string is the title."""
        goal = LifeGoal.objects.create(
            user=self.user,
            title='Read 24 Books'
        )
        self.assertIn('Read 24 Books', str(goal))
    
    def test_goal_status_choices(self):
        """Goal can have different statuses."""
        goal = LifeGoal.objects.create(
            user=self.user,
            title='Test Goal',
            status='active'
        )
        self.assertEqual(goal.status, 'active')
        
        goal.status = 'completed'
        goal.save()
        goal.refresh_from_db()
        self.assertEqual(goal.status, 'completed')


class ReflectionModelTest(TestCase):
    """Tests for the Reflection model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
    
    def test_create_reflection(self):
        """Reflection can be created."""
        reflection = Reflection.objects.create(
            user=self.user,
            title='Weekly Reflection',
            year=2025,
            reflection_type='quarterly'
        )
        self.assertEqual(reflection.title, 'Weekly Reflection')
        self.assertEqual(reflection.year, 2025)


class PurposeViewTest(TestCase):
    """Tests for purpose module views."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self._accept_terms(self.user)
        # Enable purpose module
        self.user.preferences.purpose_enabled = True
        self.user.preferences.save()
    
    def _accept_terms(self, user):
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=user,
            terms_version='1.0'
        )
    
    def test_purpose_home_requires_login(self):
        """Purpose home requires authentication."""
        response = self.client.get(reverse('purpose:home'))
        self.assertEqual(response.status_code, 302)
    
    def test_purpose_home_loads(self):
        """Purpose home page loads for authenticated user."""
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(reverse('purpose:home'))
        self.assertEqual(response.status_code, 200)
    
    def test_goal_list_loads(self):
        """Goal list page loads."""
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(reverse('purpose:goal_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_goal_create_page_loads(self):
        """Goal create page loads."""
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(reverse('purpose:goal_create'))
        self.assertEqual(response.status_code, 200)
    
    def test_direction_list_loads(self):
        """Direction list page loads."""
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(reverse('purpose:direction_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_reflection_list_loads(self):
        """Reflection list page loads."""
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(reverse('purpose:reflection_list'))
        self.assertEqual(response.status_code, 200)


class PurposeDataIsolationTest(TestCase):
    """Tests to ensure users can only see their own purpose data."""
    
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
        
        # Enable purpose module for both users
        self.user_a.preferences.purpose_enabled = True
        self.user_a.preferences.save()
        self.user_b.preferences.purpose_enabled = True
        self.user_b.preferences.save()
        
        # Create goals for each user
        self.goal_a = LifeGoal.objects.create(
            user=self.user_a,
            title='User A Goal'
        )
        self.goal_b = LifeGoal.objects.create(
            user=self.user_b,
            title='User B Goal'
        )
    
    def _accept_terms(self, user):
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=user,
            terms_version='1.0'
        )
    
    def test_user_a_sees_only_their_goals(self):
        """User A only sees their own goals."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(reverse('purpose:goal_list'))
        
        self.assertContains(response, 'User A Goal')
        self.assertNotContains(response, 'User B Goal')
    
    def test_user_cannot_edit_other_users_goal(self):
        """User A cannot edit User B's goal."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(
            reverse('purpose:goal_update', kwargs={'pk': self.goal_b.pk})
        )
        self.assertEqual(response.status_code, 404)
    
    def test_user_cannot_delete_other_users_goal(self):
        """User A cannot delete User B's goal."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.post(
            reverse('purpose:goal_delete', kwargs={'pk': self.goal_b.pk})
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(LifeGoal.objects.filter(pk=self.goal_b.pk).exists())