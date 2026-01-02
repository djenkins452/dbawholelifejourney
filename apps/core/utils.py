"""
Whole Life Journey - Core Utilities

Project: Whole Life Journey
Path: apps/core/utils.py
Purpose: Shared helper functions used across all application modules

Description:
    This module provides common utility functions that are used by multiple
    apps. Includes timezone handling for users and security utilities
    for safe URL redirects.

Key Functions:
    - get_user_today: Get today's date in user's configured timezone
    - get_user_now: Get current datetime in user's timezone
    - is_safe_redirect_url: Validate URLs to prevent open redirect attacks
    - get_safe_redirect_url: Extract safe redirect URL from request

Security Notes:
    The redirect URL functions prevent open redirect vulnerabilities by
    validating that URLs are either relative or to the same host. This
    protects against attackers using our site to redirect to malicious sites.

Dependencies:
    - pytz: Timezone handling
    - django.utils.http.url_has_allowed_host_and_scheme: URL validation

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

import pytz
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme


def get_user_today(user):
    """
    Get today's date in the user's configured timezone.

    This is critical for date comparisons (overdue tasks, streaks, etc.)
    to work correctly across timezones. Using timezone.now().date() returns
    the UTC date, which can be a day ahead/behind the user's local date.

    Args:
        user: The User object (must have preferences.timezone_iana)

    Returns:
        date: Today's date in the user's timezone
    """
    # Use timezone_iana to handle legacy US/Eastern format
    user_tz = pytz.timezone(user.preferences.timezone_iana)
    user_now = timezone.now().astimezone(user_tz)
    return user_now.date()


def get_user_now(user):
    """
    Get the current datetime in the user's configured timezone.

    Args:
        user: The User object (must have preferences.timezone_iana)

    Returns:
        datetime: Current datetime in the user's timezone (timezone-aware)
    """
    # Use timezone_iana to handle legacy US/Eastern format
    user_tz = pytz.timezone(user.preferences.timezone_iana)
    return timezone.now().astimezone(user_tz)


def is_safe_redirect_url(url, request):
    """
    Check if a URL is safe for redirecting.

    Prevents open redirect attacks by validating that the URL is either:
    - A relative URL (starts with / but not //)
    - An absolute URL to the same host

    Args:
        url: The URL to validate
        request: The current HttpRequest (used to get allowed host)

    Returns:
        bool: True if URL is safe to redirect to, False otherwise
    """
    if not url:
        return False

    return url_has_allowed_host_and_scheme(
        url=url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    )


def get_safe_redirect_url(request, default_url=None):
    """
    Get a safe redirect URL from request parameters or referer.

    Checks 'next' in POST, then GET, then HTTP_REFERER header.
    Returns the default_url if no safe redirect URL is found.

    Args:
        request: The current HttpRequest
        default_url: URL to return if no safe redirect found (default: None)

    Returns:
        str or None: A safe redirect URL, or the default_url
    """
    # Check POST 'next' parameter
    next_url = request.POST.get('next')
    if next_url and is_safe_redirect_url(next_url, request):
        return next_url

    # Check GET 'next' parameter
    next_url = request.GET.get('next')
    if next_url and is_safe_redirect_url(next_url, request):
        return next_url

    # Check HTTP_REFERER header
    referer = request.META.get('HTTP_REFERER')
    if referer and is_safe_redirect_url(referer, request):
        return referer

    return default_url
