# ==============================================================================
# File: apps/admin_console/api_urls.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: API URL routes for admin console project task management
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================

from django.urls import path

from . import views

urlpatterns = [
    # GET /api/admin/project/next-tasks/
    path("next-tasks/", views.NextTasksAPIView.as_view(), name="api_next_tasks"),
]
