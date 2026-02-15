"""
PGE -- URL configuration.
"""

from django.urls import path

from apps.core.ai_guidance.views import (
    GuidanceActionView,
    GuidanceAPIView,
    GuidanceInboxView,
)

app_name = "ai_guidance"

urlpatterns = [
    path("", GuidanceInboxView.as_view(), name="inbox"),
    path("api/", GuidanceAPIView.as_view(), name="api"),
    path("<int:pk>/action/", GuidanceActionView.as_view(), name="action"),
]
