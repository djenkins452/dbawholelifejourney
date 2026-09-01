# ==============================================================================
# File: apps/finance/urls.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Finance module URL configuration (includes import routes)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-02
# Last Updated: 2026-01-03
# ==============================================================================
from django.urls import path

from . import views
from . import views_money
from apps.finance import views_assets, views_attribution, views_categories
from apps.finance import views_recurring

app_name = 'finance'

urlpatterns = [
    # Dashboard
    path('', views.FinanceDashboardView.as_view(), name='dashboard'),

    # Finance 2.0 workspaces — the measures, the review queue, what you can change,
    # and the debt payoff comparison.
    path('money/', views_money.MoneyOverviewView.as_view(), name='money_overview'),
    path('money/review/', views_money.ReviewQueueView.as_view(), name='money_review'),
    path('money/control/', views_money.ControlView.as_view(), name='money_control'),
    path('money/debt/', views_money.DebtView.as_view(), name='money_debt'),
    path('money/budget/', views_money.BudgetReserveView.as_view(), name='money_budget'),
    path('money/debt/<int:pk>/terms/', views_money.save_loan_terms,
         name='money_save_terms'),
    path('money/debt/scenarios/save/', views_money.save_scenario,
         name='money_save_scenario'),
    path('money/debt/scenarios/<int:pk>/state/', views_money.scenario_state,
         name='money_scenario_state'),
    path('money/net-worth/', views_money.NetWorthView.as_view(), name='money_networth'),
    path('money/health/', views_money.DataHealthView.as_view(), name='money_health'),
    path('money/reserves/save/', views_money.save_reserve, name='money_save_reserve'),
    path('money/reserves/<int:pk>/archive/', views_money.archive_reserve,
         name='money_archive_reserve'),
    path('money/net-worth/snapshot/', views_money.take_snapshot,
         name='money_take_snapshot'),
    path('money/detect/', views_money.run_detection, name='money_detect'),
    path('money/series/<int:pk>/decide/', views_money.confirm_series,
         name='money_series_decide'),
    path('money/review/preview/', views_money.preview_bulk, name='money_preview_bulk'),
    path('money/review/apply/', views_money.apply_bulk, name='money_apply_bulk'),
    path('money/review/<int:pk>/undo/', views_money.undo_bulk, name='money_undo_bulk'),
    path('money/transactions/<int:pk>/role/', views_money.set_transaction_role,
         name='money_set_role'),
    path('money/control/set/', views_money.set_controllability,
         name='money_set_controllability'),
    path('money/control/<int:pk>/archive/', views_money.archive_controllability,
         name='money_archive_controllability'),
    path('money/opportunities/<int:pk>/decide/', views_money.decide_opportunity,
         name='money_decide_opportunity'),

    # Accounts
    path('accounts/', views.AccountListView.as_view(), name='account_list'),
    path('accounts/new/', views.AccountCreateView.as_view(), name='account_create'),
    path('accounts/<int:pk>/', views.AccountDetailView.as_view(), name='account_detail'),
    path('accounts/<int:pk>/edit/', views.AccountUpdateView.as_view(), name='account_update'),
    path('accounts/<int:pk>/delete/', views.AccountDeleteView.as_view(), name='account_delete'),

    # Transactions
    path('transactions/', views.TransactionListView.as_view(), name='transaction_list'),
    path('transactions/new/', views.TransactionCreateView.as_view(), name='transaction_create'),
    path('transactions/quick/', views.quick_transaction, name='quick_transaction'),
    path('transactions/<int:pk>/', views.TransactionDetailView.as_view(), name='transaction_detail'),
    path('transactions/<int:pk>/edit/', views.TransactionUpdateView.as_view(), name='transaction_update'),
    path('transactions/<int:pk>/delete/', views.TransactionDeleteView.as_view(), name='transaction_delete'),
    path('transactions/bulk/delete/', views.BulkDeleteTransactionsView.as_view(), name='transaction_bulk_delete'),

    # Transfers
    path('transfer/', views.transfer_view, name='transfer'),

    # Budgets
    path('budgets/', views.BudgetListView.as_view(), name='budget_list'),
    path('budgets/new/', views.BudgetCreateView.as_view(), name='budget_create'),
    path('budgets/<int:pk>/edit/', views.BudgetUpdateView.as_view(), name='budget_update'),
    path('budgets/<int:pk>/delete/', views.BudgetDeleteView.as_view(), name='budget_delete'),

    # Recurring Transactions
    # Detected + declared recurring commitments — the review and CRUD surface.
    path('series/', views_recurring.SeriesListView.as_view(), name='series_list'),
    path('series/new/', views_recurring.SeriesCreateView.as_view(), name='series_create'),
    path('series/detect/', views_recurring.series_detect, name='series_detect'),
    path('series/bulk/preview/', views_recurring.series_bulk_preview, name='series_bulk_preview'),
    path('series/bulk/apply/', views_recurring.series_bulk_apply, name='series_bulk_apply'),
    path('series/<int:pk>/', views_recurring.SeriesDetailView.as_view(), name='series_detail'),
    path('series/<int:pk>/edit/', views_recurring.SeriesUpdateView.as_view(), name='series_update'),
    path('series/<int:pk>/archive/', views_recurring.series_archive, name='series_archive'),
    path('series/<int:pk>/restore/', views_recurring.series_restore, name='series_restore'),
    path('series/<int:pk>/delete/', views_recurring.series_delete, name='series_delete'),
    path('series/<int:pk>/end/', views_recurring.series_end, name='series_end'),
    path('series/<int:pk>/merge/', views_recurring.series_merge, name='series_merge'),
    path('series/<int:pk>/split/', views_recurring.series_split, name='series_split'),
    path('recurring/', views.RecurringTransactionListView.as_view(), name='recurring_list'),
    path('recurring/new/', views.RecurringTransactionCreateView.as_view(), name='recurring_create'),
    path('recurring/<int:pk>/', views.RecurringTransactionDetailView.as_view(), name='recurring_detail'),
    path('recurring/<int:pk>/edit/', views.RecurringTransactionUpdateView.as_view(), name='recurring_update'),
    path('recurring/<int:pk>/delete/', views.RecurringTransactionDeleteView.as_view(), name='recurring_delete'),
    path('recurring/<int:pk>/post/', views.recurring_post_now, name='recurring_post'),
    path('recurring/<int:pk>/skip/', views.recurring_skip, name='recurring_skip'),
    path('recurring/<int:pk>/toggle/', views.recurring_toggle_active, name='recurring_toggle'),
    path('api/recurring/upcoming/', views.api_upcoming_recurring, name='api_recurring_upcoming'),

    # Goals
    path('goals/', views.GoalListView.as_view(), name='goal_list'),
    path('goals/new/', views.GoalCreateView.as_view(), name='goal_create'),
    path('goals/<int:pk>/', views.GoalDetailView.as_view(), name='goal_detail'),
    path('goals/<int:pk>/edit/', views.GoalUpdateView.as_view(), name='goal_update'),
    path('goals/<int:pk>/delete/', views.GoalDeleteView.as_view(), name='goal_delete'),
    path('goals/<int:pk>/progress/', views.goal_update_progress, name='goal_progress'),

    # Metrics & Reports
    path('metrics/', views.MetricsDashboardView.as_view(), name='metrics'),
    path('metrics/refresh/', views.refresh_metrics, name='metrics_refresh'),

    # Categories
    # Tangible asset registry — houses, vehicles, boats, RVs, other property.
    path('assets/', views_assets.asset_list, name='asset_list'),
    path('assets/new/', views_assets.asset_create, name='asset_create'),
    path('assets/net-worth/', views_assets.net_worth_detail, name='net_worth_detail'),
    path('assets/<int:pk>/', views_assets.asset_detail, name='asset_detail'),
    path('assets/<int:pk>/edit/', views_assets.asset_update, name='asset_update'),
    path('assets/<int:pk>/archive/', views_assets.asset_archive, name='asset_archive'),
    path('assets/<int:pk>/restore/', views_assets.asset_restore, name='asset_restore'),
    path('assets/<int:pk>/delete/', views_assets.asset_delete, name='asset_delete'),
    path('assets/<int:pk>/valuation/', views_assets.valuation_add,
         name='asset_valuation_add'),
    path('assets/<int:pk>/valuation/refresh/', views_assets.valuation_refresh,
         name='asset_valuation_refresh'),
    path('assets/<int:pk>/loans/link/', views_assets.loan_link, name='asset_loan_link'),
    path('assets/<int:pk>/loans/<int:link_id>/unlink/', views_assets.loan_unlink,
         name='asset_loan_unlink'),
    path('categories/', views.CategoryListView.as_view(), name='category_list'),
    # Managing personal categories — ordinary Finance permissions, no admin.
    path('categories/create/', views_categories.category_create,
         name='category_create'),
    path('categories/<int:pk>/rename/', views_categories.category_rename,
         name='category_rename'),
    path('categories/<int:pk>/archive/', views_categories.category_archive,
         name='category_archive'),
    path('categories/<int:pk>/restore/', views_categories.category_restore,
         name='category_restore'),
    path('categories/<int:pk>/delete/', views_categories.category_delete,
         name='category_delete'),
    # In-place category selection/creation, reused by every editable surface.
    path('transactions/<int:pk>/category/options/', views_categories.category_options,
         name='transaction_category_options'),
    path('transactions/<int:pk>/category/', views_categories.category_set,
         name='transaction_category_set'),

    # Import
    path('import/', views.import_upload_view, name='import_upload'),
    path('import/history/', views.ImportListView.as_view(), name='import_list'),
    path('import/<int:pk>/', views.ImportDetailView.as_view(), name='import_detail'),

    # API Endpoints
    path('api/payees/', views.api_payee_suggestions, name='api_payees'),
    path('api/accounts/<int:pk>/balance/', views.api_account_balance, name='api_account_balance'),

    # F2 — Attribution review workspace
    path('attribution/', views_attribution.AttributionReviewView.as_view(),
         name='attribution_review'),
    path('attribution/decide/', views_attribution.attribution_decide,
         name='attribution_decide'),
    path('attribution/<int:pk>/explain/', views_attribution.attribution_explain,
         name='attribution_explain'),

    path('opportunities/<int:pk>/decide/', views_attribution.opportunity_decide,
         name='opportunity_decide'),

    path('entities/', views_attribution.EntityWorkspaceView.as_view(),
         name='entity_workspace'),
    path('entities/create/', views_attribution.entity_create, name='entity_create'),
    path('accounts/<int:pk>/entity/', views_attribution.account_assign_entity,
         name='account_assign_entity'),

    # Bank Connections (Plaid Integration)
    path('connections/', views.BankConnectionListView.as_view(), name='connection_list'),
    path('connections/start/', views.bank_connection_start, name='connection_start'),
    path('connections/complete/', views.bank_connection_complete, name='connection_complete'),
    path('connections/<int:pk>/reauth/', views.bank_connection_reauth, name='connection_reauth'),
    path('connections/<int:pk>/disconnect/', views.bank_connection_disconnect, name='connection_disconnect'),
    path('connections/<int:pk>/sync/', views.bank_connection_sync, name='connection_sync'),

    # Plaid OAuth redirect-and-resume (canonical URI registered with Plaid)
    path('plaid/oauth/', views.plaid_oauth_return, name='plaid_oauth_return'),
    path('plaid/oauth/abandon/', views.plaid_oauth_abandon,
         name='plaid_oauth_abandon'),

    # Plaid Webhooks
    path('webhooks/plaid/', views.plaid_webhook, name='plaid_webhook'),
]
