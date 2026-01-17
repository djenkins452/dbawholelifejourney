"""
Whole Life Journey - User Middleware

Project: Whole Life Journey
Path: apps/users/middleware.py
Purpose: Enforce terms acceptance, onboarding, and subscription/trial for authenticated users

Description:
    This middleware runs on every request and ensures that authenticated users
    have accepted the current terms of service, completed the onboarding
    wizard, and have an active subscription or free trial before they can
    access the main application.

Key Responsibilities:
    - TermsAcceptanceMiddleware: Redirect to terms page if not accepted
    - Redirect to onboarding wizard if not completed
    - SubscriptionRequiredMiddleware: Redirect to subscribe page if trial expired
    - Exempt certain paths (login, logout, admin, static files, billing)

Enforcement Flow:
    1. Check if user is authenticated
    2. Skip exempt paths (login, terms, onboarding, static, billing)
    3. Check terms acceptance - redirect to terms page if needed
    4. Check onboarding completion - redirect to wizard if needed
    5. Check subscription/trial status - redirect to subscribe page if needed
    6. Allow request to proceed

Critical for Testing:
    All test users must have has_completed_onboarding = True and either:
    - An active subscription (is_subscribed = True), or
    - A valid trial (trial_ends_at in the future)
    Otherwise tests will get 302 redirects instead of expected responses.

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


class SubscriptionRequiredMiddleware:
    """
    Middleware to ensure authenticated users have an active subscription or trial.

    After terms acceptance and onboarding, this middleware checks if the user
    has access to premium features (via subscription or free trial).

    If the user's trial has expired and they don't have an active subscription,
    they are redirected to the subscription page.

    Exempt paths:
    - Same as TermsAcceptanceMiddleware, plus:
    - Billing/subscription pages (so users can subscribe)
    - API endpoints (handled separately with decorators)
    """

    EXEMPT_PATHS = [
        "/terms/",
        "/accounts/",  # Login, logout, password reset
        "/admin/",
        "/static/",
        "/media/",
        "/billing/",  # Subscription/payment pages
        "/user/onboarding/",
        "/user/accept-terms/",
        "/api/",  # API endpoints - use decorators for API auth
        "/help/",  # Help pages should be accessible
        "/__debug__/",  # Django debug toolbar
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only check for authenticated users
        if request.user.is_authenticated:
            # Skip exempt paths
            if not any(request.path.startswith(path) for path in self.EXEMPT_PATHS):
                # Skip for staff/superusers (admins always have access)
                if not request.user.is_staff:
                    try:
                        # Check if user has access (subscription or trial)
                        if not request.user.billing_profile.has_access:
                            # User's trial has expired and no active subscription
                            return redirect("billing:trial_expired")
                    except AttributeError:
                        # No billing profile - shouldn't happen but handle gracefully
                        pass

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
