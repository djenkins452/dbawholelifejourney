# ==============================================================================
# File: apps/finance/urls.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Finance module URL configuration
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-02
# Last Updated: 2026-01-02
# ==============================================================================
from django.urls import path

from . import views

app_name = 'finance'

urlpatterns = [
    # Dashboard
    path('', views.FinanceDashboardView.as_view(), name='dashboard'),

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

    # Transfers
    path('transfer/', views.transfer_view, name='transfer'),

    # Budgets
    path('budgets/', views.BudgetListView.as_view(), name='budget_list'),
    path('budgets/new/', views.BudgetCreateView.as_view(), name='budget_create'),
    path('budgets/<int:pk>/edit/', views.BudgetUpdateView.as_view(), name='budget_update'),
    path('budgets/<int:pk>/delete/', views.BudgetDeleteView.as_view(), name='budget_delete'),

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
    path('categories/', views.CategoryListView.as_view(), name='category_list'),

    # API Endpoints
    path('api/payees/', views.api_payee_suggestions, name='api_payees'),
    path('api/accounts/<int:pk>/balance/', views.api_account_balance, name='api_account_balance'),
]
