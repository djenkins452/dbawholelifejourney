"""
PIE URL Configuration.
"""

from django.urls import path

from apps.core.ai_insights.views import InsightActionView, InsightsInboxView

app_name = "ai_insights"

urlpatterns = [
    path("", InsightsInboxView.as_view(), name="inbox"),
    path("<int:pk>/action/", InsightActionView.as_view(), name="action"),
]
