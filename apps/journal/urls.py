"""
Journal URLs
"""
from django.urls import path
from . import views

app_name = "journal"

urlpatterns = [
    # Home (mini-dashboard)
    path("", views.JournalHomeView.as_view(), name="home"),
    
    # Entry list views
    path("entries/", views.EntryListView.as_view(), name="entry_list"),
    path("page-view/", views.PageView.as_view(), name="page_view"),
    path("book-view/", views.BookView.as_view(), name="book_view"),
    path("archived/", views.ArchivedEntryListView.as_view(), name="archived_list"),
    path("deleted/", views.DeletedEntryListView.as_view(), name="deleted_list"),
    
    # Entry CRUD
    path("new/", views.EntryCreateView.as_view(), name="entry_create"),
    path("<int:pk>/", views.EntryDetailView.as_view(), name="entry_detail"),
    path("<int:pk>/edit/", views.EntryUpdateView.as_view(), name="entry_update"),
    
    # Entry actions
    path("<int:pk>/archive/", views.ArchiveEntryView.as_view(), name="entry_archive"),
    path("<int:pk>/restore/", views.RestoreEntryView.as_view(), name="entry_restore"),
    path("<int:pk>/delete/", views.DeleteEntryView.as_view(), name="entry_delete"),
    path("<int:pk>/permanent-delete/", views.PermanentDeleteEntryView.as_view(), name="entry_permanent_delete"),
    
    # Prompts
    path("prompts/", views.PromptListView.as_view(), name="prompt_list"),
    path("prompts/random/", views.RandomPromptView.as_view(), name="random_prompt"),
    
    # Tags
    path("tags/", views.TagListView.as_view(), name="tag_list"),
    path("tags/create/", views.TagCreateView.as_view(), name="tag_create"),
    path("tags/<int:pk>/delete/", views.TagDeleteView.as_view(), name="tag_delete"),
    
    # HTMX endpoints
    path("htmx/entry-form/", views.HTMXEntryFormView.as_view(), name="htmx_entry_form"),
    path("htmx/mood-select/", views.HTMXMoodSelectView.as_view(), name="htmx_mood_select"),
]