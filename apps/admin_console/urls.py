# ==============================================================================
# File: apps/admin_console/urls.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Admin console URL configuration
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01 (Phase 17 - Configurable Task Fields)
# ==============================================================================
"""
Admin Console URLs
"""

from django.urls import path

from . import views

app_name = "admin_console"

urlpatterns = [
    # Dashboard
    path("", views.AdminDashboardView.as_view(), name="dashboard"),

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
    path("projects/<int:pk>/", views.AdminProjectDetailView.as_view(), name="admin_project_detail"),

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
]
