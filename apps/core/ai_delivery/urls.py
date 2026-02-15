"""DNE — URL configuration."""

from django.urls import path

from apps.core.ai_delivery import views

app_name = "ai_delivery"

urlpatterns = [
    path(
        "settings/",
        views.IntelligenceNotificationSettingsView.as_view(),
        name="settings",
    ),
    path(
        "settings/save/",
        views.IntelligenceNotificationSettingsSaveView.as_view(),
        name="settings_save",
    ),
    path(
        "history/",
        views.DeliveryHistoryView.as_view(),
        name="history",
    ),
]
