"""
Whole Life Journey - Core URL Configuration

Project: Whole Life Journey
Path: apps/core/urls.py
Purpose: URL routing for core pages and API endpoints

Description:
    Defines URL patterns for the core app including the landing page,
    static content pages (terms, privacy, about), and the What's New
    release notes feature.

URL Patterns:
    - /                   : Landing page (redirects to dashboard if authenticated)
    - /terms/            : Terms of Service
    - /privacy/          : Privacy Policy
    - /about/            : About page
    - /whats-new/        : Full release notes list
    - /api/whats-new/*   : Release notes API endpoints

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
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
