from django.urls import path

from . import views

app_name = "signals"

urlpatterns = [
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
