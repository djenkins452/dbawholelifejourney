from django.urls import path

from . import views

app_name = "dashboard_v2"

urlpatterns = [
    # Main dashboard shell
    path("", views.DashboardV2View.as_view(), name="home"),
    # Cockpit expanded panel (HTMX)
    path(
        "cockpit/<str:domain>/panel/",
        views.CockpitPanelView.as_view(),
        name="cockpit_panel",
    ),
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
    path(
        "sections/action-center/",
        views.ActionCenterSectionView.as_view(),
        name="section_action_center",
    ),
    # Backward compat alias for existing references
    path(
        "sections/next-action/",
        views.ActionCenterSectionView.as_view(),
        name="section_next_action",
    ),
    # Signal suggestion cards (HTMX lazy-load)
    path(
        "sections/suggestions/",
        views.SuggestionsSectionView.as_view(),
        name="section_suggestions",
    ),
    # Signal insights panel (HTMX lazy-load)
    path(
        "sections/signal-insights/",
        views.SignalInsightsSectionView.as_view(),
        name="section_signal_insights",
    ),
    # Physical Intelligence coach panel (HTMX lazy-load)
    path(
        "sections/physical-intelligence/",
        views.PhysicalIntelligenceSectionView.as_view(),
        name="section_physical_intelligence",
    ),
    # Morning reconciliation (HTMX lazy-load + POST response)
    path(
        "sections/reconciliation/",
        views.ReconciliationSectionView.as_view(),
        name="section_reconciliation",
    ),
    path(
        "reconciliation/respond/",
        views.ReconciliationRespondView.as_view(),
        name="reconciliation_respond",
    ),
    # Inline action endpoints
    path(
        "actions/task/<int:pk>/toggle/",
        views.TaskToggleAction.as_view(),
        name="task_toggle",
    ),
    path(
        "actions/intake/<int:schedule_id>/log/",
        views.IntakeLogAction.as_view(),
        name="intake_log",
    ),
    path(
        "actions/intake/group/<str:time_of_day>/log/",
        views.IntakeGroupLogAction.as_view(),
        name="intake_group_log",
    ),
    path(
        "actions/routine/<int:pk>/complete/",
        views.RoutineCompleteAction.as_view(),
        name="routine_complete",
    ),
    path(
        "actions/routine/schedule/<int:schedule_id>/toggle/",
        views.RoutineScheduleToggleAction.as_view(),
        name="routine_schedule_toggle",
    ),
    path(
        "actions/routine/<int:routine_id>/toggle-complete/",
        views.RoutineCompleteToggleAction.as_view(),
        name="routine_complete_toggle",
    ),
    # Block-level completion (Action Center Option C — time block as
    # primary execution unit). One parent control per time block;
    # dispatches to per-item handlers, with intake-window optimization.
    path(
        "actions/block/<str:block_key>/toggle/",
        views.BlockCompleteToggleAction.as_view(),
        name="block_complete_toggle",
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
    # Compliance drill-down
    path(
        "compliance/<str:bucket>/",
        views.ComplianceDetailView.as_view(),
        name="compliance_detail",
    ),
]
