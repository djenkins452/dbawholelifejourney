"""
Purpose Module - Comprehensive Tests

This test file covers:
1. Model tests (AnnualDirection, LifeGoal, ChangeIntention, Reflection)
2. View tests (loading, authentication)
3. Form validation tests
4. Edge case tests
5. Business logic tests (status changes, completion)
6. Data isolation tests

Location: apps/purpose/tests/test_purpose_comprehensive.py
"""

from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.purpose.models import (
    AnnualDirection, LifeGoal, ChangeIntention, Reflection, LifeDomain
)

User = get_user_model()


# =============================================================================
# TEST HELPERS
# =============================================================================

class PurposeTestMixin:
    """Common setup for purpose tests."""
    
    def create_user(self, email='test@example.com', password='testpass123'):
        """Create a test user with terms accepted and purpose enabled."""
        user = User.objects.create_user(email=email, password=password)
        self._accept_terms(user)
        self._enable_purpose(user)
        return user
    
    def _accept_terms(self, user):
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(user=user, terms_version='1.0')
    
    def _enable_purpose(self, user):
        user.preferences.purpose_enabled = True
        user.preferences.save()
    
    def login_user(self, email='test@example.com', password='testpass123'):
        return self.client.login(email=email, password=password)
    
    def create_direction(self, user, year=None, word='Focus', **kwargs):
        """Helper to create an annual direction."""
        if year is None:
            year = date.today().year
        return AnnualDirection.objects.create(
            user=user, year=year, word_of_year=word, **kwargs
        )
    
    def create_goal(self, user, title='Test Goal', **kwargs):
        """Helper to create a life goal."""
        return LifeGoal.objects.create(user=user, title=title, **kwargs)
    
    def create_intention(self, user, intention='Test Intention', **kwargs):
        """Helper to create a change intention."""
        return ChangeIntention.objects.create(user=user, intention=intention, **kwargs)
    
    def create_reflection(self, user, year=None, **kwargs):
        """Helper to create a reflection."""
        if year is None:
            year = date.today().year
        return Reflection.objects.create(user=user, year=year, **kwargs)
    
    def create_domain(self, name='Personal Growth', **kwargs):
        """Helper to create a life domain."""
        return LifeDomain.objects.create(
            name=name, 
            slug=name.lower().replace(' ', '-'),
            **kwargs
        )


# =============================================================================
# 1. ANNUAL DIRECTION MODEL TESTS
# =============================================================================

class AnnualDirectionModelTest(PurposeTestMixin, TestCase):
    """Tests for the AnnualDirection model."""
    
    def setUp(self):
        self.user = self.create_user()
    
    def test_create_direction(self):
        """Direction can be created."""
        direction = self.create_direction(self.user)
        self.assertEqual(direction.word_of_year, 'Focus')
    
    def test_direction_str(self):
        """Direction string includes year and word."""
        direction = self.create_direction(self.user, year=2025, word='Growth')
        str_repr = str(direction)
        self.assertIn('2025', str_repr)
        self.assertIn('Growth', str_repr)
    
    def test_direction_unique_per_year(self):
        """Only one direction per user per year."""
        self.create_direction(self.user, year=2025)
        
        with self.assertRaises(Exception):
            self.create_direction(self.user, year=2025, word='Different')
    
    def test_direction_with_theme(self):
        """Direction can have a theme."""
        direction = self.create_direction(
            self.user,
            theme='Building Foundations',
            theme_description='Focus on core habits'
        )
        self.assertEqual(direction.theme, 'Building Foundations')
    
    def test_direction_with_anchor(self):
        """Direction can have an anchor scripture/quote."""
        direction = self.create_direction(
            self.user,
            anchor_text='Trust in the Lord with all your heart',
            anchor_source='Proverbs 3:5'
        )
        self.assertIn('Trust', direction.anchor_text)
    
    def test_is_current_flag(self):
        """is_current flag works correctly."""
        direction = self.create_direction(self.user, is_current=True)
        self.assertTrue(direction.is_current)
    
    def test_only_one_current_direction(self):
        """Setting is_current unsets other directions."""
        dir1 = self.create_direction(self.user, year=2024, is_current=True)
        dir2 = self.create_direction(self.user, year=2025, is_current=True)
        
        dir1.refresh_from_db()
        self.assertFalse(dir1.is_current)
        self.assertTrue(dir2.is_current)
    
    def test_direction_ordering(self):
        """Directions are ordered by year descending."""
        old = self.create_direction(self.user, year=2023)
        new = self.create_direction(self.user, year=2025)
        
        directions = AnnualDirection.objects.filter(user=self.user)
        self.assertEqual(directions[0], new)


