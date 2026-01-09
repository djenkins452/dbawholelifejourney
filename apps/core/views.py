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
    - RestoreItemView: API to restore soft-deleted items (undo)

Security Notes:
    - Error handlers don't expose internal details
    - Release notes API requires authentication
    - Restore API requires authentication and ownership verification

Dependencies:
    - django.contrib.auth.mixins for LoginRequiredMixin
    - apps.core.models for ReleaseNote, UserReleaseNoteView

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""
import json
import logging

from django.apps import apps
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import ListView, TemplateView

from django.contrib import messages

from .models import FavoritePage, PageView, ReleaseNote, UserReleaseNoteView

logger = logging.getLogger(__name__)


# =============================================================================
# UNDO DELETE MIXIN
# =============================================================================


class UndoDeleteMixin:
    """
    Mixin for delete views to support the undo toast notification system.

    When the request is an AJAX request (has X-Requested-With: XMLHttpRequest),
    the view returns JSON instead of redirecting. This allows the JavaScript
    to show an undo toast notification.

    Usage:
        class MyDeleteView(LoginRequiredMixin, UndoDeleteMixin, View):
            model = MyModel
            item_type = 'myapp.mymodel'
            item_name = 'item'
            success_url = 'myapp:list'

            def get_object(self):
                return get_object_or_404(
                    MyModel.objects.filter(user=self.request.user),
                    pk=self.kwargs['pk']
                )

    Attributes:
        model: The model class being deleted
        item_type: String identifier for restore API (e.g., 'health.weightentry')
        item_name: Human-readable name for messages (e.g., 'weight entry')
        success_url: URL name to redirect to after delete (for non-AJAX)
    """

    model = None
    item_type = None
    item_name = 'item'
    success_url = None

    def get_object(self):
        """Override this to fetch the object to delete."""
        raise NotImplementedError("Subclasses must implement get_object()")

    def get_success_url(self):
        """Get the URL to redirect to after deletion."""
        if self.success_url:
            from django.urls import reverse
            return reverse(self.success_url)
        return '/'

    def get_item_type(self):
        """Get the item type string for the restore API."""
        if self.item_type:
            return self.item_type
        if self.model:
            return f"{self.model._meta.app_label}.{self.model._meta.model_name}"
        return None

    def is_ajax_request(self, request):
        """Check if this is an AJAX request."""
        return request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        item_id = obj.pk
        item_type = self.get_item_type()

        # Perform soft delete
        obj.soft_delete()

        # For AJAX requests, return JSON
        if self.is_ajax_request(request):
            return JsonResponse({
                'success': True,
                'item_id': item_id,
                'item_type': item_type,
                'message': f'{self.item_name.title()} deleted',
            })

        # For regular requests, show message and redirect
        messages.success(request, f"{self.item_name.title()} deleted.")
        return redirect(self.get_success_url())


# =============================================================================
# SAVE & ADD ANOTHER MIXIN
# =============================================================================


class SaveAddAnotherMixin:
    """
    Mixin for CreateViews to add "Save & Add Another" functionality.

    When the user clicks "Save & Add Another", the form is saved and the user
    is redirected back to the create page with a success message.

    Usage:
        1. Add this mixin to your CreateView (before CreateView in MRO)
        2. Add to your form template:
           <button type="submit" name="save_add_another" class="btn btn-secondary">
               Save &amp; Add Another
           </button>
        3. Set save_add_another_message to customize the success message

    Attributes:
        save_add_another_message: Message shown after saving. Use {title} as placeholder.
                                  Default: "{title} created. Add another!"
    """

    save_add_another_message = "{title} created. Add another!"

    def form_valid(self, form):
        """Handle form submission, checking for save_add_another button."""
        response = super().form_valid(form)

        # Check if "Save & Add Another" was clicked
        if 'save_add_another' in self.request.POST:
            # Get a title/name for the created object
            obj = form.instance
            title = getattr(obj, 'title', None) or getattr(obj, 'name', None) or str(obj)

            # Show success message
            message = self.save_add_another_message.format(title=title)
            messages.success(self.request, message)

            # Redirect back to create page (current URL)
            return redirect(self.request.path)

        return response


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


# =============================================================================
# FAVORITES VIEWS
# =============================================================================


