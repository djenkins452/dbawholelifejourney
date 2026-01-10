"""
Whole Life Journey - Core Middleware

Project: Whole Life Journey
Path: apps/core/middleware.py
Purpose: Track page views for the Favorites feature and security headers

Description:
    This middleware provides:
    - Page view tracking for the Favorites menu
    - Content Security Policy (CSP) headers for XSS protection

Key Responsibilities:
    - PageViewTrackingMiddleware: Record page views for authenticated users
    - ContentSecurityPolicyMiddleware: Add CSP headers to responses

Design Notes:
    - Only tracks GET requests (not API calls, form submissions)
    - Excludes static files, media, and API endpoints
    - Requires a page_title in the template context (via mixin or context processor)
    - Uses the response's title tag if no explicit page_title is set

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

import re


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


class ContentSecurityPolicyMiddleware:
    """
    Middleware to add Content-Security-Policy headers for XSS protection.

    CSP restricts which sources can load scripts, styles, images, etc.
    This helps prevent XSS attacks even if malicious content is injected.

    Policy:
    - default-src 'self': Only allow resources from same origin by default
    - script-src: Allow inline scripts (for htmx, chart.js), self, and CDNs
    - style-src: Allow inline styles (for dynamic styling) and self
    - img-src: Allow self, data URIs, and common image hosts
    - font-src: Allow self and Google Fonts
    - connect-src: Allow self and API endpoints
    - frame-ancestors 'self': Prevent clickjacking (same as X-Frame-Options)
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only add CSP to HTML responses
        content_type = response.get('Content-Type', '')
        if 'text/html' not in content_type:
            return response

        # Build CSP policy
        # Note: 'unsafe-inline' is needed for htmx attributes and inline event handlers
        # In a future iteration, consider using nonces for stricter security
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://www.google.com https://www.gstatic.com",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "img-src 'self' data: https: blob:",
            "font-src 'self' https://fonts.gstatic.com",
            "connect-src 'self' https://www.google.com",
            "frame-src 'self' https://www.google.com",
            "frame-ancestors 'self'",
            "base-uri 'self'",
            "form-action 'self'",
        ]

        csp_header = "; ".join(csp_directives)

        # TODO(2026-01-25): After testing period, change to enforcing mode:
        # 1. Check browser console for CSP violation reports
        # 2. If no violations, change 'Content-Security-Policy-Report-Only' to 'Content-Security-Policy'
        # 3. Remove this TODO comment
        # Added: 2026-01-06 by Claude Code
        response['Content-Security-Policy-Report-Only'] = csp_header

        return response
