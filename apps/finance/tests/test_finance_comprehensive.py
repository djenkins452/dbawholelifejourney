# ==============================================================================
# File: test_finance_comprehensive.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Comprehensive tests for the Finance module
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-02
# Last Updated: 2026-01-02
# ==============================================================================

"""
Comprehensive tests for the Finance module.

Tests cover:
- Model creation and validation
- View access and authentication
- Form validation
- Budget calculations
- Goal tracking
- Financial metrics
"""

from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import date, timedelta

from apps.users.models import User, TermsAcceptance
from apps.finance.models import (
    FinancialAccount,
    TransactionCategory,
    Transaction,
    Budget,
    FinancialGoal,
    FinancialMetricSnapshot,
    Payee,
)


class FinanceTestMixin:
    """Mixin providing common test setup for Finance tests."""

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
        user.preferences.finances_enabled = True
        user.preferences.save()


class FinancialAccountModelTests(FinanceTestMixin, TestCase):
    """Tests for FinancialAccount model."""

    def setUp(self):
        self.user = self.create_user()
        self.account = FinancialAccount.objects.create(
            user=self.user,
            name='Checking',
            account_type='checking',
            current_balance=Decimal('1000.00'),
        )

    def test_account_creation(self):
        """Test that an account can be created."""
        self.assertEqual(self.account.name, 'Checking')
        self.assertEqual(self.account.account_type, 'checking')
        self.assertEqual(self.account.current_balance, Decimal('1000.00'))

    def test_account_str(self):
        """Test account string representation."""
        # Account str includes type: "Name (Type)"
        self.assertIn('Checking', str(self.account))

    def test_asset_vs_liability(self):
        """Test is_asset and is_liability properties."""
        # Checking account is an asset
        self.assertTrue(self.account.is_asset)
        self.assertFalse(self.account.is_liability)

        # Credit card is a liability
        credit_card = FinancialAccount.objects.create(
            user=self.user,
            name='Credit Card',
            account_type='credit_card',
            current_balance=Decimal('500.00'),
        )
        self.assertFalse(credit_card.is_asset)
        self.assertTrue(credit_card.is_liability)


class TransactionCategoryModelTests(FinanceTestMixin, TestCase):
    """Tests for TransactionCategory model."""

    def setUp(self):
        self.user = self.create_user()
        self.category = TransactionCategory.objects.create(
            user=self.user,
            name='Groceries',
            category_type='expense',
            icon='🛒',
            color='#10b981',
        )

    def test_category_creation(self):
        """Test that a category can be created."""
        self.assertEqual(self.category.name, 'Groceries')
        self.assertEqual(self.category.category_type, 'expense')

    def test_category_str(self):
        """Test category string representation."""
        # Category str is just the name (no icon in __str__)
        self.assertEqual(str(self.category), 'Groceries')

    def test_child_category(self):
        """Test parent-child relationship for categories."""
        child = TransactionCategory.objects.create(
            user=self.user,
            name='Produce',
            category_type='expense',
            parent=self.category,
        )
        self.assertEqual(child.parent, self.category)
        self.assertIn(child, self.category.children.all())


class TransactionModelTests(FinanceTestMixin, TestCase):
    """Tests for Transaction model."""

    def setUp(self):
        self.user = self.create_user()
        self.account = FinancialAccount.objects.create(
            user=self.user,
            name='Checking',
            account_type='checking',
            current_balance=Decimal('1000.00'),
        )
        self.category = TransactionCategory.objects.create(
            user=self.user,
            name='Groceries',
            category_type='expense',
        )
        # Expenses use negative amounts
        self.transaction = Transaction.objects.create(
            user=self.user,
            account=self.account,
            category=self.category,
            amount=Decimal('-50.00'),  # Negative for expense
            description='Weekly groceries',
            date=date.today(),
        )

    def test_transaction_creation(self):
        """Test that a transaction can be created."""
        self.assertEqual(self.transaction.amount, Decimal('-50.00'))
        self.assertTrue(self.transaction.is_expense)

    def test_income_vs_expense(self):
        """Test is_income and is_expense properties."""
        # Expense is negative
        self.assertTrue(self.transaction.is_expense)
        self.assertFalse(self.transaction.is_income)

        # Income is positive
        income = Transaction.objects.create(
            user=self.user,
            account=self.account,
            amount=Decimal('100.00'),  # Positive for income
            description='Paycheck',
            date=date.today(),
        )
        self.assertTrue(income.is_income)
        self.assertFalse(income.is_expense)


