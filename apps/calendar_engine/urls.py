from django.urls import path

from . import views

app_name = 'calendar_engine'

urlpatterns = [
    # Dashboard / UI
    path('', views.CalendarDashboardView.as_view(), name='dashboard'),

    # API — event CRUD
    path('api/today/', views.TodayTimelineView.as_view(), name='api_today'),
    path('api/range/', views.RangeView.as_view(), name='api_range'),
    path('api/events/', views.EventCreateView.as_view(), name='api_event_create'),
    path('api/events/<int:pk>/', views.EventDetailView.as_view(), name='api_event_detail'),
    path('api/events/<int:pk>/move/', views.EventMoveView.as_view(), name='api_event_move'),

    # Smart suggestions
    path('api/suggestions/gaps/', views.GapSuggestionsView.as_view(), name='api_gap_suggestions'),
    path('api/suggestions/accept/', views.AcceptSuggestionView.as_view(), name='api_accept_suggestion'),

    # Domain metrics
    path('api/metrics/balance/', views.DomainBalanceView.as_view(), name='api_domain_balance'),

    # NLP quick add
    path('api/nlp_create/', views.NLPCreateView.as_view(), name='api_nlp_create'),
]
