"""
Faith URLs
"""

from django.urls import path

from . import views

app_name = "faith"

urlpatterns = [
    # Home
    path("", views.FaithHomeView.as_view(), name="home"),

    # Scripture
    path("verse/", views.TodaysVerseView.as_view(), name="todays_verse"),
    path("scripture/", views.ScriptureListView.as_view(), name="scripture_list"),
    path("scripture/save/", views.ScriptureSaveView.as_view(), name="scripture_save"),
    path("scripture/<int:pk>/", views.ScriptureDetailView.as_view(), name="scripture_detail"),
    path("scripture/<int:pk>/edit/", views.SavedVerseUpdateView.as_view(), name="saved_verse_edit"),
    path("scripture/<int:pk>/delete/", views.SavedVerseDeleteView.as_view(), name="saved_verse_delete"),
    path("scripture/<int:pk>/memory-verse/", views.ToggleMemoryVerseView.as_view(), name="toggle_memory_verse"),

    # Prayers
    path("prayers/", views.PrayerListView.as_view(), name="prayer_list"),
    path("prayers/answered/", views.AnsweredPrayersView.as_view(), name="answered_prayers"),
    path("prayers/new/", views.PrayerCreateView.as_view(), name="prayer_create"),
    path("prayers/<int:pk>/", views.PrayerDetailView.as_view(), name="prayer_detail"),
    path("prayers/<int:pk>/edit/", views.PrayerUpdateView.as_view(), name="prayer_update"),
    path("prayers/<int:pk>/answered/", views.MarkPrayerAnsweredView.as_view(), name="prayer_answered"),
    path("prayers/<int:pk>/delete/", views.PrayerDeleteView.as_view(), name="prayer_delete"),

    # Milestones
    path("milestones/", views.MilestoneListView.as_view(), name="milestone_list"),
    path("milestones/new/", views.MilestoneCreateView.as_view(), name="milestone_create"),
    path("milestones/<int:pk>/", views.MilestoneDetailView.as_view(), name="milestone_detail"),
    path("milestones/<int:pk>/edit/", views.MilestoneUpdateView.as_view(), name="milestone_update"),
    path("milestones/<int:pk>/delete/", views.MilestoneDeleteView.as_view(), name="milestone_delete"),

    # Reflections (Journal entries with Faith category)
    path("reflections/", views.FaithReflectionsView.as_view(), name="reflections"),
    path("reflections/new/", views.ReflectionCreateView.as_view(), name="reflection_create"),

    # Bible API Proxy (Security: keeps API key server-side)
    path("api/bible/status/", views.BibleAPIStatusView.as_view(), name="bible_api_status"),
    path("api/bible/bibles/", views.BibleAPIBiblesView.as_view(), name="bible_api_bibles"),
    path("api/bible/bibles/<str:bible_id>/books/", views.BibleAPIBooksView.as_view(), name="bible_api_books"),
    path("api/bible/bibles/<str:bible_id>/books/<str:book_id>/chapters/", views.BibleAPIChaptersView.as_view(), name="bible_api_chapters"),
    path("api/bible/bibles/<str:bible_id>/chapters/<str:chapter_id>/verses/", views.BibleAPIVersesView.as_view(), name="bible_api_verses"),
    path("api/bible/bibles/<str:bible_id>/verses/<path:verse_id>/", views.BibleAPIVerseView.as_view(), name="bible_api_verse"),
    path("api/bible/bibles/<str:bible_id>/passages/<path:passage_id>/", views.BibleAPIPassageView.as_view(), name="bible_api_passage"),
    path("api/bible/bibles/<str:bible_id>/search/", views.BibleAPISearchView.as_view(), name="bible_api_search"),
]
