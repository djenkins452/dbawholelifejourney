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
    path("dashboard/", _placeholder(
        "dashboard", "Dashboard",
        "Your operational overview — what needs tending, and a quiet sense of your record."),
        name="dashboard"),
    path("memories/", _placeholder(
        "stories", "Stories",
        "Every memory you've kept, gathered here to browse, revisit, and tend."),
        name="library"),
    path("memories/new/", _placeholder(
        "stories", "Remember",
        "A calm, unhurried space to tell a story — by voice or by writing."),
        name="editor_new"),
    path("people/", _placeholder(
        "people", "People",
        "The people who shaped you — a wall of faces, each a living portrait."),
        name="people"),
    path("places/", _placeholder(
        "places", "Places",
        "The places that mattered — homes, towns, a favorite table."),
        name="places"),
    path("timeline/", _placeholder(
        "timeline", "Timeline",
        "A gentle lens across the years of your life."),
        name="timeline"),
    path("media/", _placeholder(
        "media", "Media",
        "Photos, voices, letters, and film — doorways to memory."),
        name="media"),
    path("relationships/", _placeholder(
        "relationships", "Relationships",
        "How the people in your life are connected."),
        name="relationships"),
    path("contributors/", _placeholder(
        "contributors", "Contributors",
        "The family who help you remember — a life is remembered together."),
        name="contributors"),
    path("outputs/", _placeholder(
        "outputs", "Outputs",
        "Turn your memories into something to hold or share."),
        name="outputs"),
    path("studio/", _placeholder(
        "studio", "Studio",
        "A quiet workshop for tending your life's record."),
        name="studio"),
    path("search/", _placeholder(
        "search", "Search",
        "Reach for a memory — a name, a place, a year, or something someone used to say."),
        name="search"),
    path("settings/", _placeholder(
        "settings", "Settings",
        "Your Legacy preferences."),
        name="settings"),
]