# =============================================================================
# 2. LIFE GOAL MODEL TESTS
# =============================================================================

class LifeGoalModelTest(PurposeTestMixin, TestCase):
    """Tests for the LifeGoal model."""
    
    def setUp(self):
        self.user = self.create_user()
    
    def test_create_goal(self):
        """Goal can be created."""
        goal = self.create_goal(self.user)
        self.assertEqual(goal.title, 'Test Goal')
        self.assertEqual(goal.status, 'active')
    
    def test_goal_str(self):
        """Goal string is the title."""
        goal = self.create_goal(self.user, title='Learn Spanish')
        self.assertEqual(str(goal), 'Learn Spanish')
    
    def test_goal_statuses(self):
        """Goal supports different statuses."""
        for status in ['active', 'paused', 'completed', 'released']:
            goal = self.create_goal(
                self.user,
                title=f'{status} goal',
                status=status
            )
            self.assertEqual(goal.status, status)
    
    def test_goal_timeframes(self):
        """Goal supports different timeframes."""
        for timeframe in ['year_1', 'year_2', 'year_3', 'ongoing']:
            goal = self.create_goal(
                self.user,
                title=f'{timeframe} goal',
                timeframe=timeframe
            )
            self.assertEqual(goal.timeframe, timeframe)
    
    def test_goal_with_domain(self):
        """Goal can be linked to a domain."""
        domain = self.create_domain()
        goal = self.create_goal(self.user, domain=domain)
        
        self.assertEqual(goal.domain, domain)
    
    def test_goal_with_direction(self):
        """Goal can be linked to annual direction."""
        direction = self.create_direction(self.user)
        goal = self.create_goal(self.user, annual_direction=direction)
        
        self.assertEqual(goal.annual_direction, direction)
    
    def test_mark_complete(self):
        """mark_complete() sets status and date."""
        goal = self.create_goal(self.user)
        goal.mark_complete()
        
        self.assertEqual(goal.status, 'completed')
        self.assertIsNotNone(goal.completed_date)
    
    def test_mark_released(self):
        """mark_released() sets status."""
        goal = self.create_goal(self.user)
        goal.mark_released()
        
        self.assertEqual(goal.status, 'released')
    
    def test_goal_with_why(self):
        """Goal can include why it matters."""
        goal = self.create_goal(
            self.user,
            why_it_matters='To connect with my heritage'
        )
        self.assertIn('heritage', goal.why_it_matters)
    
    def test_goal_with_success_definition(self):
        """Goal can define what success looks like."""
        goal = self.create_goal(
            self.user,
            success_looks_like='Having a 30-minute conversation in Spanish'
        )
        self.assertIn('conversation', goal.success_looks_like)


# =============================================================================
# 3. CHANGE INTENTION MODEL TESTS
# =============================================================================

class ChangeIntentionModelTest(PurposeTestMixin, TestCase):
    """Tests for the ChangeIntention model."""
    
    def setUp(self):
        self.user = self.create_user()
    
    def test_create_intention(self):
        """Intention can be created."""
        intention = self.create_intention(self.user)
        self.assertEqual(intention.intention, 'Test Intention')
    
    def test_intention_str(self):
        """Intention string is the intention text."""
        intention = self.create_intention(self.user, intention='Be more present')
        self.assertEqual(str(intention), 'Be more present')
    
    def test_intention_with_description(self):
        """Intention can have a description."""
        intention = self.create_intention(
            self.user,
            description='Put away phone during family time'
        )
        self.assertIn('phone', intention.description)


# =============================================================================
# 4. REFLECTION MODEL TESTS
# =============================================================================

class ReflectionModelTest(PurposeTestMixin, TestCase):
    """Tests for the Reflection model."""
    
    def setUp(self):
        self.user = self.create_user()
    
    def test_create_reflection(self):
        """Reflection can be created."""
        reflection = self.create_reflection(self.user)
        self.assertEqual(reflection.year, date.today().year)
    
    def test_reflection_str(self):
        """Reflection string includes year."""
        reflection = self.create_reflection(self.user, year=2024)
        self.assertIn('2024', str(reflection))


