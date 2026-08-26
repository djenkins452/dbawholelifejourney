# ==============================================================================
# File: apps/finance/models.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Finance module data models - accounts, transactions, budgets, goals,
#              imports with audit tracking
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-02
# Last Updated: 2026-01-03
# ==============================================================================
"""
Finance Module Models

The Finance module provides personal financial tracking with a calm, intentional
approach aligned with WLJ's philosophy. Manual-first design with future support
for bank integrations.

Key Models:
    - FinancialAccount: Bank accounts, credit cards, loans, investments
    - TransactionCategory: Hierarchical categories for income/expenses
    - Transaction: Individual financial transactions
    - Budget: Monthly spending plans by category
    - FinancialGoal: Savings, debt payoff, giving, and purchase goals
    - FinancialMetricSnapshot: Point-in-time financial health metrics

Security:
    - All models extend UserOwnedModel for ownership and soft delete
    - Sensitive balance data marked for encryption consideration
    - Audit trail via created_at/updated_at timestamps

See docs/wlj_finance_module_scope.md for full specification.
"""

from decimal import Decimal

import django.core.files.storage
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.models import UserOwnedModel
from apps.core.utils import get_user_today


# =============================================================================
# Financial Account
# =============================================================================

class FinancialAccount(UserOwnedModel):
    """
    A financial account (bank, credit card, loan, investment, etc.)

    Accounts are the containers for transactions and the basis for
    balance calculations.

    Security Note: current_balance is sensitive financial data.
    """

    # Account Types - Assets (positive) and Liabilities (negative)
    TYPE_CHECKING = 'checking'
    TYPE_SAVINGS = 'savings'
    TYPE_CASH = 'cash'
    TYPE_INVESTMENT = 'investment'
    TYPE_PROPERTY = 'property'
    TYPE_OTHER_ASSET = 'other_asset'
    TYPE_CREDIT_CARD = 'credit_card'
    TYPE_LOAN = 'loan'
    TYPE_MORTGAGE = 'mortgage'
    TYPE_STUDENT_LOAN = 'student_loan'
    TYPE_OTHER_LIABILITY = 'other_liability'

    ACCOUNT_TYPE_CHOICES = [
        ('Assets', (
            (TYPE_CHECKING, 'Checking'),
            (TYPE_SAVINGS, 'Savings'),
            (TYPE_CASH, 'Cash'),
            (TYPE_INVESTMENT, 'Investment'),
            (TYPE_PROPERTY, 'Property'),
            (TYPE_OTHER_ASSET, 'Other Asset'),
        )),
        ('Liabilities', (
            (TYPE_CREDIT_CARD, 'Credit Card'),
            (TYPE_LOAN, 'Loan'),
            (TYPE_MORTGAGE, 'Mortgage'),
            (TYPE_STUDENT_LOAN, 'Student Loan'),
            (TYPE_OTHER_LIABILITY, 'Other Liability'),
        )),
    ]

    # Flat list for validation
    ASSET_TYPES = [TYPE_CHECKING, TYPE_SAVINGS, TYPE_CASH, TYPE_INVESTMENT,
                   TYPE_PROPERTY, TYPE_OTHER_ASSET]
    LIABILITY_TYPES = [TYPE_CREDIT_CARD, TYPE_LOAN, TYPE_MORTGAGE,
                       TYPE_STUDENT_LOAN, TYPE_OTHER_LIABILITY]

    CURRENCY_CHOICES = [
        ('USD', 'US Dollar'),
        ('EUR', 'Euro'),
        ('GBP', 'British Pound'),
        ('CAD', 'Canadian Dollar'),
        ('AUD', 'Australian Dollar'),
    ]

    # Core fields
    name = models.CharField(
        max_length=100,
        help_text="Account name (e.g., 'Chase Checking', 'Emergency Fund')"
    )
    account_type = models.CharField(
        max_length=20,
        choices=ACCOUNT_TYPE_CHOICES,
        help_text="Type of financial account"
    )
    institution = models.CharField(
        max_length=100,
        blank=True,
        help_text="Bank or financial institution name"
    )

    # Balance tracking (SENSITIVE)
    current_balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Current account balance"
    )
    balance_updated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the balance was last updated"
    )

    # Currency
    currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default='USD'
    )

    # Optional metadata
    account_number_last4 = models.CharField(
        max_length=4,
        blank=True,
        help_text="Last 4 digits of account number (for identification)"
    )
    notes = models.TextField(blank=True)

    # Display
    color = models.CharField(
        max_length=7,
        default='#6366f1',
        help_text="Hex color for UI display"
    )
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Icon identifier for UI"
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order in account lists"
    )

    # Tracking
    include_in_net_worth = models.BooleanField(
        default=True,
        help_text="Include this account in net worth calculations"
    )
    is_hidden = models.BooleanField(
        default=False,
        help_text="Hide from main views (but keep in calculations)"
    )

    # Plaid integration fields
    bank_connection = models.ForeignKey(
        'BankConnection',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accounts',
        help_text="Linked bank connection if synced"
    )
    plaid_account_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Plaid account ID for synced accounts"
    )
    is_synced = models.BooleanField(
        default=False,
        help_text="Whether this account syncs with a bank"
    )
    last_balance_sync = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time balance was synced from bank"
    )

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = "Financial Account"
        verbose_name_plural = "Financial Accounts"

    def __str__(self):
        return f"{self.name} ({self.get_account_type_display()})"

    def get_absolute_url(self):
        return reverse('finance:account_detail', kwargs={'pk': self.pk})

    @property
    def is_asset(self):
        """Check if this is an asset account (positive balance is good)."""
        return self.account_type in self.ASSET_TYPES

    @property
    def is_liability(self):
        """Check if this is a liability account (represents debt)."""
        return self.account_type in self.LIABILITY_TYPES

    @property
    def net_worth_value(self):
        """
        Return the value for net worth calculation.
        Assets are positive, liabilities are negative.
        """
        if not self.include_in_net_worth:
            return Decimal('0.00')
        if self.is_liability:
            return -abs(self.current_balance)
        return self.current_balance

    def update_balance(self, new_balance):
        """Update the current balance with timestamp."""
        self.current_balance = new_balance
        self.balance_updated_at = timezone.now()
        self.save(update_fields=['current_balance', 'balance_updated_at', 'updated_at'])

    def recalculate_balance(self):
        """
        Recalculate balance from transactions.

        Starts from initial balance (stored as first transaction or 0)
        and sums all subsequent transactions.
        """
        # Get the sum of all transaction amounts for this account
        from django.db.models import Sum

        # For asset accounts: income adds, expenses subtract
        # For liability accounts: payments reduce debt (positive), charges add debt (negative)
        total = self.transactions.filter(
            status='active'
        ).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')

        # Get opening balance transaction if exists
        opening = self.transactions.filter(
            is_opening_balance=True,
            status='active'
        ).first()
        opening_balance = opening.amount if opening else Decimal('0.00')

        # Calculate current balance
        self.current_balance = opening_balance + total
        self.balance_updated_at = timezone.now()
        self.save(update_fields=['current_balance', 'balance_updated_at', 'updated_at'])

        return self.current_balance


# =============================================================================
# Transaction Category
# =============================================================================

class TransactionCategory(models.Model):
    """
    Hierarchical transaction categories for organizing income and expenses.

    Categories can be system-defined (global) or user-defined.
    Supports parent/child relationships for sub-categories.
    """

    CATEGORY_TYPE_INCOME = 'income'
    CATEGORY_TYPE_EXPENSE = 'expense'
    CATEGORY_TYPE_TRANSFER = 'transfer'

    CATEGORY_TYPE_CHOICES = [
        (CATEGORY_TYPE_INCOME, 'Income'),
        (CATEGORY_TYPE_EXPENSE, 'Expense'),
        (CATEGORY_TYPE_TRANSFER, 'Transfer'),
    ]

    # Core fields
    name = models.CharField(
        max_length=100,
        help_text="Category name"
    )
    category_type = models.CharField(
        max_length=10,
        choices=CATEGORY_TYPE_CHOICES,
        default=CATEGORY_TYPE_EXPENSE
    )

    # Hierarchy
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        help_text="Parent category for sub-categories"
    )

    # User ownership (null = system category)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='transaction_categories',
        help_text="Owner (null for system categories)"
    )

    # Display
    color = models.CharField(
        max_length=7,
        default='#6b7280',
        help_text="Hex color for charts and UI"
    )
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Emoji or icon identifier"
    )
    sort_order = models.PositiveIntegerField(default=0)

    # Flags
    is_system = models.BooleanField(
        default=False,
        help_text="System categories cannot be deleted"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive categories hidden from dropdowns"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category_type', 'sort_order', 'name']
        verbose_name = "Transaction Category"
        verbose_name_plural = "Transaction Categories"
        # User can have same name as system category
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'name', 'category_type'],
                name='unique_user_category_name'
            ),
        ]

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} > {self.name}"
        return self.name

    @property
    def full_path(self):
        """Return full category path (e.g., 'Expenses > Food > Dining Out')."""
        if self.parent:
            return f"{self.parent.full_path} > {self.name}"
        return self.name

    @classmethod
    def get_for_user(cls, user, category_type=None, include_system=True):
        """
        Get categories available to a user.

        Includes system categories and user's custom categories.
        """
        from django.db.models import Q

        query = Q(user=user) | Q(is_system=True) if include_system else Q(user=user)
        queryset = cls.objects.filter(query, is_active=True)

        if category_type:
            queryset = queryset.filter(category_type=category_type)

        return queryset.order_by('category_type', 'sort_order', 'name')


# =============================================================================
# Transaction
# =============================================================================

