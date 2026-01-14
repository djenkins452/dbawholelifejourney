"""
Tests for the Teaching Tool feature.

The Teaching Tool helps users find where to perform actions in the app
by matching natural language questions to destination URLs.
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.conf import settings
from django.contrib.auth import get_user_model

from apps.help.models import TeachingDestination
from apps.help.services import TeachingToolService


User = get_user_model()


class BaseTeachingToolTest(TestCase):
    """Base class with authentication helpers."""

    def _accept_terms(self, user):
        """Helper to accept terms for a user."""
        try:
            from apps.users.models import TermsAcceptance
            TermsAcceptance.objects.create(
                user=user,
                terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
            )
        except (ImportError, Exception):
            pass

    def _complete_onboarding(self, user):
        """Mark user onboarding as complete."""
        user.preferences.has_completed_onboarding = True
        user.preferences.save()


class TeachingDestinationModelTest(TestCase):
    """Tests for the TeachingDestination model."""

    def test_create_destination(self):
        """Test creating a teaching destination."""
        dest = TeachingDestination.objects.create(
            destination_id='test-destination',
            name='Test Destination',
            path_description='Test > Path',
            explanation='This is a test destination.',
            url='/test/path/',
            keywords='test, testing, sample',
            module='test',
            sort_order=1,
        )
        self.assertEqual(dest.name, 'Test Destination')
        self.assertEqual(dest.url, '/test/path/')
        self.assertTrue(dest.is_active)

    def test_keywords_list_property(self):
        """Test that keywords are properly parsed into a list."""
        dest = TeachingDestination.objects.create(
            destination_id='test-keywords',
            name='Keywords Test',
            path_description='Test',
            url='/test/',
            keywords='weight, log weight, track weight, weigh myself',
        )
        expected = ['weight', 'log weight', 'track weight', 'weigh myself']
        self.assertEqual(dest.keywords_list, expected)

    def test_keywords_list_empty(self):
        """Test keywords_list with empty keywords."""
        dest = TeachingDestination.objects.create(
            destination_id='test-empty-keywords',
            name='Empty Keywords Test',
            path_description='Test',
            url='/test/',
            keywords='',
        )
        self.assertEqual(dest.keywords_list, [])

    def test_get_all_active(self):
        """Test getting all active destinations."""
        TeachingDestination.objects.create(
            destination_id='active-1',
            name='Active 1',
            path_description='Test',
            url='/test1/',
            keywords='test1',
            is_active=True,
        )
        TeachingDestination.objects.create(
            destination_id='active-2',
            name='Active 2',
            path_description='Test',
            url='/test2/',
            keywords='test2',
            is_active=True,
        )
        TeachingDestination.objects.create(
            destination_id='inactive',
            name='Inactive',
            path_description='Test',
            url='/test3/',
            keywords='test3',
            is_active=False,
        )

        active = TeachingDestination.get_all_active()
        self.assertEqual(len(active), 2)
        self.assertTrue(all(d.is_active for d in active))

    def test_str_representation(self):
        """Test string representation of destination."""
        dest = TeachingDestination.objects.create(
            destination_id='str-test',
            name='String Test',
            path_description='Test',
            url='/test/',
            keywords='test',
        )
        self.assertEqual(str(dest), 'String Test (str-test)')


class TeachingToolServiceTest(TestCase):
    """Tests for the TeachingToolService."""

    def setUp(self):
        """Set up test data."""
        self.service = TeachingToolService()

        # Create test destinations
        TeachingDestination.objects.create(
            destination_id='weight-tracking',
            name='Weight Tracking',
            path_description='Health > Weight',
            explanation='Log your daily weight and view trends.',
            url='/health/weight/',
            keywords='weight, log weight, track weight, weigh myself',
            module='health',
            sort_order=1,
        )
        TeachingDestination.objects.create(
            destination_id='journal-new',
            name='New Journal Entry',
            path_description='Journal > New Entry',
            explanation='Write a new journal entry.',
            url='/journal/new/',
            keywords='journal, write journal, diary, entry',
            module='journal',
            sort_order=2,
        )
        TeachingDestination.objects.create(
            destination_id='goals',
            name='My Goals',
            path_description='Goals > My Goals',
            explanation='Set and track your personal goals.',
            url='/purpose/goals/',
            keywords='goals, goal setting, objectives',
            module='purpose',
            sort_order=3,
        )

    def test_search_exact_keyword_match(self):
        """Test search with exact keyword match."""
        result = self.service.search('Where do I log my weight?')

        self.assertTrue(result['found'])
        self.assertIsNotNone(result['destination'])
        self.assertEqual(result['destination']['id'], 'weight-tracking')
        self.assertEqual(result['destination']['url'], '/health/weight/')

    def test_search_partial_match(self):
        """Test search with partial keyword match."""
        result = self.service.search('How do I write in my journal?')

        self.assertTrue(result['found'])
        self.assertIsNotNone(result['destination'])
        self.assertEqual(result['destination']['id'], 'journal-new')

    def test_search_no_match(self):
        """Test search with no matching keywords."""
        result = self.service.search('Where is the spaceship?')

        self.assertFalse(result['found'])
        self.assertIsNone(result['destination'])
        self.assertIn('suggestions', result)

    def test_search_empty_query(self):
        """Test search with empty query."""
        result = self.service.search('')

        self.assertFalse(result['found'])
        self.assertIsNone(result['destination'])

    def test_search_short_query(self):
        """Test search with very short query."""
        result = self.service.search('a')

        self.assertFalse(result['found'])
        self.assertIsNone(result['destination'])

    def test_search_returns_suggestions(self):
        """Test that suggestions are returned."""
        result = self.service.search('weight')

        self.assertTrue(result['found'])
        self.assertIn('suggestions', result)

    def test_get_popular_destinations(self):
        """Test getting popular destinations."""
        popular = self.service.get_popular_destinations(limit=2)

        self.assertEqual(len(popular), 2)
        self.assertEqual(popular[0]['id'], 'weight-tracking')  # sort_order 1
        self.assertEqual(popular[1]['id'], 'journal-new')  # sort_order 2

    def test_response_message_format(self):
        """Test that response message is properly formatted."""
        result = self.service.search('track my weight')

        self.assertTrue(result['found'])
        self.assertIn('message', result)
        self.assertIn('Health > Weight', result['message'])


class TeachingToolViewTest(BaseTeachingToolTest):
    """Tests for the teaching tool API views."""

    def setUp(self):
        """Set up test client and user."""
        self.client = Client()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpassword123',
        )
        self._accept_terms(self.user)
        self._complete_onboarding(self.user)

        # Create test destination
        TeachingDestination.objects.create(
            destination_id='test-dest',
            name='Test Destination',
            path_description='Test > Path',
            explanation='Test explanation.',
            url='/test/',
            keywords='test, testing',
            module='test',
        )

    def test_search_requires_login(self):
        """Test that search endpoint requires authentication."""
        response = self.client.get(reverse('help:teaching_search'), {'q': 'test'})
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_search_authenticated(self):
        """Test search with authenticated user."""
        self.client.login(email='test@example.com', password='testpassword123')
        response = self.client.get(reverse('help:teaching_search'), {'q': 'test'})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['found'])
        self.assertEqual(data['destination']['id'], 'test-dest')

    def test_suggestions_requires_login(self):
        """Test that suggestions endpoint requires authentication."""
        response = self.client.get(reverse('help:teaching_suggestions'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_suggestions_authenticated(self):
        """Test suggestions with authenticated user."""
        self.client.login(email='test@example.com', password='testpassword123')
        response = self.client.get(reverse('help:teaching_suggestions'))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('destinations', data)
        self.assertEqual(len(data['destinations']), 1)
