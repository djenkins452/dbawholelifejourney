"""
Whole Life Journey - Admin Console Application Package

Project: Whole Life Journey
Path: apps/admin_console/__init__.py
Purpose: Custom administrative dashboard for site management

Description:
    The Admin Console provides a custom administrative interface beyond
    Django's built-in admin. It offers site-wide statistics, user management,
    system health monitoring, and test result viewing.

Key Responsibilities:
    - Admin dashboard with site statistics
    - User management and activity overview
    - System health and error monitoring
    - Test run history and results viewing
    - Quick links to Django admin sections

Package Contents:
    - views.py: Admin dashboard and management views
    - urls.py: URL routing (mounted at /admin-console/)
    - templates/: Admin console templates

Access Control:
    - Requires staff or superuser permission
    - Separate from Django admin for specialized views

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""