class Transaction(UserOwnedModel):
    """
    A single financial transaction (income, expense, or transfer).

    Transactions are the core data unit for tracking money flow.

    Amount convention:
    - Positive: Money coming IN (income, refunds, transfers in)
    - Negative: Money going OUT (expenses, payments, transfers out)
    """

    # Core fields
    account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.CASCADE,
        related_name='transactions',
        help_text="Account this transaction belongs to"
    )
    date = models.DateField(
        help_text="Transaction date"
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Transaction amount (positive=income, negative=expense)"
    )
    description = models.CharField(
        max_length=300,
        help_text="Transaction description or merchant name"
    )

    # Categorization
    category = models.ForeignKey(
        TransactionCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions',
        help_text="Transaction category"
    )

    # Optional metadata
    payee = models.CharField(
        max_length=200,
        blank=True,
        help_text="Who received or sent the money"
    )
    notes = models.TextField(blank=True)
    reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="Check number, confirmation code, etc."
    )

    # Status flags
    is_cleared = models.BooleanField(
        default=False,
        help_text="Transaction has cleared the account"
    )
    is_recurring = models.BooleanField(
        default=False,
        help_text="This is a recurring transaction"
    )
    is_opening_balance = models.BooleanField(
        default=False,
        help_text="This is the opening balance entry"
    )

    # Transfer tracking (links two transactions)
    transfer_pair = models.OneToOneField(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transfer_counterpart',
        help_text="Linked transaction for transfers between accounts"
    )

    # Tagging
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text="User-defined tags"
    )

    # Import tracking
    import_record = models.ForeignKey(
        'TransactionImport',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions',
        help_text="Import record if this transaction was imported from a file"
    )

    # Source tracking (Phase 6A)
    SOURCE_TYPE_CHOICES = [
        ('manual', 'Manual Entry'),
        ('import', 'File Import'),
        ('email', 'Email Extraction'),
        ('document', 'Document Extraction'),
        ('receipt_scan', 'Receipt Scan'),
        ('plaid', 'Plaid Sync'),
    ]

    source_type = models.CharField(
        max_length=20,
        choices=SOURCE_TYPE_CHOICES,
        default='manual',
        help_text="How this transaction was created",
    )
    source_id = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Source record ID (document ID, email message ID, etc.)",
    )

    # Phase 6B: Transaction fingerprint for cross-source dedup
    fingerprint = models.CharField(
        max_length=64,
        blank=True,
        default='',
        db_index=True,
        help_text="Hash of normalized merchant+amount+date for dedup",
    )

    # Phase 6B: Receipt document link
    receipt_document = models.ForeignKey(
        'life.Document',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='receipt_transactions',
        help_text="Linked receipt document (from email attachment)",
    )

    # =========================================================================
    # Provider provenance (Plaid) — WHAT THE PROVIDER SAID, kept verbatim
    # =========================================================================
    # Three dimensions stay SEPARATE and each keeps its own authority:
    #   provider_*        what Plaid said            (never overwritten by WLJ)
    #   category          WLJ's canonical spending category
    #   attribution       which economic entity bears the cost (F0)
    # "Software / Beacon / paid from Personal" is three independent facts, not one.
    # Credentials, full account numbers, and raw payloads are deliberately NOT stored.

    provider_category = models.JSONField(
        default=list, blank=True,
        help_text="Provider's legacy category hierarchy, verbatim. Never overwritten.",
    )
    provider_category_primary = models.CharField(
        max_length=64, blank=True, default='', db_index=True,
        help_text="Provider's personal-finance-category PRIMARY value, verbatim.",
    )
    provider_category_detailed = models.CharField(
        max_length=128, blank=True, default='',
        help_text="Provider's personal-finance-category DETAILED value, verbatim.",
    )
    provider_category_confidence = models.CharField(
        max_length=16, blank=True, default='',
        help_text="Provider's confidence in its own classification (gates mapping).",
    )
    provider_payment_channel = models.CharField(
        max_length=24, blank=True, default='',
        help_text="online / in store / other — a transfer signal.",
    )
    provider_transaction_code = models.CharField(
        max_length=32, blank=True, default='',
        help_text="Provider transaction code (e.g. 'transfer', 'purchase').",
    )
    provider_merchant_name = models.CharField(
        max_length=200, blank=True, default='',
        help_text="Normalized merchant as the provider resolved it.",
    )
    provider_counterparties = models.JSONField(
        default=list, blank=True,
        help_text="Counterparty NAMES and TYPES only — never account identifiers.",
    )
    provider_pending_transaction_id = models.CharField(
        max_length=100, blank=True, default='', db_index=True,
        help_text="The pending row this posted transaction replaces. The key to "
                  "pending→posted matching; without it a pending and its posted twin "
                  "become two transactions.",
    )
    provider_authorized_date = models.DateField(
        null=True, blank=True,
        help_text="When the provider says it was authorized (may precede posting).",
    )

    # =========================================================================
    # WLJ canonical spending category — authority and provenance
    # =========================================================================
    CATEGORY_SOURCE_NONE = 'none'
    CATEGORY_SOURCE_PROVIDER = 'provider_mapped'
    CATEGORY_SOURCE_RULE = 'rule'
    CATEGORY_SOURCE_USER = 'user'
    CATEGORY_SOURCE_CHOICES = [
        (CATEGORY_SOURCE_NONE, 'Not categorized'),
        (CATEGORY_SOURCE_PROVIDER, 'Mapped from the provider'),
        (CATEGORY_SOURCE_RULE, 'Applied from a user rule'),
        (CATEGORY_SOURCE_USER, 'Chosen by the user'),
    ]
    category_source = models.CharField(
        max_length=20, choices=CATEGORY_SOURCE_CHOICES, default=CATEGORY_SOURCE_NONE,
        db_index=True,
        help_text="How the WLJ category was decided. A user choice outranks every "
                  "provider or inferred value and is never silently replaced.",
    )
    category_confirmed_at = models.DateTimeField(null=True, blank=True)

    # =========================================================================
    # Transfer classification — a THIRD dimension, independent of category/entity
    # =========================================================================
    TRANSFER_STATE_UNKNOWN = 'unknown'
    TRANSFER_STATE_NOT_TRANSFER = 'not_transfer'
    TRANSFER_STATE_CANDIDATE = 'candidate'
    TRANSFER_STATE_CONFIRMED = 'confirmed'
    TRANSFER_STATE_CHOICES = [
        (TRANSFER_STATE_UNKNOWN, 'Not yet assessed'),
        (TRANSFER_STATE_NOT_TRANSFER, 'Ordinary activity'),
        (TRANSFER_STATE_CANDIDATE, 'Possible transfer — held for review'),
        (TRANSFER_STATE_CONFIRMED, 'Confirmed transfer / payment'),
    ]
    TRANSFER_KIND_INTERNAL = 'internal_transfer'
    TRANSFER_KIND_CARD_PAYMENT = 'credit_card_payment'
    TRANSFER_KIND_REFUND = 'refund'
    TRANSFER_KIND_REVERSAL = 'reversal'
    TRANSFER_KIND_CHOICES = [
        ('', 'None'),
        (TRANSFER_KIND_INTERNAL, 'Internal transfer'),
        (TRANSFER_KIND_CARD_PAYMENT, 'Credit-card payment'),
        (TRANSFER_KIND_REFUND, 'Refund'),
        (TRANSFER_KIND_REVERSAL, 'Reversal'),
    ]
    TRANSFER_BY_PROVIDER = 'provider'
    TRANSFER_BY_PAIRING = 'pairing'
    TRANSFER_BY_USER = 'user'
    TRANSFER_BY_CHOICES = [
        ('', 'Unset'),
        (TRANSFER_BY_PROVIDER, 'Provider classification'),
        (TRANSFER_BY_PAIRING, 'Matched to its counterpart'),
        (TRANSFER_BY_USER, 'Confirmed by the user'),
    ]
    transfer_state = models.CharField(
        max_length=16, choices=TRANSFER_STATE_CHOICES,
        default=TRANSFER_STATE_UNKNOWN, db_index=True,
        help_text="CONFIRMED leaves spending totals; CANDIDATE is held out AND reviewed "
                  "— never silently counted either way.",
    )
    transfer_kind = models.CharField(
        max_length=24, choices=TRANSFER_KIND_CHOICES, blank=True, default='',
    )
    transfer_classified_by = models.CharField(
        max_length=16, choices=TRANSFER_BY_CHOICES, blank=True, default='',
        help_text="A user decision here outranks provider and pairing alike.",
    )

    # F0: link a generated transaction back to the commitment that produced it.
    # `is_recurring` only says "this repeats"; it does not say WHICH series, which the
    # recurring-scope attribution rule and the F3 "move this recurring expense" flow both
    # need. Nullable and never backfilled — historical rows resolve by payee instead.
    recurring_source = models.ForeignKey(
        'RecurringTransaction',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_transactions',
        help_text="The recurring commitment that generated this transaction, if any.",
    )

    # Plaid integration
    plaid_transaction_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Plaid transaction ID for synced transactions"
    )
    plaid_pending = models.BooleanField(
        default=False,
        help_text="Whether this is a pending Plaid transaction"
    )

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        indexes = [
            models.Index(fields=['user', 'date']),
            models.Index(fields=['account', 'date']),
            models.Index(fields=['category', 'date']),
            models.Index(fields=['plaid_transaction_id']),
            models.Index(fields=['user', 'recurring_source'],
                         name='idx_txn_user_recurring_src'),
            # The population authority's hottest filter.
            models.Index(fields=['user', 'transfer_state', 'date'],
                         name='idx_txn_user_transfer'),
            models.Index(fields=['provider_pending_transaction_id'],
                         name='idx_txn_pending_link'),
        ]

    def __str__(self):
        return f"{self.date}: {self.description} ({self.amount:+.2f})"

    def get_absolute_url(self):
        return reverse('finance:transaction_detail', kwargs={'pk': self.pk})

    @property
    def is_income(self):
        """Check if this is an income transaction."""
        return self.amount > 0

    @property
    def is_expense(self):
        """Check if this is an expense transaction."""
        return self.amount < 0

    @property
    def is_transfer(self):
        """Check if this is a transfer between accounts."""
        return self.transfer_pair is not None

    @property
    def absolute_amount(self):
        """Return absolute value of amount."""
        return abs(self.amount)

    def save(self, *args, **kwargs):
        """Update account balance after saving transaction."""
        super().save(*args, **kwargs)
        # Optionally recalculate account balance
        # self.account.recalculate_balance()


