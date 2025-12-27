from django.urls import path
from . import views

app_name = 'help'

urlpatterns = [
    # User help API (context-aware help)
    path('api/topic/<str:context_id>/', views.HelpTopicAPIView.as_view(), name='api_topic'),

    # Admin help API
    path('api/admin/<str:context_id>/', views.AdminHelpTopicAPIView.as_view(), name='api_admin_topic'),

    # Search API (context-aware help)
    path('api/search/', views.HelpSearchAPIView.as_view(), name='api_search'),

    # ==========================================================================
    # WLJ ASSISTANT CHAT BOT
    # ==========================================================================

    # Help Center pages
    path('', views.HelpCenterView.as_view(), name='center'),
    path('article/<slug:slug>/', views.HelpArticleView.as_view(), name='article'),
    path('category/<slug:slug>/', views.HelpCategoryView.as_view(), name='category'),

    # Chat API endpoints
    path('api/chat/start/', views.ChatStartView.as_view(), name='chat_start'),
    path('api/chat/message/', views.ChatMessageView.as_view(), name='chat_message'),
    path('api/chat/end/', views.ChatEndView.as_view(), name='chat_end'),
    path('api/chat/search/', views.ChatSearchView.as_view(), name='chat_search'),
    path('api/chat/suggestions/', views.ChatSuggestionsView.as_view(), name='chat_suggestions'),
]
