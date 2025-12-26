"""
Dashboard URLs
"""

from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="home"),
    path("configure/", views.ConfigureDashboardView.as_view(), name="configure"),
    
    # HTMX endpoints for dynamic tile updates
    path("tiles/journal-summary/", views.JournalSummaryTileView.as_view(), name="tile_journal_summary"),
    path("tiles/encouragement/", views.EncouragementTileView.as_view(), name="tile_encouragement"),
]