# =============================================================================
# Budget
# =============================================================================

class Budget(UserOwnedModel):
    """
    Monthly budget for a specific category.

    Tracks planned vs. actual spending by category and month.
    """

    # Budget period (stored as first day of month)
    month = models.DateField(
        help_text="Budget month (stored as first of month)"
    )

    # Category
    category = models.ForeignKey(
        TransactionCategory,
        on_delete=models.CASCADE,
        related_name='budgets',
        help_text="Category this budget applies to"
    )

    # Budget amount
    budgeted_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Planned spending limit"
    )

    # Rollover
    rollover_enabled = models.BooleanField(
        default=False,
        help_text="Roll unused budget to next month"
    )
    rollover_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Amount rolled over from previous month"
    )

    # Notes
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-month', 'category__name']
        verbose_name = "Budget"
        verbose_name_plural = "Budgets"
        unique_together = ['user', 'month', 'category']

    def __str__(self):
        return f"{self.category.name} - {self.month.strftime('%B %Y')}"

    @property
    def total_budget(self):
        """Total budget including rollover."""
        return self.budgeted_amount + self.rollover_amount

    @property
    def spent_amount(self):
        """Calculate amount spent in this category for this month."""
        from django.db.models import Sum

        # Get the month's date range
        next_month = self.month.replace(day=28) + timezone.timedelta(days=4)
        end_of_month = next_month.replace(day=1) - timezone.timedelta(days=1)

        # F4 convergence: ONE population authority decides what counts as activity, so a
        # transfer or an opening balance can never be reported as spend (Article III.1).
        from apps.finance.services.attribution_population import financial_activity

        spent = financial_activity(
            self.user, start=self.month, end=end_of_month,
        ).filter(
            category=self.category,
            amount__lt=0,  # Expenses are negative
        ).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')

        return abs(spent)

    @property
    def remaining_amount(self):
        """Budget remaining."""
        return self.total_budget - self.spent_amount

    @property
    def spent_percentage(self):
        """Percentage of budget spent."""
        if self.total_budget == 0:
            return 0
        return min(100, (self.spent_amount / self.total_budget) * 100)

    @property
    def health_status(self):
        """
        Budget health status indicator.

        Returns:
            'on_track': Under 80% spent
            'warning': 80-100% spent
            'over': Over 100% spent

        Note: Named 'health_status' to avoid shadowing the inherited 'status'
        field from SoftDeleteModel which tracks active/archived/deleted state.
        """
        pct = self.spent_percentage
        if pct >= 100:
            return 'over'
        elif pct >= 80:
            return 'warning'
        return 'on_track'

    @property
    def health_status_color(self):
        """CSS color class for health status."""
        colors = {
            'on_track': 'green',
            'warning': 'yellow',
            'over': 'red'
        }
        return colors.get(self.health_status, 'gray')


# =============================================================================
# Financial Goal
# =============================================================================

class FinancialGoal(UserOwnedModel):
    """
    Financial goal (savings, debt payoff, giving, major purchase).

    Goals track progress toward a specific financial target and can
    optionally link to Life Goals for holistic tracking.
    """

    GOAL_TYPE_SAVINGS = 'savings'
    GOAL_TYPE_DEBT_PAYOFF = 'debt_payoff'
    GOAL_TYPE_GIVING = 'giving'
    GOAL_TYPE_PURCHASE = 'purchase'
    GOAL_TYPE_EMERGENCY = 'emergency'
    GOAL_TYPE_OTHER = 'other'

    GOAL_TYPE_CHOICES = [
        (GOAL_TYPE_SAVINGS, 'Savings Goal'),
        (GOAL_TYPE_DEBT_PAYOFF, 'Debt Payoff'),
        (GOAL_TYPE_GIVING, 'Giving Goal'),
        (GOAL_TYPE_PURCHASE, 'Major Purchase'),
        (GOAL_TYPE_EMERGENCY, 'Emergency Fund'),
        (GOAL_TYPE_OTHER, 'Other'),
    ]

    STATUS_ACTIVE = 'active'
    STATUS_PAUSED = 'paused'
    STATUS_COMPLETED = 'completed'
    STATUS_ABANDONED = 'abandoned'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_PAUSED, 'Paused'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_ABANDONED, 'Abandoned'),
    ]

    # Core fields
    name = models.CharField(
        max_length=200,
        help_text="Goal name (e.g., 'Emergency Fund', 'Pay off Credit Card')"
    )
    goal_type = models.CharField(
        max_length=20,
        choices=GOAL_TYPE_CHOICES,
        default=GOAL_TYPE_SAVINGS
    )
    description = models.TextField(
        blank=True,
        help_text="Details about this goal"
    )

    # Target
    target_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Target dollar amount"
    )
    current_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Current progress amount"
    )

    # Timeline
    target_date = models.DateField(
        null=True,
        blank=True,
        help_text="Target completion date"
    )
    started_at = models.DateField(
        default=timezone.now,
        help_text="When goal tracking started"
    )
    completed_at = models.DateField(
        null=True,
        blank=True,
        help_text="When goal was completed"
    )

    # Status
    goal_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE
    )

    # Linked account (optional)
    linked_account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='financial_goals',
        help_text="Linked savings or debt account"
    )

    # Link to Purpose module (optional)
    life_goal = models.ForeignKey(
        'purpose.LifeGoal',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='financial_goals',
        help_text="Linked life goal from Purpose module"
    )

    # Display
    color = models.CharField(
        max_length=7,
        default='#10b981',
        help_text="Hex color for progress bar"
    )
    icon = models.CharField(
        max_length=50,
        blank=True,
        default='💰',
        help_text="Emoji or icon"
    )

    # Notes
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Financial Goal"
        verbose_name_plural = "Financial Goals"

    def __str__(self):
        return f"{self.name} ({self.get_goal_type_display()})"

    def get_absolute_url(self):
        return reverse('finance:goal_detail', kwargs={'pk': self.pk})

    @property
    def progress_percentage(self):
        """Percentage of goal completed."""
        if self.target_amount == 0:
            return 0
        return min(100, (self.current_amount / self.target_amount) * 100)

    @property
    def remaining_amount(self):
        """Amount remaining to reach goal."""
        return max(Decimal('0.00'), self.target_amount - self.current_amount)

    @property
    def is_completed(self):
        """Check if goal is completed."""
        return self.goal_status == self.STATUS_COMPLETED or self.current_amount >= self.target_amount

    @property
    def days_remaining(self):
        """Days until target date, or None if no target."""
        if not self.target_date:
            return None
        today = get_user_today(self.user) if self.user_id else timezone.now().date()
        delta = self.target_date - today
        return max(0, delta.days)

    @property
    def monthly_contribution_needed(self):
        """Monthly amount needed to reach goal by target date."""
        if not self.target_date or self.days_remaining == 0:
            return None
        months_remaining = max(1, self.days_remaining / 30)
        return self.remaining_amount / Decimal(str(months_remaining))

    def update_progress(self, amount):
        """
        Update goal progress by adding an amount.

        Positive for progress, negative for regression.
        """
        self.current_amount += amount
        if self.current_amount >= self.target_amount:
            self.mark_completed()
        else:
            self.save(update_fields=['current_amount', 'updated_at'])

    def mark_completed(self):
        """Mark goal as completed."""
        self.goal_status = self.STATUS_COMPLETED
        self.completed_at = timezone.now().date()
        self.save(update_fields=['goal_status', 'completed_at', 'current_amount', 'updated_at'])

    def sync_from_account(self):
        """
        Sync current amount from linked account balance.

        For savings goals, uses account balance.
        For debt payoff goals, uses inverse of debt balance.
        """
        if not self.linked_account:
            return

        if self.goal_type == self.GOAL_TYPE_DEBT_PAYOFF:
            # For debt payoff, progress = starting debt - current debt
            # We need to track starting balance separately
            pass
        else:
            self.current_amount = self.linked_account.current_balance
            self.save(update_fields=['current_amount', 'updated_at'])


# =============================================================================
# Financial Metric Snapshot
# =============================================================================