class BudgetModelTests(FinanceTestMixin, TestCase):
    """Tests for Budget model."""

    def setUp(self):
        self.user = self.create_user()
        self.account = FinancialAccount.objects.create(
            user=self.user,
            name='Checking',
            account_type='checking',
            current_balance=Decimal('1000.00'),
        )
        self.category = TransactionCategory.objects.create(
            user=self.user,
            name='Groceries',
            category_type='expense',
        )
        self.budget = Budget.objects.create(
            user=self.user,
            category=self.category,
            budgeted_amount=Decimal('500.00'),
            month=date.today().replace(day=1),
        )

    def test_budget_creation(self):
        """Test that a budget can be created."""
        self.assertEqual(self.budget.budgeted_amount, Decimal('500.00'))
        self.assertEqual(self.budget.month, date.today().replace(day=1))

    def test_spent_amount(self):
        """Test spent_amount calculation."""
        # Create expense transactions in this budget period (negative amounts)
        Transaction.objects.create(
            user=self.user,
            account=self.account,
            category=self.category,
            amount=Decimal('-100.00'),
            description='Groceries 1',
            date=date.today(),
        )
        Transaction.objects.create(
            user=self.user,
            account=self.account,
            category=self.category,
            amount=Decimal('-150.00'),
            description='Groceries 2',
            date=date.today(),
        )
        self.assertEqual(self.budget.spent_amount, Decimal('250.00'))

    def test_remaining_amount(self):
        """Test remaining_amount calculation."""
        Transaction.objects.create(
            user=self.user,
            account=self.account,
            category=self.category,
            amount=Decimal('-100.00'),
            description='Groceries',
            date=date.today(),
        )
        self.assertEqual(self.budget.remaining_amount, Decimal('400.00'))

    def test_budget_health_status(self):
        """Test budget health_status property."""
        # Under budget - on_track
        self.assertEqual(self.budget.health_status, 'on_track')

        # Over 80% - warning
        Transaction.objects.create(
            user=self.user,
            account=self.account,
            category=self.category,
            amount=Decimal('-450.00'),
            description='Big grocery run',
            date=date.today(),
        )
        self.assertEqual(self.budget.health_status, 'warning')


class FinancialGoalModelTests(FinanceTestMixin, TestCase):
    """Tests for FinancialGoal model."""

    def setUp(self):
        self.user = self.create_user()
        self.goal = FinancialGoal.objects.create(
            user=self.user,
            name='Emergency Fund',
            goal_type='savings',
            target_amount=Decimal('10000.00'),
            current_amount=Decimal('2500.00'),
            target_date=date.today() + timedelta(days=365),
        )

    def test_goal_creation(self):
        """Test that a goal can be created."""
        self.assertEqual(self.goal.name, 'Emergency Fund')
        self.assertEqual(self.goal.target_amount, Decimal('10000.00'))

    def test_progress_percentage(self):
        """Test progress_percentage calculation."""
        self.assertEqual(self.goal.progress_percentage, 25)

    def test_remaining_amount(self):
        """Test remaining_amount calculation."""
        self.assertEqual(self.goal.remaining_amount, Decimal('7500.00'))

    def test_days_remaining(self):
        """Test days_remaining calculation."""
        self.assertIsNotNone(self.goal.days_remaining)
        self.assertGreater(self.goal.days_remaining, 0)


