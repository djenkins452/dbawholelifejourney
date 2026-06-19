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
from django.views.generic import RedirectView

from . import views

app_name = "dashboard"

urlpatterns = [
    # Redirect /dashboard/ to V2 cockpit (V2 is now the primary dashboard)
    path("", RedirectView.as_view(pattern_name='dashboard_v2:home', permanent=False), name="home"),
    # Preserved V1 Command-Mode dashboard — direct access for validation +
    # rollback target. Owns the Command Brief / Command Mode greeting banner
    # builders (_get_command_brief / _get_command_mode) and their templates.
    path("classic/", views.DashboardView.as_view(), name="classic"),
    path("configure/", views.ConfigureDashboardView.as_view(), name="configure"),
    path("debug/", views.DashboardDebugView.as_view(), name="debug"),  # Temporary

    # API endpoints
    path("api/weight-data/", views.WeightChartDataView.as_view(), name="weight_chart_data"),

    # HTMX tile endpoints
    path("tiles/journal/", views.JournalSummaryTileView.as_view(), name="tile_journal"),
    path("tiles/encouragement/", views.EncouragementTileView.as_view(), name="tile_encouragement"),

    # Quarterly review
    path("api/quarterly-review/dismiss/", views.DismissQuarterlyReviewView.as_view(), name="dismiss_quarterly_review"),

    # Weight goal
    path("api/weight-goal/clear/", views.ClearWeightGoalView.as_view(), name="clear_weight_goal"),

    # Dashboard configuration API
    path("api/setup-banner/dismiss/", views.DismissSetupBannerView.as_view(), name="dismiss_setup_banner"),
    path("api/config/", views.DashboardConfigAPIView.as_view(), name="config_api"),
    path("api/config/reorder/", views.DashboardReorderAPIView.as_view(), name="config_reorder"),
    path("api/config/tile/<str:tile_id>/", views.DashboardTileConfigAPIView.as_view(), name="tile_config_api"),

    # Transformation dashboard
    path("transformation/", views.TransformationDashboardView.as_view(), name="transformation"),
    path("api/transformation-data/", views.TransformationChartDataView.as_view(), name="transformation_chart_data"),
]
