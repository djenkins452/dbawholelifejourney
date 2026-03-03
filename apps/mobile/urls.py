"""
Mobile API URL Configuration

All mobile API endpoints are prefixed with /api/mobile/
"""

from django.urls import path

from . import views

app_name = "mobile"

urlpatterns = [
    # Token exchange (web session -> API token)
    path("generate-code/", views.generate_exchange_code, name="generate_code"),
    path("token/exchange/", views.exchange_token, name="token_exchange"),
    path("token/revoke/", views.revoke_token, name="token_revoke"),
    path("token/revoke-all/", views.revoke_all_tokens, name="token_revoke_all"),

    # Device management
    path("devices/", views.list_devices, name="list_devices"),
    path("devices/<int:device_id>/deactivate/", views.deactivate_device, name="deactivate_device"),

    # Health data sync (from native app)
    path("health/ingest/", views.health_ingest, name="health_ingest"),
    path("health/sync-status/", views.sync_status, name="sync_status"),

    # Push notifications
    path("push/register/", views.push_register, name="push_register"),
    path("push/unregister/", views.push_unregister, name="push_unregister"),

    # Contact import (from iOS contact picker)
    path("contacts/import/", views.contact_import, name="contact_import"),
]
