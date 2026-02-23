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
    - zoneinfo: Timezone handling (Phase 2 — deterministic DST)
    - django.utils.http.url_has_allowed_host_and_scheme: URL validation

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

import hashlib
from zoneinfo import ZoneInfo

from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

# Phase 2: Backward compatibility — pytz still importable for third-party code,
# but all WLJ time authority uses zoneinfo.
try:
    import pytz  # noqa: F401 — retained for backward compatibility
except ImportError:
    pytz = None


def _get_user_tz(user):
    """
    Get the user's timezone as a zoneinfo.ZoneInfo instance.

    Phase 2: Uses zoneinfo (not pytz) for deterministic DST handling.
    - Spring-forward gap: zoneinfo moves to next valid time automatically.
    - Fall-back fold: always selects first occurrence (fold=0).

    Args:
        user: User instance with preferences.timezone_iana.

    Returns:
        ZoneInfo instance.
    """
    return ZoneInfo(user.preferences.timezone_iana)


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
    user_tz = _get_user_tz(user)
    user_now = timezone.now().astimezone(user_tz)
    return user_now.date()


def get_user_now(user):
    """
    Get the current datetime in the user's configured timezone.

    Phase 2: Uses zoneinfo for deterministic DST handling.

    Args:
        user: The User object (must have preferences.timezone_iana)

    Returns:
        datetime: Current datetime in the user's timezone (timezone-aware)
    """
    user_tz = _get_user_tz(user)
    return timezone.now().astimezone(user_tz)


# Canonical alias required by scheduling reliability contract.
# All scheduling code MUST call this to obtain the authoritative local datetime.
get_current_local_datetime = get_user_now


def make_dst_safe(dt, user):
    """
    Ensure a datetime is DST-safe in the user's timezone.

    Phase 2 DST handling determinism:
    - Spring-forward gap: move to next valid time.
    - Fall-back fold: always select first occurrence (fold=0).

    Args:
        dt: datetime — possibly ambiguous or in DST gap.
        user: User instance for timezone lookup.

    Returns:
        datetime — DST-safe, timezone-aware datetime.
    """
    user_tz = _get_user_tz(user)

    if dt.tzinfo is None:
        # Naive datetime — localize with fold=0 (first occurrence)
        dt = dt.replace(tzinfo=user_tz, fold=0)
    else:
        dt = dt.astimezone(user_tz)

    # Ensure fold=0 (first occurrence for fall-back ambiguity)
    if dt.fold != 0:
        dt = dt.replace(fold=0)

    return dt


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


# ==============================================================================
# PII Redaction Utilities
# ==============================================================================

def hash_pii(value: str, prefix: str = 'user') -> str:
    """
    Hash personally identifiable information for logging.

    Use this function when logging user data to protect privacy while
    still allowing correlation of log entries. The hash is truncated
    to 8 characters for readability while still providing uniqueness.

    Args:
        value: The PII to hash (email, phone, etc.)
        prefix: A label for the type of data (default: 'user')

    Returns:
        str: A hashed representation like "user:a1b2c3d4"

    Examples:
        >>> logger.info(f"Login failed for {hash_pii(email, 'email')}")
        # Logs: "Login failed for email:a1b2c3d4"

        >>> logger.debug(f"Processing request for {hash_pii(user.email)}")
        # Logs: "Processing request for user:f8e7d6c5"
    """
    if not value:
        return f"{prefix}:unknown"

    # Normalize and hash the value
    normalized = str(value).lower().strip()
    hash_digest = hashlib.sha256(normalized.encode()).hexdigest()[:8]
    return f"{prefix}:{hash_digest}"


def redact_email(email: str) -> str:
    """
    Partially redact an email address for display in logs.

    Shows first 2 characters, then asterisks, then @domain.
    This allows identification while protecting the full email.

    Args:
        email: The email address to redact

    Returns:
        str: A redacted email like "da***@example.com"

    Example:
        >>> redact_email("danny@example.com")
        'da***@example.com'
    """
    if not email or '@' not in email:
        return '[REDACTED]'

    local, domain = email.rsplit('@', 1)
    if len(local) <= 2:
        redacted_local = '*' * len(local)
    else:
        redacted_local = local[:2] + '***'

    return f"{redacted_local}@{domain}"


def user_log_id(user) -> str:
    """
    Get a privacy-safe identifier for logging user activity.

    Returns the user's primary key, which is safe for logging since
    it doesn't reveal personal information but allows correlation.

    Args:
        user: A User model instance

    Returns:
        str: "user:<id>" format for logging

    Example:
        >>> logger.info(f"Action performed by {user_log_id(request.user)}")
        # Logs: "Action performed by user:42"
    """
    if not user or not hasattr(user, 'pk'):
        return "user:anonymous"

    return f"user:{user.pk}"