class FinancialMetricSnapshot(UserOwnedModel):
    """
    Point-in-time snapshot of financial health metrics.

    Stored periodically (daily or on-demand) to enable trend analysis
    and historical comparison.
    """

    # Snapshot date
    snapshot_date = models.DateField(
        help_text="Date of this snapshot"
    )

    # Balance metrics
    total_assets = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Sum of all asset account balances"
    )
    total_liabilities = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Sum of all liability account balances"
    )
    net_worth = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Assets minus liabilities"
    )

    # Cash flow (for the month)
    monthly_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total income for the month"
    )
    monthly_expenses = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total expenses for the month"
    )
    monthly_cash_flow = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Income minus expenses"
    )

    # Calculated rates
    savings_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Percentage of income saved"
    )
    debt_to_income_ratio = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Monthly debt payments / monthly income"
    )

    # Liquid savings metrics
    liquid_assets = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Checking + Savings + Cash"
    )
    emergency_fund_months = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Months of expenses covered by liquid assets"
    )

    class Meta:
        ordering = ['-snapshot_date']
        verbose_name = "Financial Metric Snapshot"
        verbose_name_plural = "Financial Metric Snapshots"
        unique_together = ['user', 'snapshot_date']
        indexes = [
            models.Index(fields=['user', 'snapshot_date']),
        ]

    def __str__(self):
        return f"Snapshot {self.snapshot_date}: NW ${self.net_worth:,.2f}"

    @classmethod
    def create_snapshot(cls, user, snapshot_date=None):
        """
        Create a new financial snapshot for a user.

        Calculates all metrics based on current account balances
        and transaction history.
        """
        from django.db.models import Sum

        if snapshot_date is None:
            snapshot_date = get_user_today(user)

        # Calculate asset and liability totals
        accounts = FinancialAccount.objects.filter(
            user=user,
            status='active',
            include_in_net_worth=True
        )

        total_assets = Decimal('0.00')
        total_liabilities = Decimal('0.00')
        liquid_assets = Decimal('0.00')

        for account in accounts:
            if account.is_asset:
                total_assets += account.current_balance
                if account.account_type in [FinancialAccount.TYPE_CHECKING,
                                            FinancialAccount.TYPE_SAVINGS,
                                            FinancialAccount.TYPE_CASH]:
                    liquid_assets += account.current_balance
            else:
                total_liabilities += abs(account.current_balance)

        net_worth = total_assets - total_liabilities

        # Calculate monthly income/expenses
        month_start = snapshot_date.replace(day=1)

        # F4 convergence: the shared population authority (was: transfer_pair only, which
        # disagreed with FinanceHistory's category-based definition).
        from apps.finance.services.attribution_population import financial_activity

        activity = financial_activity(user, start=month_start, end=snapshot_date)
        monthly_income = activity.filter(amount__gt=0).aggregate(
            total=Sum('amount'))['total'] or Decimal('0.00')
        monthly_expenses = abs(activity.filter(amount__lt=0).aggregate(
            total=Sum('amount'))['total'] or Decimal('0.00'))

        monthly_cash_flow = monthly_income - monthly_expenses

        # Calculate savings rate
        savings_rate = Decimal('0.00')
        if monthly_income > 0:
            savings_rate = (monthly_cash_flow / monthly_income) * 100

        # Calculate emergency fund months
        emergency_fund_months = None
        if monthly_expenses > 0:
            emergency_fund_months = liquid_assets / monthly_expenses

        # Create or update snapshot
        snapshot, created = cls.objects.update_or_create(
            user=user,
            snapshot_date=snapshot_date,
            defaults={
                'total_assets': total_assets,
                'total_liabilities': total_liabilities,
                'net_worth': net_worth,
                'monthly_income': monthly_income,
                'monthly_expenses': monthly_expenses,
                'monthly_cash_flow': monthly_cash_flow,
                'savings_rate': savings_rate,
                'liquid_assets': liquid_assets,
                'emergency_fund_months': emergency_fund_months,
            }
        )

        return snapshot


# =============================================================================
# Transaction Import (for file uploads and audit trail)
# =============================================================================

class TransactionImport(UserOwnedModel):
    """
    Record of a transaction file import for audit purposes.

    Tracks who uploaded what file, when, and how many transactions
    were created from it.
    """

    IMPORT_STATUS_PENDING = 'pending'
    IMPORT_STATUS_PROCESSING = 'processing'
    IMPORT_STATUS_COMPLETED = 'completed'
    IMPORT_STATUS_FAILED = 'failed'
    IMPORT_STATUS_PARTIAL = 'partial'

    IMPORT_STATUS_CHOICES = [
        (IMPORT_STATUS_PENDING, 'Pending'),
        (IMPORT_STATUS_PROCESSING, 'Processing'),
        (IMPORT_STATUS_COMPLETED, 'Completed'),
        (IMPORT_STATUS_FAILED, 'Failed'),
        (IMPORT_STATUS_PARTIAL, 'Partial Success'),
    ]

    FILE_TYPE_CSV = 'csv'
    FILE_TYPE_OFX = 'ofx'
    FILE_TYPE_QFX = 'qfx'
    FILE_TYPE_QIF = 'qif'

    FILE_TYPE_CHOICES = [
        (FILE_TYPE_CSV, 'CSV'),
        (FILE_TYPE_OFX, 'OFX'),
        (FILE_TYPE_QFX, 'QFX'),
        (FILE_TYPE_QIF, 'QIF'),
    ]

    # File information
    # NOTE: We do NOT store the actual file for security reasons.
    # Transaction files contain sensitive financial data and should be
    # processed immediately and discarded. We only keep metadata for audit trail.
    # The file field is kept but set to blank/null after processing.
    file = models.FileField(
        upload_to='finance/imports/%Y/%m/',
        storage=django.core.files.storage.FileSystemStorage(),
        blank=True,
        null=True,
        help_text="Uploaded transaction file (deleted after processing for security)"
    )
    original_filename = models.CharField(
        max_length=255,
        help_text="Original name of uploaded file"
    )
    file_type = models.CharField(
        max_length=10,
        choices=FILE_TYPE_CHOICES,
        help_text="Type of file uploaded"
    )
    file_size = models.PositiveIntegerField(
        help_text="File size in bytes"
    )

    # Target account
    account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.CASCADE,
        related_name='imports',
        help_text="Account to import transactions into"
    )

    # Import status and results
    import_status = models.CharField(
        max_length=20,
        choices=IMPORT_STATUS_CHOICES,
        default=IMPORT_STATUS_PENDING
    )
    rows_total = models.PositiveIntegerField(
        default=0,
        help_text="Total rows in file"
    )
    rows_imported = models.PositiveIntegerField(
        default=0,
        help_text="Rows successfully imported"
    )
    rows_skipped = models.PositiveIntegerField(
        default=0,
        help_text="Rows skipped (duplicates, errors)"
    )
    rows_failed = models.PositiveIntegerField(
        default=0,
        help_text="Rows that failed to import"
    )

    # Timing
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When import processing started"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When import processing completed"
    )

    # Error tracking
    error_message = models.TextField(
        blank=True,
        help_text="Error message if import failed"
    )
    error_details = models.JSONField(
        default=list,
        blank=True,
        help_text="Detailed error information for each failed row"
    )

    # Notes
    notes = models.TextField(
        blank=True,
        help_text="User notes about this import"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Transaction Import"
        verbose_name_plural = "Transaction Imports"
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['account', 'created_at']),
        ]

    def __str__(self):
        return f"{self.original_filename} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"

    def get_absolute_url(self):
        return reverse('finance:import_detail', kwargs={'pk': self.pk})

    @property
    def duration_seconds(self):
        """Return processing duration in seconds."""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return delta.total_seconds()
        return None

    @property
    def success_rate(self):
        """Return percentage of rows successfully imported."""
        if self.rows_total == 0:
            return 0
        return (self.rows_imported / self.rows_total) * 100

    def mark_processing(self):
        """Mark import as processing."""
        self.import_status = self.IMPORT_STATUS_PROCESSING
        self.started_at = timezone.now()
        self.save(update_fields=['import_status', 'started_at', 'updated_at'])

    def mark_completed(self, rows_imported, rows_skipped=0, rows_failed=0):
        """Mark import as completed with results."""
        self.import_status = self.IMPORT_STATUS_COMPLETED
        self.rows_imported = rows_imported
        self.rows_skipped = rows_skipped
        self.rows_failed = rows_failed
        self.completed_at = timezone.now()

        if rows_failed > 0 and rows_imported > 0:
            self.import_status = self.IMPORT_STATUS_PARTIAL

        self.save(update_fields=[
            'import_status', 'rows_imported', 'rows_skipped',
            'rows_failed', 'completed_at', 'updated_at'
        ])

    def mark_failed(self, error_message, error_details=None):
        """Mark import as failed with error information."""
        self.import_status = self.IMPORT_STATUS_FAILED
        self.error_message = error_message
        if error_details:
            self.error_details = error_details
        self.completed_at = timezone.now()
        self.save(update_fields=[
            'import_status', 'error_message', 'error_details',
            'completed_at', 'updated_at'
        ])


# =============================================================================
# Bank Connection (Plaid integration)
# =============================================================================

