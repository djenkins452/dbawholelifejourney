"""
Brain Training URL Configuration

Routes for the Brain Training module:
- /brain/ - Hub page
- /brain/<game>/play/ - Game play page
- /api/brain/<game>/batch/ - Fetch batch of challenges
- /api/brain/session/start/ - Start a session
- /api/brain/session/complete/ - Complete a session
- /api/brain/stats/overview/ - Overall stats
- /api/brain/stats/<game>/ - Game-specific stats
"""

from django.urls import path

from . import views

app_name = 'brain_training'

urlpatterns = [
    # Hub page
    path('', views.hub, name='hub'),

    # Game play pages
    path('<slug:game_slug>/play/', views.play, name='play'),

    # API endpoints
    path('api/<slug:game_slug>/batch/', views.api_batch, name='api_batch'),
    path('api/session/start/', views.api_session_start, name='api_session_start'),
    path('api/session/complete/', views.api_session_complete, name='api_session_complete'),
    path('api/session/<int:session_id>/update/', views.api_session_update, name='api_session_update'),
    path('api/stats/overview/', views.api_stats_overview, name='api_stats_overview'),
    path('api/stats/ai-summary/', views.api_ai_summary, name='api_ai_summary'),
    path('api/stats/<slug:game_slug>/', views.api_stats_game, name='api_stats_game'),

    # Stats dashboard page
    path('stats/', views.stats_dashboard, name='stats_dashboard'),
]