# =============================================================================
# 5. VIEW TESTS - Basic Loading
# =============================================================================

class PurposeViewBasicTest(PurposeTestMixin, TestCase):
    """Basic view loading tests."""
    
    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
    
    # --- Authentication Required ---
    
    def test_purpose_home_requires_login(self):
        """Purpose home redirects anonymous users."""
        response = self.client.get(reverse('purpose:home'))
        self.assertEqual(response.status_code, 302)
    
    def test_goal_list_requires_login(self):
        """Goal list requires authentication."""
        response = self.client.get(reverse('purpose:goal_list'))
        self.assertEqual(response.status_code, 302)
    
    def test_direction_list_requires_login(self):
        """Direction list requires authentication."""
        response = self.client.get(reverse('purpose:direction_list'))
        self.assertEqual(response.status_code, 302)
    
    # --- Authenticated Access ---
    
    def test_purpose_home_loads(self):
        """Purpose home loads for authenticated user."""
        self.login_user()
        response = self.client.get(reverse('purpose:home'))
        self.assertEqual(response.status_code, 200)
    
    def test_goal_list_loads(self):
        """Goal list page loads."""
        self.login_user()
        response = self.client.get(reverse('purpose:goal_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_goal_create_loads(self):
        """Goal create page loads."""
        self.login_user()
        response = self.client.get(reverse('purpose:goal_create'))
        self.assertEqual(response.status_code, 200)
    
    def test_direction_list_loads(self):
        """Direction list page loads."""
        self.login_user()
        response = self.client.get(reverse('purpose:direction_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_direction_create_loads(self):
        """Direction create page loads."""
        self.login_user()
        response = self.client.get(reverse('purpose:direction_create'))
        self.assertEqual(response.status_code, 200)
    
    def test_intention_list_loads(self):
        """Intention list page loads."""
        self.login_user()
        response = self.client.get(reverse('purpose:intention_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_reflection_list_loads(self):
        """Reflection list page loads."""
        self.login_user()
        response = self.client.get(reverse('purpose:reflection_list'))
        self.assertEqual(response.status_code, 200)


# =============================================================================
# 6. FORM VALIDATION TESTS
# =============================================================================

class PurposeFormTest(PurposeTestMixin, TestCase):
    """Tests for purpose form validation."""
    
    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()
    
    def test_create_goal_via_model(self):
        """Goal can be created via model."""
        goal = self.create_goal(self.user, title='New Goal')
        self.assertTrue(
            LifeGoal.objects.filter(user=self.user, title='New Goal').exists()
        )
    
    def test_create_direction_via_model(self):
        """Direction can be created via model."""
        direction = self.create_direction(self.user, word='Clarity')
        self.assertTrue(
            AnnualDirection.objects.filter(
                user=self.user, word_of_year='Clarity'
            ).exists()
        )
    
    def test_goal_create_has_form(self):
        """Goal create page has form."""
        response = self.client.get(reverse('purpose:goal_create'))
        self.assertIn('form', response.context)


# =============================================================================
# 7. EDGE CASE TESTS
# =============================================================================

class PurposeEdgeCaseTest(PurposeTestMixin, TestCase):
    """Tests for edge cases."""
    
    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()
    
    def test_goal_list_empty(self):
        """Goal list loads with no goals."""
        response = self.client.get(reverse('purpose:goal_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_direction_list_empty(self):
        """Direction list loads with no directions."""
        response = self.client.get(reverse('purpose:direction_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_long_goal_title(self):
        """Goal handles long title."""
        long_title = 'A' * 200
        goal = self.create_goal(self.user, title=long_title)
        self.assertEqual(goal.title, long_title)
    
    def test_long_word_of_year(self):
        """Direction handles long word."""
        long_word = 'B' * 50
        direction = self.create_direction(self.user, word=long_word)
        self.assertEqual(direction.word_of_year, long_word)
    
    def test_goal_with_past_target_date(self):
        """Goal can have past target date."""
        past = date.today() - timedelta(days=365)
        goal = self.create_goal(self.user, target_date=past)
        self.assertEqual(goal.target_date, past)


# =============================================================================
# 8. BUSINESS LOGIC TESTS
# =============================================================================

class PurposeBusinessLogicTest(PurposeTestMixin, TestCase):
    """Tests for business logic."""
    
    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()
    
    def test_filter_active_goals(self):
        """Can filter active goals."""
        active = self.create_goal(self.user, status='active')
        completed = self.create_goal(self.user, status='completed')
        
        active_goals = LifeGoal.objects.filter(user=self.user, status='active')
        self.assertEqual(active_goals.count(), 1)
    
    def test_filter_goals_by_timeframe(self):
        """Can filter goals by timeframe."""
        year1 = self.create_goal(self.user, timeframe='year_1')
        ongoing = self.create_goal(self.user, timeframe='ongoing')
        
        year1_goals = LifeGoal.objects.filter(
            user=self.user, timeframe='year_1'
        )
        self.assertEqual(year1_goals.count(), 1)
    
    def test_filter_goals_by_domain(self):
        """Can filter goals by domain."""
        domain = self.create_domain(name='Health')
        health_goal = self.create_goal(self.user, domain=domain)
        other_goal = self.create_goal(self.user)
        
        health_goals = LifeGoal.objects.filter(user=self.user, domain=domain)
        self.assertEqual(health_goals.count(), 1)
    
    def test_get_current_direction(self):
        """Can get current year's direction."""
        past = self.create_direction(self.user, year=2023)
        current = self.create_direction(self.user, year=2025, is_current=True)
        
        current_dir = AnnualDirection.objects.filter(
            user=self.user, is_current=True
        ).first()
        self.assertEqual(current_dir, current)


# =============================================================================
# 9. DATA ISOLATION TESTS
# =============================================================================

class PurposeDataIsolationTest(PurposeTestMixin, TestCase):
    """Tests to ensure users can only see their own purpose data."""
    
    def setUp(self):
        self.client = Client()
        self.user_a = self.create_user(email='usera@example.com')
        self.user_b = self.create_user(email='userb@example.com')
        
        self.goal_a = self.create_goal(self.user_a, title='User A Goal')
        self.goal_b = self.create_goal(self.user_b, title='User B Goal')
        
        self.direction_a = self.create_direction(
            self.user_a, year=2025, word='WordA'
        )
        self.direction_b = self.create_direction(
            self.user_b, year=2025, word='WordB'
        )
    
    def test_user_sees_only_own_goals(self):
        """User only sees their own goals."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(reverse('purpose:goal_list'))
        
        self.assertContains(response, 'User A Goal')
        self.assertNotContains(response, 'User B Goal')
    
    def test_user_sees_only_own_directions(self):
        """User only sees their own directions."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(reverse('purpose:direction_list'))
        
        self.assertContains(response, 'WordA')
        self.assertNotContains(response, 'WordB')
    
    def test_user_cannot_view_other_users_goal(self):
        """User cannot view another user's goal detail."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(
            reverse('purpose:goal_detail', kwargs={'pk': self.goal_b.pk})
        )
        self.assertEqual(response.status_code, 404)
    
    def test_user_cannot_edit_other_users_goal(self):
        """User cannot edit another user's goal."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(
            reverse('purpose:goal_update', kwargs={'pk': self.goal_b.pk})
        )
        self.assertEqual(response.status_code, 404)
    
    def test_user_cannot_delete_other_users_goal(self):
        """User cannot delete another user's goal."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.post(
            reverse('purpose:goal_delete', kwargs={'pk': self.goal_b.pk})
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(LifeGoal.objects.filter(pk=self.goal_b.pk).exists())


# =============================================================================
# 10. CONTEXT TESTS
# =============================================================================

class PurposeContextTest(PurposeTestMixin, TestCase):
    """Tests for view context data."""
    
    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()
    
    def test_goal_list_has_goals(self):
        """Goal list includes goals in context."""
        self.create_goal(self.user)
        
        response = self.client.get(reverse('purpose:goal_list'))
        
        self.assertTrue(
            'object_list' in response.context or 'goals' in response.context
        )
    
    def test_goal_detail_has_goal(self):
        """Goal detail includes goal in context."""
        goal = self.create_goal(self.user)
        
        response = self.client.get(
            reverse('purpose:goal_detail', kwargs={'pk': goal.pk})
        )
        
        self.assertEqual(response.context['object'], goal)