"""URLs for the canonical Person domain (read APIs for Phase 0b).

The full always-on People management UI (moving into apps/people) lands with
consumer migration; this ships the canonical lookup/resolution API surface now.
"""

from django.urls import path

from . import api

app_name = "people"

urlpatterns = [
    path("api/lookup/", api.lookup, name="lookup"),
    path("api/resolve/", api.resolve, name="resolve"),
]
