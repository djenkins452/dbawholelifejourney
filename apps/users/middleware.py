"""
User Middleware - Enforce terms acceptance and onboarding completion.
"""

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


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
        "/users/onboarding/",
        "/users/accept-terms/",
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
