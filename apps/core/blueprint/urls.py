"""
Whole Life Journey - Blueprint URL Configuration

Project: Whole Life Journey
Path: apps/core/blueprint/urls.py
Purpose: URL routing for blueprint API endpoints

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

from django.urls import path

from . import api
from . import panel_views

urlpatterns = [
    # Blueprint CRUD
    path('', api.BlueprintView.as_view(), name='blueprint'),
    path('explain/', api.BlueprintExplainView.as_view(), name='blueprint_explain'),
    path('sync/', api.BlueprintSyncView.as_view(), name='blueprint_sync'),

    # Non-negotiables
    path('non-negotiables/', api.NonNegotiableListView.as_view(), name='non_negotiable_list'),
    path('non-negotiables/<int:pk>/', api.NonNegotiableDetailView.as_view(), name='non_negotiable_detail'),

    # Panel HTMX endpoints
    path('plan/today/', panel_views.TodayPlanView.as_view(), name='panel_plan_today'),
    path('drift/summary/', panel_views.DriftSummaryView.as_view(), name='panel_drift_summary'),
    path('interventions/pending/', panel_views.PendingInterventionsView.as_view(), name='panel_interventions'),
    path('interventions/check/', panel_views.InterventionCheckView.as_view(), name='panel_intervention_check'),
    path('interventions/<int:pk>/respond/', panel_views.InterventionRespondView.as_view(), name='panel_intervention_respond'),
    path('curveball/', panel_views.CurveballView.as_view(), name='panel_curveball'),
    path('panel/mobile/', panel_views.MobilePanelView.as_view(), name='panel_mobile'),
]
