"""
Core URLs - Landing page and static pages.
"""

from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.LandingPageView.as_view(), name="landing"),
    path("terms/", views.TermsOfServiceView.as_view(), name="terms"),
    path("privacy/", views.PrivacyPolicyView.as_view(), name="privacy"),
    path("about/", views.AboutView.as_view(), name="about"),
]
