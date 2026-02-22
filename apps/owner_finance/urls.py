from django.urls import path

from . import views

app_name = 'owner_finance'

urlpatterns = [
    # Phase 2: Core dashboard
    path('', views.OverviewView.as_view(), name='overview'),
    path('users/', views.UserCostsView.as_view(), name='users'),
    path('features/', views.FeatureBreakdownView.as_view(), name='features'),
    path('vendors/', views.VendorLedgerView.as_view(), name='vendors'),

    # Phase 3: Charts, audit, export, power user
    path('api/daily-chart/', views.DailyChartDataView.as_view(), name='daily_chart'),
    path('audit/', views.AuditLedgerView.as_view(), name='audit'),
    path('export/', views.ExportCSVView.as_view(), name='export_csv'),
    path('users/<int:user_id>/', views.PowerUserView.as_view(), name='power_user'),

    # Phase 4: Scenario simulator
    path('simulator/', views.SimulatorView.as_view(), name='simulator'),

    # Phase 5: Budget guardrails
    path('budgets/', views.BudgetGuardrailsView.as_view(), name='budgets'),
]