class BankConnection(UserOwnedModel):
    """
    Stores Plaid access tokens and connection metadata for bank integrations.

    Security:
        - Access tokens are encrypted at rest using Fernet
        - WLJ never stores bank credentials (Plaid handles authentication)
        - Tokens are revoked when connection is disconnected

    See docs/wlj_bank_integration_architecture.md for full architecture.
    """

    # Connection status choices
    STATUS_ACTIVE = 'active'
    STATUS_PENDING = 'pending'
    STATUS_ERROR = 'error'
    STATUS_DISCONNECTED = 'disconnected'
    STATUS_REAUTH_REQUIRED = 'reauth_required'
    #: Provider revocation was attempted and FAILED. The encrypted token is deliberately
    #: retained: it is the only credential that can revoke the Item, and discarding it
    #: would leave provider access live forever with no way to withdraw it.
    STATUS_REVOCATION_PENDING = 'revocation_pending'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_PENDING, 'Pending Initial Sync'),
        (STATUS_ERROR, 'Error'),
        (STATUS_DISCONNECTED, 'Disconnected'),
        (STATUS_REAUTH_REQUIRED, 'Requires Re-authentication'),
        (STATUS_REVOCATION_PENDING, 'Disconnect pending — provider revocation failed'),
    ]

    # Plaid identifiers
    item_id = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Plaid Item ID (unique per institution connection)"
    )
    access_token_encrypted = models.TextField(
        help_text="Encrypted Plaid access token"
    )

    # Institution info
    institution_id = models.CharField(
        max_length=50,
        help_text="Plaid institution ID"
    )
    institution_name = models.CharField(
        max_length=200,
        help_text="Display name of the institution"
    )
    institution_logo = models.URLField(
        blank=True,
        help_text="URL to institution logo (from Plaid)"
    )
    institution_color = models.CharField(
        max_length=7,
        blank=True,
        help_text="Institution primary color (hex)"
    )

    # Connection status
    connection_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING
    )

    # Error tracking
    error_code = models.CharField(
        max_length=50,
        blank=True,
        help_text="Plaid error code if connection has issues"
    )
    error_message = models.TextField(
        blank=True,
        help_text="Human-readable error message"
    )

    # Sync tracking
    last_sync_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last successful transaction sync"
    )
    last_sync_cursor = models.CharField(
        max_length=500,
        blank=True,
        help_text="Plaid sync cursor for incremental updates"
    )
    transactions_synced = models.PositiveIntegerField(
        default=0,
        help_text="Total transactions synced from this connection"
    )

    # Consent and audit
    consent_given_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When user authorized this connection"
    )
    consent_ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address when consent was given"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Bank Connection"
        verbose_name_plural = "Bank Connections"
        unique_together = ['user', 'item_id']
        indexes = [
            models.Index(fields=['user', 'connection_status']),
        ]

    def __str__(self):
        return f"{self.institution_name} ({self.get_connection_status_display()})"

    @property
    def is_active(self):
        """Check if connection is active and syncing."""
        return self.connection_status == self.STATUS_ACTIVE

    @property
    def needs_attention(self):
        """Check if connection requires user action."""
        return self.connection_status in [
            self.STATUS_ERROR,
            self.STATUS_REAUTH_REQUIRED
        ]

    def get_access_token(self):
        """Decrypt and return the access token."""
        from apps.finance.services.encryption import decrypt_token
        if not self.access_token_encrypted:
            return None
        return decrypt_token(self.access_token_encrypted)

    def set_access_token(self, token):
        """Encrypt and store the access token."""
        from apps.finance.services.encryption import encrypt_token
        self.access_token_encrypted = encrypt_token(token)

    def mark_error(self, error_code, error_message):
        """Mark connection as having an error."""
        self.connection_status = self.STATUS_ERROR
        self.error_code = error_code
        self.error_message = error_message
        self.save(update_fields=[
            'connection_status', 'error_code', 'error_message', 'updated_at'
        ])

    def mark_reauth_required(self):
        """Mark connection as requiring re-authentication."""
        self.connection_status = self.STATUS_REAUTH_REQUIRED
        self.error_code = 'ITEM_LOGIN_REQUIRED'
        self.error_message = 'Please reconnect your bank account.'
        self.save(update_fields=[
            'connection_status', 'error_code', 'error_message', 'updated_at'
        ])

    def mark_active(self):
        """Mark connection as active and clear errors."""
        self.connection_status = self.STATUS_ACTIVE
        self.error_code = ''
        self.error_message = ''
        self.save(update_fields=[
            'connection_status', 'error_code', 'error_message', 'updated_at'
        ])

    def mark_disconnected(self):
        """Mark disconnected and clear the token.

        ONLY call this AFTER the provider has confirmed revocation — see
        `apps.finance.services.provider_disconnect.revoke_and_disconnect`. Clearing the
        token before revocation destroys the only credential that can withdraw access.
        """
        self.connection_status = self.STATUS_DISCONNECTED
        self.access_token_encrypted = ''
        self.save(update_fields=[
            'connection_status', 'access_token_encrypted', 'updated_at'
        ])

    def mark_revocation_pending(self, error_message=''):
        """Provider revocation failed. KEEP the token so a retry can still revoke."""
        self.connection_status = self.STATUS_REVOCATION_PENDING
        self.error_code = 'REVOCATION_FAILED'
        self.error_message = (error_message or '')[:500]
        self.save(update_fields=[
            'connection_status', 'error_code', 'error_message', 'updated_at'
        ])

    @property
    def has_live_provider_access(self):
        """True while a usable provider credential is still stored.

        The deletion guards below refuse to remove a row in this state so that provider
        access can never be silently orphaned.
        """
        return bool(self.access_token_encrypted) and self.connection_status not in (
            self.STATUS_DISCONNECTED,
        )

    def soft_delete(self):
        """Refuse to hide a connection whose provider access is still live."""
        if self.has_live_provider_access:
            from django.core.exceptions import ValidationError
            raise ValidationError(
                "This connection still has live provider access. Disconnect it first so "
                "the provider revokes it; otherwise access would be orphaned."
            )
        return super().soft_delete()

    def delete(self, *args, **kwargs):
        """Refuse to delete a connection whose provider access is still live.

        Deliberately a REFUSAL, not a network call: an external request inside a delete
        path (or a cascade from user deletion) is exactly the fragile coupling that
        produces half-deleted state. Revocation belongs in the disconnect service.
        """
        if self.has_live_provider_access:
            from django.core.exceptions import ValidationError
            raise ValidationError(
                "Cannot delete a bank connection with live provider access. Disconnect "
                "it first (which revokes at the provider), then delete."
            )
        return super().delete(*args, **kwargs)

    def update_sync_cursor(self, cursor, transactions_added=0):
        """Update the sync cursor after a successful sync."""
        self.last_sync_cursor = cursor
        self.last_sync_at = timezone.now()
        self.transactions_synced += transactions_added
        self.save(update_fields=[
            'last_sync_cursor', 'last_sync_at', 'transactions_synced', 'updated_at'
        ])


# =============================================================================
# Bank Integration Log (audit trail)
# =============================================================================

