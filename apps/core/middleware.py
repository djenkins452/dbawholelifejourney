"""
Whole Life Journey - Core Middleware

Project: Whole Life Journey
Path: apps/core/middleware.py
Purpose: Track page views for the Favorites feature and security headers

Description:
    This middleware provides:
    - Page view tracking for the Favorites menu
    - Content Security Policy (CSP) headers for XSS protection
    - CSP nonce generation for inline scripts (CISO Review 2026-01-12)

Key Responsibilities:
    - PageViewTrackingMiddleware: Record page views for authenticated users
    - ContentSecurityPolicyMiddleware: Add CSP headers to responses
    - CSPNonceMiddleware: Generate per-request nonces for inline scripts

Design Notes:
    - Only tracks GET requests (not API calls, form submissions)
    - Excludes static files, media, and API endpoints
    - Requires a page_title in the template context (via mixin or context processor)
    - Uses the response's title tag if no explicit page_title is set
    - CSP nonces are generated per-request and stored on request.csp_nonce

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

import base64
import logging
import os
import re


class NoCacheHTMLMiddleware:
    """
    Prevents caching of HTML responses to avoid FOUC on navigation.

    Sets Cache-Control headers on HTML responses to prevent CDN/browser
    from caching HTML pages, which can cause Flash of Unstyled Content
    when navigating between pages.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only affect HTML responses
        content_type = response.get('Content-Type', '')
        if 'text/html' in content_type:
            # Prevent caching of HTML pages and disable bfcache
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            # Vary header helps prevent incorrect cache hits
            response['Vary'] = 'Accept-Encoding, Cookie'

        return response


