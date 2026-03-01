"""
Whole Life Journey - Notes URL Configuration

Project: Whole Life Journey
Path: apps/notes/urls.py
Purpose: URL routing for notes CRUD operations
"""

from django.urls import path

from . import views

app_name = "notes"

urlpatterns = [
    path("", views.NoteListView.as_view(), name="note_list"),
    path("new/", views.NoteCreateView.as_view(), name="note_create"),
    path("<int:pk>/", views.NoteDetailView.as_view(), name="note_detail"),
    path("<int:pk>/edit/", views.NoteUpdateView.as_view(), name="note_update"),
    path("<int:pk>/delete/", views.NoteDeleteView.as_view(), name="note_delete"),
    path("<int:pk>/pin/", views.NoteTogglePinView.as_view(), name="note_toggle_pin"),
]
