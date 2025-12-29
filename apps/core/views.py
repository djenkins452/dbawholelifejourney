"""
Whole Life Journey - Core Views

Project: Whole Life Journey
Path: apps/core/views.py
Purpose: Landing page, static content pages, and system-wide API endpoints

Description:
    This module contains views for the public-facing pages (landing, terms,
    privacy, about), custom error handlers, and the What's New release notes
    feature API endpoints.

Key Responsibilities:
    - LandingPageView: Public landing page, redirects authenticated users
    - TermsOfServiceView: Terms of service with version tracking
    - PrivacyPolicyView: Privacy policy page
    - AboutView: About page explaining the app's mission
    - custom_404/custom_500: User-friendly error pages
    - WhatsNewCheckView: API to check for unseen release notes
    - WhatsNewDismissView: API to mark release notes as seen
    - WhatsNewListView: Full page listing of all release notes

Security Notes:
    - Error handlers don't expose internal details
    - Release notes API requires authentication

Dependencies:
    - django.contrib.auth.mixins for LoginRequiredMixin
    - apps.core.models for ReleaseNote, UserReleaseNoteView

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import ListView, TemplateView

from .models import ReleaseNote, UserReleaseNoteView

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


# =============================================================================
# WHAT'S NEW / RELEASE NOTES VIEWS
# =============================================================================


class WhatsNewCheckView(LoginRequiredMixin, View):
    """
    API endpoint to check if there are unseen release notes.

    Returns JSON with:
    - has_unseen: boolean
    - count: number of unseen notes
    - notes: list of unseen notes (title, description, type, date)

    Used by JavaScript to decide whether to show the popup.
    """

    def get(self, request, *args, **kwargs):
        unseen_notes = ReleaseNote.get_unseen_for_user(request.user)

        # Convert to list for JSON
        notes_data = [
            {
                'id': note.id,
                'title': note.title,
                'description': note.description,
                'entry_type': note.entry_type,
                'type_display': note.get_entry_type_display(),
                'icon': note.get_icon(),
                'release_date': note.release_date.isoformat(),
                'is_major': note.is_major,
                'learn_more_url': note.learn_more_url,
            }
            for note in unseen_notes
        ]

        return JsonResponse({
            'has_unseen': len(notes_data) > 0,
            'count': len(notes_data),
            'notes': notes_data,
        })


class WhatsNewDismissView(LoginRequiredMixin, View):
    """
    API endpoint to mark release notes as seen.

    Called when user dismisses the What's New popup.
    Updates the user's last-viewed timestamp.
    """

    def post(self, request, *args, **kwargs):
        UserReleaseNoteView.mark_viewed(request.user)
        return JsonResponse({'success': True})


class WhatsNewListView(LoginRequiredMixin, ListView):
    """
    Full page view of all release notes.

    Users can view the complete history of release notes here.
    Accessible via link in the footer or from settings.
    """

    model = ReleaseNote
    template_name = 'core/whats_new_list.html'
    context_object_name = 'release_notes'
    paginate_by = 20

    def get_queryset(self):
        return ReleaseNote.get_published()
