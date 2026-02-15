"""
E3 — URL configuration.
"""

from django.urls import path

from apps.core.ai_explain.views import ExplainDetailView

app_name = "ai_explain"

urlpatterns = [
    path(
        "<str:source_engine>/<str:object_type>/<int:object_id>/",
        ExplainDetailView.as_view(),
        name="detail",
    ),
]
