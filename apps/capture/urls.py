"""Capture URL configuration."""

from django.urls import path

from . import views

app_name = 'capture'

urlpatterns = [
    path('', views.CaptureListView.as_view(), name='list'),
]
