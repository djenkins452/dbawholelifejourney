"""
Intelligence Command Center URL configuration.

Mounted at /intelligence/ in config/urls.py.
"""

from django.urls import path

from apps.core.ai_observability.views import ObservabilityDashboardView
from apps.core.views_intelligence_center import IntelligenceCommandCenterView

app_name = "intelligence"

urlpatterns = [
    path("", IntelligenceCommandCenterView.as_view(), name="command_center"),
    path(
        "observability/",
        ObservabilityDashboardView.as_view(),
        name="observability",
    ),
]
