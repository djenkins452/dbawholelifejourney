from django.urls import path

from . import views
from . import views_renderer

app_name = "signals"

urlpatterns = [
    # GET /api/signals/ — Phase 1 Signal Rendering Framework.
    # Deterministic table-driven renderer. No LLM.
    path(
        "",
        views_renderer.SignalsAPIView.as_view(),
        name="api_signals",
    ),
    path(
        "feedback/",
        views.SignalFeedbackView.as_view(),
        name="feedback",
    ),
    path(
        "insights/",
        views.SignalInsightsView.as_view(),
        name="insights",
    ),
]
