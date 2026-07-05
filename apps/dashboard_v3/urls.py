from django.urls import path

from apps.dashboard_v3 import views

app_name = "dashboard_v3"

urlpatterns = [
    path("", views.DashboardV3View.as_view(), name="home"),
    # Phase 4 — hydration partial refresh POC. After a water/coffee/
    # electrolyte tap succeeds, the home.html JS dispatches
    # `dashboard:water-changed` and the utilities <section> self-refreshes
    # via hx-get to this endpoint. No full dashboard reload.
    path(
        "section/utilities/",
        views.UtilitiesSectionView.as_view(),
        name="section_utilities",
    ),
    # Dynamic region refresh — after a completion the home.html JS dispatches
    # `dashboard:completed` and #v3-live self-refreshes via hx-get here. No
    # full window.location.reload(); perceived completion is instant.
    path(
        "section/live/",
        views.SectionLiveView.as_view(),
        name="section_live",
    ),
]