class BankIntegrationLog(UserOwnedModel):
    """
    Audit log for all bank integration events.

    Tracks connections, disconnections, syncs, and errors for
    compliance and debugging purposes.
    """

    ACTION_CONNECT = 'connect'
    ACTION_DISCONNECT = 'disconnect'
    ACTION_SYNC = 'sync'
    ACTION_ERROR = 'error'
    ACTION_REAUTH = 'reauth'
    ACTION_WEBHOOK = 'webhook'

    ACTION_CHOICES = [
        (ACTION_CONNECT, 'Connected'),
        (ACTION_DISCONNECT, 'Disconnected'),
        (ACTION_SYNC, 'Synced'),
        (ACTION_ERROR, 'Error'),
        (ACTION_REAUTH, 'Re-authenticated'),
        (ACTION_WEBHOOK, 'Webhook Received'),
    ]

    bank_connection = models.ForeignKey(
        BankConnection,
        on_delete=models.CASCADE,
        related_name='logs',
        help_text="Related bank connection"
    )
    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES
    )
    success = models.BooleanField(default=True)
    details = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional event details (redacted for security)"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Bank Integration Log"
        verbose_name_plural = "Bank Integration Logs"
        indexes = [
            models.Index(fields=['bank_connection', 'action']),
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f"{self.get_action_display()} - {self.bank_connection.institution_name}"


# =============================================================================
# Finance Audit Log (comprehensive audit trail)
# =============================================================================

class FinanceAuditLog(models.Model):
    """
    Comprehensive audit log for ALL finance module operations.

    Unlike BankIntegrationLog which is specific to bank connections,
    this logs all finance operations including:
    - Account CRUD operations
    - Transaction CRUD operations
    - Budget/Goal changes
    - Imports/Exports
    - AI queries
    - Transfers

    Security: This table is append-only in application logic.
    """

    # Action types
    ACTION_CREATE = 'create'
    ACTION_UPDATE = 'update'
    ACTION_DELETE = 'delete'
    ACTION_VIEW = 'view'
    ACTION_TRANSFER = 'transfer'
    ACTION_IMPORT = 'import'
    ACTION_EXPORT = 'export'
    ACTION_AI_QUERY = 'ai_query'
    #: A deliberate, authorised wipe of Finance data. Recorded so the reset itself
    #: leaves evidence even though the data it removed is gone.
    ACTION_RESET = 'reset'

    ACTION_CHOICES = [
        (ACTION_CREATE, 'Created'),
        (ACTION_UPDATE, 'Updated'),
        (ACTION_DELETE, 'Deleted'),
        (ACTION_VIEW, 'Viewed'),
        (ACTION_TRANSFER, 'Transferred'),
        (ACTION_IMPORT, 'Imported'),
        (ACTION_EXPORT, 'Exported'),
        (ACTION_AI_QUERY, 'AI Query'),
        (ACTION_RESET, 'Module Reset'),
    ]

    # Entity types
    ENTITY_CHOICES = [
        ('account', 'Account'),
        ('transaction', 'Transaction'),
        ('budget', 'Budget'),
        ('goal', 'Goal'),
        ('import', 'Import'),
        ('bank_connection', 'Bank Connection'),
        ('ai_insight', 'AI Insight'),
        ('module', 'Finance Module'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='finance_audit_logs'
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    entity_type = models.CharField(max_length=30, choices=ENTITY_CHOICES)
    entity_id = models.IntegerField(null=True, blank=True)
    success = models.BooleanField(default=True)
    details = models.JSONField(
        default=dict,
        blank=True,
        help_text="Redacted operation details"
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Finance Audit Log"
        verbose_name_plural = "Finance Audit Logs"
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['action', 'entity_type']),
            models.Index(fields=['entity_type', 'entity_id']),
        ]

    def __str__(self):
        return f"{self.get_action_display()} {self.entity_type} - {self.created_at}"


# =============================================================================
# Payee (for autocomplete and categorization)
# =============================================================================

class Payee(UserOwnedModel):
    """
    Saved payees for transaction entry autocomplete.

    Also stores default category for automatic categorization.
    """

    name = models.CharField(
        max_length=200,
        help_text="Payee/merchant name"
    )
    default_category = models.ForeignKey(
        TransactionCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='default_payees',
        help_text="Default category when this payee is selected"
    )

    # Usage tracking
    use_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times used (for sorting suggestions)"
    )
    last_used_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        ordering = ['-use_count', 'name']
        verbose_name = "Payee"
        verbose_name_plural = "Payees"
        unique_together = ['user', 'name']

    def __str__(self):
        return self.name

    def record_use(self):
        """Record that this payee was used in a transaction."""
        self.use_count += 1
        self.last_used_at = timezone.now()
        self.save(update_fields=['use_count', 'last_used_at', 'updated_at'])


# =============================================================================
# Recurring Transaction
# =============================================================================

class RecurringTransaction(UserOwnedModel):
    """
    Template for recurring financial transactions (subscriptions, bills, income).

    Defines a pattern for automatic transaction generation. The service generates
    actual Transaction records based on this template.

    Example use cases:
    - Monthly subscriptions (Netflix, Spotify)
    - Bi-weekly paychecks
    - Quarterly insurance payments
    - Annual fees
    - Monthly rent/mortgage
    """

    # Frequency choices
    FREQUENCY_DAILY = 'daily'
    FREQUENCY_WEEKLY = 'weekly'
    FREQUENCY_BIWEEKLY = 'biweekly'
    FREQUENCY_MONTHLY = 'monthly'
    FREQUENCY_QUARTERLY = 'quarterly'
    FREQUENCY_YEARLY = 'yearly'
    FREQUENCY_CUSTOM = 'custom'

    FREQUENCY_CHOICES = [
        (FREQUENCY_DAILY, 'Daily'),
        (FREQUENCY_WEEKLY, 'Weekly'),
        (FREQUENCY_BIWEEKLY, 'Every Two Weeks'),
        (FREQUENCY_MONTHLY, 'Monthly'),
        (FREQUENCY_QUARTERLY, 'Quarterly'),
        (FREQUENCY_YEARLY, 'Yearly'),
        (FREQUENCY_CUSTOM, 'Custom'),
    ]

    # Transaction type
    TYPE_EXPENSE = 'expense'
    TYPE_INCOME = 'income'

    TYPE_CHOICES = [
        (TYPE_EXPENSE, 'Expense'),
        (TYPE_INCOME, 'Income'),
    ]

    # Core fields
    name = models.CharField(
        max_length=200,
        help_text="Name of the recurring transaction (e.g., 'Netflix', 'Paycheck')"
    )
    transaction_type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        default=TYPE_EXPENSE,
        help_text="Whether this is income or expense"
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Transaction amount (always positive, type determines sign)"
    )

    # Categorization
    account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.CASCADE,
        related_name='recurring_transactions',
        help_text="Account for this recurring transaction"
    )
    category = models.ForeignKey(
        TransactionCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recurring_transactions',
        help_text="Category for generated transactions"
    )
    payee = models.CharField(
        max_length=200,
        blank=True,
        help_text="Who receives or sends the money"
    )
    notes = models.TextField(
        blank=True,
        help_text="Notes for generated transactions"
    )

    # Schedule
    frequency = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        default=FREQUENCY_MONTHLY
    )
    custom_pattern = models.CharField(
        max_length=100,
        blank=True,
        help_text="Custom recurrence pattern (e.g., 'every_3_weeks', 'monthly:15')"
    )
    day_of_month = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Day of month for monthly transactions (1-31)"
    )
    day_of_week = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Day of week for weekly transactions (0=Monday, 6=Sunday)"
    )

    # Date range
    start_date = models.DateField(
        help_text="When this recurring transaction starts"
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        help_text="When this recurring transaction ends (optional)"
    )
    next_due_date = models.DateField(
        help_text="Next scheduled occurrence"
    )

    # Generation tracking
    last_generated_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date of last generated transaction"
    )
    total_generated = models.PositiveIntegerField(
        default=0,
        help_text="Total transactions generated from this template"
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this recurring transaction is active"
    )
    is_auto_post = models.BooleanField(
        default=False,
        help_text="Automatically create transactions (vs. reminder only)"
    )

    # Notification settings
    remind_days_before = models.PositiveSmallIntegerField(
        default=0,
        help_text="Days before due date to send reminder (0 = no reminder)"
    )

    class Meta:
        ordering = ['next_due_date', 'name']
        verbose_name = "Recurring Transaction"
        verbose_name_plural = "Recurring Transactions"
        indexes = [
            models.Index(fields=['user', 'is_active', 'next_due_date']),
            models.Index(fields=['next_due_date']),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_frequency_display()})"

    def get_absolute_url(self):
        return reverse('finance:recurring_detail', kwargs={'pk': self.pk})

    @property
    def signed_amount(self):
        """Return amount with correct sign based on type."""
        if self.transaction_type == self.TYPE_EXPENSE:
            return -abs(self.amount)
        return abs(self.amount)

    @property
    def is_expense(self):
        """Check if this is an expense."""
        return self.transaction_type == self.TYPE_EXPENSE

    @property
    def is_income(self):
        """Check if this is income."""
        return self.transaction_type == self.TYPE_INCOME

    @property
    def recurrence_pattern(self):
        """Return the recurrence pattern string for the recurrence service."""
        if self.frequency == self.FREQUENCY_CUSTOM and self.custom_pattern:
            return self.custom_pattern

        pattern_map = {
            self.FREQUENCY_DAILY: 'daily',
            self.FREQUENCY_WEEKLY: 'weekly',
            self.FREQUENCY_BIWEEKLY: 'biweekly',
            self.FREQUENCY_MONTHLY: 'monthly',
            self.FREQUENCY_QUARTERLY: 'every_3_months',
            self.FREQUENCY_YEARLY: 'yearly',
        }

        base_pattern = pattern_map.get(self.frequency, 'monthly')

        # Add specifics for monthly
        if self.frequency == self.FREQUENCY_MONTHLY and self.day_of_month:
            return f"monthly:{self.day_of_month}"

        return base_pattern

    def calculate_next_due_date(self, from_date=None):
        """
        Calculate the next due date after the given date.

        Args:
            from_date: The reference date (defaults to next_due_date)

        Returns:
            The next due date
        """
        from apps.life.services.recurrence import RecurrencePattern

        if from_date is None:
            from_date = self.next_due_date

        pattern = RecurrencePattern(self.recurrence_pattern)
        next_date = pattern.get_next_occurrence(from_date)

        # Check if past end_date
        if self.end_date and next_date and next_date > self.end_date:
            return None

        return next_date

    def advance_to_next(self):
        """
        Move next_due_date to the next occurrence.

        Called after generating a transaction.
        """
        next_date = self.calculate_next_due_date()
        if next_date:
            self.next_due_date = next_date
            self.save(update_fields=['next_due_date', 'updated_at'])
        else:
            # No more occurrences, deactivate
            self.is_active = False
            self.save(update_fields=['is_active', 'updated_at'])

    def generate_transaction(self, transaction_date=None):
        """
        Generate a Transaction from this recurring template.

        Args:
            transaction_date: Date for the transaction (defaults to next_due_date)

        Returns:
            The created Transaction instance
        """
        if transaction_date is None:
            transaction_date = self.next_due_date

        transaction = Transaction.objects.create(
            user=self.user,
            account=self.account,
            date=transaction_date,
            amount=self.signed_amount,
            description=self.name,
            category=self.category,
            payee=self.payee,
            notes=self.notes,
            is_recurring=True,
            recurring_source=self,
        )

        # Update tracking
        self.last_generated_date = transaction_date
        self.total_generated += 1
        self.save(update_fields=['last_generated_date', 'total_generated', 'updated_at'])

        # Move to next occurrence
        self.advance_to_next()

        return transaction

    def get_upcoming_occurrences(self, count=5):
        """
        Get the next N upcoming occurrence dates.

        Args:
            count: Number of occurrences to return

        Returns:
            List of dates
        """
        from apps.life.services.recurrence import RecurrencePattern

        pattern = RecurrencePattern(self.recurrence_pattern)
        occurrences = []
        current = self.next_due_date

        for _ in range(count):
            if current is None:
                break
            if self.end_date and current > self.end_date:
                break
            occurrences.append(current)
            current = pattern.get_next_occurrence(current)

        return occurrences


# =============================================================================
# F0 — Financial Entity & Attribution Truth
# =============================================================================
# Governing plan: docs/WLJ_FINANCE_F0_ENTITY_ATTRIBUTION_PLAN.md
#
# WLJ owns the deterministic truth of WHO money belongs to. It never moves money.
#   * FinancialEntity          — the economic actor (Personal, a household, a business…).
#                                Type is logic; NAME IS DATA. No code branches on a name.
#   * AccountEntityAssignment  — the TEMPORAL authority for `paid_by`: which entity owned an
#                                account over which date range.
#   * TransactionAttribution   — first-class, auditable, superseding: who SHOULD bear a cost,
#                                alongside a historical snapshot of who DID.
#   * AttributionRule          — user-owned, scoped, precedence-ordered. Never auto-created.
#
# Corrections SUPERSEDE; nothing is mutated or erased. User confirmation outranks every
# inference and may only be replaced by another explicit user confirmation.


def normalize_entity_name(name: str) -> str:
    """Normalized uniqueness key for an entity name.

    Case- and whitespace-insensitive so `Beacon`, `beacon`, `BEACON`, and ` Beacon `
    cannot coexist as ACTIVE entities for one user. The user-facing `name` keeps the
    exact casing/spacing the user typed; this key exists only for uniqueness and lookup.
    Computed in Python (not a functional index) so the constraint behaves identically on
    SQLite (dev) and PostgreSQL (prod).
    """
    return " ".join((name or "").split()).casefold()


