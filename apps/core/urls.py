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

    # What's New / Release Notes
    path("whats-new/", views.WhatsNewListView.as_view(), name="whats_new_list"),
    path("api/whats-new/check/", views.WhatsNewCheckView.as_view(), name="whats_new_check"),
    path("api/whats-new/dismiss/", views.WhatsNewDismissView.as_view(), name="whats_new_dismiss"),
]
