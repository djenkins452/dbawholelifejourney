"""
Search Service Tests - Task 9.1

Tests for the SearchService class that provides unified search
across all WLJ modules.
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.ai.search_service import SearchService

User = get_user_model()


class SearchServiceTestMixin:
    """Common setup for search service tests."""

    def create_user(self, email='searchtest@example.com'):
        """Create a test user with terms and onboarding completed."""
        from django.conf import settings
        from apps.users.models import TermsAcceptance

        user = User.objects.create_user(email=email, password='testpass123')
        TermsAcceptance.objects.create(
            user=user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
        )
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user


class SearchServiceBasicTests(SearchServiceTestMixin, TestCase):
    """Basic tests for SearchService initialization and helpers."""

    def setUp(self):
        self.user = self.create_user()
        self.service = SearchService(self.user)

    def test_init(self):
        """SearchService should initialize with user."""
        self.assertEqual(self.service.user, self.user)

    def test_truncate_snippet_short(self):
        """Short text should not be truncated."""
        text = "Short text"
        result = self.service._truncate_snippet(text)
        self.assertEqual(result, "Short text")

    def test_truncate_snippet_long(self):
        """Long text should be truncated with ellipsis."""
        text = "This is a very long text that should be truncated because it exceeds the maximum length allowed for snippets in search results and needs to be shortened."
        result = self.service._truncate_snippet(text, max_length=50)
        self.assertTrue(result.endswith("..."))
        self.assertLessEqual(len(result), 53)  # 50 + "..."

    def test_truncate_snippet_empty(self):
        """Empty text should return empty string."""
        self.assertEqual(self.service._truncate_snippet(""), "")
        self.assertEqual(self.service._truncate_snippet(None), "")

    def test_build_keyword_filter_empty(self):
        """Empty keywords should return empty Q."""
        from django.db.models import Q
        result = self.service._build_keyword_filter([], ['title'])
        self.assertEqual(result, Q())

    def test_build_keyword_filter_single(self):
        """Single keyword should create OR filter for each field."""
        result = self.service._build_keyword_filter(['test'], ['title', 'body'])
        # Result should be a Q object with OR conditions
        self.assertIsNotNone(result)

    def test_create_result(self):
        """Create result should return standardized dict."""
        result = self.service._create_result(
            id=123,
            title="Test Title",
            snippet="Test snippet",
            date_value=date(2026, 1, 15),
            url="/test/123/",
            metadata={"key": "value"}
        )
        self.assertEqual(result['id'], 123)
        self.assertEqual(result['title'], "Test Title")
        self.assertEqual(result['snippet'], "Test snippet")
        self.assertEqual(result['date'], "2026-01-15")
        self.assertEqual(result['url'], "/test/123/")
        self.assertEqual(result['metadata'], {"key": "value"})


class SearchServiceJournalTests(SearchServiceTestMixin, TestCase):
    """Tests for journal search functionality."""

    def setUp(self):
        self.user = self.create_user()
        self.service = SearchService(self.user)

    def test_search_journal_empty(self):
        """Search with no entries should return empty results."""
        result = self.service.search_journal(keywords=['test'])
        self.assertEqual(result['module'], 'journal')
        self.assertEqual(result['count'], 0)
        self.assertEqual(result['results'], [])

    def test_search_journal_with_entries(self):
        """Search should return matching journal entries."""
        from apps.journal.models import JournalEntry

        # Create test entries
        JournalEntry.objects.create(
            user=self.user,
            title="Feeling grateful today",
            body="I am thankful for my health and family.",
            entry_date=date.today(),
            mood='great'
        )
        JournalEntry.objects.create(
            user=self.user,
            title="Work stress",
            body="Had a challenging day at work.",
            entry_date=date.today() - timedelta(days=1),
            mood='low'
        )

        # Search for 'grateful'
        result = self.service.search_journal(keywords=['grateful'])
        self.assertEqual(result['module'], 'journal')
        self.assertEqual(result['count'], 1)
        self.assertIn('grateful', result['results'][0]['title'].lower())

    def test_search_journal_mood_filter(self):
        """Search should filter by mood."""
        from apps.journal.models import JournalEntry

        JournalEntry.objects.create(
            user=self.user,
            title="Happy day",
            body="Great day today!",
            entry_date=date.today(),
            mood='great'
        )
        JournalEntry.objects.create(
            user=self.user,
            title="Tough day",
            body="Not feeling well.",
            entry_date=date.today(),
            mood='low'
        )

        result = self.service.search_journal(mood='great')
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['results'][0]['metadata']['mood'], 'great')

    def test_search_journal_date_range(self):
        """Search should filter by date range."""
        from apps.journal.models import JournalEntry

        today = date.today()
        JournalEntry.objects.create(
            user=self.user,
            title="Recent entry",
            body="Test",
            entry_date=today
        )
        JournalEntry.objects.create(
            user=self.user,
            title="Old entry",
            body="Test",
            entry_date=today - timedelta(days=30)
        )

        # Search last 7 days
        result = self.service.search_journal(
            date_range=(today - timedelta(days=7), today)
        )
        self.assertEqual(result['count'], 1)
        self.assertIn('Recent', result['results'][0]['title'])


class SearchServiceGoalsTests(SearchServiceTestMixin, TestCase):
    """Tests for goals search functionality."""

    def setUp(self):
        self.user = self.create_user()
        self.service = SearchService(self.user)

    def test_search_goals_empty(self):
        """Search with no goals should return empty results."""
        result = self.service.search_goals(keywords=['fitness'])
        self.assertEqual(result['module'], 'purpose')
        self.assertEqual(result['count'], 0)

    def test_search_goals_with_goals(self):
        """Search should return matching goals."""
        from apps.purpose.models import LifeGoal

        LifeGoal.objects.create(
            user=self.user,
            title="Get fit",
            description="Improve my fitness level",
            why_it_matters="Health is important",
            status='active'
        )
        LifeGoal.objects.create(
            user=self.user,
            title="Learn guitar",
            description="Play music",
            status='active'
        )

        result = self.service.search_goals(keywords=['fitness', 'fit'])
        self.assertEqual(result['count'], 1)
        self.assertIn('fit', result['results'][0]['title'].lower())

    def test_search_goals_status_filter(self):
        """Search should filter by status."""
        from apps.purpose.models import LifeGoal

        LifeGoal.objects.create(
            user=self.user,
            title="Active goal",
            status='active'
        )
        LifeGoal.objects.create(
            user=self.user,
            title="Completed goal",
            status='completed'
        )

        result = self.service.search_goals(status='active')
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['results'][0]['metadata']['status'], 'active')


class SearchServiceOrganizeTests(SearchServiceTestMixin, TestCase):
    """Tests for Organize (tasks, projects, etc) search functionality."""

    def setUp(self):
        self.user = self.create_user()
        self.service = SearchService(self.user)

    def test_search_organize_tasks(self):
        """Search should return matching tasks."""
        from apps.life.models import Task

        Task.objects.create(
            user=self.user,
            title="Buy groceries",
            notes="Need milk and eggs"
        )
        Task.objects.create(
            user=self.user,
            title="Call doctor",
            notes="Schedule appointment"
        )

        result = self.service.search_organize(
            keywords=['groceries'],
            item_type='task'
        )
        self.assertEqual(result['count'], 1)
        self.assertIn('groceries', result['results'][0]['title'].lower())

    def test_search_organize_projects(self):
        """Search should return matching projects."""
        from apps.life.models import Project

        Project.objects.create(
            user=self.user,
            title="Home renovation",
            description="Remodel the kitchen"
        )

        result = self.service.search_organize(
            keywords=['kitchen'],
            item_type='project'
        )
        self.assertEqual(result['count'], 1)
        self.assertIn('renovation', result['results'][0]['title'].lower())


class SearchServiceFinanceTests(SearchServiceTestMixin, TestCase):
    """Tests for finance search functionality."""

    def setUp(self):
        self.user = self.create_user()
        self.service = SearchService(self.user)

    def test_search_finance_empty(self):
        """Search with no transactions should return empty results."""
        result = self.service.search_finance(keywords=['grocery'])
        self.assertEqual(result['module'], 'finance')
        self.assertEqual(result['count'], 0)

    def test_search_finance_with_transactions(self):
        """Search should return matching transactions."""
        from apps.finance.models import FinancialAccount, Transaction

        account = FinancialAccount.objects.create(
            user=self.user,
            name="Checking",
            account_type='checking'
        )
        Transaction.objects.create(
            user=self.user,
            account=account,
            amount=Decimal('-50.00'),
            description="Grocery store",
            date=date.today()
        )

        result = self.service.search_finance(keywords=['grocery'])
        self.assertEqual(result['count'], 1)
        self.assertIn('Grocery', result['results'][0]['title'])


class SearchServiceFaithTests(SearchServiceTestMixin, TestCase):
    """Tests for faith search functionality."""

    def setUp(self):
        self.user = self.create_user()
        self.service = SearchService(self.user)

    def test_search_faith_prayers(self):
        """Search should return matching prayers."""
        from apps.faith.models import PrayerRequest

        PrayerRequest.objects.create(
            user=self.user,
            title="Healing for mom",
            description="Praying for her recovery"
        )

        result = self.service.search_faith(
            keywords=['healing'],
            content_type='prayer'
        )
        self.assertEqual(result['count'], 1)
        self.assertIn('Healing', result['results'][0]['title'])


class SearchServiceGlobalTests(SearchServiceTestMixin, TestCase):
    """Tests for global search across all modules."""

    def setUp(self):
        self.user = self.create_user()
        self.service = SearchService(self.user)

    def test_search_all_empty_keywords(self):
        """Global search with empty keywords should return empty results."""
        result = self.service.search_all(keywords=[])
        self.assertEqual(result['module'], 'all')
        self.assertEqual(result['count'], 0)

    def test_search_all_across_modules(self):
        """Global search should find results across multiple modules."""
        from apps.journal.models import JournalEntry
        from apps.life.models import Task

        # Create test data
        JournalEntry.objects.create(
            user=self.user,
            title="Vacation plans",
            body="Planning our summer vacation",
            entry_date=date.today()
        )
        Task.objects.create(
            user=self.user,
            title="Book vacation flights",
            notes="Check prices"
        )

        result = self.service.search_all(keywords=['vacation'])
        self.assertEqual(result['module'], 'all')
        self.assertGreaterEqual(result['count'], 2)
        self.assertIn('by_module', result)