class FinancialEntity(UserOwnedModel):
    """An economic actor money can belong to — the source of both attribution and `paid_by`.

    General and user-owned by design: a user may have Personal, a household, one or more
    businesses, an `other`, and exactly one `unknown`. **No business name is ever a system
    concept** — "Beacon" is a row in this table, never a branch in code.

    `unknown` is EXPLICIT truth ("we looked and cannot tell"), which is a different fact
    from having no attribution record at all ("nobody has decided yet"). Both are kept.
    """

    TYPE_PERSONAL = 'personal'
    TYPE_HOUSEHOLD = 'household'
    TYPE_BUSINESS = 'business'
    TYPE_OTHER = 'other'
    TYPE_UNKNOWN = 'unknown'

    ENTITY_TYPE_CHOICES = [
        (TYPE_PERSONAL, 'Personal'),
        (TYPE_HOUSEHOLD, 'Household / Shared'),
        (TYPE_BUSINESS, 'Business'),
        (TYPE_OTHER, 'Other'),
        (TYPE_UNKNOWN, 'Unknown'),
    ]

    entity_type = models.CharField(
        max_length=16,
        choices=ENTITY_TYPE_CHOICES,
        default=TYPE_BUSINESS,
        db_index=True,
        help_text="Classification. This is the only part of an entity code may branch on.",
    )
    name = models.CharField(
        max_length=120,
        help_text="Display name exactly as the user typed it. Data, never logic.",
    )
    name_key = models.CharField(
        max_length=120,
        db_index=True,
        editable=False,
        help_text="Normalized (case/whitespace-insensitive) uniqueness key derived from name.",
    )
    is_default_personal = models.BooleanField(
        default=False,
        help_text="The user's default personal entity. Exactly one per user.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Retired entities stay resolvable for historical attribution.",
    )
    space_ref = models.CharField(
        max_length=120,
        blank=True,
        default='',
        help_text=(
            "Forward hook for Space linkage (docs/WLJ_SECURITY_AUTHORIZATION_FRAMEWORK.md). "
            "UNUSED — no authorization logic reads this field."
        ),
    )
    sort_order = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = "Financial Entity"
        verbose_name_plural = "Financial Entities"
        indexes = [
            models.Index(fields=['user', 'entity_type', 'is_active'],
                         name='idx_finentity_user_type'),
        ]
        constraints = [
            # Duplicate ACTIVE names are impossible regardless of case or spacing.
            models.UniqueConstraint(
                fields=['user', 'name_key'],
                condition=models.Q(is_active=True, status='active'),
                name='uq_finentity_active_name_key',
            ),
            models.UniqueConstraint(
                fields=['user'],
                condition=models.Q(is_default_personal=True, status='active'),
                name='uq_finentity_default_personal',
            ),
            models.UniqueConstraint(
                fields=['user'],
                condition=models.Q(entity_type='unknown', status='active'),
                name='uq_finentity_unknown',
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_entity_type_display()})"

    def save(self, *args, **kwargs):
        self.name = " ".join((self.name or "").split())
        self.name_key = normalize_entity_name(self.name)
        super().save(*args, **kwargs)


class AccountEntityAssignment(UserOwnedModel):
    """WHICH entity economically owned an account, over WHICH dates.

    The temporal authority behind `paid_by`. `FinancialAccount.entity` is a convenience
    pointer to the open assignment; this table is the truth, so changing an account's
    entity can never silently rewrite what was true when a past transaction cleared.

    First assignment for an existing account may reach back over imported history
    (`effective_from` = earliest known activity). Later changes are forward-dated unless a
    retroactive `effective_from` is supplied deliberately.
    """

    ACTOR_USER = 'user'
    ACTOR_MIGRATION = 'migration'
    ACTOR_SYSTEM = 'system'
    ACTOR_CHOICES = [
        (ACTOR_USER, 'User'),
        (ACTOR_MIGRATION, 'Migration'),
        (ACTOR_SYSTEM, 'System'),
    ]

    account = models.ForeignKey(
        'FinancialAccount', on_delete=models.PROTECT,
        related_name='entity_assignments',
    )
    entity = models.ForeignKey(
        'FinancialEntity', on_delete=models.PROTECT,
        related_name='account_assignments',
    )
    effective_from = models.DateField(
        db_index=True,
        help_text="First date this entity owned the account (inclusive).",
    )
    effective_to = models.DateField(
        null=True, blank=True,
        help_text="Last date this entity owned the account (inclusive). NULL = current.",
    )
    actor = models.CharField(max_length=16, choices=ACTOR_CHOICES, default=ACTOR_USER)
    reason = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        ordering = ['account_id', '-effective_from']
        verbose_name = "Account Entity Assignment"
        verbose_name_plural = "Account Entity Assignments"
        indexes = [
            models.Index(fields=['account', 'effective_from'],
                         name='idx_acctentity_acct_from'),
            models.Index(fields=['user', 'entity'], name='idx_acctentity_user_entity'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['account'],
                condition=models.Q(effective_to__isnull=True, status='active'),
                name='uq_acctentity_one_open',
            ),
        ]

    def __str__(self):
        end = self.effective_to.isoformat() if self.effective_to else 'current'
        return f"{self.account_id}: {self.entity_id} [{self.effective_from} → {end}]"


class TransactionAttribution(UserOwnedModel):
    """WHO should bear a transaction — first-class, provenance-rich, and auditable.

    Immutable after creation except for the supersession fields. A correction creates a NEW
    active row and marks the old one SUPERSEDED; the old row's entity, source, actor,
    confidence, evidence, and timestamps are preserved untouched. Nothing is ever erased.

    `paid_by_entity` is SNAPSHOTTED at creation from the account's assignment covering the
    transaction date. It is historical evidence: a later account-ownership change does not
    rewrite it, which is what keeps a past finding auditable.

    Trust is three separate facts, following `PersonalKnowledgeFact`:
        `source`  — HOW the entity was decided (permanent)
        `actor`   — WHO acted (permanent)
        `user_confirmed` — whether a human explicitly said so (only the confirmation
                    service may set it; no rule path can).
    """

    SOURCE_USER_DIRECT = 'user_direct'
    SOURCE_USER_RULE = 'user_rule'
    SOURCE_ACCOUNT_DEFAULT = 'account_default'
    SOURCE_IMPORT_DECLARED = 'import_declared'
    SOURCE_MIGRATION_BOOTSTRAP = 'migration_bootstrap'
    SOURCE_MODEL_SUGGESTED = 'model_suggested'
    SOURCE_CHOICES = [
        (SOURCE_USER_DIRECT, 'User chose directly'),
        (SOURCE_USER_RULE, 'Applied from a user rule'),
        (SOURCE_ACCOUNT_DEFAULT, "Paying account's entity"),
        (SOURCE_IMPORT_DECLARED, 'Declared by the import source'),
        (SOURCE_MIGRATION_BOOTSTRAP, 'Written by a migration'),
        (SOURCE_MODEL_SUGGESTED, 'Suggested in conversation'),
    ]
    #: Sources that may NEVER carry user_confirmed=True.
    INFERRED_SOURCES = frozenset({
        SOURCE_USER_RULE, SOURCE_ACCOUNT_DEFAULT, SOURCE_IMPORT_DECLARED,
        SOURCE_MIGRATION_BOOTSTRAP, SOURCE_MODEL_SUGGESTED,
    })

    ACTOR_USER = 'user'
    ACTOR_RULE = 'rule'
    ACTOR_IMPORT = 'import'
    ACTOR_MIGRATION = 'migration'
    ACTOR_SYSTEM = 'system'
    ACTOR_CHOICES = [
        (ACTOR_USER, 'User'),
        (ACTOR_RULE, 'Rule'),
        (ACTOR_IMPORT, 'Import'),
        (ACTOR_MIGRATION, 'Migration'),
        (ACTOR_SYSTEM, 'System (deterministic refresh)'),
    ]

    STATUS_ACTIVE = 'active'
    STATUS_SUPERSEDED = 'superseded'
    ATTRIBUTION_STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_SUPERSEDED, 'Superseded by a correction'),
    ]

    SHARE_FULL = 'full'
    SHARE_PERCENT = 'percent'
    SHARE_AMOUNT = 'amount'
    SHARE_BASIS_CHOICES = [
        (SHARE_FULL, 'Whole transaction'),
        (SHARE_PERCENT, 'Percentage share'),
        (SHARE_AMOUNT, 'Fixed amount share'),
    ]

    #: Fields that may never change after the row is created.
    IMMUTABLE_FIELDS = (
        'transaction_id', 'attributed_entity_id', 'paid_by_entity_id', 'source', 'actor',
        'confidence', 'evidence', 'rule_id', 'share_basis', 'share_value',
    )

    transaction = models.ForeignKey(
        'Transaction', on_delete=models.CASCADE, related_name='attributions',
    )
    attributed_entity = models.ForeignKey(
        'FinancialEntity', on_delete=models.PROTECT, related_name='attributions',
        help_text="Who SHOULD bear this cost.",
    )
    paid_by_entity = models.ForeignKey(
        'FinancialEntity', on_delete=models.PROTECT, related_name='paid_attributions',
        help_text="Who DID bear it — snapshot of the account's entity on the transaction date.",
    )
    source = models.CharField(max_length=24, choices=SOURCE_CHOICES, db_index=True)
    actor = models.CharField(max_length=16, choices=ACTOR_CHOICES)
    confidence = models.FloatField(
        default=1.0, help_text="0.0–1.0. User-confirmed rows are 1.0.",
    )
    evidence = models.JSONField(
        default=dict, blank=True,
        help_text="Concise references + scalars only. Never account numbers or tokens.",
    )
    user_confirmed = models.BooleanField(
        default=False, db_index=True,
        help_text="Only the confirmation service may set this. No rule path can.",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    rule = models.ForeignKey(
        'AttributionRule', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='attributions',
    )
    attribution_status = models.CharField(
        max_length=16, choices=ATTRIBUTION_STATUS_CHOICES,
        default=STATUS_ACTIVE, db_index=True,
    )
    superseded_by = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='supersedes',
    )
    share_basis = models.CharField(
        max_length=8, choices=SHARE_BASIS_CHOICES, default=SHARE_FULL,
        help_text="Always 'full' in the MVP. Splits attach here without a schema change.",
    )
    share_value = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Percentage or amount when share_basis is not 'full'.",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Transaction Attribution"
        verbose_name_plural = "Transaction Attributions"
        indexes = [
            models.Index(fields=['user', 'attribution_status'],
                         name='idx_txattr_user_status'),
            models.Index(fields=['user', 'attributed_entity', 'attribution_status'],
                         name='idx_txattr_user_entity'),
            # The F1 mismatch scan: one single-table indexed read, no joins.
            models.Index(fields=['user', 'paid_by_entity', 'attributed_entity',
                                 'attribution_status'],
                         name='idx_txattr_mismatch'),
        ]
        constraints = [
            # Exactly one CURRENT whole-transaction attribution. Percentage/amount shares
            # are deliberately outside the condition, so future splits attach without
            # dropping this constraint.
            models.UniqueConstraint(
                fields=['transaction'],
                condition=models.Q(attribution_status='active', share_basis='full',
                                   status='active'),
                name='uq_txattr_one_active_full',
            ),
        ]

    def __str__(self):
        return (f"tx={self.transaction_id} → entity={self.attributed_entity_id} "
                f"({self.source}, {self.attribution_status})")

    @property
    def is_mismatch(self):
        """Fact, not verdict: the attributed entity differs from who actually paid."""
        return self.attributed_entity_id != self.paid_by_entity_id


