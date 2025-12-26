"""
Purpose Module URLs
"""

from django.urls import path

from .views import (
    # Home
    PurposeHomeView,
    # Annual Direction
    DirectionListView,
    DirectionDetailView,
    DirectionCreateView,
    DirectionUpdateView,
    DirectionDeleteView,
    # Goals
    GoalListView,
    GoalDetailView,
    GoalCreateView,
    GoalUpdateView,
    GoalDeleteView,
    GoalToggleStatusView,
    # Intentions
    IntentionListView,
    IntentionDetailView,
    IntentionCreateView,
    IntentionUpdateView,
    IntentionDeleteView,
    # Reflections
    ReflectionListView,
    ReflectionDetailView,
    ReflectionCreateView,
    ReflectionEditView,
    ReflectionDeleteView,
    # Planning Actions
    PlanningActionCreateView,
    PlanningActionDeleteView,
)

app_name = "purpose"

urlpatterns = [
    # Home
    path("", PurposeHomeView.as_view(), name="home"),
    
    # Annual Direction
    path("direction/", DirectionListView.as_view(), name="direction_list"),
    path("direction/new/", DirectionCreateView.as_view(), name="direction_create"),
    path("direction/<int:pk>/", DirectionDetailView.as_view(), name="direction_detail"),
    path("direction/<int:pk>/edit/", DirectionUpdateView.as_view(), name="direction_update"),
    path("direction/<int:pk>/delete/", DirectionDeleteView.as_view(), name="direction_delete"),
    
    # Planning Actions (under direction)
    path("direction/<int:direction_pk>/action/new/", PlanningActionCreateView.as_view(), name="planning_action_create"),
    path("action/<int:pk>/delete/", PlanningActionDeleteView.as_view(), name="planning_action_delete"),
    
    # Goals
    path("goals/", GoalListView.as_view(), name="goal_list"),
    path("goals/new/", GoalCreateView.as_view(), name="goal_create"),
    path("goals/<int:pk>/", GoalDetailView.as_view(), name="goal_detail"),
    path("goals/<int:pk>/edit/", GoalUpdateView.as_view(), name="goal_update"),
    path("goals/<int:pk>/delete/", GoalDeleteView.as_view(), name="goal_delete"),
    path("goals/<int:pk>/status/", GoalToggleStatusView.as_view(), name="goal_toggle_status"),
    
    # Intentions
    path("intentions/", IntentionListView.as_view(), name="intention_list"),
    path("intentions/new/", IntentionCreateView.as_view(), name="intention_create"),
    path("intentions/<int:pk>/", IntentionDetailView.as_view(), name="intention_detail"),
    path("intentions/<int:pk>/edit/", IntentionUpdateView.as_view(), name="intention_update"),
    path("intentions/<int:pk>/delete/", IntentionDeleteView.as_view(), name="intention_delete"),
    
    # Reflections
    path("reflections/", ReflectionListView.as_view(), name="reflection_list"),
    path("reflections/new/", ReflectionCreateView.as_view(), name="reflection_create"),
    path("reflections/<int:pk>/", ReflectionDetailView.as_view(), name="reflection_detail"),
    path("reflections/<int:pk>/edit/", ReflectionEditView.as_view(), name="reflection_edit"),
    path("reflections/<int:pk>/delete/", ReflectionDeleteView.as_view(), name="reflection_delete"),
]
