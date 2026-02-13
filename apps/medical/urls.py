"""
Whole Life Journey - Medical URL Configuration

Project: Whole Life Journey
Path: apps/medical/urls.py
Purpose: URL patterns for medical lab ingestion and results viewing
"""

from django.urls import path

from . import views

app_name = "medical"

urlpatterns = [
    # Home / Labs Summary
    path("", views.LabsSummaryView.as_view(), name="home"),
    # Upload
    path("upload/", views.LabUploadView.as_view(), name="upload"),
    # Import results
    path("import/<uuid:pk>/", views.ImportDetailView.as_view(), name="import_detail"),
    path("import/<uuid:pk>/errors/csv/", views.ImportErrorCSVView.as_view(), name="import_errors_csv"),
    # Result detail
    path("result/<uuid:pk>/", views.ResultDetailView.as_view(), name="result_detail"),
    # Test trend (single test over time)
    path("trend/<uuid:test_id>/", views.TestTrendView.as_view(), name="test_trend"),
    # Panel detail
    path("panel/<uuid:pk>/", views.PanelDetailView.as_view(), name="panel_detail"),
    # Document detail
    path("document/<uuid:pk>/", views.DocumentDetailView.as_view(), name="document_detail"),
    # Delete actions
    path("document/<uuid:pk>/delete/", views.DocumentDeleteView.as_view(), name="document_delete"),
    path("result/<uuid:pk>/delete/", views.ResultDeleteView.as_view(), name="result_delete"),
]
