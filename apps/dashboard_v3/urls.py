from django.urls import path

from apps.dashboard_v3 import views

app_name = "dashboard_v3"

urlpatterns = [
    path("", views.DashboardV3View.as_view(), name="home"),
]
