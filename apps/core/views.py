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
from django.db import connection
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


# =============================================================================
# HEALTH CHECK ENDPOINT
# =============================================================================


class HealthCheckView(View):
    """
    Health check endpoint for monitoring services.

    Returns JSON with:
    - status: "healthy" or "unhealthy"
    - database: "connected" or error message
    - version: Current release/commit SHA if available

    Used by:
    - Railway for deployment health checks
    - External uptime monitors (UptimeRobot, Pingdom, etc.)
    - Load balancers for backend health

    This endpoint is public (no authentication required) and should
    respond quickly without hitting expensive resources.
    """

    def get(self, request, *args, **kwargs):
        import os
        health_status = {
            'status': 'healthy',
            'database': 'connected',
            'version': os.environ.get('RAILWAY_GIT_COMMIT_SHA', 'development')[:12],
        }

        # Check database connectivity
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
        except Exception as e:
            health_status['status'] = 'unhealthy'
            health_status['database'] = f'error: {str(e)[:100]}'
            return JsonResponse(health_status, status=503)

        return JsonResponse(health_status, status=200)


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


class MoreView(LoginRequiredMixin, TemplateView):
    """
    More screen - shows all enabled modules as tiles plus quick links.
    """

    template_name = "core/more.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Hardcoded module URLs - avoids any DB/route_name issues
        MODULE_URLS = {
            'journal': '/journal/',
            'health': '/health/',
            'faith': '/faith/',
            'life': '/life/',
            'purpose': '/purpose/',
            'finance': '/finance/',
            'capture': '/capture/',
        }

        modules = []
        try:
            from apps.users.models import UserModulePreference

            prefs = UserModulePreference.objects.filter(
                user=self.request.user,
                is_enabled=True,
                module__is_active=True,
            ).select_related('module').order_by('sort_order', 'module__default_order')

            for pref in prefs:
                modules.append({
                    'slug': pref.module.slug,
                    'name': pref.module.name,
                    'icon_svg': pref.module.icon_svg,
                    'url': MODULE_URLS.get(pref.module.slug, f'/{pref.module.slug}/'),
                })
        except Exception:
            pass

        context['modules'] = modules
        return context


class FavoritesHubView(LoginRequiredMixin, TemplateView):
    """
    Favorites hub - shows user's favorited pages as a tile grid.
    """

    template_name = "core/favorites_hub.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        from apps.core.models import FavoritePage

        # Get all user favorites
        favorites = FavoritePage.get_favorites_for_user(
            self.request.user,
            limit=FavoritePage.MAX_FAVORITES
        )

        context['favorites'] = favorites
        return context


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
    import sys
    import traceback
    exc_type, exc_value, exc_tb = sys.exc_info()
    if exc_type:
        tb_str = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.error(f"500 error occurred for path: {request.path}\n{tb_str}")
    else:
        logger.error(f"500 error occurred for path: {request.path} (no exception info available)")
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
# DEVELOPMENT NOTICE VIEWS
# =============================================================================


class DevelopmentNoticeCheckView(LoginRequiredMixin, View):
    """
    API endpoint to check if the development notice should be shown.

    Shows the notice if:
    - User has been registered for more than 48 hours
    - User hasn't dismissed the notice yet (development_notice_seen_at is None)

    Returns JSON with:
    - should_show: boolean
    """

    def get(self, request, *args, **kwargs):
        from datetime import timedelta
        from django.utils import timezone
        from apps.users.models import UserPreferences

        should_show = False

        try:
            # Get or create user preferences
            prefs, _ = UserPreferences.objects.get_or_create(user=request.user)

            # Check if notice hasn't been seen yet
            if prefs.development_notice_seen_at is None:
                # Check if user has been registered for more than 48 hours
                hours_since_signup = (timezone.now() - request.user.date_joined).total_seconds() / 3600
                if hours_since_signup >= 48:
                    should_show = True
        except Exception as e:
            logger.warning(f"Error checking development notice: {e}")

        return JsonResponse({'should_show': should_show})


