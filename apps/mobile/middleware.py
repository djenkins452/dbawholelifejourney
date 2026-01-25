"""
Mobile API Authentication Middleware

Provides Bearer token authentication for mobile API endpoints.
This runs after Django's session middleware, so endpoints can
support both session auth (web) and token auth (native app).

Usage in views:
    from apps.mobile.middleware import require_mobile_auth

    @require_mobile_auth
    def my_api_view(request):
        # request.user is authenticated
        # request.mobile_token is the MobileAPIToken instance
        # request.mobile_device is the MobileDevice instance
        pass
"""

import functools
import logging

from apps.core.utils import hash_pii

from django.http import JsonResponse

from .models import MobileAPIToken

logger = logging.getLogger(__name__)


class MobileAuthenticationMiddleware:
    """
    Middleware that authenticates requests with Bearer tokens.

    This middleware:
    1. Checks for Authorization: Bearer <token> header
    2. Validates the token
    3. Sets request.user, request.mobile_token, request.mobile_device

    Does NOT block requests without tokens - that's up to individual views.
    This allows views to support both session and token auth.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Initialize mobile attributes
        request.mobile_token = None
        request.mobile_device = None
        request.is_mobile_authenticated = False

        # Check for Bearer token
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")

        if auth_header.startswith("Bearer "):
            raw_token = auth_header[7:]  # Remove "Bearer " prefix

            token = MobileAPIToken.validate_token(raw_token)

            if token:
                request.user = token.user
                request.mobile_token = token
                request.mobile_device = token.device
                request.is_mobile_authenticated = True

                logger.debug(
                    f"Mobile auth successful: user={hash_pii(token.user.email, 'user')}, "
                    f"device={token.device.device_name or token.device.device_id[:8]}"
                )
            else:
                logger.warning(f"Invalid mobile token attempt from {get_client_ip(request)}")

        return self.get_response(request)


def get_client_ip(request):
    """Extract client IP from request, handling proxies."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def require_mobile_auth(view_func):
    """
    Decorator that requires mobile token authentication.

    Returns 401 if no valid Bearer token is provided.
    Sets request.mobile_token and request.mobile_device.

    Usage:
        @require_mobile_auth
        def my_view(request):
            user = request.user
            device = request.mobile_device
            ...
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not getattr(request, "is_mobile_authenticated", False):
            return JsonResponse(
                {
                    "error": "Authentication required",
                    "code": "auth_required",
                    "message": "Valid Bearer token required in Authorization header",
                },
                status=401,
            )
        return view_func(request, *args, **kwargs)

    return wrapper


def require_auth(view_func):
    """
    Decorator that requires either mobile token OR session authentication.

    This allows endpoints to work for both:
    - Native iOS app (Bearer token)
    - Web browser (session cookie)

    Usage:
        @require_auth
        def my_view(request):
            user = request.user  # Authenticated either way
            ...
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        is_mobile_auth = getattr(request, "is_mobile_authenticated", False)
        is_session_auth = request.user.is_authenticated

        if not (is_mobile_auth or is_session_auth):
            return JsonResponse(
                {
                    "error": "Authentication required",
                    "code": "auth_required",
                    "message": "Valid authentication required",
                },
                status=401,
            )
        return view_func(request, *args, **kwargs)

    return wrapper
