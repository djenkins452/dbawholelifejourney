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
    path('barcode/', views.BarcodeLookupView.as_view(), name='barcode_lookup'),
    path('barcode/product/', views.ProductLookupView.as_view(), name='product_lookup'),
    path('barcode/medicine/', views.MedicineLookupView.as_view(), name='medicine_lookup'),
    path('action/<uuid:request_id>/', views.ScanRecordActionView.as_view(), name='record_action'),

    # History
    path('history/', views.ScanHistoryView.as_view(), name='history'),
]
