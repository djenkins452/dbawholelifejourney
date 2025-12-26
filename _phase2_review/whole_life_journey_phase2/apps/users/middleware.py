"""
User Middleware - Enforce terms acceptance and other user-related checks.
"""

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class TermsAcceptanceMiddleware:
    """
    Middleware to ensure authenticated users have accepted the current terms.
    
    If a user hasn't accepted the current terms version, they are redirected
    to the terms acceptance page. This ensures compliance when terms are updated.
    
    Exempt paths:
    - Terms page itself
    - Logout
    - Static files
    - Admin (admins can manage terms)
    """

    EXEMPT_PATHS = [
        "/terms/",
        "/accounts/logout/",
        "/admin/",
        "/static/",
        "/media/",
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only check for authenticated users
        if request.user.is_authenticated:
            # Skip exempt paths
            if not any(request.path.startswith(path) for path in self.EXEMPT_PATHS):
                # Check if user has accepted current terms
                if not request.user.has_accepted_current_terms:
                    # Allow POST to terms acceptance
                    if request.path == reverse("users:accept_terms"):
                        pass  # Let it through to process acceptance
                    else:
                        return redirect("users:accept_terms")

        response = self.get_response(request)
        return response
