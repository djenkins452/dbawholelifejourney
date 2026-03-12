from django.urls import path

from . import views

app_name = "dashboard_v2"

urlpatterns = [
    # Main dashboard shell
    path("", views.DashboardV2View.as_view(), name="home"),
    # HTMX lazy-load section endpoints
    path(
        "sections/execution/",
        views.ExecutionSectionView.as_view(),
        name="section_execution",
    ),
    path(
        "sections/state/",
        views.StatePanelView.as_view(),
        name="section_state",
    ),
    path(
        "sections/celebration/",
        views.CelebrationSectionView.as_view(),
        name="section_celebration",
    ),
    path(
        "sections/insights/",
        views.InsightsSectionView.as_view(),
        name="section_insights",
    ),
    # Inline action endpoints
    path(
        "actions/task/<int:pk>/toggle/",
        views.TaskToggleAction.as_view(),
        name="task_toggle",
    ),
    path(
        "actions/medicine/<int:schedule_id>/log/",
        views.MedicineLogAction.as_view(),
        name="medicine_log",
    ),
    path(
        "actions/medicine/group/<str:time_of_day>/log/",
        views.MedicineGroupLogAction.as_view(),
        name="medicine_group_log",
    ),
    path(
        "actions/routine/<int:pk>/complete/",
        views.RoutineCompleteAction.as_view(),
        name="routine_complete",
    ),
    # Celebration endpoints
    path(
        "celebration/<int:pk>/reveal/",
        views.CelebrationRevealView.as_view(),
        name="celebration_reveal",
    ),
    path(
        "celebration/<int:pk>/dismiss/",
        views.CelebrationDismissView.as_view(),
        name="celebration_dismiss",
    ),
]
