"""
Whole Life Journey - User Middleware

Project: Whole Life Journey
Path: apps/users/middleware.py
Purpose: Enforce terms acceptance and onboarding completion for authenticated users

Description:
    This middleware runs on every request and ensures that authenticated users
    have accepted the current terms of service and completed the onboarding
    wizard before they can access the main application.

Key Responsibilities:
    - TermsAcceptanceMiddleware: Redirect to terms page if not accepted
    - Redirect to onboarding wizard if not completed
    - Exempt certain paths (login, logout, admin, static files)

Enforcement Flow:
    1. Check if user is authenticated
    2. Skip exempt paths (login, terms, onboarding, static)
    3. Check terms acceptance - redirect to terms page if needed
    4. Check onboarding completion - redirect to wizard if needed
    5. Allow request to proceed

Critical for Testing:
    All test users must have has_completed_onboarding = True or tests will
    get 302 redirects instead of expected responses.

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

import zoneinfo

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone


class TermsAcceptanceMiddleware:
    """
    Middleware to ensure authenticated users have accepted the current terms
    and completed onboarding.

    Flow:
    1. Check terms acceptance - redirect to terms page if not accepted
    2. Check onboarding completion - redirect to wizard if not completed

    Exempt paths:
    - Terms page itself
    - Onboarding wizard
    - Logout
    - Static files
    - Admin (admins can manage settings)
    """

    EXEMPT_PATHS = [
        "/terms/",
        "/accounts/logout/",
        "/admin/",
        "/static/",
        "/media/",
    ]

    ONBOARDING_PATHS = [
        "/user/onboarding/",
        "/user/accept-terms/",
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only check for authenticated users
        if request.user.is_authenticated:
            # Skip exempt paths
            if not any(request.path.startswith(path) for path in self.EXEMPT_PATHS):
                # Step 1: Check if user has accepted current terms
                if not request.user.has_accepted_current_terms:
                    # Allow access to terms acceptance page
                    if request.path == reverse("users:accept_terms"):
                        pass  # Let it through to process acceptance
                    else:
                        return redirect("users:accept_terms")

                # Step 2: Check if user has completed onboarding
                elif not request.user.preferences.has_completed_onboarding:
                    # Allow access to onboarding pages
                    if any(request.path.startswith(path) for path in self.ONBOARDING_PATHS):
                        pass  # Let it through
                    else:
                        return redirect("users:onboarding_wizard")

        response = self.get_response(request)
        return response


class TimezoneMiddleware:
    """
    Middleware to activate the user's timezone for each request.

    This ensures that Django's timezone-aware template filters (like |date)
    automatically convert UTC times to the user's local timezone.

    Flow:
    1. Check if user is authenticated
    2. Get user's timezone from preferences
    3. Activate timezone for the request
    4. Deactivate timezone after response (Django handles this automatically)

    Note: This must run AFTER authentication middleware so request.user is available.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            try:
                # Use timezone_iana property which handles legacy US/Eastern format
                user_timezone = request.user.preferences.timezone_iana
                if user_timezone:
                    tz = zoneinfo.ZoneInfo(user_timezone)
                    timezone.activate(tz)
            except (AttributeError, zoneinfo.ZoneInfoNotFoundError):
                # If timezone is invalid or preferences don't exist, use UTC
                timezone.deactivate()
        else:
            # For anonymous users, deactivate to use default (UTC)
            timezone.deactivate()

        response = self.get_response(request)
        return response
