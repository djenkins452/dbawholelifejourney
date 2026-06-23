# ==============================================================================
# File: urls.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: URL routing for Dashboard AI Personal Assistant
# Owner: Danny Jenkins (admin@wholelifejourney.com)
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

    # Pre-Warm / Readiness
    path('api/wake/', views.AssistantWakeView.as_view(), name='api_wake'),

    # Proactive Daily Executive Briefing (v7)
    path('api/briefing/', views.ProactiveBriefingView.as_view(), name='api_briefing'),

    # Session Start — Adaptive CoS Presence (deterministic, no LLM)
    path('api/session-start/', views.SessionStartView.as_view(), name='api_session_start'),

    # Conversation / Chat
    path('api/chat/', views.AssistantChatView.as_view(), name='api_chat'),
    path('api/chat/stream/', views.AssistantChatStreamView.as_view(), name='api_chat_stream'),
    # Reconnect to an in-progress generation by job_id (P0 navigation fix)
    path('api/chat/stream/resume/<str:job_id>/', views.AssistantChatResumeView.as_view(), name='api_chat_stream_resume'),
    path('api/history/', views.ConversationHistoryView.as_view(), name='api_history'),
    path('api/history/<int:conversation_id>/', views.ConversationHistoryView.as_view(), name='api_history_detail'),
    path('api/feedback/', views.MessageFeedbackView.as_view(), name='api_feedback'),
    path('api/clear/', views.ClearConversationView.as_view(), name='api_clear'),
    path('api/quick-reply/', views.QuickReplyView.as_view(), name='api_quick_reply'),

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

    # CoS Settings
    path('cos/settings/', views.CosSettingsView.as_view(), name='cos_settings'),
    path('cos/settings/save/', views.CosSettingsSaveView.as_view(), name='cos_settings_save'),

    # Learning Mode Toggle (Phase 1)
    path('cos/learning-mode/toggle/', views.LearningModeToggleView.as_view(), name='cos_learning_mode_toggle'),

    # Event Reflections (Post-Event Check-ins)
    path('api/event-reflection/', views.EventReflectionView.as_view(), name='api_event_reflection'),

    # CoS deterministic decision modes (execution / risk / fix)
    path('api/cos/decision/', views.CosDecisionView.as_view(), name='api_cos_decision'),

    # Text-to-Speech (TTS)
    path('api/tts/', views.TextToSpeechView.as_view(), name='api_tts'),

    # Temporary debug endpoint (remove after calibration is working)
    path('api/calibration-debug/', views.CalibrationDebugView.as_view(), name='api_calibration_debug'),
]
