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

    # Group CRUD
    path('groups/', views.GroupListView.as_view(), name='group_list'),
    path('groups/add/', views.GroupCreateView.as_view(), name='group_create'),
    path('groups/<int:pk>/', views.GroupDetailView.as_view(), name='group_detail'),
    path('groups/<int:pk>/edit/', views.GroupUpdateView.as_view(), name='group_update'),
    path('groups/<int:pk>/delete/', views.GroupDeleteView.as_view(), name='group_delete'),
    path('groups/quick-create/', views.GroupQuickCreateView.as_view(), name='group_quick_create'),

    # Insights dashboard (Phase R2)
    path('insights/', views.RelationshipInsightsView.as_view(), name='insights'),

    # Contact import (Phase 5)
    path('import/', views.ContactImportView.as_view(), name='contact_import'),

    # API endpoints
    path('autocomplete/', views.PersonAutocompleteView.as_view(), name='autocomplete'),
    path('quick-create/', views.PersonQuickCreateView.as_view(), name='quick_create'),
]
