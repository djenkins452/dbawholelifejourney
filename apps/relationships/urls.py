"""
Whole Life Journey - Relationships URL Configuration

Project: Whole Life Journey
Path: apps/relationships/urls.py
Purpose: URL routing for relationships app

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

from django.urls import path

from . import views

app_name = 'relationships'

urlpatterns = [
    # Person CRUD
    path('', views.PersonListView.as_view(), name='person_list'),
    path('add/', views.PersonCreateView.as_view(), name='person_create'),
    path('<int:pk>/', views.PersonDetailView.as_view(), name='person_detail'),
    path('<int:pk>/edit/', views.PersonUpdateView.as_view(), name='person_update'),
    path('<int:pk>/delete/', views.PersonDeleteView.as_view(), name='person_delete'),

    # API endpoints
    path('autocomplete/', views.PersonAutocompleteView.as_view(), name='autocomplete'),
    path('quick-create/', views.PersonQuickCreateView.as_view(), name='quick_create'),
]
