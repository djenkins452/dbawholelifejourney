# ==============================================================================
# File: urls.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: URL routing for Dashboard AI Personal Assistant
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-29
# Last Updated: 2025-12-29
# ==============================================================================

from django.urls import path

from . import views

app_name = 'ai'

urlpatterns = [
    # Assistant Dashboard Page
    path('', views.AssistantDashboardView.as_view(), name='dashboard'),

    # Opening Message / Daily Check-in
    path('api/opening/', views.AssistantOpeningView.as_view(), name='api_opening'),

    # Conversation / Chat
    path('api/chat/', views.AssistantChatView.as_view(), name='api_chat'),
    path('api/history/', views.ConversationHistoryView.as_view(), name='api_history'),
    path('api/history/<int:conversation_id>/', views.ConversationHistoryView.as_view(), name='api_history_detail'),
    path('api/feedback/', views.MessageFeedbackView.as_view(), name='api_feedback'),

    # Daily Priorities
    path('api/priorities/', views.DailyPrioritiesView.as_view(), name='api_priorities'),
    path('api/priorities/<int:priority_id>/complete/', views.PriorityCompleteView.as_view(), name='api_priority_complete'),
    path('api/priorities/<int:priority_id>/dismiss/', views.PriorityDismissView.as_view(), name='api_priority_dismiss'),

    # State Assessment
    path('api/state/', views.StateAssessmentView.as_view(), name='api_state'),

    # Trend Analysis
    path('api/analysis/weekly/', views.WeeklyAnalysisView.as_view(), name='api_weekly_analysis'),
    path('api/analysis/monthly/', views.MonthlyAnalysisView.as_view(), name='api_monthly_analysis'),
    path('api/analysis/drift/', views.DriftDetectionView.as_view(), name='api_drift'),
    path('api/analysis/goals/', views.GoalProgressView.as_view(), name='api_goal_progress'),

    # Reflection Prompts
    path('api/reflection/', views.ReflectionPromptView.as_view(), name='api_reflection'),
    path('api/reflection/used/', views.ReflectionPromptUsedView.as_view(), name='api_reflection_used'),
]
