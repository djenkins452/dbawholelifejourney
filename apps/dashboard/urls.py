"""
Dashboard URLs
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