class AttributionRule(UserOwnedModel):
    """A user-owned, scoped rule that assigns an entity to future transactions.

    Rules are NEVER created automatically from inference — only from an explicit user
    decision. Precedence is most-specific-first: recurring series → payee → account.

    Category is deliberately NOT a scope and never will be: `TransactionCategory.user` is
    nullable with `is_system` (system categories are shared across every user), so a
    category-anchored rule would leak one user's attribution into another's.
    """

    SCOPE_RECURRING = 'recurring_series'
    SCOPE_PAYEE = 'payee'
    SCOPE_ACCOUNT = 'account'
    SCOPE_PATTERN = 'description_pattern'
    SCOPE_CHOICES = [
        (SCOPE_RECURRING, 'Recurring series'),
        (SCOPE_PAYEE, 'Payee'),
        (SCOPE_ACCOUNT, 'Account'),
        (SCOPE_PATTERN, 'Description pattern'),
    ]
    #: Most specific first. The ordering IS the precedence.
    SCOPE_PRECEDENCE = (SCOPE_RECURRING, SCOPE_PAYEE, SCOPE_ACCOUNT, SCOPE_PATTERN)

    ORIGIN_USER_CONFIRMATION = 'user_confirmation'
    ORIGIN_USER_AUTHORED = 'user_authored'
    ORIGIN_IMPORTED = 'imported'
    ORIGIN_CHOICES = [
        (ORIGIN_USER_CONFIRMATION, 'Created from a user confirmation'),
        (ORIGIN_USER_AUTHORED, 'Authored by the user'),
        (ORIGIN_IMPORTED, 'Imported'),
    ]

    STATUS_ACTIVE = 'active'
    STATUS_SUPERSEDED = 'superseded'
    STATUS_EXPIRED = 'expired'
    RULE_STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_SUPERSEDED, 'Superseded'),
        (STATUS_EXPIRED, 'Expired'),
    ]

    scope = models.CharField(max_length=24, choices=SCOPE_CHOICES, db_index=True)
    payee = models.ForeignKey(
        'Payee', on_delete=models.CASCADE, null=True, blank=True,
        related_name='attribution_rules',
    )
    recurring = models.ForeignKey(
        'RecurringTransaction', on_delete=models.CASCADE, null=True, blank=True,
        related_name='attribution_rules',
    )
    account = models.ForeignKey(
        'FinancialAccount', on_delete=models.CASCADE, null=True, blank=True,
        related_name='attribution_rules',
    )
    pattern = models.CharField(
        max_length=200, blank=True, default='',
        help_text="Reserved for the description_pattern scope. Unused in the MVP.",
    )
    entity = models.ForeignKey(
        'FinancialEntity', on_delete=models.PROTECT, related_name='attribution_rules',
    )
    origin = models.CharField(
        max_length=24, choices=ORIGIN_CHOICES, default=ORIGIN_USER_CONFIRMATION,
    )
    user_confirmed = models.BooleanField(default=True)
    confidence = models.FloatField(default=1.0)
    rule_status = models.CharField(
        max_length=16, choices=RULE_STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True,
    )
    superseded_by = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='supersedes',
    )
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    use_count = models.PositiveIntegerField(default=0)
    last_used_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Attribution Rule"
        verbose_name_plural = "Attribution Rules"
        indexes = [
            models.Index(fields=['user', 'rule_status', 'scope'],
                         name='idx_attrrule_user_status'),
            models.Index(fields=['user', 'payee'], name='idx_attrrule_user_payee'),
            models.Index(fields=['user', 'recurring'], name='idx_attrrule_user_recur'),
            models.Index(fields=['user', 'account'], name='idx_attrrule_user_account'),
        ]

    def __str__(self):
        return f"{self.scope} → entity={self.entity_id} ({self.rule_status})"

    @property
    def anchor_id(self):
        """The id of whatever this rule is scoped to."""
        return {
            self.SCOPE_RECURRING: self.recurring_id,
            self.SCOPE_PAYEE: self.payee_id,
            self.SCOPE_ACCOUNT: self.account_id,
        }.get(self.scope)


# =============================================================================
# F3 — Opportunity lifecycle & outcome verification
# =============================================================================

class FinanceOpportunity(UserOwnedModel):
    """The state of a change the USER makes in the outside world, and whether it happened.

    NOT a second action authority. WLJ executes nothing here: it cannot move money, change
    a payment method, cancel a subscription, or touch an external account. This record
    tracks (a) what WLJ deterministically detected, (b) what the user decided about it, and
    (c) whether later transaction truth shows the change actually occurred.

    Detection stays in `Insight` (the canonical finding). This adds only the lifecycle and
    the verification evidence, keyed to the insight's stable `dedupe_key` so a re-detection
    reattaches to the same opportunity instead of forking it.

    Verification is deterministic, never inferred: transactions matching the pattern that
    appear AFTER acceptance are compared against the baseline captured at acceptance
    (reusing `Transaction.fingerprint`, so a pre-existing row can never be mistaken for
    evidence of a change).
    """

    KIND_ENTITY_PAYMENT_MISMATCH = 'entity_payment_mismatch'
    KIND_CHOICES = [
        (KIND_ENTITY_PAYMENT_MISMATCH, 'Expense paid by the wrong entity'),
    ]

    STATE_DETECTED = 'detected'
    STATE_PRESENTED = 'presented'
    STATE_ACCEPTED = 'accepted'
    STATE_REJECTED = 'rejected'
    STATE_DEFERRED = 'deferred'
    STATE_IN_PROGRESS = 'in_progress'
    STATE_COMPLETED = 'completed'
    STATE_VERIFIED_AUTO = 'verified_auto'
    STATE_VERIFIED_MANUAL = 'verified_manual'
    STATE_NOT_RELEVANT = 'not_relevant'
    STATE_CHOICES = [
        (STATE_DETECTED, 'Detected'),
        (STATE_PRESENTED, 'Presented'),
        (STATE_ACCEPTED, 'Accepted'),
        (STATE_REJECTED, 'Rejected'),
        (STATE_DEFERRED, 'Deferred'),
        (STATE_IN_PROGRESS, 'In progress'),
        (STATE_COMPLETED, 'Completed'),
        (STATE_VERIFIED_AUTO, 'Verified automatically'),
        (STATE_VERIFIED_MANUAL, 'Verified manually'),
        (STATE_NOT_RELEVANT, 'No longer relevant'),
    ]
    #: States where WLJ should keep watching later transactions for evidence.
    WATCHING_STATES = (STATE_ACCEPTED, STATE_IN_PROGRESS, STATE_COMPLETED)
    #: States the user has closed — never reopened by detection.
    CLOSED_STATES = (STATE_REJECTED, STATE_VERIFIED_AUTO, STATE_VERIFIED_MANUAL,
                     STATE_NOT_RELEVANT)

    kind = models.CharField(max_length=32, choices=KIND_CHOICES,
                            default=KIND_ENTITY_PAYMENT_MISMATCH)
    dedupe_key = models.CharField(
        max_length=64, db_index=True,
        help_text="Stable key shared with the canonical Insight for this pattern.",
    )
    insight = models.ForeignKey(
        'core.Insight', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='finance_opportunities',
    )
    attributed_entity = models.ForeignKey(
        'FinancialEntity', on_delete=models.PROTECT,
        related_name='opportunities_as_bearer',
    )
    paid_by_entity = models.ForeignKey(
        'FinancialEntity', on_delete=models.PROTECT,
        related_name='opportunities_as_payer',
    )
    recurring = models.ForeignKey(
        'RecurringTransaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='opportunities',
    )
    payee_key = models.CharField(max_length=200, blank=True, default='')
    label = models.CharField(max_length=200, blank=True, default='')

    state = models.CharField(max_length=20, choices=STATE_CHOICES,
                             default=STATE_DETECTED, db_index=True)
    state_changed_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    deferred_until = models.DateField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    occurrences = models.PositiveIntegerField(default=0)
    annual_estimate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    baseline = models.JSONField(
        default=dict, blank=True,
        help_text="Truth captured at acceptance, so later evidence is provably NEW.",
    )
    verification_evidence = models.JSONField(default=dict, blank=True)
    follow_up = models.ForeignKey(
        'ai.ConversationFollowUp', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='finance_opportunities',
        help_text="The existing follow-through record — WLJ adds no second scheduler.",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-annual_estimate', '-created_at']
        verbose_name = "Finance Opportunity"
        verbose_name_plural = "Finance Opportunities"
        indexes = [
            models.Index(fields=['user', 'state'], name='idx_finopp_user_state'),
            models.Index(fields=['user', 'kind', 'state'], name='idx_finopp_user_kind'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'dedupe_key'],
                condition=models.Q(status='active'),
                name='uq_finopp_user_dedupe',
            ),
        ]

    def __str__(self):
        return f"{self.label or self.kind} [{self.state}]"

    @property
    def is_open(self):
        return self.state not in self.CLOSED_STATES
