# ==============================================================================
# File: apps/core/rate_limiting.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Rate limiting and API security utilities
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-12 (CISO Security Review)
# Last Updated: 2026-01-12
# ==============================================================================
"""
Rate Limiting and API Security Utilities

Provides:
    - In-memory rate limiting for API endpoints
    - Secure constant-time API key comparison (HMAC)
    - IP address extraction from proxied requests

Usage:
    from apps.core.rate_limiting import rate_limit_api, secure_compare_api_key

    @rate_limit_api(requests_per_minute=60, requests_per_hour=1000)
    def my_api_view(request):
        ...

Security:
    - Tracks requests by IP address
    - Returns 429 Too Many Requests when limits exceeded
    - Logs rate limit violations to security logger
    - Uses constant-time comparison for API keys to prevent timing attacks
"""

import functools
import hmac
import logging

from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone

from apps.core.security_logging import log_security_event

logger = logging.getLogger(__name__)


# ==============================================================================
# Secure API Key Comparison (CISO Review 2026-01-12)
# ==============================================================================

def secure_compare_api_key(provided_key: str, expected_key: str) -> bool:
    """
    Securely compare an API key using constant-time comparison.

    This prevents timing attacks where an attacker could measure response
    times to determine how many characters of the key are correct.

    Args:
        provided_key: The API key provided in the request header
        expected_key: The expected API key from settings

    Returns:
        True if keys match, False otherwise

    Security Notes:
        - Uses hmac.compare_digest for constant-time comparison
        - Prevents timing-based side-channel attacks
        - Always compares same-length strings (encodes to bytes)
    """
    if not provided_key or not expected_key:
        return False

    # Encode both keys to bytes for comparison
    provided_bytes = provided_key.encode('utf-8')
    expected_bytes = expected_key.encode('utf-8')

    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(provided_bytes, expected_bytes)


def get_client_ip(request) -> str:
    """
    Extract client IP address from request, handling proxies.

    Checks X-Forwarded-For header first (for reverse proxy setups),
    then falls back to REMOTE_ADDR.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        # Take the first IP in the chain (client's IP)
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', 'unknown')
    return ip


def rate_limit_api(
    requests_per_minute: int = 60,
    requests_per_hour: int = 1000,
    key_prefix: str = 'api_rate_limit',
):
    """
    Decorator to rate limit API endpoints.

    Args:
        requests_per_minute: Maximum requests allowed per minute per IP
        requests_per_hour: Maximum requests allowed per hour per IP
        key_prefix: Cache key prefix for namespacing

    Returns:
        JsonResponse with 429 status if rate limit exceeded,
        otherwise continues to the view function.

    Example:
        @method_decorator(rate_limit_api(requests_per_minute=30))
        def get(self, request):
            ...
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            ip = get_client_ip(request)
            now = timezone.now()

            # Minute-level rate limiting
            minute_key = f"{key_prefix}:minute:{ip}:{now.strftime('%Y%m%d%H%M')}"
            minute_count = cache.get(minute_key, 0)

            if minute_count >= requests_per_minute:
                _log_rate_limit(request, ip, 'minute', minute_count, requests_per_minute)
                return JsonResponse(
                    {
                        'error': 'Rate limit exceeded. Please try again later.',
                        'retry_after': 60,
                    },
                    status=429
                )

            # Hour-level rate limiting
            hour_key = f"{key_prefix}:hour:{ip}:{now.strftime('%Y%m%d%H')}"
            hour_count = cache.get(hour_key, 0)

            if hour_count >= requests_per_hour:
                _log_rate_limit(request, ip, 'hour', hour_count, requests_per_hour)
                return JsonResponse(
                    {
                        'error': 'Rate limit exceeded. Please try again later.',
                        'retry_after': 3600,
                    },
                    status=429
                )

            # Increment counters
            cache.set(minute_key, minute_count + 1, timeout=60)
            cache.set(hour_key, hour_count + 1, timeout=3600)

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator


def _log_rate_limit(request, ip: str, window: str, count: int, limit: int):
    """Log rate limit violation to security logger."""
    log_security_event(
        event_type='rate_limit',
        severity='warning',
        message=f'API rate limit exceeded ({window}): {count}/{limit}',
        request=request,
        details={
            'ip': ip,
            'window': window,
            'count': count,
            'limit': limit,
            'endpoint': request.path,
        }
    )


class APIRateLimitMixin:
    """
    Mixin for class-based views to add rate limiting.

    Add this mixin to API views and set rate_limit_* attributes.

    Example:
        class MyAPIView(APIRateLimitMixin, View):
            rate_limit_requests_per_minute = 30
            rate_limit_requests_per_hour = 500
    """

    rate_limit_requests_per_minute: int = 60
    rate_limit_requests_per_hour: int = 1000
    rate_limit_key_prefix: str = 'api_rate_limit'

    def dispatch(self, request, *args, **kwargs):
        """Check rate limits before dispatching to the view."""
        ip = get_client_ip(request)
        now = timezone.now()

        # Minute-level rate limiting
        minute_key = f"{self.rate_limit_key_prefix}:minute:{ip}:{now.strftime('%Y%m%d%H%M')}"
        minute_count = cache.get(minute_key, 0)

        if minute_count >= self.rate_limit_requests_per_minute:
            _log_rate_limit(
                request, ip, 'minute',
                minute_count, self.rate_limit_requests_per_minute
            )
            return JsonResponse(
                {
                    'error': 'Rate limit exceeded. Please try again later.',
                    'retry_after': 60,
                },
                status=429
            )

        # Hour-level rate limiting
        hour_key = f"{self.rate_limit_key_prefix}:hour:{ip}:{now.strftime('%Y%m%d%H')}"
        hour_count = cache.get(hour_key, 0)

        if hour_count >= self.rate_limit_requests_per_hour:
            _log_rate_limit(
                request, ip, 'hour',
                hour_count, self.rate_limit_requests_per_hour
            )
            return JsonResponse(
                {
                    'error': 'Rate limit exceeded. Please try again later.',
                    'retry_after': 3600,
                },
                status=429
            )

        # Increment counters
        cache.set(minute_key, minute_count + 1, timeout=60)
        cache.set(hour_key, hour_count + 1, timeout=3600)

        return super().dispatch(request, *args, **kwargs)
