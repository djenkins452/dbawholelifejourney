# ==============================================================================
# File: apps/admin_console/api_urls.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: API URL routes for admin console project task management
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01 (Phase 9 - Session Bootstrapping)
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
]
