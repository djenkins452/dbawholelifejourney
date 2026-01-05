"""
URL configuration for the assistant app.

Includes admin approval endpoints for improvement tasks.
"""

from django.urls import path

from . import admin_views

app_name = 'assistant'

urlpatterns = [
    # Admin approval endpoints
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