class FinancialMetricSnapshotModelTests(FinanceTestMixin, TestCase):
    """Tests for FinancialMetricSnapshot model."""

    def setUp(self):
        self.user = self.create_user()
        # Create accounts
        self.checking = FinancialAccount.objects.create(
            user=self.user,
            name='Checking',
            account_type='checking',
            current_balance=Decimal('5000.00'),
        )
        self.savings = FinancialAccount.objects.create(
            user=self.user,
            name='Savings',
            account_type='savings',
            current_balance=Decimal('10000.00'),
        )
        self.credit_card = FinancialAccount.objects.create(
            user=self.user,
            name='Credit Card',
            account_type='credit_card',
            current_balance=Decimal('2000.00'),
        )

    def test_create_snapshot(self):
        """Test creating a financial metric snapshot."""
        snapshot = FinancialMetricSnapshot.create_snapshot(self.user)

        # Total assets = checking + savings
        self.assertEqual(snapshot.total_assets, Decimal('15000.00'))

        # Total liabilities = credit card
        self.assertEqual(snapshot.total_liabilities, Decimal('2000.00'))

        # Net worth = assets - liabilities
        self.assertEqual(snapshot.net_worth, Decimal('13000.00'))


class FinanceViewsTests(FinanceTestMixin, TestCase):
    """Tests for Finance views."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.client.login(email='test@example.com', password='testpass123')

    def test_dashboard_view(self):
        """Test finance dashboard view."""
        response = self.client.get(reverse('finance:dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_account_list_view(self):
        """Test account list view."""
        response = self.client.get(reverse('finance:account_list'))
        self.assertEqual(response.status_code, 200)

    def test_account_create_view(self):
        """Test account create view."""
        response = self.client.get(reverse('finance:account_create'))
        self.assertEqual(response.status_code, 200)

    def test_transaction_list_view(self):
        """Test transaction list view."""
        response = self.client.get(reverse('finance:transaction_list'))
        self.assertEqual(response.status_code, 200)

    def test_budget_list_view(self):
        """Test budget list view."""
        response = self.client.get(reverse('finance:budget_list'))
        self.assertEqual(response.status_code, 200)

    def test_goal_list_view(self):
        """Test goal list view."""
        response = self.client.get(reverse('finance:goal_list'))
        self.assertEqual(response.status_code, 200)

    def test_metrics_dashboard_view(self):
        """Test metrics dashboard view."""
        response = self.client.get(reverse('finance:metrics'))
        self.assertEqual(response.status_code, 200)

    def test_unauthenticated_access_redirects(self):
        """Test that unauthenticated users are redirected to login."""
        self.client.logout()
        response = self.client.get(reverse('finance:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('accounts/login', response.url)


class FinanceAccountCRUDTests(FinanceTestMixin, TestCase):
    """Tests for Account CRUD operations."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.client.login(email='test@example.com', password='testpass123')

    def test_create_account(self):
        """Test creating a new account."""
        response = self.client.post(reverse('finance:account_create'), {
            'name': 'New Checking',
            'account_type': 'checking',
            'current_balance': '1000.00',
            'currency': 'USD',
            'color': '#6366f1',
            'sort_order': '0',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            FinancialAccount.objects.filter(
                user=self.user,
                name='New Checking'
            ).exists()
        )

    def test_update_account(self):
        """Test updating an account."""
        account = FinancialAccount.objects.create(
            user=self.user,
            name='Old Name',
            account_type='checking',
            current_balance=Decimal('100.00'),
        )
        response = self.client.post(
            reverse('finance:account_update', args=[account.pk]),
            {
                'name': 'New Name',
                'account_type': 'checking',
                'current_balance': '200.00',
                'currency': 'USD',
                'color': '#6366f1',
                'sort_order': '0',
            }
        )
        self.assertEqual(response.status_code, 302)
        account.refresh_from_db()
        self.assertEqual(account.name, 'New Name')
        self.assertEqual(account.current_balance, Decimal('200.00'))

    def test_delete_account(self):
        """Test deleting an account (soft delete)."""
        account = FinancialAccount.objects.create(
            user=self.user,
            name='To Delete',
            account_type='checking',
            current_balance=Decimal('100.00'),
        )
        response = self.client.post(
            reverse('finance:account_delete', args=[account.pk])
        )
        self.assertEqual(response.status_code, 302)
        account.refresh_from_db()
        self.assertEqual(account.status, 'deleted')
