# ==============================================================================
# File: apps/faith/urls.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: URL patterns for faith module including reading plans and study tools
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2024-01-01
# Last Updated: 2026-01-01
# ==============================================================================
"""
Faith URLs - Scripture, prayers, reading plans, and study tools.
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

    # ==========================================================================
    # READING PLANS
    # ==========================================================================
    path("reading-plans/", views.ReadingPlanListView.as_view(), name="reading_plans"),
    path("reading-plans/<slug:slug>/", views.ReadingPlanDetailView.as_view(), name="reading_plan_detail"),
    path("reading-plans/<slug:slug>/start/", views.StartReadingPlanView.as_view(), name="start_reading_plan"),
    path("reading-plans/progress/<int:pk>/", views.ReadingPlanProgressView.as_view(), name="reading_plan_progress"),
    path("reading-plans/progress/<int:pk>/day/<int:day_pk>/complete/", views.MarkDayCompleteView.as_view(), name="mark_day_complete"),
    path("reading-plans/progress/<int:pk>/pause/", views.PauseReadingPlanView.as_view(), name="pause_reading_plan"),
    path("reading-plans/progress/<int:pk>/resume/", views.ResumeReadingPlanView.as_view(), name="resume_reading_plan"),
    path("reading-plans/progress/<int:pk>/abandon/", views.AbandonReadingPlanView.as_view(), name="abandon_reading_plan"),

    # ==========================================================================
    # BIBLE STUDY TOOLS
    # ==========================================================================
    # Study Tools Home
    path("study-tools/", views.StudyToolsHomeView.as_view(), name="study_tools"),

    # Highlights
    path("study-tools/highlights/", views.HighlightListView.as_view(), name="highlight_list"),
    path("study-tools/highlights/new/", views.HighlightCreateView.as_view(), name="highlight_create"),
    path("study-tools/highlights/<int:pk>/delete/", views.HighlightDeleteView.as_view(), name="highlight_delete"),

    # Bookmarks
    path("study-tools/bookmarks/", views.BookmarkListView.as_view(), name="bookmark_list"),
    path("study-tools/bookmarks/new/", views.BookmarkCreateView.as_view(), name="bookmark_create"),
    path("study-tools/bookmarks/<int:pk>/delete/", views.BookmarkDeleteView.as_view(), name="bookmark_delete"),

    # Study Notes
    path("study-tools/notes/", views.StudyNoteListView.as_view(), name="study_note_list"),
    path("study-tools/notes/new/", views.StudyNoteCreateView.as_view(), name="study_note_create"),
    path("study-tools/notes/<int:pk>/", views.StudyNoteDetailView.as_view(), name="study_note_detail"),
    path("study-tools/notes/<int:pk>/edit/", views.StudyNoteUpdateView.as_view(), name="study_note_edit"),
    path("study-tools/notes/<int:pk>/delete/", views.StudyNoteDeleteView.as_view(), name="study_note_delete"),

    # ==========================================================================
    # BIBLE API PROXY (Security: keeps API key server-side)
    # ==========================================================================
    path("api/bible/status/", views.BibleAPIStatusView.as_view(), name="bible_api_status"),
    path("api/bible/bibles/", views.BibleAPIBiblesView.as_view(), name="bible_api_bibles"),
    path("api/bible/bibles/<str:bible_id>/books/", views.BibleAPIBooksView.as_view(), name="bible_api_books"),
    path("api/bible/bibles/<str:bible_id>/books/<str:book_id>/chapters/", views.BibleAPIChaptersView.as_view(), name="bible_api_chapters"),
    path("api/bible/bibles/<str:bible_id>/chapters/<str:chapter_id>/verses/", views.BibleAPIVersesView.as_view(), name="bible_api_verses"),
    path("api/bible/bibles/<str:bible_id>/verses/<path:verse_id>/", views.BibleAPIVerseView.as_view(), name="bible_api_verse"),
    path("api/bible/bibles/<str:bible_id>/passages/<path:passage_id>/", views.BibleAPIPassageView.as_view(), name="bible_api_passage"),
    path("api/bible/bibles/<str:bible_id>/search/", views.BibleAPISearchView.as_view(), name="bible_api_search"),
]
