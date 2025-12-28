"""
Core Views - Landing page and static content pages.

apps/core/views.py
"""
import logging

from django.conf import settings
from django.shortcuts import redirect, render
from django.views.generic import TemplateView

logger = logging.getLogger(__name__)


class LandingPageView(TemplateView):
    """
    Landing page for unauthenticated users.
    
    Authenticated users are redirected to their dashboard.
    """

    template_name = "core/landing.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("dashboard:home")
        return super().dispatch(request, *args, **kwargs)


class TermsOfServiceView(TemplateView):
    """
    Terms of Service page.
    
    Displays the current terms that users must accept.
    Includes AI disclaimer and liability information.
    """

    template_name = "core/terms.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["terms_version"] = settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        return context


class PrivacyPolicyView(TemplateView):
    """
    Privacy Policy page.
    """

    template_name = "core/privacy.html"


class AboutView(TemplateView):
    """
    About page - explains the mission and values of Whole Life Journey.
    """

    template_name = "core/about.html"


# =============================================================================
# CUSTOM ERROR HANDLERS
# =============================================================================

def custom_404(request, exception=None):
    """
    Custom 404 error handler.

    Returns a user-friendly 404 page without exposing internal details.
    """
    return render(request, '404.html', status=404)


def custom_500(request):
    """
    Custom 500 error handler.

    Logs the error and returns a user-friendly error page.
    Note: The actual exception is logged by Django's default handler.
    """
    logger.error(f"500 error occurred for path: {request.path}")
    return render(request, '500.html', status=500)
