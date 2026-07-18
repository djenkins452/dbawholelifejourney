"""URLs for the canonical Person domain (read APIs for Phase 0b).

The full always-on People management UI (moving into apps/people) lands with
consumer migration; this ships the canonical lookup/resolution API surface now.
"""

from django.urls import path

from . import api, views

app_name = "people"

urlpatterns = [
    path("api/lookup/", api.lookup, name="lookup"),
    path("api/resolve/", api.resolve, name="resolve"),
    path("api/<int:pk>/card/", api.card, name="card"),  # shared hover-card data
    # Canonical Person page (recognition-phrase management home).
    path("<int:pk>/", views.PersonDetailView.as_view(), name="person_detail"),
    # Canonical recognition-phrase management (host-agnostic; any page passes ?next).
    path("<int:pk>/phrases/add/", views.phrase_add, name="phrase_add"),
    path("<int:pk>/phrases/<int:phrase_pk>/edit/", views.phrase_edit, name="phrase_edit"),
    path("<int:pk>/phrases/<int:phrase_pk>/delete/", views.phrase_delete, name="phrase_delete"),
]