class DevelopmentNoticeDismissView(LoginRequiredMixin, View):
    """
    API endpoint to dismiss the development notice.

    Called when user dismisses the modal.
    Sets development_notice_seen_at to the current time.
    """

    def post(self, request, *args, **kwargs):
        from django.utils import timezone
        from apps.users.models import UserPreferences

        try:
            prefs, _ = UserPreferences.objects.get_or_create(user=request.user)
            prefs.development_notice_seen_at = timezone.now()
            prefs.save(update_fields=['development_notice_seen_at'])
        except Exception as e:
            logger.warning(f"Error dismissing development notice: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

        return JsonResponse({'success': True})


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

            # Invalidate favorites cache since favorites changed
            from apps.core.context_processors import invalidate_favorites_cache
            invalidate_favorites_cache(request.user.id)

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


# =============================================================================
# 404 REPORTING
# =============================================================================


from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt


@method_decorator(csrf_exempt, name='dispatch')
class Report404View(View):
    """
    API endpoint to report 404 errors for tracking and fixing broken links.

    CSRF exempt because 404 pages don't have CSRF tokens.

    Accepts POST with JSON:
    - url: The URL that resulted in 404
    - referrer: The page that linked to the broken URL
    - timestamp: When the error occurred

    Creates an AdminTask for broken link investigation if the URL hasn't
    been reported recently.
    """

    def post(self, request, *args, **kwargs):

        try:
            data = json.loads(request.body)
            url = data.get('url', '')
            referrer = data.get('referrer', 'direct')

            if not url:
                return JsonResponse({'success': False, 'error': 'No URL provided'}, status=400)

            # Rate limit: Check if this URL was reported recently (using cache)
            from django.core.cache import cache
            cache_key = f"404_report_{hash(url)}"
            if cache.get(cache_key):
                # Already reported in the last hour
                return JsonResponse({'success': True, 'already_reported': True})

            # Log the 404
            logger.warning(f"404 reported: {url} (referrer: {referrer})")

            # Create AdminTask for the broken link
            try:
                from apps.admin_console.models import AdminTask, AdminProject, AdminProjectPhase

                # Get or create the "Bug Reports" project
                project, _ = AdminProject.objects.get_or_create(
                    name="Bug Reports",
                    defaults={
                        'description': 'Bug reports and broken links from users',
                        'status': 'open',
                        'priority': 2,
                    }
                )

                # Get Phase 1 for new tasks
                phase = AdminProjectPhase.objects.filter(phase_number=1).first()
                if not phase:
                    phase = AdminProjectPhase.objects.first()

                # Extract path from URL for the title
                from urllib.parse import urlparse
                parsed = urlparse(url)
                path = parsed.path or url

                # Check if we already have a task for this exact URL
                existing = AdminTask.objects.filter(
                    title__icontains=path,
                    project=project,
                    status__in=['backlog', 'ready', 'in_progress']
                ).first()

                if not existing and phase:
                    task = AdminTask(
                        title=f"404: {path[:70]}",
                        description={
                            "objective": f"Fix broken link: {path}",
                            "inputs": [
                                f"URL: {url}",
                                f"Referrer: {referrer}",
                                "Reported from 404 page"
                            ],
                            "actions": [
                                "Identify why this URL returns 404",
                                "Either create the missing page or fix the link",
                                "Test that the URL now works"
                            ],
                            "output": f"URL {path} no longer returns 404"
                        },
                        category='bug',
                        priority=3,  # Medium priority
                        status='backlog',
                        effort='S',
                        phase=phase,
                        project=project,
                        created_by='404_reporter',
                    )
                    task.save(skip_validation=False)
                    logger.info(f"Created AdminTask #{task.id} for 404: {path}")

            except Exception as e:
                logger.error(f"Failed to create AdminTask for 404: {e}")

            # Mark as reported (cache for 1 hour)
            cache.set(cache_key, True, timeout=3600)

            return JsonResponse({'success': True})

        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"Error in Report404View: {e}")
            return JsonResponse({'success': False, 'error': 'Server error'}, status=500)


# =============================================================================
# NOTIFICATION VIEWS
# =============================================================================


class NotificationListView(LoginRequiredMixin, ListView):
    """
    Full page notification center.

    Shows all notifications with filtering and mark-as-read functionality.
    """
    template_name = 'core/notifications.html'
    context_object_name = 'notifications'
    paginate_by = 25

    def get_queryset(self):
        from .models import Notification
        return Notification.objects.filter(
            user=self.request.user
        ).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .models import Notification
        context['unread_count'] = Notification.get_unread_count(self.request.user)
        return context


class NotificationUnreadView(LoginRequiredMixin, View):
    """
    API endpoint to get unread notifications for the bell dropdown.

    GET returns JSON with:
    - notifications: list of unread notifications (max 10)
    - unread_count: total unread count
    """

    def get(self, request, *args, **kwargs):
        from .models import Notification

        notifications = Notification.get_unread_for_user(request.user, limit=10)
        unread_count = Notification.get_unread_count(request.user)

        return JsonResponse({
            'notifications': [
                {
                    'id': n.id,
                    'category': n.category,
                    'title': n.title,
                    'message': n.message[:100] + '...' if len(n.message) > 100 else n.message,
                    'action_url': n.action_url,
                    'icon': n.get_icon(),
                    'created_at': n.created_at.isoformat(),
                    'is_read': n.is_read,
                }
                for n in notifications
            ],
            'unread_count': unread_count,
        })


class NotificationMarkReadView(LoginRequiredMixin, View):
    """
    API endpoint to mark a notification as read.

    POST to /notifications/<pk>/read/
    """

    def post(self, request, pk, *args, **kwargs):
        from .models import Notification

        try:
            notification = Notification.objects.get(pk=pk, user=request.user)
            notification.mark_read()
            return JsonResponse({'success': True})
        except Notification.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Not found'}, status=404)


class NotificationMarkAllReadView(LoginRequiredMixin, View):
    """
    API endpoint to mark all notifications as read.

    POST to /notifications/mark-all-read/
    """

    def post(self, request, *args, **kwargs):
        from .models import Notification

        count = Notification.mark_all_read(request.user)
        return JsonResponse({
            'success': True,
            'marked_count': count,
        })


class NotificationCountView(LoginRequiredMixin, View):
    """
    API endpoint to get unread notification count.

    GET returns JSON with:
    - unread_count: number of unread notifications
    """

    def get(self, request, *args, **kwargs):
        from .models import Notification

        unread_count = Notification.get_unread_count(request.user)
        return JsonResponse({'unread_count': unread_count})


class NotificationSetupCheckView(LoginRequiredMixin, View):
    """
    API endpoint to check if notification setup popup should be shown.

    GET returns JSON with:
    - should_show: boolean indicating if popup should be shown
    """

    def get(self, request, *args, **kwargs):
        try:
            prefs = request.user.preferences
            should_show = not prefs.notification_setup_shown
        except Exception:
            should_show = False

        return JsonResponse({'should_show': should_show})


class NotificationSetupDismissView(LoginRequiredMixin, View):
    """
    API endpoint to dismiss the notification setup popup.

    POST marks the popup as shown.
    """

    def post(self, request, *args, **kwargs):
        try:
            prefs = request.user.preferences
            prefs.notification_setup_shown = True
            prefs.save(update_fields=['notification_setup_shown'])
            return JsonResponse({'success': True})
        except Exception as e:
            logger.error(f"Error dismissing notification setup: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
