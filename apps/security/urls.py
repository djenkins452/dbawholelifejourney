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

    # Run detail
    path('run/<uuid:pk>/', views.SecurityRunDetailView.as_view(), name='run_detail'),

    # API endpoints for popups
    path('api/test/<uuid:pk>/', views.TestDetailAPIView.as_view(), name='api_test_detail'),
    path('api/finding/<uuid:pk>/', views.FindingDetailAPIView.as_view(), name='api_finding_detail'),
    path('api/remediation/<uuid:pk>/', views.RemediationPromptView.as_view(), name='api_remediation'),
    path('api/trends/', views.TrendDataAPIView.as_view(), name='api_trends'),
]
