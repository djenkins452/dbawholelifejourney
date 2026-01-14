"""Capture URL configuration."""

from django.urls import path

from . import views

app_name = 'capture'

urlpatterns = [
    path('', views.CaptureListView.as_view(), name='list'),
    path('record/', views.CaptureRecordView.as_view(), name='record'),
    path('upload/', views.CaptureUploadView.as_view(), name='upload'),
]
