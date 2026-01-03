# ==============================================================================
# File: apps/finance/models.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Finance module data models - accounts, transactions, budgets, goals,
#              imports with audit tracking
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
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

        # Sum all expense transactions in this category
        spent = Transaction.objects.filter(
            user=self.user,
            category=self.category,
            date__gte=self.month,
            date__lte=end_of_month,
            status='active',
            amount__lt=0  # Expenses are negative
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

        monthly_income = Transaction.objects.filter(
            user=user,
            date__gte=month_start,
            date__lte=snapshot_date,
            status='active',
            amount__gt=0,
            is_opening_balance=False
        ).exclude(
            transfer_pair__isnull=False
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        monthly_expenses = abs(Transaction.objects.filter(
            user=user,
            date__gte=month_start,
            date__lte=snapshot_date,
            status='active',
            amount__lt=0,
            is_opening_balance=False
        ).exclude(
            transfer_pair__isnull=False
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00'))

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
    file = models.FileField(
        upload_to='finance/imports/%Y/%m/',
        help_text="Uploaded transaction file"
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

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_PENDING, 'Pending Initial Sync'),
        (STATUS_ERROR, 'Error'),
        (STATUS_DISCONNECTED, 'Disconnected'),
        (STATUS_REAUTH_REQUIRED, 'Requires Re-authentication'),
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
        """Mark connection as disconnected and clear token."""
        self.connection_status = self.STATUS_DISCONNECTED
        self.access_token_encrypted = ''
        self.save(update_fields=[
            'connection_status', 'access_token_encrypted', 'updated_at'
        ])

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

    ACTION_CHOICES = [
        (ACTION_CREATE, 'Created'),
        (ACTION_UPDATE, 'Updated'),
        (ACTION_DELETE, 'Deleted'),
        (ACTION_VIEW, 'Viewed'),
        (ACTION_TRANSFER, 'Transferred'),
        (ACTION_IMPORT, 'Imported'),
        (ACTION_EXPORT, 'Exported'),
        (ACTION_AI_QUERY, 'AI Query'),
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
