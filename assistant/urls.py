"""
URL configuration for the assistant app.

Includes admin approval endpoints and dashboard for improvement tasks.
"""

from django.urls import path

from . import admin_views

app_name = 'assistant'

urlpatterns = [
    # Admin dashboard
    path(
        'admin/dashboard/',
        admin_views.improvement_dashboard,
        name='improvement_dashboard'
    ),

    # Analytics dashboard
    path(
        'admin/analytics/',
        admin_views.improvement_analytics,
        name='improvement_analytics'
    ),

    # Dashboard action endpoints
    path(
        'admin/dashboard/approve/<uuid:task_id>/',
        admin_views.dashboard_approve_task,
        name='dashboard_approve_task'
    ),
    path(
        'admin/dashboard/reject/<uuid:task_id>/',
        admin_views.dashboard_reject_task,
        name='dashboard_reject_task'
    ),
    path(
        'admin/dashboard/rollback/<uuid:task_id>/',
        admin_views.dashboard_rollback_task,
        name='dashboard_rollback_task'
    ),

    # Token-based approval endpoints (from email links)
    path(
        'admin/approve/<uuid:task_id>/<str:token>/',
        admin_views.approve_task,
        name='approve_task'
    ),
    path(
        'admin/reject/<uuid:task_id>/<str:token>/',
        admin_views.reject_task,
        name='reject_task'
    ),
]
