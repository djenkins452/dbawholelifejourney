# ==============================================================================
# File: apps/finance/views.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Finance module views for accounts, transactions, budgets, goals,
#              and file imports
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-02
# Last Updated: 2026-01-06
# ==============================================================================
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum, Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json
import logging

logger = logging.getLogger(__name__)
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView, View
)

from apps.core.current_context import PageSummaryMixin
from apps.core.utils import get_user_today
from apps.finance.services.finance_home_summary import build_finance_home_summary

from apps.core.events.domain_events import safe_emit_event, EventTypes

from .models import (
    FinancialAccount,
    TransactionCategory,
    Transaction,
    Budget,
    FinancialGoal,
    FinancialMetricSnapshot,
    Payee,
    TransactionImport,
    BankConnection,
    BankIntegrationLog,
    RecurringTransaction,
)
from .forms import (
    FinancialAccountForm,
    TransactionForm,
    QuickTransactionForm,
    BudgetForm,
    FinancialGoalForm,
    TransactionFilterForm,
    TransferForm,
    TransactionImportForm,
    RecurringTransactionForm,
)


# =============================================================================
# Mixins
# =============================================================================

from apps.finance.access import (  # noqa: E402
    FinanceEnabledRequiredMixin,
    finance_enabled_required,
)
from apps.finance.security import (  # noqa: E402
    finance_rate_limit,
    requires_recent_auth,
)


class FinanceUserMixin(FinanceEnabledRequiredMixin, LoginRequiredMixin):
    """Mixin for finance views that filters by current user."""

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user, status='active')


class FinanceSensitiveOperationMixin:
    """
    Mixin for views that perform sensitive financial operations.

    CISO Review 2026-01-12: Activity-based timeout for financial operations.

    If the user hasn't performed a financial action within the timeout period,
    they must re-authenticate (re-enter password) before proceeding.

    Configuration:
        - Timeout period: Configured via settings.WLJ_SETTINGS['FINANCE_ACTIVITY_TIMEOUT_MINUTES']
        - Default: 15 minutes
        - Session key: 'finance_last_activity' stores the last activity timestamp

    Usage:
        Add this mixin to views that perform sensitive operations like:
        - Bank account connections
        - Large transactions
        - Account deletions
        - Bulk operations

    Example:
        class BankConnectView(FinanceSensitiveOperationMixin, LoginRequiredMixin, View):
            finance_operation_name = 'bank_connection'
            ...
    """

    # Override in subclass to describe the operation for logging
    finance_operation_name = 'sensitive_operation'

    def dispatch(self, request, *args, **kwargs):
        """Check activity timeout before processing the request."""
        if not self._check_finance_activity_timeout(request):
            # Redirect to password confirmation
            from django.urls import reverse
            from django.contrib import messages

            messages.warning(
                request,
                "For your security, please confirm your password to continue with this financial operation."
            )
            # Store the intended destination
            request.session['finance_return_url'] = request.get_full_path()
            return redirect(reverse('users:confirm_password'))

        return super().dispatch(request, *args, **kwargs)

    def _check_finance_activity_timeout(self, request) -> bool:
        """
        Check if the user has been active within the timeout period.

        Returns True if the user can proceed, False if re-authentication is needed.
        """
        from django.conf import settings
        from django.utils import timezone

        # Get timeout from settings (default 15 minutes)
        timeout_minutes = settings.WLJ_SETTINGS.get('FINANCE_ACTIVITY_TIMEOUT_MINUTES', 15)

        # Get last activity timestamp from session
        last_activity = request.session.get('finance_last_activity')

        if last_activity is None:
            # No previous activity, require authentication
            return False

        # Parse the timestamp
        try:
            last_activity_time = timezone.datetime.fromisoformat(last_activity)
            if timezone.is_naive(last_activity_time):
                last_activity_time = timezone.make_aware(last_activity_time)
        except (ValueError, TypeError):
            return False

        # Check if within timeout period
        now = timezone.now()
        elapsed_minutes = (now - last_activity_time).total_seconds() / 60

        if elapsed_minutes > timeout_minutes:
            # Timeout exceeded
            self._log_finance_timeout(request)
            return False

        return True

    def _update_finance_activity(self, request):
        """Update the last activity timestamp in the session."""
        from django.utils import timezone
        request.session['finance_last_activity'] = timezone.now().isoformat()

    def _log_finance_timeout(self, request):
        """Log when a timeout occurs for security monitoring."""
        from apps.core.security_logging import log_security_event
        log_security_event(
            event_type='permission_denied',
            severity='info',
            message=f'Finance activity timeout for {self.finance_operation_name}',
            request=request,
            user=request.user,
            details={
                'operation': self.finance_operation_name,
                'path': request.path,
            }
        )

    def form_valid(self, form):
        """Update activity timestamp on successful form submission."""
        self._update_finance_activity(self.request)
        return super().form_valid(form)


class FinanceAuditMixin:
    """
    Mixin to add audit logging to finance views.

    Automatically logs create, update, and delete operations.
    """

    audit_entity_type = None  # Override in subclass

    def get_audit_logger(self):
        from apps.finance.security import FinanceAuditLogger
        return FinanceAuditLogger(
            user=self.request.user,
            request=self.request
        )

    def form_valid(self, form):
        response = super().form_valid(form)
        audit_logger = self.get_audit_logger()

        if self.audit_entity_type:
            # Determine action based on view type
            if hasattr(self, 'object') and self.object:
                if isinstance(self, DeleteView):
                    audit_logger.log(
                        action='delete',
                        entity_type=self.audit_entity_type,
                        entity_id=self.object.id,
                    )
                elif self.object.pk and form.changed_data:
                    audit_logger.log(
                        action='update',
                        entity_type=self.audit_entity_type,
                        entity_id=self.object.id,
                        details={'changed_fields': form.changed_data}
                    )
                else:
                    audit_logger.log(
                        action='create',
                        entity_type=self.audit_entity_type,
                        entity_id=self.object.id,
                    )

        return response


# =============================================================================
# Dashboard / Home
# =============================================================================

