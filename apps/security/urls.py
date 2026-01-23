# ==============================================================================
# File: apps/security/urls.py
# Project: Whole Life Journey
# Description: Security dashboard URL configuration
# ==============================================================================

from django.urls import path

from . import views

app_name = 'security'

urlpatterns = [
    # Dashboard
    path('dashboard/', views.SecurityDashboardView.as_view(), name='dashboard'),

    # Run assessment
    path('run-assessment/', views.RunAssessmentView.as_view(), name='run_assessment'),

    # Run detail
    path('run/<uuid:pk>/', views.SecurityRunDetailView.as_view(), name='run_detail'),

    # API endpoints for popups
    path('api/test/<uuid:pk>/', views.TestDetailAPIView.as_view(), name='api_test_detail'),
    path('api/finding/<uuid:pk>/', views.FindingDetailAPIView.as_view(), name='api_finding_detail'),
    path('api/remediation/<uuid:pk>/', views.RemediationPromptView.as_view(), name='api_remediation'),
    path('api/trends/', views.TrendDataAPIView.as_view(), name='api_trends'),

    # Finding tracking endpoints
    path('api/finding-trends/', views.FindingTrendAPIView.as_view(), name='api_finding_trends'),
    path('api/improvement/', views.ImprovementMetricsAPIView.as_view(), name='api_improvement'),

    # Export endpoints
    path('export/csv/<uuid:pk>/', views.ExportCSVView.as_view(), name='export_csv'),
    path('export/pdf/<uuid:pk>/', views.ExportPDFView.as_view(), name='export_pdf'),
]
