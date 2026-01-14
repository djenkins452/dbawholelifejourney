"""Capture URL configuration."""

from django.urls import path

from . import views

app_name = 'capture'

urlpatterns = [
    path('', views.CaptureListView.as_view(), name='list'),
    path('record/', views.CaptureRecordView.as_view(), name='record'),
    path('upload/', views.CaptureUploadView.as_view(), name='upload'),
    path('submit/', views.CaptureSubmitView.as_view(), name='submit'),
    path('status/<uuid:entry_id>/', views.CaptureStatusView.as_view(), name='status'),
    path('<uuid:pk>/', views.CaptureDetailView.as_view(), name='detail'),
    path('<uuid:pk>/update-title/', views.CaptureUpdateTitleView.as_view(), name='update_title'),
    path('<uuid:pk>/update-category/', views.CaptureUpdateCategoryView.as_view(), name='update_category'),
    path('<uuid:pk>/pdf/', views.CaptureDownloadPDFView.as_view(), name='download_pdf'),
]
