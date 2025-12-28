"""
Core Utilities - Shared helper functions across the app.

apps/core/utils.py
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
        user: The User object (must have preferences.timezone)

    Returns:
        date: Today's date in the user's timezone
    """
    user_tz = pytz.timezone(user.preferences.timezone)
    user_now = timezone.now().astimezone(user_tz)
    return user_now.date()


def get_user_now(user):
    """
    Get the current datetime in the user's configured timezone.

    Args:
        user: The User object (must have preferences.timezone)

    Returns:
        datetime: Current datetime in the user's timezone (timezone-aware)
    """
    user_tz = pytz.timezone(user.preferences.timezone)
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