class FavoriteToggleView(LoginRequiredMixin, View):
    """
    API endpoint to toggle a page as favorite.

    POST with:
    - url: The URL to favorite/unfavorite
    - title: Display title for the favorite

    Returns JSON with:
    - is_favorite: boolean indicating current state
    - error: error message if any (e.g., max reached)
    """

    def post(self, request, *args, **kwargs):
        import json
        try:
            data = json.loads(request.body)
            url = data.get('url', '').strip()
            title = data.get('title', '').strip()

            if not url:
                return JsonResponse({'error': 'URL is required'}, status=400)
            if not title:
                return JsonResponse({'error': 'Title is required'}, status=400)

            is_favorite, error = FavoritePage.toggle(request.user, url, title)

            response_data = {'is_favorite': is_favorite}
            if error:
                response_data['error'] = error

            return JsonResponse(response_data)

        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)


class FavoriteCheckView(LoginRequiredMixin, View):
    """
    API endpoint to check if a URL is favorited.

    GET with:
    - url: The URL to check

    Returns JSON with:
    - is_favorite: boolean
    """

    def get(self, request, *args, **kwargs):
        url = request.GET.get('url', '').strip()
        if not url:
            return JsonResponse({'error': 'URL is required'}, status=400)

        is_favorite = FavoritePage.is_favorite(request.user, url)
        return JsonResponse({'is_favorite': is_favorite})


class FavoritesMenuDataView(LoginRequiredMixin, View):
    """
    API endpoint to get favorites menu data.

    Returns JSON with:
    - favorites: list of favorite pages
    - most_used: list of most frequently visited pages (to fill remaining slots)
    - favorites_count: number of favorites
    """

    def get(self, request, *args, **kwargs):
        # Get favorites (up to 10)
        favorites = FavoritePage.get_favorites_for_user(
            request.user,
            limit=FavoritePage.MAX_FAVORITES
        )

        # Calculate how many most-used pages to show
        favorites_count = favorites.count()
        most_used_slots = FavoritePage.MAX_FAVORITES - favorites_count

        # Get most-used pages, excluding favorites
        most_used = []
        if most_used_slots > 0:
            favorite_urls = list(favorites.values_list('url', flat=True))
            most_used = PageView.get_most_used_for_user(
                request.user,
                limit=most_used_slots,
                exclude_urls=favorite_urls
            )

        return JsonResponse({
            'favorites': [
                {'url': f.url, 'title': f.title}
                for f in favorites
            ],
            'most_used': [
                {'url': r.url, 'title': r.title}
                for r in most_used
            ],
            'favorites_count': favorites_count,
        })


# =============================================================================
# RESTORE (UNDO DELETE) VIEW
# =============================================================================


