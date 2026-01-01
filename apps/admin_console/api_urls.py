# ==============================================================================
# File: apps/admin_console/api_urls.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: API URL routes for admin console project task management
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01 (Phase 10 - Hardening & Fail-Safes)
# ==============================================================================

from django.urls import path

from . import views

urlpatterns = [
    # GET /api/admin/project/next-tasks/
    path("next-tasks/", views.NextTasksAPIView.as_view(), name="api_next_tasks"),
    # GET /api/admin/project/metrics/
    path("metrics/", views.ProjectMetricsAPIView.as_view(), name="api_project_metrics"),
    # GET /api/admin/project/system-state/
    path("system-state/", views.SystemStateAPIView.as_view(), name="api_system_state"),

    # Phase 10 - Hardening & Fail-Safes
    # GET /api/admin/project/system-issues/
    path("system-issues/", views.SystemIssuesAPIView.as_view(), name="api_system_issues"),
    # POST /api/admin/project/override/reset-phase/
    path("override/reset-phase/", views.ResetPhaseOverrideAPIView.as_view(), name="api_override_reset_phase"),
    # POST /api/admin/project/override/unblock-task/
    path("override/unblock-task/", views.UnblockTaskOverrideAPIView.as_view(), name="api_override_unblock_task"),
    # POST /api/admin/project/override/recheck-phase/
    path("override/recheck-phase/", views.RecheckPhaseOverrideAPIView.as_view(), name="api_override_recheck_phase"),
]