class PageViewTrackingMiddleware:
    """
    Middleware to track page views for the Favorites/Recent feature.

    Only tracks:
    - GET requests
    - Authenticated users
    - HTML responses (not API calls)
    - Non-exempt paths (not static, media, api)

    Page titles are extracted from the HTML <title> tag.
    """

    EXEMPT_PATH_PREFIXES = [
        '/static/',
        '/media/',
        '/api/',
        '/admin/',
        '/accounts/',
        '/__debug__/',
    ]

    EXEMPT_PATH_EXACT = [
        '/',
        '/favicon.ico',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only track GET requests
        if request.method != 'GET':
            return response

        # Only track for authenticated users
        if not request.user.is_authenticated:
            return response

        # Only track successful HTML responses
        if response.status_code != 200:
            return response

        content_type = response.get('Content-Type', '')
        if 'text/html' not in content_type:
            return response

        # Skip exempt paths
        path = request.path
        if path in self.EXEMPT_PATH_EXACT:
            return response
        if any(path.startswith(prefix) for prefix in self.EXEMPT_PATH_PREFIXES):
            return response

        # Extract title from HTML
        title = self._extract_title(response)
        if title:
            # Import here to avoid circular imports
            from apps.core.models import PageView
            PageView.record_view(request.user, path, title)

        return response

    def _extract_title(self, response):
        """
        Extract the page title from the HTML response.

        Returns the title text, cleaned up and stripped of the site name suffix.
        """
        try:
            # Get response content - handle streaming responses
            if hasattr(response, 'content'):
                content = response.content.decode('utf-8', errors='ignore')
            else:
                return None

            # Find the title tag
            match = re.search(r'<title[^>]*>([^<]+)</title>', content, re.IGNORECASE)
            if not match:
                return None

            title = match.group(1).strip()

            # Remove common suffixes like " | Whole Life Journey" or " - Site Name"
            for separator in [' | ', ' - ', ' – ']:
                if separator in title:
                    title = title.split(separator)[0].strip()
                    break

            # Limit title length
            if len(title) > 200:
                title = title[:197] + '...'

            return title if title else None

        except Exception:
            return None


def generate_csp_nonce():
    """
    Generate a cryptographically secure nonce for CSP.

    Returns a base64-encoded 16-byte random value.
    """
    return base64.b64encode(os.urandom(16)).decode('utf-8')


class CSPNonceMiddleware:
    """
    Middleware to generate a CSP nonce for each request.

    CISO Review 2026-01-12: Generate per-request nonces for inline scripts.

    The nonce is stored on request.csp_nonce and can be accessed:
    - In templates via {{ request.csp_nonce }} or {{ csp_nonce }}
    - In views via request.csp_nonce

    Usage in templates:
        <script nonce="{{ csp_nonce }}">
            // Your inline JavaScript
        </script>

    Note: This middleware must run BEFORE ContentSecurityPolicyMiddleware
    in the MIDDLEWARE list.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Generate a unique nonce for this request
        request.csp_nonce = generate_csp_nonce()
        return self.get_response(request)


class ContentSecurityPolicyMiddleware:
    """
    Middleware to add Content-Security-Policy headers for XSS protection.

    CISO Review 2026-01-12: Updated to use nonces for stricter security.

    CSP restricts which sources can load scripts, styles, images, etc.
    This helps prevent XSS attacks even if malicious content is injected.

    Policy:
    - default-src 'self': Only allow resources from same origin by default
    - script-src: Allow scripts with matching nonce, self, and CDNs
      (jsdelivr, unpkg for HTMX, tailwindcss, plaid, google)
    - style-src: Allow inline styles (still uses unsafe-inline for CSS)
      (includes tailwindcss for billing pages)
    - img-src: Allow self, data URIs, and common image hosts
    - font-src: Allow self and Google Fonts
    - connect-src: Allow self and API endpoints
    - frame-ancestors 'self': Prevent clickjacking (same as X-Frame-Options)

    Nonce Support:
    - Scripts must include nonce="{{ csp_nonce }}" to execute
    - 'unsafe-inline' is kept as fallback for legacy compatibility
    - 'strict-dynamic' allows nonced scripts to load other scripts
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only add CSP to HTML responses
        content_type = response.get('Content-Type', '')
        if 'text/html' not in content_type:
            return response

        # Get the nonce from the request (set by CSPNonceMiddleware)
        nonce = getattr(request, 'csp_nonce', None)

        # Build CSP policy
        # CISO Review 2026-01-12: Nonce-based CSP for XSS protection
        # All inline <script> and <style> tags have nonce="{{ csp_nonce }}" attributes.
        # When nonce is present, browsers ignore 'unsafe-inline' - this is by design.
        # External CDNs are explicitly allowed so they don't need nonces.
        if nonce:
            # Nonce-based CSP for scripts provides XSS protection
            # Note: 'unsafe-inline' is ignored when nonce is present (browser spec)
            script_src = f"script-src 'self' 'nonce-{nonce}' 'unsafe-eval' https://cdn.jsdelivr.net https://unpkg.com https://cdn.tailwindcss.com https://cdn.plaid.com https://www.google.com https://www.gstatic.com"
            # Style-src keeps 'unsafe-inline' to prevent FOUC (Flash of Unstyled Content)
            # Nonce-based styles cause rendering delays; inline styles are lower XSS risk
            style_src = "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.tailwindcss.com"
        else:
            # Fallback if nonce middleware didn't run (shouldn't happen in normal operation)
            script_src = "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://unpkg.com https://cdn.tailwindcss.com https://cdn.plaid.com https://www.google.com https://www.gstatic.com"
            style_src = "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.tailwindcss.com"

        csp_directives = [
            "default-src 'self'",
            script_src,
            style_src,
            "img-src 'self' data: https: blob:",
            "font-src 'self' https://fonts.gstatic.com",
            "connect-src 'self' https://www.google.com",
            "frame-src 'self' https://www.google.com",
            "frame-ancestors 'self'",
            "base-uri 'self'",
            "form-action 'self'",
        ]

        csp_header = "; ".join(csp_directives)

        # CSP enforcement mode enabled 2026-01-12 (CISO Review)
        # Previously in Report-Only mode for testing (2026-01-06 to 2026-01-12)
        response['Content-Security-Policy'] = csp_header

        return response


class APIRequestLoggingMiddleware:
    """
    Logs API requests for security monitoring and anomaly detection.

    CISO Review 2026-01-12: Added for security requirement
    "API request logging with anomaly detection"

    Features:
    - Logs all requests to /api/* endpoints
    - Captures timing, status codes, and error messages
    - Performs real-time anomaly detection
    - Triggers alerts for suspicious patterns

    Configuration:
    - WLJ_SETTINGS['API_LOGGING_ENABLED']: Enable/disable logging (default: True)
    - WLJ_SETTINGS['API_LOGGING_PATHS']: List of path prefixes to log (default: ['/api/', '/admin-console/api/'])
    - WLJ_SETTINGS['API_ANOMALY_DETECTION']: Enable real-time anomaly detection (default: True)

    Note: This middleware should be placed after AuthenticationMiddleware
    so that request.user is available.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger('wlj.security')

    def __call__(self, request):
        from django.conf import settings as django_settings
        import time
        import uuid

        # Check if API logging is enabled
        wlj_settings = getattr(django_settings, 'WLJ_SETTINGS', {})
        if not wlj_settings.get('API_LOGGING_ENABLED', True):
            return self.get_response(request)

        # Check if this path should be logged
        log_paths = wlj_settings.get('API_LOGGING_PATHS', ['/api/', '/admin-console/api/'])
        should_log = any(request.path.startswith(prefix) for prefix in log_paths)

        if not should_log:
            return self.get_response(request)

        # Generate request ID for correlation
        request.request_id = str(uuid.uuid4())

        # Record start time
        start_time = time.time()

        # Get response
        response = self.get_response(request)

        # Calculate response time
        response_time_ms = int((time.time() - start_time) * 1000)

        # Log the request (async to avoid blocking)
        try:
            self._log_request(request, response, response_time_ms, wlj_settings)
        except Exception as e:
            # Don't let logging errors break the request
            self.logger.error(f"API logging failed: {e}")

        return response

    def _log_request(self, request, response, response_time_ms, wlj_settings):
        """Log the API request and check for anomalies."""
        from apps.core.models import APIRequestLog
        from apps.core.security_logging import log_security_event

        # Extract error message if present
        error_message = ""
        if response.status_code >= 400:
            try:
                import json
                content = response.content.decode('utf-8')
                data = json.loads(content)
                error_message = data.get('error', data.get('detail', ''))
            except Exception:
                pass

        # Create log entry
        log_entry = APIRequestLog.log_request(
            request=request,
            response=response,
            response_time_ms=response_time_ms,
            error_message=error_message
        )

        # Real-time anomaly detection (if enabled)
        if wlj_settings.get('API_ANOMALY_DETECTION', True):
            self._check_realtime_anomalies(request, log_entry)

    def _check_realtime_anomalies(self, request, log_entry):
        """
        Perform real-time anomaly checks on the current request.

        This checks:
        1. Burst detection: Too many requests from same IP in short window
        2. Auth failure spike: Multiple auth failures in short window
        """
        from apps.core.models import APIRequestLog
        from apps.core.rate_limiting import get_client_ip
        from apps.core.security_logging import log_security_event
        from django.utils import timezone
        from datetime import timedelta

        ip = get_client_ip(request)
        now = timezone.now()
        five_min_ago = now - timedelta(minutes=5)

        # Check for burst (>50 requests in 5 minutes from same IP)
        recent_count = APIRequestLog.objects.filter(
            ip_address=ip,
            created_at__gte=five_min_ago
        ).count()

        if recent_count > 50:
            # Flag as anomaly
            log_entry.is_anomaly = True
            log_entry.anomaly_reason = f"Burst detected: {recent_count} requests in 5 minutes"
            log_entry.anomaly_score = min(1.0, recent_count / 100)
            log_entry.save()

            # Log security event
            log_security_event(
                event_type='api_anomaly',
                details={
                    'ip_address': ip,
                    'reason': log_entry.anomaly_reason,
                    'score': log_entry.anomaly_score,
                    'request_id': log_entry.request_id,
                    'path': request.path,
                },
                request=request
            )

        # Check for auth failure spike (>5 auth failures in 5 minutes)
        if log_entry.status_code in [401, 403]:
            auth_failures = APIRequestLog.objects.filter(
                ip_address=ip,
                status_code__in=[401, 403],
                created_at__gte=five_min_ago
            ).count()

            if auth_failures > 5:
                log_entry.is_anomaly = True
                log_entry.anomaly_reason = f"Auth failure spike: {auth_failures} failures in 5 minutes"
                log_entry.anomaly_score = min(1.0, auth_failures / 15)
                log_entry.save()

                log_security_event(
                    event_type='api_anomaly',
                    details={
                        'ip_address': ip,
                        'reason': log_entry.anomaly_reason,
                        'score': log_entry.anomaly_score,
                        'request_id': log_entry.request_id,
                        'path': request.path,
                        'type': 'auth_failure_spike',
                    },
                    request=request
                )
