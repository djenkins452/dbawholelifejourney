"""
Whole Life Journey - Dashboard URL Configuration

Project: Whole Life Journey
Path: apps/dashboard/urls.py
Purpose: URL routing for dashboard views and API endpoints

Description:
    Defines URL patterns for the main dashboard view, configuration,
    and HTMX tile endpoints for dynamic content loading.

URL Patterns:
    - /dashboard/          : Main dashboard view
    - /dashboard/configure/: Dashboard configuration
    - /dashboard/api/*     : API endpoints for charts
    - /dashboard/tiles/*   : HTMX tile endpoints

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""
from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="home"),
    path("configure/", views.ConfigureDashboardView.as_view(), name="configure"),
    path("debug/", views.DashboardDebugView.as_view(), name="debug"),  # Temporary

    # API endpoints
    path("api/weight-data/", views.WeightChartDataView.as_view(), name="weight_chart_data"),

    # HTMX tile endpoints
    path("tiles/journal/", views.JournalSummaryTileView.as_view(), name="tile_journal"),
    path("tiles/encouragement/", views.EncouragementTileView.as_view(), name="tile_encouragement"),
]
