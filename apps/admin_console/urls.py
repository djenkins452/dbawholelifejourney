# ==============================================================================
# File: apps/admin_console/urls.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Admin console URL configuration
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-01
# Last Updated: 2026-01-03 (Added DataLoadConfig management routes)
# ==============================================================================
"""
Admin Console URLs
"""

from django.urls import path

from . import views
from apps.core.ai_observability import diagnostics_views as diag_views
from apps.core.ai_observability import ops_views

app_name = "admin_console"

urlpatterns = [
    # Dashboard
    path("", views.AdminDashboardView.as_view(), name="dashboard"),

    # Diagnostics Console (Truth Layer)
    path("diagnostics/", diag_views.DiagnosticsConsoleView.as_view(), name="diagnostics_console"),
    path("diagnostics/stream/", diag_views.DiagnosticsStreamView.as_view(), name="diagnostics_stream"),
    path("diagnostics/trace/<str:trace_id>/", diag_views.DiagnosticsTraceDetailView.as_view(), name="diagnostics_trace_detail"),
    path("diagnostics/search/", diag_views.DiagnosticsSearchView.as_view(), name="diagnostics_search"),

    # Operations Wall v2 (Vegas Layer)
    path("ops/", ops_views.OperationsWallView.as_view(), name="ops_wall"),
    path("ops/stream/", ops_views.OpsStreamView.as_view(), name="ops_stream"),
    path("ops/actions/", ops_views.OpsActionView.as_view(), name="ops_actions"),
    path("ops/trigger-same/", ops_views.TriggerSAMEView.as_view(), name="ops_trigger_same"),
    path("ops/same-status/", ops_views.SAMEStatusView.as_view(), name="ops_same_status"),
    path("ops/trigger-engine/", ops_views.TriggerEngineView.as_view(), name="ops_trigger_engine"),
    path("ops/engine-status/", ops_views.EngineStatusView.as_view(), name="ops_engine_status"),
    path("ops/all-engines/", ops_views.AllEnginesView.as_view(), name="ops_all_engines"),
    path("ops/integrity/", ops_views.IntegrityIndexView.as_view(), name="ops_integrity"),
    path("ops/cadence/", ops_views.CadenceTimelineView.as_view(), name="ops_cadence"),
    # Legacy poll endpoint (redirect to stream)
    path("ops/poll/", ops_views.OpsStreamView.as_view(), name="ops_poll"),

    # Site Configuration
    path("config/", views.SiteConfigView.as_view(), name="site_config"),

    # Themes
    path("themes/", views.ThemeListView.as_view(), name="theme_list"),
    path("themes/new/", views.ThemeCreateView.as_view(), name="theme_create"),
    path("themes/<int:pk>/edit/", views.ThemeUpdateView.as_view(), name="theme_update"),
    path("themes/<int:pk>/delete/", views.ThemeDeleteView.as_view(), name="theme_delete"),
    path("themes/<int:pk>/preview/", views.ThemePreviewView.as_view(), name="theme_preview"),

    # Categories
    path("categories/", views.CategoryListView.as_view(), name="category_list"),
    path("categories/new/", views.CategoryCreateView.as_view(), name="category_create"),
    path("categories/<int:pk>/edit/", views.CategoryUpdateView.as_view(), name="category_update"),
    path("categories/<int:pk>/delete/", views.CategoryDeleteView.as_view(), name="category_delete"),

    # Users
    path("users/", views.UserListView.as_view(), name="user_list"),

    # Choice Categories
    path("choices/", views.ChoiceCategoryListView.as_view(), name="choice_category_list"),
    path("choices/new/", views.ChoiceCategoryCreateView.as_view(), name="choice_category_create"),
    path("choices/<int:pk>/edit/", views.ChoiceCategoryUpdateView.as_view(), name="choice_category_update"),
    path("choices/<int:pk>/delete/", views.ChoiceCategoryDeleteView.as_view(), name="choice_category_delete"),

    # Choice Options
    path("choices/<int:category_pk>/options/", views.ChoiceOptionListView.as_view(), name="choice_option_list"),
    path("choices/<int:category_pk>/options/new/", views.ChoiceOptionCreateView.as_view(), name="choice_option_create"),
    path("choices/options/<int:pk>/edit/", views.ChoiceOptionUpdateView.as_view(), name="choice_option_update"),
    path("choices/options/<int:pk>/delete/", views.ChoiceOptionDeleteView.as_view(), name="choice_option_delete"),

    # Test History
    path("tests/", views.TestRunListView.as_view(), name="test_run_list"),
    path("tests/run/", views.RunTestsView.as_view(), name="run_tests"),
    path("tests/<int:pk>/", views.TestRunDetailView.as_view(), name="test_run_detail"),
    path("tests/<int:pk>/delete/", views.TestRunDeleteView.as_view(), name="test_run_delete"),

    # Project Phases
    path("projects/phases/", views.ProjectPhaseListView.as_view(), name="project_phase_list"),
    path("projects/phases/new/", views.ProjectPhaseCreateView.as_view(), name="project_phase_create"),
    path("projects/phases/<int:pk>/edit/", views.ProjectPhaseUpdateView.as_view(), name="project_phase_update"),
    path("projects/phases/<int:pk>/delete/", views.ProjectPhaseDeleteView.as_view(), name="project_phase_delete"),

    # Admin Tasks
    path("projects/tasks/", views.AdminTaskListView.as_view(), name="admin_task_list"),
    path("projects/tasks/new/", views.AdminTaskCreateView.as_view(), name="admin_task_create"),
    path("projects/tasks/<int:pk>/edit/", views.AdminTaskUpdateView.as_view(), name="admin_task_update"),
    path("projects/tasks/<int:pk>/delete/", views.AdminTaskDeleteView.as_view(), name="admin_task_delete"),

    # Phase 12: Task Intake (human-only task creation)
    path("projects/intake/", views.TaskIntakeView.as_view(), name="task_intake"),

    # Phase 12: Mark Ready toggle API
    path("api/projects/tasks/<int:pk>/mark-ready/", views.MarkReadyAPIView.as_view(), name="api_mark_ready"),

    # Phase 13: Inline Editing APIs
    path("api/projects/tasks/<int:pk>/inline-status/", views.InlineStatusUpdateAPIView.as_view(), name="api_inline_status"),
    path("api/projects/tasks/<int:pk>/inline-priority/", views.InlinePriorityUpdateAPIView.as_view(), name="api_inline_priority"),

    # Activity Logs
    path("projects/activity/", views.ActivityLogListView.as_view(), name="activity_log_list"),
    path("projects/activity/new/", views.ActivityLogCreateView.as_view(), name="activity_log_create"),
    path("projects/activity/<int:pk>/edit/", views.ActivityLogUpdateView.as_view(), name="activity_log_update"),
    path("projects/activity/<int:pk>/delete/", views.ActivityLogDeleteView.as_view(), name="activity_log_delete"),

    # Project Status Page (Phase 7)
    path("projects/status/", views.ProjectStatusView.as_view(), name="project_status"),

    # Projects Operator Runbook (Phase 15)
    path("projects/help/", views.ProjectsRunbookView.as_view(), name="projects_runbook"),

    # Admin Projects (Phase 16)
    path("projects/", views.AdminProjectListView.as_view(), name="admin_project_list"),
    path("projects/new/", views.AdminProjectCreateView.as_view(), name="admin_project_create"),
    path("projects/<int:pk>/", views.AdminProjectDetailView.as_view(), name="admin_project_detail"),
    path("projects/<int:pk>/edit/", views.AdminProjectUpdateView.as_view(), name="admin_project_update"),
    path("projects/<int:pk>/delete/", views.AdminProjectDeleteView.as_view(), name="admin_project_delete"),

    # API Endpoints
    path("api/admin/project/active-phase/", views.ActivePhaseAPIView.as_view(), name="api_active_phase"),
    path("api/admin/project/tasks/<int:pk>/status/", views.TaskStatusUpdateAPIView.as_view(), name="api_task_status"),

    # Phase 17: Task Configuration Management
    path("projects/config/", views.TaskConfigDashboardView.as_view(), name="config_dashboard"),

    # Status Config
    path("projects/config/status/", views.StatusConfigListView.as_view(), name="config_status_list"),
    path("projects/config/status/new/", views.StatusConfigCreateView.as_view(), name="config_status_create"),
    path("projects/config/status/<int:pk>/edit/", views.StatusConfigUpdateView.as_view(), name="config_status_update"),
    path("projects/config/status/<int:pk>/delete/", views.StatusConfigDeleteView.as_view(), name="config_status_delete"),

    # Priority Config
    path("projects/config/priority/", views.PriorityConfigListView.as_view(), name="config_priority_list"),
    path("projects/config/priority/new/", views.PriorityConfigCreateView.as_view(), name="config_priority_create"),
    path("projects/config/priority/<int:pk>/edit/", views.PriorityConfigUpdateView.as_view(), name="config_priority_update"),
    path("projects/config/priority/<int:pk>/delete/", views.PriorityConfigDeleteView.as_view(), name="config_priority_delete"),

    # Category Config
    path("projects/config/category/", views.CategoryConfigListView.as_view(), name="config_category_list"),
    path("projects/config/category/new/", views.CategoryConfigCreateView.as_view(), name="config_category_create"),
    path("projects/config/category/<int:pk>/edit/", views.CategoryConfigUpdateView.as_view(), name="config_category_update"),
    path("projects/config/category/<int:pk>/delete/", views.CategoryConfigDeleteView.as_view(), name="config_category_delete"),

    # Effort Config
    path("projects/config/effort/", views.EffortConfigListView.as_view(), name="config_effort_list"),
    path("projects/config/effort/new/", views.EffortConfigCreateView.as_view(), name="config_effort_create"),
    path("projects/config/effort/<int:pk>/edit/", views.EffortConfigUpdateView.as_view(), name="config_effort_update"),
    path("projects/config/effort/<int:pk>/delete/", views.EffortConfigDeleteView.as_view(), name="config_effort_delete"),

    # Admin Guide
    path("admin-guide/", views.AdminGuideHomeView.as_view(), name="admin_guide_home"),
    path("admin-guide/manage/", views.AdminGuideManageView.as_view(), name="admin_guide_manage"),
    path("admin-guide/manage/<int:pk>/edit/", views.AdminGuideArticleEditView.as_view(), name="admin_guide_article_edit"),
    path("admin-guide/sync-cos/", views.AdminGuideSyncCosView.as_view(), name="admin_guide_sync_cos"),
    path("admin-guide/<slug:section_key>/", views.AdminGuideSectionView.as_view(), name="admin_guide_section"),
    path("admin-guide/<slug:section_key>/<slug:slug>/", views.AdminGuideArticleView.as_view(), name="admin_guide_article"),

    # Claude Code API - Ready Tasks (for "What's Next?" protocol)
    path("api/claude/ready-tasks/", views.ReadyTasksAPIView.as_view(), name="api_claude_ready_tasks"),
    path("api/claude/tasks/<int:pk>/status/", views.UpdateTaskStatusAPIView.as_view(), name="api_claude_task_status"),
    path("api/claude/process-emails/", views.ProcessEmailsAPIView.as_view(), name="api_claude_process_emails"),

    # Data Load Configuration Management
    path("dataload/", views.DataLoadConfigListView.as_view(), name="dataload_list"),
    path("dataload/<int:pk>/reset/", views.DataLoadConfigResetView.as_view(), name="dataload_reset"),
    path("dataload/reset-all/", views.DataLoadConfigResetAllView.as_view(), name="dataload_reset_all"),
    path("dataload/run/", views.DataLoadConfigForceRunView.as_view(), name="dataload_run"),

    # Clarity CSV Import (manual glucose data upload)
    path("clarity-import/", views.ClarityImportView.as_view(), name="clarity_import"),

    # Project Management JSON Import
    path("project-import/", views.ProjectImportView.as_view(), name="project_import"),

    # Codebase Metrics Report
    path("codebase-metrics/", views.CodebaseMetricsView.as_view(), name="codebase_metrics"),

    # System Announcements
    path("announcements/", views.SystemAnnouncementListView.as_view(), name="system_announcement_list"),
    path("announcements/new/", views.SystemAnnouncementCreateView.as_view(), name="system_announcement_create"),
    path("announcements/<int:pk>/edit/", views.SystemAnnouncementUpdateView.as_view(), name="system_announcement_update"),
    path("announcements/<int:pk>/delete/", views.SystemAnnouncementDeleteView.as_view(), name="system_announcement_delete"),
    path("api/announcements/<int:pk>/dismiss/", views.SystemAnnouncementDismissAPIView.as_view(), name="api_announcement_dismiss"),

    # Production Test Plans
    path("test-plans/", views.TestCycleListView.as_view(), name="test_cycle_list"),
    path("test-plans/new/", views.TestCycleCreateView.as_view(), name="test_cycle_create"),
    path("test-plans/<int:pk>/", views.TestCycleDetailView.as_view(), name="test_cycle_detail"),
    path("test-plans/<int:pk>/delete/", views.TestCycleDeleteView.as_view(), name="test_cycle_delete"),
    path("test-plans/<int:pk>/start/", views.TestCycleStartView.as_view(), name="test_cycle_start"),
    path("test-plans/<int:pk>/complete/", views.TestCycleCompleteView.as_view(), name="test_cycle_complete"),
    path("test-plans/<int:pk>/pause/", views.TestCyclePauseView.as_view(), name="test_cycle_pause"),
    path("test-plans/<int:pk>/resume/", views.TestCycleResumeView.as_view(), name="test_cycle_resume"),
    path("test-plans/<int:pk>/cancel/", views.TestCycleCancelView.as_view(), name="test_cycle_cancel"),

    # Test Phases
    path("test-plans/<int:cycle_pk>/phases/new/", views.TestPhaseCreateView.as_view(), name="test_phase_create"),
    path("test-plans/phases/<int:pk>/delete/", views.TestPhaseDeleteView.as_view(), name="test_phase_delete"),

    # Test Items
    path("test-plans/phases/<int:phase_pk>/items/new/", views.TestItemCreateView.as_view(), name="test_item_create"),
    path("test-plans/items/<int:pk>/delete/", views.TestItemDeleteView.as_view(), name="test_item_delete"),

    # Test Plan API Endpoints
    path("test-plans/api/item/<int:pk>/update/", views.TestItemUpdateAPIView.as_view(), name="api_test_item_update"),
    path("test-plans/api/bulk-update/", views.TestItemBulkUpdateAPIView.as_view(), name="api_test_item_bulk_update"),
]
