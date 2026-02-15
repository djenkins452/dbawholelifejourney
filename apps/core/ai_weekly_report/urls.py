"""
WIRE — URL configuration.
"""

from django.urls import path

from apps.core.ai_weekly_report.views import (
    WeeklyReportDetailView,
    WeeklyReportHistoryView,
)

app_name = "ai_weekly_report"

urlpatterns = [
    path("", WeeklyReportHistoryView.as_view(), name="history"),
    path("<int:pk>/", WeeklyReportDetailView.as_view(), name="detail"),
]
