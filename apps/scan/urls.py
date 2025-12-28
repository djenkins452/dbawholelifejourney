"""Scan URL patterns."""

from django.urls import path

from . import views

app_name = 'scan'

urlpatterns = [
    # Main scan page
    path('', views.ScanHomeView.as_view(), name='home'),

    # Consent
    path('consent/', views.ScanConsentView.as_view(), name='consent'),

    # API endpoints
    path('analyze/', views.ScanAnalyzeView.as_view(), name='analyze'),
    path('action/<uuid:request_id>/', views.ScanRecordActionView.as_view(), name='record_action'),

    # History
    path('history/', views.ScanHistoryView.as_view(), name='history'),
]