class FinanceDashboardView(PageSummaryMixin, LoginRequiredMixin, TemplateView):
    """Main finance dashboard with overview of all financial data."""

    template_name = 'finance/dashboard.html'
    # Current Context — the Finance workspace declares a deterministic overview summary.
    # The finance.dashboard provider reads the SAME build_finance_home_summary source this
    # view exposes below (request-path-safe SAE snapshot), so the page and the assistant
    # never disagree about the figures.
    page_summary_key = "finance.dashboard"
    page_summary_title = "Finance"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = get_user_today(user)
        month_start = today.replace(day=1)

        # ONE deterministic source feeds both this render and the finance.dashboard page
        # summary provider (Current Context contract — never re-derive independently).
        context["finance_summary"] = build_finance_home_summary(user)

        # Accounts summary
        accounts = FinancialAccount.objects.filter(
            user=user, status='active', is_hidden=False
        ).order_by('sort_order', 'name')

        total_assets = Decimal('0.00')
        total_liabilities = Decimal('0.00')

        for account in accounts:
            if account.is_asset:
                total_assets += account.current_balance
            else:
                total_liabilities += abs(account.current_balance)

        context['accounts'] = accounts
        context['total_assets'] = total_assets
        context['total_liabilities'] = total_liabilities
        context['net_worth'] = total_assets - total_liabilities

        # Recent transactions
        context['recent_transactions'] = Transaction.objects.filter(
            user=user, status='active'
        ).select_related('account', 'category')[:10]

        # Monthly summary — F4 convergence: the ONE shared population authority, so the
        # dashboard, budgets, history, the metric snapshots, and the Chief of Staff can no
        # longer disagree about transfers or opening balances (Article III.1).
        from apps.finance.services.attribution_population import financial_activity

        activity = financial_activity(user, start=month_start, end=today)
        monthly_income = activity.filter(amount__gt=0).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')

        monthly_expenses = abs(activity.filter(amount__lt=0).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00'))

        # Finance intelligence (F1–F3) — ONE deterministic source, also feeding the
        # Current Context summary. Bounded, indexed reads only; no provider call.
        from apps.finance.services.finance_intelligence_summary import (
            build_finance_intelligence,
        )
        context['intel'] = build_finance_intelligence(user)

        context['monthly_income'] = monthly_income
        context['monthly_expenses'] = monthly_expenses
        context['monthly_cash_flow'] = monthly_income - monthly_expenses

        # Budget summary
        budgets = Budget.objects.filter(
            user=user, status='active', month=month_start
        ).select_related('category')
        context['budgets'] = budgets
        context['budgets_over'] = [b for b in budgets if b.health_status == 'over']

        # Active goals
        context['active_goals'] = FinancialGoal.objects.filter(
            user=user, status='active', goal_status='active'
        )[:5]

        # Quick add form
        context['quick_form'] = QuickTransactionForm(user)

        # Upcoming recurring transactions
        from datetime import timedelta
        upcoming_end = today + timedelta(days=14)
        upcoming_recurring = RecurringTransaction.objects.filter(
            user=user,
            status='active',
            is_active=True,
            next_due_date__lte=upcoming_end,
        ).select_related('account', 'category').order_by('next_due_date')[:5]
        context['upcoming_recurring'] = upcoming_recurring

        return context


# =============================================================================
# Accounts
# =============================================================================

class AccountListView(FinanceUserMixin, ListView):
    """List all financial accounts."""

    model = FinancialAccount
    template_name = 'finance/account_list.html'
    context_object_name = 'accounts'

    def get_queryset(self):
        return super().get_queryset().order_by('sort_order', 'name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        accounts = context['accounts']

        # Calculate totals
        total_assets = sum(
            a.current_balance for a in accounts if a.is_asset
        )
        total_liabilities = sum(
            abs(a.current_balance) for a in accounts if a.is_liability
        )

        context['total_assets'] = total_assets
        context['total_liabilities'] = total_liabilities
        context['net_worth'] = total_assets - total_liabilities

        # Group accounts
        context['asset_accounts'] = [a for a in accounts if a.is_asset]
        context['liability_accounts'] = [a for a in accounts if a.is_liability]

        return context


class AccountDetailView(FinanceUserMixin, DetailView):
    """View account details with transaction history."""

    model = FinancialAccount
    template_name = 'finance/account_detail.html'
    context_object_name = 'account'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        account = self.object

        # Recent transactions for this account
        context['transactions'] = Transaction.objects.filter(
            user=self.request.user,
            account=account,
            status='active'
        ).select_related('category')[:50]

        return context


class AccountCreateView(FinanceAuditMixin, LoginRequiredMixin, CreateView):
    """Create a new financial account."""

    model = FinancialAccount
    form_class = FinancialAccountForm
    template_name = 'finance/account_form.html'
    success_url = reverse_lazy('finance:account_list')
    audit_entity_type = 'account'

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.balance_updated_at = timezone.now()
        messages.success(self.request, f'Account "{form.instance.name}" created.')
        return super().form_valid(form)

    def form_invalid(self, form):
        logger.error(f"Account form errors: {form.errors}")
        return super().form_invalid(form)


class AccountUpdateView(FinanceAuditMixin, FinanceUserMixin, UpdateView):
    """Edit a financial account."""

    model = FinancialAccount
    form_class = FinancialAccountForm
    template_name = 'finance/account_form.html'
    success_url = reverse_lazy('finance:account_list')
    audit_entity_type = 'account'

    def form_valid(self, form):
        messages.success(self.request, f'Account "{form.instance.name}" updated.')
        return super().form_valid(form)


class AccountDeleteView(FinanceAuditMixin, FinanceUserMixin, DeleteView):
    """Delete (soft delete) a financial account."""

    model = FinancialAccount
    template_name = 'finance/account_confirm_delete.html'
    success_url = reverse_lazy('finance:account_list')
    audit_entity_type = 'account'

    def form_valid(self, form):
        # Log before soft delete
        audit_logger = self.get_audit_logger()
        audit_logger.log_account_deleted(self.object)
        self.object.soft_delete()
        messages.success(self.request, f'Account "{self.object.name}" deleted.')
        return redirect(self.success_url)


# =============================================================================
# Transactions
# =============================================================================

class TransactionListView(FinanceUserMixin, ListView):
    """List transactions with filtering."""

    model = Transaction
    template_name = 'finance/transaction_list.html'
    context_object_name = 'transactions'
    paginate_by = 50

    def get_queryset(self):
        queryset = super().get_queryset().select_related('account', 'category')

        # Apply filters from GET params
        form = TransactionFilterForm(self.request.user, self.request.GET)
        if form.is_valid():
            data = form.cleaned_data

            if data.get('date_from'):
                queryset = queryset.filter(date__gte=data['date_from'])
            if data.get('date_to'):
                queryset = queryset.filter(date__lte=data['date_to'])
            if data.get('account'):
                queryset = queryset.filter(account=data['account'])
            if data.get('category'):
                queryset = queryset.filter(category=data['category'])
            if data.get('transaction_type') == 'income':
                queryset = queryset.filter(amount__gt=0)
            elif data.get('transaction_type') == 'expense':
                queryset = queryset.filter(amount__lt=0)
            if data.get('search'):
                queryset = queryset.filter(
                    Q(description__icontains=data['search']) |
                    Q(payee__icontains=data['search']) |
                    Q(notes__icontains=data['search'])
                )

        return queryset.order_by('-date', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = TransactionFilterForm(
            self.request.user, self.request.GET
        )
        # ONE categories query for the whole page, however many rows are shown.
        from apps.finance.services.category_assignment import attach_category_options
        attach_category_options(self.request.user, context['transactions'])
        return context


class TransactionDetailView(FinanceUserMixin, DetailView):
    """View transaction details."""

    model = Transaction
    template_name = 'finance/transaction_detail.html'
    context_object_name = 'transaction'

    def get_queryset(self):
        return super().get_queryset().select_related('account', 'category')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.finance.services.category_assignment import attach_category_options
        attach_category_options(self.request.user, [context['transaction']])
        return context


class TransactionCreateView(FinanceAuditMixin, LoginRequiredMixin, CreateView):
    """Create a new transaction."""

    model = Transaction
    template_name = 'finance/transaction_form.html'
    success_url = reverse_lazy('finance:transaction_list')
    audit_entity_type = 'transaction'

    def get_form(self, form_class=None):
        return TransactionForm(self.request.user, **self.get_form_kwargs())

    def form_valid(self, form):
        messages.success(self.request, 'Transaction created.')
        response = super().form_valid(form)
        safe_emit_event(EventTypes.FINANCE_TRANSACTION_LOGGED, self.request.user, {
            "entry_id": self.object.id, "source": "web_view",
        })
        return response


class TransactionUpdateView(FinanceAuditMixin, FinanceUserMixin, UpdateView):
    """Edit a transaction."""

    model = Transaction
    template_name = 'finance/transaction_form.html'
    success_url = reverse_lazy('finance:transaction_list')
    audit_entity_type = 'transaction'

    def get_form(self, form_class=None):
        return TransactionForm(self.request.user, **self.get_form_kwargs())

    def form_valid(self, form):
        messages.success(self.request, 'Transaction updated.')
        return super().form_valid(form)


class TransactionDeleteView(FinanceAuditMixin, FinanceUserMixin, DeleteView):
    """Delete a transaction."""

    model = Transaction
    template_name = 'finance/transaction_confirm_delete.html'
    success_url = reverse_lazy('finance:transaction_list')
    audit_entity_type = 'transaction'

    def form_valid(self, form):
        audit_logger = self.get_audit_logger()
        audit_logger.log_transaction_deleted(self.object)
        self.object.soft_delete()
        messages.success(self.request, 'Transaction deleted.')
        return redirect(self.success_url)


@login_required
def quick_transaction(request):
    """Handle quick transaction form submission."""
    if request.method == 'POST':
        form = QuickTransactionForm(request.user, request.POST)
        if form.is_valid():
            transaction = form.save()
            safe_emit_event(EventTypes.FINANCE_TRANSACTION_LOGGED, request.user, {
                "entry_id": transaction.id, "source": "web_view",
            })
            messages.success(request, f'Transaction added: {transaction.description}')
            return redirect('finance:dashboard')
    return redirect('finance:dashboard')


@login_required
def transfer_view(request):
    """Handle transfers between accounts."""
    if request.method == 'POST':
        form = TransferForm(request.user, request.POST)
        if form.is_valid():
            outgoing, incoming = form.save()
            messages.success(
                request,
                f'Transfer of ${form.cleaned_data["amount"]:,.2f} completed.'
            )
            return redirect('finance:dashboard')
    else:
        form = TransferForm(request.user)

    return render(request, 'finance/transfer_form.html', {'form': form})


# =============================================================================
# Budgets
# =============================================================================

class BudgetListView(FinanceUserMixin, ListView):
    """List budgets for current month."""

    model = Budget
    template_name = 'finance/budget_list.html'
    context_object_name = 'budgets'

    def get_queryset(self):
        # Get month from GET param or default to current month
        month_str = self.request.GET.get('month')
        if month_str:
            try:
                year, month = month_str.split('-')
                month_date = timezone.datetime(int(year), int(month), 1).date()
            except (ValueError, TypeError):
                month_date = get_user_today(self.request.user).replace(day=1)
        else:
            month_date = get_user_today(self.request.user).replace(day=1)

        self.current_month = month_date

        return super().get_queryset().filter(
            month=month_date
        ).select_related('category').order_by('category__sort_order', 'category__name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_month'] = self.current_month

        # Calculate totals
        budgets = context['budgets']
        context['total_budgeted'] = sum(b.budgeted_amount for b in budgets)
        context['total_spent'] = sum(b.spent_amount for b in budgets)
        context['total_remaining'] = sum(b.remaining_amount for b in budgets)

        # Count by health status
        context['on_track_count'] = sum(1 for b in budgets if b.health_status == 'on_track')
        context['warning_count'] = sum(1 for b in budgets if b.health_status == 'warning')
        context['over_count'] = sum(1 for b in budgets if b.health_status == 'over')

        return context


class BudgetCreateView(FinanceAuditMixin, LoginRequiredMixin, CreateView):
    """Create a new budget."""

    model = Budget
    template_name = 'finance/budget_form.html'
    success_url = reverse_lazy('finance:budget_list')
    audit_entity_type = 'budget'

    def get_form(self, form_class=None):
        return BudgetForm(self.request.user, **self.get_form_kwargs())

    def form_valid(self, form):
        messages.success(self.request, 'Budget created.')
        return super().form_valid(form)


class BudgetUpdateView(FinanceAuditMixin, FinanceUserMixin, UpdateView):
    """Edit a budget."""

    model = Budget
    template_name = 'finance/budget_form.html'
    success_url = reverse_lazy('finance:budget_list')
    audit_entity_type = 'budget'

    def get_form(self, form_class=None):
        return BudgetForm(self.request.user, **self.get_form_kwargs())

    def form_valid(self, form):
        messages.success(self.request, 'Budget updated.')
        return super().form_valid(form)


class BudgetDeleteView(FinanceAuditMixin, FinanceUserMixin, DeleteView):
    """Delete a budget."""

    model = Budget
    template_name = 'finance/budget_confirm_delete.html'
    success_url = reverse_lazy('finance:budget_list')
    audit_entity_type = 'budget'

    def form_valid(self, form):
        audit_logger = self.get_audit_logger()
        audit_logger.log(
            action='delete',
            entity_type='budget',
            entity_id=self.object.id,
        )
        self.object.soft_delete()
        messages.success(self.request, 'Budget deleted.')
        return redirect(self.success_url)


# =============================================================================
# Financial Goals
# =============================================================================

class GoalListView(FinanceUserMixin, ListView):
    """List financial goals."""

    model = FinancialGoal
    template_name = 'finance/goal_list.html'
    context_object_name = 'goals'

    def get_queryset(self):
        return super().get_queryset().order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        goals = context['goals']

        context['active_goals'] = [g for g in goals if g.goal_status == 'active']
        context['completed_goals'] = [g for g in goals if g.goal_status == 'completed']
        context['paused_goals'] = [g for g in goals if g.goal_status == 'paused']

        return context


class GoalDetailView(FinanceUserMixin, DetailView):
    """View goal details."""

    model = FinancialGoal
    template_name = 'finance/goal_detail.html'
    context_object_name = 'goal'


class GoalCreateView(FinanceAuditMixin, LoginRequiredMixin, CreateView):
    """Create a new financial goal."""

    model = FinancialGoal
    template_name = 'finance/goal_form.html'
    success_url = reverse_lazy('finance:goal_list')
    audit_entity_type = 'goal'

    def get_form(self, form_class=None):
        return FinancialGoalForm(self.request.user, **self.get_form_kwargs())

    def form_valid(self, form):
        # The user's own date, not the server's. `started_at` defaults to the project
        # timezone; a user in New York creating a goal at 21:45 would otherwise be
        # told it started tomorrow.
        if not form.cleaned_data.get('started_at'):
            form.instance.started_at = get_user_today(self.request.user)
        messages.success(self.request, f'Goal "{form.instance.name}" created.')
        response = super().form_valid(form)
        if self.object.linked_account_id:
            self.get_audit_logger().log(
                action='update', entity_type='goal', entity_id=self.object.pk,
                details={'field': 'linked_account', 'from_account_id': None,
                         'to_account_id': self.object.linked_account_id,
                         'to_account': self.object.linked_account.name})
        return response


class GoalUpdateView(FinanceAuditMixin, FinanceUserMixin, UpdateView):
    """Edit a financial goal."""

    model = FinancialGoal
    template_name = 'finance/goal_form.html'
    success_url = reverse_lazy('finance:goal_list')
    audit_entity_type = 'goal'

    def get_form(self, form_class=None):
        return FinancialGoalForm(self.request.user, **self.get_form_kwargs())

    def form_valid(self, form):
        # Audit the LINK DECISION only. The balance itself is derived live and read
        # on every page render, so auditing "the balance was looked at" would bury
        # the one event that matters — a person changing where the money comes from.
        previous_id = None
        if self.object and self.object.pk:
            previous_id = (FinancialGoal.objects.filter(pk=self.object.pk)
                           .values_list('linked_account_id', flat=True).first())

        messages.success(self.request, f'Goal "{form.instance.name}" updated.')
        response = super().form_valid(form)

        if previous_id != self.object.linked_account_id:
            self.get_audit_logger().log(
                action='update', entity_type='goal', entity_id=self.object.pk,
                details={'field': 'linked_account',
                         'from_account_id': previous_id,
                         'to_account_id': self.object.linked_account_id,
                         'to_account': (self.object.linked_account.name
                                        if self.object.linked_account_id else None)})
        return response


class GoalDeleteView(FinanceAuditMixin, FinanceUserMixin, DeleteView):
    """Delete a financial goal."""

    model = FinancialGoal
    template_name = 'finance/goal_confirm_delete.html'
    success_url = reverse_lazy('finance:goal_list')
    audit_entity_type = 'goal'

    def form_valid(self, form):
        audit_logger = self.get_audit_logger()
        audit_logger.log(
            action='delete',
            entity_type='goal',
            entity_id=self.object.id,
            details={'name': self.object.name}
        )
        self.object.soft_delete()
        messages.success(self.request, f'Goal "{self.object.name}" deleted.')
        return redirect(self.success_url)


@login_required
def goal_update_progress(request, pk):
    """Update goal progress."""
    goal = get_object_or_404(
        FinancialGoal, pk=pk, user=request.user, status='active'
    )

    if request.method == 'POST':
        # The template hides this form for an account-funded goal; refusing here too
        # is what actually protects the invariant, since a hidden field is not a
        # closed door.
        if goal.is_account_funded:
            messages.error(
                request,
                f'"{goal.name}" is funded by {goal.linked_account.name}, so its '
                f'balance comes from that account. Unlink it to track progress by hand.')
            return redirect('finance:goal_detail', pk=pk)

        try:
            new_amount = Decimal(request.POST.get('current_amount', '0'))
            goal.current_amount = new_amount
            if goal.current_amount >= goal.target_amount:
                goal.mark_completed()
                messages.success(request, f'Congratulations! Goal "{goal.name}" completed!')
            else:
                goal.save(update_fields=['current_amount', 'updated_at'])
                messages.success(request, 'Goal progress updated.')
        except (ValueError, TypeError, InvalidOperation):
            messages.error(request, 'Invalid amount.')

    return redirect('finance:goal_detail', pk=pk)


# =============================================================================
# Metrics & Reports
# =============================================================================

class MetricsDashboardView(LoginRequiredMixin, TemplateView):
    """Financial metrics and reports dashboard."""

    template_name = 'finance/metrics_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = get_user_today(user)

        # Get or create today's snapshot
        snapshot = FinancialMetricSnapshot.create_snapshot(user, today)
        context['current_snapshot'] = snapshot

        # Get historical snapshots for trend
        context['snapshots'] = FinancialMetricSnapshot.objects.filter(
            user=user, status='active'
        ).order_by('-snapshot_date')[:30]

        # Net worth trend data for chart
        net_worth_data = list(
            FinancialMetricSnapshot.objects.filter(
                user=user, status='active'
            ).order_by('snapshot_date').values('snapshot_date', 'net_worth')[:12]
        )
        context['net_worth_data'] = net_worth_data

        return context


@login_required
def refresh_metrics(request):
    """Refresh financial metrics snapshot."""
    user = request.user
    today = get_user_today(user)

    FinancialMetricSnapshot.create_snapshot(user, today)
    messages.success(request, 'Financial metrics refreshed.')

    return redirect('finance:metrics')


# =============================================================================
# Categories
# =============================================================================

class CategoryListView(LoginRequiredMixin, ListView):
    """List and manage transaction categories."""

    model = TransactionCategory
    template_name = 'finance/category_list.html'
    context_object_name = 'categories'

    def get_queryset(self):
        return TransactionCategory.get_for_user(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        categories = context['categories']

        context['income_categories'] = [
            c for c in categories if c.category_type == 'income'
        ]
        context['expense_categories'] = [
            c for c in categories if c.category_type == 'expense'
        ]

        return context


# =============================================================================
# API Endpoints
# =============================================================================

@login_required
def api_payee_suggestions(request):
    """Return payee suggestions for autocomplete."""
    query = request.GET.get('q', '')
    if len(query) < 2:
        return JsonResponse({'payees': []})

    payees = Payee.objects.filter(
        user=request.user,
        status='active',
        name__icontains=query
    ).order_by('-use_count')[:10]

    return JsonResponse({
        'payees': [
            {
                'name': p.name,
                'category_id': p.default_category_id if p.default_category else None
            }
            for p in payees
        ]
    })


@login_required
def api_account_balance(request, pk):
    """Return current balance for an account."""
    account = get_object_or_404(
        FinancialAccount, pk=pk, user=request.user, status='active'
    )

    return JsonResponse({
        'balance': float(account.current_balance),
        'formatted': f'${account.current_balance:,.2f}',
        'updated_at': account.balance_updated_at.isoformat() if account.balance_updated_at else None
    })


# =============================================================================
# Transaction Import
# =============================================================================

class ImportListView(FinanceUserMixin, ListView):
    """List all transaction imports for the user."""

    model = TransactionImport
    template_name = 'finance/import_list.html'
    context_object_name = 'imports'
    paginate_by = 20

    def get_queryset(self):
        return super().get_queryset().select_related('account').order_by('-created_at')


class ImportDetailView(FinanceUserMixin, DetailView):
    """View import details and results."""

    model = TransactionImport
    template_name = 'finance/import_detail.html'
    context_object_name = 'import_record'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get transactions created by this import
        context['transactions'] = Transaction.objects.filter(
            user=self.request.user,
            import_record=self.object,
            status='active'
        ).select_related('category').order_by('-date')[:50]
        return context


@login_required
def import_upload_view(request):
    """
    Handle transaction file upload and processing.

    Security: Files are processed in memory and NOT stored permanently.
    Transaction files contain sensitive financial data, so we:
    1. Read the file content directly from the upload
    2. Process and create transactions
    3. Never save the file to disk/cloud storage
    4. Only keep metadata (filename, row counts) for audit trail
    """
    if request.method == 'POST':
        form = TransactionImportForm(request.user, request.POST, request.FILES)
        if form.is_valid():
            # Get file data BEFORE creating record (don't save file to storage)
            uploaded_file = form.cleaned_data['file']
            file_content = uploaded_file.read()
            original_filename = uploaded_file.name
            file_size = uploaded_file.size

            # Detect file type
            filename_lower = original_filename.lower()
            if filename_lower.endswith('.csv'):
                file_type = 'csv'
            elif filename_lower.endswith('.ofx'):
                file_type = 'ofx'
            elif filename_lower.endswith('.qfx'):
                file_type = 'qfx'
            elif filename_lower.endswith('.qif'):
                file_type = 'qif'
            else:
                file_type = 'csv'

            # Create import record WITHOUT the file (security best practice)
            import_record = TransactionImport.objects.create(
                user=request.user,
                account=form.cleaned_data['account'],
                original_filename=original_filename,
                file_type=file_type,
                file_size=file_size,
                notes=form.cleaned_data.get('notes', ''),
                # file field intentionally left empty - we don't store the file
            )

            # Process the file in memory
            try:
                from .import_service import TransactionImportService

                # Initialize service
                service = TransactionImportService(
                    user=request.user,
                    account=import_record.account
                )

                # Mark as processing
                import_record.mark_processing()

                # Parse file from memory
                parsed = service.parse_file(file_content, file_type)
                import_record.rows_total = len(parsed)
                import_record.save(update_fields=['rows_total'])

                # Create transactions
                results = service.create_transactions(parsed, import_record)

                # Update import record with results
                import_record.mark_completed(
                    rows_imported=results['imported'],
                    rows_skipped=results['skipped'],
                    rows_failed=results['failed']
                )

                if results['errors']:
                    import_record.error_details = results['errors']
                    import_record.save(update_fields=['error_details'])

                # Show success message
                if results['imported'] > 0:
                    messages.success(
                        request,
                        f"Successfully imported {results['imported']} transactions."
                    )
                if results['skipped'] > 0:
                    messages.info(
                        request,
                        f"Skipped {results['skipped']} duplicate transactions."
                    )
                if results['failed'] > 0:
                    messages.warning(
                        request,
                        f"Failed to import {results['failed']} transactions. "
                        "See import details for more information."
                    )

                return redirect('finance:import_detail', pk=import_record.pk)

            except Exception as e:
                logger.error(f"Import failed for user {request.user.id}: {e}")
                import_record.mark_failed(str(e))
                messages.error(request, f"Import failed: {e}")
                return redirect('finance:import_detail', pk=import_record.pk)
    else:
        form = TransactionImportForm(request.user)

    # Get recent imports
    recent_imports = TransactionImport.objects.filter(
        user=request.user, status='active'
    ).select_related('account')[:5]

    return render(request, 'finance/import_form.html', {
        'form': form,
        'recent_imports': recent_imports
    })


# =============================================================================
# Bank Connections (Plaid Integration)
# =============================================================================

class BankConnectionListView(LoginRequiredMixin, ListView):
    """List user's connected bank accounts."""

    model = BankConnection
    template_name = 'finance/bank_connection_list.html'
    context_object_name = 'connections'

    def get_queryset(self):
        return BankConnection.objects.filter(
            user=self.request.user
        ).exclude(
            connection_status=BankConnection.STATUS_DISCONNECTED
        ).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Check if Plaid is configured
        from apps.finance.services.plaid_service import PlaidService
        plaid = PlaidService()
        context['plaid_configured'] = plaid.is_configured

        # Count accounts needing attention
        context['needs_attention_count'] = self.get_queryset().filter(
            connection_status__in=[
                BankConnection.STATUS_ERROR,
                BankConnection.STATUS_REAUTH_REQUIRED
            ]
        ).count()

        return context


@login_required
@finance_enabled_required
@requires_recent_auth(15)
@finance_rate_limit('bank_connect')
def bank_connection_start(request):
    """
    Start bank connection flow - generate Plaid Link token.

    Returns JSON with link_token for Plaid Link UI.
    """
    from apps.finance.services.plaid_service import (
        PlaidEnvironmentError,
        PlaidNotConfiguredError,
        get_plaid_service,
    )
    from apps.finance.services.provider_diagnostics import (
        classify_provider_failure,
        safe_provider_diagnostics,
    )

    try:
        plaid = get_plaid_service()
        result = plaid.create_link_token(request.user, request)

        # When OAuth is configured the browser will leave WLJ entirely and come back to
        # /finance/plaid/oauth/, where Plaid requires the SAME Link token. Bind the
        # attempt to this user and session so the return can be trusted.
        from django.conf import settings as django_settings

        from apps.finance.services import plaid_oauth

        if (getattr(django_settings, 'PLAID_REDIRECT_URI', '') or '').strip():
            plaid_oauth.begin(request, link_token=result['link_token'])

        return JsonResponse({
            'success': True,
            'link_token': result['link_token'],
        })

    except PlaidNotConfiguredError as e:
        logger.warning("Plaid not configured: %s", type(e).__name__)
        return JsonResponse({
            'success': False,
            'error': 'Bank connection is not set up yet. Please contact support.'
        }, status=503)

    except PlaidEnvironmentError as e:
        # Configuration is wrong in a way support can actually fix — say so plainly
        # instead of inviting the user to retry something that cannot succeed.
        logger.error("Plaid environment misconfigured: %s", e)
        return JsonResponse({
            'success': False,
            'error': ('Bank connection is misconfigured on our side. Retrying will not '
                      'help — please contact support.'),
            'retryable': False,
        }, status=503)

    except Exception as e:
        diagnostics = safe_provider_diagnostics(e)
        message, retryable = classify_provider_failure(diagnostics)
        logger.error("Error creating link token: %s", diagnostics, exc_info=True)
        return JsonResponse({
            'success': False,
            'error': message,
            'retryable': retryable,
            # Safe fields only — type/code/request id. The internal exception class
            # name stays in the LOG; the client gets provider facts, nothing about our
            # call stack.
            'provider': {k: v for k, v in diagnostics.items() if k != 'exception'},
        }, status=502 if retryable else 503)


@login_required
@finance_enabled_required
@requires_recent_auth(15)
@finance_rate_limit('bank_connect')
@require_POST
def bank_connection_complete(request):
    """
    Complete bank connection - exchange public token for access token.

    Expects JSON body with:
        - public_token: From Plaid Link
        - metadata: Institution info from Plaid Link
    """
    from apps.finance.services.plaid_service import get_plaid_service
    from apps.finance.services.sync_service import TransactionSyncService

    try:
        data = json.loads(request.body)
        public_token = data.get('public_token')
        metadata = data.get('metadata', {})

        if not public_token:
            return JsonResponse({
                'success': False,
                'error': 'Missing public_token'
            }, status=400)

        # An OAuth attempt ends here. Mark it used BEFORE the exchange so a replayed
        # return cannot ride the same state through a second time.
        from apps.finance.services import plaid_oauth
        plaid_oauth.consume(request)

        plaid = get_plaid_service()

        # Exchange token
        exchange_result = plaid.exchange_public_token(public_token)
        access_token = exchange_result['access_token']
        item_id = exchange_result['item_id']

        # Get institution info
        institution_id = metadata.get('institution', {}).get('institution_id', '')
        institution_name = metadata.get('institution', {}).get('name', 'Unknown Bank')

        # Check if connection already exists
        existing = BankConnection.objects.filter(
            user=request.user,
            item_id=item_id
        ).first()

        if existing:
            # Update existing connection
            existing.set_access_token(access_token)
            existing.mark_active()
            connection = existing
            logger.info(f"Updated existing bank connection: {connection}")
        else:
            # Create new connection
            connection = BankConnection.objects.create(
                user=request.user,
                item_id=item_id,
                institution_id=institution_id,
                institution_name=institution_name,
                connection_status=BankConnection.STATUS_PENDING,
                consent_ip_address=get_client_ip(request),
            )
            connection.set_access_token(access_token)
            # Record the window we asked for, so coverage can be judged honestly later.
            from apps.finance.services.plaid_service import (
                TRANSACTION_HISTORY_DAYS_REQUESTED,
            )
            connection.history_days_requested = TRANSACTION_HISTORY_DAYS_REQUESTED
            connection.save()
            logger.info("Created new bank connection %s", connection.pk)

        # The attempt is finished; nothing should survive it.
        plaid_oauth.clear(request)

        # Log the connection
        BankIntegrationLog.objects.create(
            user=request.user,
            bank_connection=connection,
            action=BankIntegrationLog.ACTION_CONNECT,
            success=True,
            details={'institution': institution_name},
            ip_address=get_client_ip(request),
        )

        # Start initial sync in background (or inline for now)
        try:
            sync_service = TransactionSyncService(connection)
            sync_result = sync_service.sync(trigger="link")
            logger.info(f"Initial sync completed: {sync_result}")
        except Exception as e:
            logger.error(f"Initial sync failed: {e}")
            # Don't fail the connection for sync errors

        return JsonResponse({
            'success': True,
            'connection_id': connection.id,
            'institution_name': connection.institution_name,
            'message': f'Successfully connected to {connection.institution_name}'
        })

    except Exception as e:
        logger.error(f"Error completing bank connection: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@finance_enabled_required
def plaid_oauth_return(request):
    """Where an OAuth bank sends the user back. Resumes Link with the SAME token.

    Deliberately NOT behind `requires_recent_auth`: the user has been at their bank for
    however long that took, and the recency proof for this flow is the bound OAuth state
    — created moments after a password confirmation, tied to this user and session,
    single-use, and expiring in 30 minutes. Re-challenging here would strand people who
    took too long at their bank, which is a loop, not a control.

    The Link token is handed to the page for exactly one purpose — re-initialising Link —
    and is never logged, stored in the browser, or placed in a URL.
    """
    from apps.finance.services import plaid_oauth

    context = {
        'connections_url': reverse('finance:connection_list'),
        'complete_url': reverse('finance:connection_complete'),
        'link_token': '',
        'state_error': '',
    }
    try:
        context['link_token'] = plaid_oauth.resolve(request)
    except plaid_oauth.OAuthStateError as exc:
        reason = str(exc)
        context['state_error'] = plaid_oauth.message_for(reason)
        logger.warning("Plaid OAuth return refused: %s", reason)

    return render(request, 'finance/plaid_oauth_return.html', context)


@login_required
@finance_enabled_required
@require_POST
def plaid_oauth_abandon(request):
    """The user backed out of the bank flow. Drop the attempt; connect nothing."""
    from apps.finance.services import plaid_oauth

    plaid_oauth.clear(request)
    return JsonResponse({'success': True})


@login_required
@finance_enabled_required
@requires_recent_auth(15)
@finance_rate_limit('bank_connect')
def bank_connection_reauth(request, pk):
    """
    Start re-authentication flow for a bank connection.

    Returns JSON with link_token for Plaid Link update mode.
    """
    from apps.finance.services.plaid_service import get_plaid_service

    connection = get_object_or_404(
        BankConnection, pk=pk, user=request.user
    )

    try:
        plaid = get_plaid_service()
        access_token = connection.get_access_token()

        if not access_token:
            return JsonResponse({
                'success': False,
                'error': 'Connection token not found'
            }, status=400)

        result = plaid.create_link_token_for_update(request.user, access_token)

        return JsonResponse({
            'success': True,
            'link_token': result['link_token'],
        })

    except Exception as e:
        logger.error(f"Error creating reauth link token: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to start re-authentication. Please try again.'
        }, status=500)


@login_required
@finance_enabled_required
@requires_recent_auth(15)
@finance_rate_limit('bank_disconnect')
@require_POST
def bank_connection_disconnect(request, pk):
    """
    Disconnect a bank connection.

    Revokes Plaid access and marks connection as disconnected.
    """
    from apps.finance.services.plaid_service import get_plaid_service

    connection = get_object_or_404(
        BankConnection, pk=pk, user=request.user
    )

    from apps.finance.services.provider_disconnect import (
        RevocationFailed,
        revoke_and_disconnect,
    )

    try:
        # ONE path: revoke at the provider FIRST, and only then forget the credential.
        revoke_and_disconnect(connection, ip_address=get_client_ip(request))
    except RevocationFailed as exc:
        # Never claim success while provider access may still be live.
        return JsonResponse({
            'success': False,
            'status': connection.connection_status,
            'error': str(exc),
            'retry_available': True,
        }, status=502)

    try:
        messages.success(request, f'{connection.institution_name} has been disconnected.')

        return JsonResponse({
            'success': True,
            'message': f'{connection.institution_name} disconnected'
        })

    except Exception as e:
        logger.error(f"Error disconnecting bank: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@finance_enabled_required
@requires_recent_auth(15)
@finance_rate_limit('bank_sync')
@require_POST
def bank_connection_sync(request, pk):
    """
    Manually trigger a sync for a bank connection.
    """
    from apps.finance.services.sync_service import TransactionSyncService

    connection = get_object_or_404(
        BankConnection, pk=pk, user=request.user
    )

    if connection.connection_status != BankConnection.STATUS_ACTIVE:
        return JsonResponse({
            'success': False,
            'error': 'Connection is not active'
        }, status=400)

    try:
        sync_service = TransactionSyncService(connection)
        result = sync_service.sync(trigger="manual")

        return JsonResponse({
            'success': True,
            'added': result.get('added', 0),
            'modified': result.get('modified', 0),
            'removed': result.get('removed', 0),
            'message': f"Synced {result.get('added', 0)} new transactions"
        })

    except Exception as e:
        logger.error(f"Sync failed: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def verify_plaid_webhook(request):
    """Verify a Plaid webhook cryptographically. Fails CLOSED.

    Delegates to `plaid_webhook_verification.verify_webhook`, which pins ES256, fetches
    Plaid's JWK by `kid`, verifies the signature, checks the timestamp window and body
    hash, and rejects replays. Returns the legacy `(is_valid, error)` shape so the
    existing view is unchanged; the error is a reason CODE, never payload content.
    """
    from apps.finance.services.plaid_webhook_verification import verify_webhook

    result = verify_webhook(request)
    return bool(result), (None if result else result.reason)


def _record_webhook_rejection(request, reason):
    """Make a REFUSED delivery visible without trusting its contents.

    Nothing here acts on the payload — it is used only to find a connection we
    already know about. If the item_id is absent or unrecognised, we record nothing,
    so an unauthenticated caller cannot write rows or grow the table. Two fields are
    overwritten in place; no history accumulates.

    Why this exists: rejected webhooks previously left no durable trace at all, so an
    operator reading "0 webhook records" could reasonably — and wrongly — conclude the
    provider had never called.
    """
    try:
        item_id = json.loads(request.body or b"{}").get('item_id')
        if not item_id:
            return
        updated = BankConnection.objects.filter(item_id=item_id).update(
            last_webhook_rejected_at=timezone.now(),
            last_webhook_rejection_reason=(reason or "")[:64],
        )
        if updated:
            logger.warning("Plaid webhook REJECTED for a known connection (%s). "
                           "The provider is calling us and we are refusing it.", reason)
    except Exception:                       # observability must never break the response
        logger.warning("Could not record Plaid webhook rejection", exc_info=True)


#: Webhook codes that mean "new transaction state is waiting at the provider".
#: `/transactions/sync` reconciles from its durable cursor, so the correct response to
#: every one of these is the same ordinary incremental sync.
#:
#: The legacy INITIAL_UPDATE / HISTORICAL_UPDATE pair is deliberately NOT here. Plaid
#: sends them to this sync integration ALONGSIDE SYNC_UPDATES_AVAILABLE, about 20ms
#: apart — observed repeatedly on 2026-08-27 (00:07:30.954/.972, 00:08:11.027/.055,
#: 00:10:21.063/.120). Triggering on both meant every provider notification launched
#: TWO concurrent inline syncs, which raced into 1,677 duplicate rows and tripped
#: Plaid's TRANSACTIONS_SYNC_LIMIT four times. They still update completion flags
#: below; they just no longer double the work. Fetching stays driven by the
#: sync-integration codes alone.
SYNC_TRIGGERING_WEBHOOK_CODES = frozenset({
    'SYNC_UPDATES_AVAILABLE',   # the sync integration's primary signal
    'DEFAULT_UPDATE',           # ongoing new transactions
    'TRANSACTIONS_REMOVED',     # removals are delivered through sync's `removed`
})


@csrf_exempt
@require_POST
def plaid_webhook(request):
    """
    Handle Plaid webhooks for real-time updates.

    Plaid sends webhooks for:
    - TRANSACTIONS: New/updated transactions available
    - ITEM: Connection status changes

    Security: Webhook signature is verified before processing.
    """
    # Verify webhook signature
    is_valid, error = verify_plaid_webhook(request)
    if not is_valid:
        logger.warning(f"Plaid webhook verification failed: {error}")
        _record_webhook_rejection(request, error)
        return JsonResponse({'status': 'unauthorized', 'error': error}, status=401)

    try:
        data = json.loads(request.body)
        webhook_type = data.get('webhook_type')
        webhook_code = data.get('webhook_code')
        item_id = data.get('item_id')

        # Redacted: the webhook TYPE is operational signal; the provider item id is not
        # logged in full (it identifies a specific bank connection).
        logger.info("Plaid webhook: %s/%s for item %s…",
                    webhook_type, webhook_code, (item_id or "")[:6])

        # Find the connection
        connection = BankConnection.objects.filter(item_id=item_id).first()
        if not connection:
            logger.warning(f"No connection found for item_id: {item_id}")
            return JsonResponse({'status': 'ignored'})

        # Log the webhook
        BankIntegrationLog.objects.create(
            user=connection.user,
            bank_connection=connection,
            action=BankIntegrationLog.ACTION_WEBHOOK,
            success=True,
            details={
                'webhook_type': webhook_type,
                'webhook_code': webhook_code,
            },
        )

        # Handle different webhook types
        if webhook_type == 'TRANSACTIONS':
            # Record coverage milestones so partial history is never shown as complete.
            #
            # WLJ ingests through /transactions/sync, and for a sync integration Plaid
            # sends SYNC_UPDATES_AVAILABLE carrying the two milestones as BOOLEAN
            # FIELDS. It does NOT send the legacy INITIAL_UPDATE / HISTORICAL_UPDATE
            # codes — those belong to the /transactions/get flow. Keying the flags on
            # the legacy codes alone meant they could never be set for our integration,
            # so history was permanently reported as "still running".
            initial_done = historical_done = False
            if webhook_code == 'SYNC_UPDATES_AVAILABLE':
                initial_done = bool(data.get('initial_update_complete'))
                historical_done = bool(data.get('historical_update_complete'))
            elif webhook_code == 'INITIAL_UPDATE':          # legacy /transactions/get
                initial_done = True
            elif webhook_code == 'HISTORICAL_UPDATE':       # legacy /transactions/get
                initial_done = historical_done = True

            # Only ever advance. A later webhook reporting historical_update_complete
            # as false must not un-complete a connection that already finished.
            changed = []
            if initial_done and not connection.initial_update_complete:
                connection.initial_update_complete = True
                changed.append('initial_update_complete')
            if historical_done and not connection.historical_update_complete:
                connection.initial_update_complete = True
                connection.historical_update_complete = True
                connection.historical_update_at = timezone.now()
                changed += ['initial_update_complete', 'historical_update_complete',
                            'historical_update_at']
            if changed:
                connection.save(update_fields=sorted(set(changed)) + ['updated_at'])

            # Every code that means "there is something to pull". A
            # /transactions/sync integration receives SYNC_UPDATES_AVAILABLE,
            # DEFAULT_UPDATE and TRANSACTIONS_REMOVED; the INITIAL_/HISTORICAL_
            # pair is the legacy /transactions/get flow, kept for safety.
            # DEFAULT_UPDATE was missing, and there is NO scheduled sync task —
            # webhooks are the only ongoing ingestion path, so omitting it meant
            # no new transaction would ever arrive on its own after the backfill.
            if webhook_code in SYNC_TRIGGERING_WEBHOOK_CODES:
                # Trigger sync
                from apps.finance.services.sync_service import TransactionSyncService
                sync_service = TransactionSyncService(connection)
                sync_service.sync(trigger="webhook")

        elif webhook_type == 'ITEM':
            if webhook_code == 'ERROR':
                error = data.get('error', {})
                connection.mark_error(
                    error.get('error_code', 'UNKNOWN'),
                    error.get('error_message', 'Unknown error')
                )
            elif webhook_code == 'LOGIN_REQUIRED':
                connection.mark_reauth_required()
            elif webhook_code == 'PENDING_EXPIRATION':
                connection.mark_reauth_required()

        return JsonResponse({'status': 'processed'})

    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


def get_client_ip(request) -> str:
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


# =============================================================================
# Bulk Delete Views
# =============================================================================

class BulkDeleteTransactionsView(LoginRequiredMixin, View):
    """Bulk delete transactions."""

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if not ids:
            return JsonResponse({'success': False, 'error': 'No items selected'}, status=400)

        entries = Transaction.objects.filter(user=request.user, pk__in=ids)
        count = entries.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'No entries found'}, status=404)

        for entry in entries:
            entry.soft_delete()

        return JsonResponse({
            'success': True,
            'message': f'{count} transaction{"" if count == 1 else "s"} deleted',
            'count': count
        })


# =============================================================================
# Recurring Transactions
# =============================================================================

class RecurringTransactionListView(FinanceUserMixin, ListView):
    """List all recurring transactions."""

    model = RecurringTransaction
    template_name = 'finance/recurring_list.html'
    context_object_name = 'recurring_transactions'

    def get_queryset(self):
        queryset = super().get_queryset().select_related('account', 'category')
        # Filter by status if provided
        status_filter = self.request.GET.get('status')
        if status_filter == 'active':
            queryset = queryset.filter(is_active=True)
        elif status_filter == 'inactive':
            queryset = queryset.filter(is_active=False)
        return queryset.order_by('next_due_date', 'name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = get_user_today(user)

        recurring = context['recurring_transactions']

        # Categorize by income/expense
        context['income_recurring'] = [r for r in recurring if r.is_income and r.is_active]
        context['expense_recurring'] = [r for r in recurring if r.is_expense and r.is_active]
        context['inactive_recurring'] = [r for r in recurring if not r.is_active]

        # Calculate totals
        monthly_income = sum(
            r.amount for r in recurring
            if r.is_income and r.is_active and r.frequency == 'monthly'
        )
        monthly_expenses = sum(
            r.amount for r in recurring
            if r.is_expense and r.is_active and r.frequency == 'monthly'
        )

        context['monthly_recurring_income'] = monthly_income
        context['monthly_recurring_expenses'] = monthly_expenses
        context['monthly_recurring_net'] = monthly_income - monthly_expenses

        # Upcoming this week
        from datetime import timedelta
        week_end = today + timedelta(days=7)
        context['upcoming_this_week'] = [
            r for r in recurring
            if r.is_active and r.next_due_date <= week_end
        ]

        # Status filter
        context['current_status'] = self.request.GET.get('status', '')

        return context


class RecurringTransactionDetailView(FinanceUserMixin, DetailView):
    """View recurring transaction details."""

    model = RecurringTransaction
    template_name = 'finance/recurring_detail.html'
    context_object_name = 'recurring'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        recurring = self.object

        # Get upcoming occurrences
        context['upcoming_dates'] = recurring.get_upcoming_occurrences(count=10)

        # Get generated transactions
        context['generated_transactions'] = Transaction.objects.filter(
            user=self.request.user,
            description=recurring.name,
            is_recurring=True,
            status='active'
        ).order_by('-date')[:20]

        return context


class RecurringTransactionCreateView(FinanceAuditMixin, LoginRequiredMixin, CreateView):
    """Create a new recurring transaction."""

    model = RecurringTransaction
    template_name = 'finance/recurring_form.html'
    success_url = reverse_lazy('finance:recurring_list')
    audit_entity_type = 'recurring_transaction'

    def get_form(self, form_class=None):
        return RecurringTransactionForm(self.request.user, **self.get_form_kwargs())

    def form_valid(self, form):
        messages.success(self.request, f'Recurring transaction "{form.instance.name}" created.')
        return super().form_valid(form)


class RecurringTransactionUpdateView(FinanceAuditMixin, FinanceUserMixin, UpdateView):
    """Edit a recurring transaction."""

    model = RecurringTransaction
    template_name = 'finance/recurring_form.html'
    success_url = reverse_lazy('finance:recurring_list')
    audit_entity_type = 'recurring_transaction'

    def get_form(self, form_class=None):
        return RecurringTransactionForm(self.request.user, **self.get_form_kwargs())

    def form_valid(self, form):
        messages.success(self.request, f'Recurring transaction "{form.instance.name}" updated.')
        return super().form_valid(form)


class RecurringTransactionDeleteView(FinanceAuditMixin, FinanceUserMixin, DeleteView):
    """Delete (soft delete) a recurring transaction."""

    model = RecurringTransaction
    template_name = 'finance/recurring_confirm_delete.html'
    success_url = reverse_lazy('finance:recurring_list')
    audit_entity_type = 'recurring_transaction'

    def form_valid(self, form):
        self.object.soft_delete()
        messages.success(self.request, f'Recurring transaction "{self.object.name}" deleted.')
        return redirect(self.success_url)


@login_required
@require_POST
def recurring_post_now(request, pk):
    """Manually post a recurring transaction now."""
    recurring = get_object_or_404(
        RecurringTransaction, pk=pk, user=request.user, status='active'
    )

    try:
        from .services.recurring import RecurringTransactionService

        transaction = RecurringTransactionService.post_now(recurring)

        messages.success(
            request,
            f'Posted "{recurring.name}" - ${abs(transaction.amount):,.2f}'
        )

        return JsonResponse({
            'success': True,
            'transaction_id': transaction.id,
            'next_due_date': recurring.next_due_date.isoformat() if recurring.next_due_date else None,
        })

    except Exception as e:
        logger.error(f"Error posting recurring transaction: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_POST
def recurring_skip(request, pk):
    """Skip the next occurrence of a recurring transaction."""
    recurring = get_object_or_404(
        RecurringTransaction, pk=pk, user=request.user, status='active'
    )

    try:
        from .services.recurring import RecurringTransactionService

        new_date = RecurringTransactionService.skip_occurrence(recurring)

        if new_date:
            messages.success(
                request,
                f'Skipped occurrence. Next due: {new_date.strftime("%b %d, %Y")}'
            )
            return JsonResponse({
                'success': True,
                'next_due_date': new_date.isoformat(),
            })
        else:
            messages.info(request, f'No more occurrences for "{recurring.name}".')
            return JsonResponse({
                'success': True,
                'next_due_date': None,
                'deactivated': True,
            })

    except Exception as e:
        logger.error(f"Error skipping recurring transaction: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_POST
def recurring_toggle_active(request, pk):
    """Toggle the active status of a recurring transaction."""
    recurring = get_object_or_404(
        RecurringTransaction, pk=pk, user=request.user, status='active'
    )

    recurring.is_active = not recurring.is_active
    recurring.save(update_fields=['is_active', 'updated_at'])

    status = 'activated' if recurring.is_active else 'paused'
    messages.success(request, f'Recurring transaction "{recurring.name}" {status}.')

    return JsonResponse({
        'success': True,
        'is_active': recurring.is_active,
    })


@login_required
def api_upcoming_recurring(request):
    """Get upcoming recurring transactions for dashboard widget."""
    from .services.recurring import RecurringTransactionService

    days_ahead = int(request.GET.get('days', 14))

    upcoming = RecurringTransactionService.get_upcoming_transactions(
        request.user, days_ahead=days_ahead
    )

    return JsonResponse({
        'success': True,
        'upcoming': [
            {
                'id': item['recurring'].id,
                'name': item['recurring'].name,
                'amount': float(item['amount']),
                'signed_amount': float(item['signed_amount']),
                'is_expense': item['is_expense'],
                'is_income': item['is_income'],
                'next_due_date': item['next_due_date'].isoformat(),
                'days_until': item['days_until'],
                'is_overdue': item['is_overdue'],
                'is_due_today': item['is_due_today'],
                'account_name': item['recurring'].account.name,
                'category_name': item['recurring'].category.name if item['recurring'].category else None,
            }
            for item in upcoming
        ],
        'count': len(upcoming),
    })