class RestoreItemView(LoginRequiredMixin, View):
    """
    API endpoint to restore a soft-deleted item.

    Used by the undo toast notification system to restore items
    within a short window after deletion.

    POST with JSON body:
    - item_type: Model identifier (e.g., 'health.weightentry')
    - item_id: Primary key of the deleted item

    Returns JSON with:
    - success: boolean
    - error: error message if any

    Security:
    - Requires authentication
    - Verifies the user owns the item being restored
    - Only works on soft-deleted items (status='deleted')
    """

    # Whitelist of models that support restore
    ALLOWED_MODELS = {
        # Health models
        'health.weightentry',
        'health.fastingwindow',
        'health.heartrateentry',
        'health.bloodpressureentry',
        'health.bloodoxygenentry',
        'health.glucoseentry',
        'health.workoutsession',
        'health.workouttemplate',
        'health.medicine',
        'health.medicineentry',
        'health.foodentry',
        'health.customfood',
        'health.medicalprovider',
        'health.providerstaff',
        # Journal models
        'journal.journalentry',
        # Faith models
        'faith.prayerrequest',
        'faith.biblestudy',
        'faith.savedverse',
        'faith.blessing',
        'faith.faithquestion',
        # Purpose models
        'purpose.goal',
        'purpose.goalstep',
        'purpose.habit',
        # Life models
        'life.note',
        'life.task',
        'life.reminder',
        'life.bookmark',
        'life.contact',
        'life.importantdate',
        # Finance models
        'finance.financialaccount',
        'finance.financialtransaction',
        'finance.budget',
        'finance.recurringexpense',
    }

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            item_type = data.get('item_type', '').lower().strip()
            item_id = data.get('item_id')

            if not item_type:
                return JsonResponse(
                    {'success': False, 'error': 'item_type is required'},
                    status=400
                )

            if not item_id:
                return JsonResponse(
                    {'success': False, 'error': 'item_id is required'},
                    status=400
                )

            # Security: Only allow whitelisted models
            if item_type not in self.ALLOWED_MODELS:
                logger.warning(
                    f"Restore attempt for non-whitelisted model: {item_type} "
                    f"by user {request.user.id}"
                )
                return JsonResponse(
                    {'success': False, 'error': 'Invalid item type'},
                    status=400
                )

            # Get the model class
            try:
                app_label, model_name = item_type.split('.')
                model = apps.get_model(app_label, model_name)
            except (ValueError, LookupError):
                return JsonResponse(
                    {'success': False, 'error': 'Invalid item type'},
                    status=400
                )

            # Check if model has soft delete support
            if not hasattr(model, 'restore'):
                return JsonResponse(
                    {'success': False, 'error': 'Model does not support restore'},
                    status=400
                )

            # Get the item - use all_objects to include deleted items
            try:
                if hasattr(model, 'all_objects'):
                    item = model.all_objects.get(pk=item_id)
                else:
                    item = model.objects.get(pk=item_id)
            except model.DoesNotExist:
                return JsonResponse(
                    {'success': False, 'error': 'Item not found'},
                    status=404
                )

            # Security: Verify ownership
            if hasattr(item, 'user_id'):
                if item.user_id != request.user.id:
                    logger.warning(
                        f"Unauthorized restore attempt: user {request.user.id} "
                        f"tried to restore {item_type} {item_id} owned by {item.user_id}"
                    )
                    return JsonResponse(
                        {'success': False, 'error': 'Item not found'},
                        status=404
                    )
            elif hasattr(item, 'user'):
                if item.user != request.user:
                    logger.warning(
                        f"Unauthorized restore attempt: user {request.user.id} "
                        f"tried to restore {item_type} {item_id}"
                    )
                    return JsonResponse(
                        {'success': False, 'error': 'Item not found'},
                        status=404
                    )

            # Verify item is actually deleted
            if hasattr(item, 'status') and item.status != 'deleted':
                return JsonResponse(
                    {'success': False, 'error': 'Item is not deleted'},
                    status=400
                )

            # Restore the item
            item.restore()

            logger.info(
                f"Item restored: {item_type} {item_id} by user {request.user.id}"
            )

            return JsonResponse({'success': True})

        except json.JSONDecodeError:
            return JsonResponse(
                {'success': False, 'error': 'Invalid JSON'},
                status=400
            )


# =============================================================================
# SEARCH HISTORY VIEWS
# =============================================================================


class SearchHistoryGetView(LoginRequiredMixin, View):
    """
    API endpoint to get the user's search history.

    GET returns JSON with:
    - history: list of recent search queries (max 10)
    """

    def get(self, request, *args, **kwargs):
        try:
            preferences = request.user.preferences
            history = preferences.search_history or []
        except Exception:
            history = []

        return JsonResponse({'history': history})


class SearchHistorySaveView(LoginRequiredMixin, View):
    """
    API endpoint to save a search query to history.

    POST with JSON body:
    - query: The search query to save

    Returns JSON with:
    - success: boolean
    - history: updated list of search queries

    Behavior:
    - Adds query to the front of the list
    - Removes duplicates (case-insensitive)
    - Limits to 10 items
    - Ignores empty queries or queries under 2 characters
    """

    MAX_HISTORY_ITEMS = 10

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            query = data.get('query', '').strip()

            # Ignore empty or too-short queries
            if len(query) < 2:
                return JsonResponse({
                    'success': False,
                    'error': 'Query too short'
                }, status=400)

            try:
                preferences = request.user.preferences
            except Exception:
                return JsonResponse({
                    'success': False,
                    'error': 'User preferences not found'
                }, status=500)

            # Get current history
            history = preferences.search_history or []

            # Remove any existing instance (case-insensitive)
            history = [h for h in history if h.lower() != query.lower()]

            # Add new query to front
            history.insert(0, query)

            # Limit to max items
            history = history[:self.MAX_HISTORY_ITEMS]

            # Save
            preferences.search_history = history
            preferences.save(update_fields=['search_history'])

            return JsonResponse({
                'success': True,
                'history': history
            })

        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON'
            }, status=400)


class SearchHistoryClearView(LoginRequiredMixin, View):
    """
    API endpoint to clear the user's search history.

    POST returns JSON with:
    - success: boolean
    """

    def post(self, request, *args, **kwargs):
        try:
            preferences = request.user.preferences
            preferences.search_history = []
            preferences.save(update_fields=['search_history'])
            return JsonResponse({'success': True})
        except Exception as e:
            logger.error(f"Error clearing search history: {e}")
            return JsonResponse({
                'success': False,
                'error': 'Failed to clear history'
            }, status=500)
