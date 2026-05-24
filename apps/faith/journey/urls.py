"""
Journey URL patterns. Mounted at /faith/journey/ via root urls.py.

Namespace: 'journey'
"""

from django.urls import path

from apps.faith.journey import views


app_name = "journey"


urlpatterns = [
    # Canonical entry — resolves to the user's current day
    path("today/", views.journey_today, name="today"),

    # Start the journey (POST)
    path("start/", views.journey_start, name="start"),

    # Settings
    path("settings/", views.journey_settings, name="settings"),

    # Addressable, read-only review of a specific day
    path("<slug:arc_slug>/day/<int:day_number>/", views.journey_review_day, name="review_day"),

    # Complete-day action (POST)
    path("<slug:arc_slug>/day/<int:day_number>/complete/", views.journey_complete_day, name="complete_day"),

    # Annotation endpoints — reuse-only wrappers around existing models
    path("annotations/highlight/", views.annotation_highlight_create, name="annotation_highlight"),
    path("annotations/bookmark/", views.annotation_bookmark_create, name="annotation_bookmark"),
    path("annotations/save-verse/", views.annotation_save_verse, name="annotation_save_verse"),
    path("annotations/note/", views.annotation_note_create, name="annotation_note"),
]
