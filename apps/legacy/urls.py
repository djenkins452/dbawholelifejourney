from django.urls import path

from . import views

app_name = "legacy"


def _placeholder(nav_active, title, blurb):
    return views.LegacyPlaceholderView.as_view(extra_context={
        "nav_active": nav_active,
        "page_title": title,
        "page_blurb": blurb,
    })


urlpatterns = [
    path("", views.HearthView.as_view(), name="home"),

    # Destinations arriving in later Phase-1 slices — graceful placeholders for now.
    # Dashboard + Studio/Review (Slice 4)
    path("dashboard/", views.StudioView.as_view(), name="dashboard"),
    path("studio/", views.ReviewView.as_view(), name="studio"),

    # Import Engine (Phase 2)
    path("import/", views.ImportsView.as_view(), name="imports"),
    path("import/new/", views.ImportCreateView.as_view(), name="import_new"),
    path("import/<int:pk>/", views.ImportDetailView.as_view(), name="import_detail"),
    path("import/<int:pk>/run/", views.ImportRunView.as_view(), name="import_run"),
    # Memory Library + Editor (Slice 2)
    path("memories/", views.LibraryView.as_view(), name="library"),
    path("memories/new/", views.EditorView.as_view(), name="editor_new"),
    path("memories/save/", views.MemorySaveView.as_view(), name="memory_save"),
    path("memories/discover/", views.MemoryDiscoverView.as_view(), name="memory_discover"),
    path("memories/<int:pk>/discover/confirm/", views.DiscoveryConfirmView.as_view(), name="discovery_confirm"),
    path("memories/<int:pk>/edit/", views.EditorView.as_view(), name="editor"),
    path("memories/<int:pk>/state/", views.MemorySetStateView.as_view(), name="memory_set_state"),
    path("memories/<int:pk>/archive/", views.MemoryArchiveView.as_view(), name="memory_archive"),
    path("memories/<int:pk>/restore/", views.MemoryRestoreView.as_view(), name="memory_restore"),
    path("memories/<int:pk>/delete-forever/", views.MemoryDeleteForeverView.as_view(), name="memory_delete_forever"),
    path("memories/<int:pk>/media/add/", views.MediaAddView.as_view(), name="memory_media_add"),
    # People (Slice 3)
    path("people/", views.PeopleView.as_view(), name="people"),
    path("people/new/", views.PersonCreateView.as_view(), name="person_new"),
    path("people/<int:pk>/", views.PersonProfileView.as_view(), name="person_detail"),
    path("people/<int:pk>/edit/", views.PersonEditView.as_view(), name="person_edit"),
    path("people/<int:pk>/archive/", views.PersonArchiveView.as_view(), name="person_archive"),
    path("people/<int:pk>/restore/", views.PersonRestoreView.as_view(), name="person_restore"),

    # Places (Slice 3)
    path("places/", views.PlacesView.as_view(), name="places"),
    path("places/new/", views.PlaceCreateView.as_view(), name="place_new"),
    path("places/<int:pk>/", views.PlaceProfileView.as_view(), name="place_detail"),
    path("places/<int:pk>/edit/", views.PlaceEditView.as_view(), name="place_edit"),
    path("places/<int:pk>/archive/", views.PlaceArchiveView.as_view(), name="place_archive"),
    path("places/<int:pk>/restore/", views.PlaceRestoreView.as_view(), name="place_restore"),
    path("timeline/", _placeholder(
        "timeline", "Timeline",
        "A gentle lens across the years of your life."),
        name="timeline"),
    # Media (Slice 3)
    path("media/", views.MediaLibraryView.as_view(), name="media"),
    path("media/upload/", views.MediaUploadView.as_view(), name="media_upload"),
    path("media/<int:pk>/", views.MediaDetailView.as_view(), name="media_detail"),
    path("relationships/", _placeholder(
        "relationships", "Relationships",
        "How the people in your life are connected."),
        name="relationships"),
    # Contributors / Family (Slice 4)
    path("contributors/", views.ContributorsView.as_view(), name="contributors"),
    path("contributors/new/", views.ContributorCreateView.as_view(), name="contributor_new"),
    path("contributors/<int:pk>/", views.ContributorDetailView.as_view(), name="contributor_detail"),
    path("contributors/<int:pk>/edit/", views.ContributorEditView.as_view(), name="contributor_edit"),
    path("contributors/<int:pk>/archive/", views.ContributorArchiveView.as_view(), name="contributor_archive"),

    # Outputs / Create (Slice 4)
    path("outputs/", views.OutputsView.as_view(), name="outputs"),
    path("outputs/new/", views.OutputCreateView.as_view(), name="output_new"),
    path("outputs/<int:pk>/", views.OutputDetailView.as_view(), name="output_detail"),
    path("outputs/<int:pk>/archive/", views.OutputArchiveView.as_view(), name="output_archive"),

    path("search/", _placeholder(
        "search", "Search",
        "Reach for a memory — a name, a place, a year, or something someone used to say."),
        name="search"),
    path("settings/", _placeholder(
        "settings", "Settings",
        "Your Legacy preferences."),
        name="settings"),
]
