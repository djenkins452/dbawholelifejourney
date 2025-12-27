from django.urls import path
from . import views

app_name = 'help'

urlpatterns = [
    # User help API
    path('api/topic/<str:context_id>/', views.HelpTopicAPIView.as_view(), name='api_topic'),

    # Admin help API
    path('api/admin/<str:context_id>/', views.AdminHelpTopicAPIView.as_view(), name='api_admin_topic'),

    # Search API
    path('api/search/', views.HelpSearchAPIView.as_view(), name='api_search'),
]
