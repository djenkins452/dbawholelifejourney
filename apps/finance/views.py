# ==============================================================================
# File: apps/finance/views.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Finance module views for accounts, transactions, budgets, goals,
#              and file imports
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-02
# Last Updated: 2026-01-03
# ==============================================================================
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum, Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
)

from apps.core.utils import get_user_today

from .models import (
    FinancialAccount,
    TransactionCategory,
    Transaction,
    Budget,
    FinancialGoal,
    FinancialMetricSnapshot,
    Payee,
    TransactionImport,
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
)


# =============================================================================
# Mixins
# =============================================================================

class FinanceUserMixin(LoginRequiredMixin):
    """Mixin for finance views that filters by current user."""

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user, status='active')


# =============================================================================
# Dashboard / Home
# =============================================================================

class FinanceDashboardView(LoginRequiredMixin, TemplateView):
    """Main finance dashboard with overview of all financial data."""

    template_name = 'finance/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = get_user_today(user)
        month_start = today.replace(day=1)

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

        # Monthly summary
        monthly_income = Transaction.objects.filter(
            user=user,
            status='active',
            date__gte=month_start,
            date__lte=today,
            amount__gt=0,
            is_opening_balance=False
        ).exclude(transfer_pair__isnull=False).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')

        monthly_expenses = abs(Transaction.objects.filter(
            user=user,
            status='active',
            date__gte=month_start,
            date__lte=today,
            amount__lt=0,
            is_opening_balance=False
        ).exclude(transfer_pair__isnull=False).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00'))

        context['monthly_income'] = monthly_income
        context['monthly_expenses'] = monthly_expenses
        context['monthly_cash_flow'] = monthly_income - monthly_expenses

        # Budget summary
        budgets = Budget.objects.filter(
            user=user, status='active', month=month_start
        ).select_related('category')
        context['budgets'] = budgets
        context['budgets_over'] = [b for b in budgets if b.status == 'over']

        # Active goals
        context['active_goals'] = FinancialGoal.objects.filter(
            user=user, status='active', goal_status='active'
        )[:5]

        # Quick add form
        context['quick_form'] = QuickTransactionForm(user)

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


class AccountCreateView(LoginRequiredMixin, CreateView):
    """Create a new financial account."""

    model = FinancialAccount
    form_class = FinancialAccountForm
    template_name = 'finance/account_form.html'
    success_url = reverse_lazy('finance:account_list')

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.balance_updated_at = timezone.now()
        messages.success(self.request, f'Account "{form.instance.name}" created.')
        return super().form_valid(form)


class AccountUpdateView(FinanceUserMixin, UpdateView):
    """Edit a financial account."""

    model = FinancialAccount
    form_class = FinancialAccountForm
    template_name = 'finance/account_form.html'
    success_url = reverse_lazy('finance:account_list')

    def form_valid(self, form):
        messages.success(self.request, f'Account "{form.instance.name}" updated.')
        return super().form_valid(form)


class AccountDeleteView(FinanceUserMixin, DeleteView):
    """Delete (soft delete) a financial account."""

    model = FinancialAccount
    template_name = 'finance/account_confirm_delete.html'
    success_url = reverse_lazy('finance:account_list')

    def form_valid(self, form):
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
        return context


class TransactionDetailView(FinanceUserMixin, DetailView):
    """View transaction details."""

    model = Transaction
    template_name = 'finance/transaction_detail.html'
    context_object_name = 'transaction'


class TransactionCreateView(LoginRequiredMixin, CreateView):
    """Create a new transaction."""

    model = Transaction
    template_name = 'finance/transaction_form.html'
    success_url = reverse_lazy('finance:transaction_list')

    def get_form(self, form_class=None):
        return TransactionForm(self.request.user, **self.get_form_kwargs())

    def form_valid(self, form):
        messages.success(self.request, 'Transaction created.')
        return super().form_valid(form)


class TransactionUpdateView(FinanceUserMixin, UpdateView):
    """Edit a transaction."""

    model = Transaction
    template_name = 'finance/transaction_form.html'
    success_url = reverse_lazy('finance:transaction_list')

    def get_form(self, form_class=None):
        return TransactionForm(self.request.user, **self.get_form_kwargs())

    def form_valid(self, form):
        messages.success(self.request, 'Transaction updated.')
        return super().form_valid(form)


class TransactionDeleteView(FinanceUserMixin, DeleteView):
    """Delete a transaction."""

    model = Transaction
    template_name = 'finance/transaction_confirm_delete.html'
    success_url = reverse_lazy('finance:transaction_list')

    def form_valid(self, form):
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

        # Count by status
        context['on_track_count'] = sum(1 for b in budgets if b.status == 'on_track')
        context['warning_count'] = sum(1 for b in budgets if b.status == 'warning')
        context['over_count'] = sum(1 for b in budgets if b.status == 'over')

        return context


class BudgetCreateView(LoginRequiredMixin, CreateView):
    """Create a new budget."""

    model = Budget
    template_name = 'finance/budget_form.html'
    success_url = reverse_lazy('finance:budget_list')

    def get_form(self, form_class=None):
        return BudgetForm(self.request.user, **self.get_form_kwargs())

    def form_valid(self, form):
        messages.success(self.request, 'Budget created.')
        return super().form_valid(form)


class BudgetUpdateView(FinanceUserMixin, UpdateView):
    """Edit a budget."""

    model = Budget
    template_name = 'finance/budget_form.html'
    success_url = reverse_lazy('finance:budget_list')

    def get_form(self, form_class=None):
        return BudgetForm(self.request.user, **self.get_form_kwargs())

    def form_valid(self, form):
        messages.success(self.request, 'Budget updated.')
        return super().form_valid(form)


class BudgetDeleteView(FinanceUserMixin, DeleteView):
    """Delete a budget."""

    model = Budget
    template_name = 'finance/budget_confirm_delete.html'
    success_url = reverse_lazy('finance:budget_list')

    def form_valid(self, form):
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


class GoalCreateView(LoginRequiredMixin, CreateView):
    """Create a new financial goal."""

    model = FinancialGoal
    template_name = 'finance/goal_form.html'
    success_url = reverse_lazy('finance:goal_list')

    def get_form(self, form_class=None):
        return FinancialGoalForm(self.request.user, **self.get_form_kwargs())

    def form_valid(self, form):
        messages.success(self.request, f'Goal "{form.instance.name}" created.')
        return super().form_valid(form)


class GoalUpdateView(FinanceUserMixin, UpdateView):
    """Edit a financial goal."""

    model = FinancialGoal
    template_name = 'finance/goal_form.html'
    success_url = reverse_lazy('finance:goal_list')

    def get_form(self, form_class=None):
        return FinancialGoalForm(self.request.user, **self.get_form_kwargs())

    def form_valid(self, form):
        messages.success(self.request, f'Goal "{form.instance.name}" updated.')
        return super().form_valid(form)


class GoalDeleteView(FinanceUserMixin, DeleteView):
    """Delete a financial goal."""

    model = FinancialGoal
    template_name = 'finance/goal_confirm_delete.html'
    success_url = reverse_lazy('finance:goal_list')

    def form_valid(self, form):
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
        try:
            new_amount = Decimal(request.POST.get('current_amount', '0'))
            goal.current_amount = new_amount
            if goal.current_amount >= goal.target_amount:
                goal.mark_completed()
                messages.success(request, f'Congratulations! Goal "{goal.name}" completed!')
            else:
                goal.save(update_fields=['current_amount', 'updated_at'])
                messages.success(request, 'Goal progress updated.')
        except (ValueError, TypeError):
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

    snapshot = FinancialMetricSnapshot.create_snapshot(user, today)
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
    """Handle transaction file upload and processing."""
    if request.method == 'POST':
        form = TransactionImportForm(request.user, request.POST, request.FILES)
        if form.is_valid():
            # Create the import record
            import_record = form.save()

            # Process the file
            try:
                from .import_service import TransactionImportService

                # Read file content
                file_content = import_record.file.read()
                import_record.file.seek(0)  # Reset file pointer

                # Initialize service
                service = TransactionImportService(
                    user=request.user,
                    account=import_record.account
                )

                # Mark as processing
                import_record.mark_processing()

                # Parse file
                parsed = service.parse_file(file_content, import_record.file_type)
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
