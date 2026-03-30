"""
Whole Life Journey - Core Context Processors

Project: Whole Life Journey
Path: apps/core/context_processors.py
Purpose: Add global variables to every template context

Description:
    Context processors run on every request and inject variables into
    the template context. This module provides site configuration and
    user-specific settings like theme and module toggles.

Key Responsibilities:
    - site_context: Inject site name, tagline, logo, favicon
    - theme_context: Inject user's theme, accent color, module toggles
    - favorites_context: Inject favorites data for navigation menu

Template Variables Provided:
    - site_name, site_tagline, site_logo_url, site_favicon_url
    - current_theme, accent_color
    - journal_enabled, faith_enabled, health_enabled, life_enabled, purpose_enabled, finance_enabled
    - user_today (date in user's timezone for date comparisons)
    - favorites_menu_data: favorites and recent pages for nav dropdown
    - is_current_page_favorite: whether current page is favorited

Dependencies:
    - apps.core.models.SiteConfiguration for site settings
    - apps.core.models.FavoritePage, PageView for favorites
    - apps.users.models.UserPreferences for user settings
    - apps.core.utils.get_user_today for timezone handling

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

import logging

from django.conf import settings
from django.core.cache import cache as _default_cache

logger = logging.getLogger(__name__)

# Cache for module enablement defaults (anonymous users)
_MODULE_DEFAULTS_CACHE_KEY = 'wlj:module_defaults'
_MODULE_DEFAULTS_CACHE_TTL = 300  # 5 minutes


def _get_module_enablement_defaults():
    """
    Get default module enablement from catalog for anonymous users.

    Returns dict of {slug: bool} based on catalog defaults.
    Cached for 5 minutes.
    """
    cached = _default_cache.get(_MODULE_DEFAULTS_CACHE_KEY)
    if cached is not None:
        return cached

    defaults = {}
    try:
        from apps.users.models import ModuleDefinition
        for m in ModuleDefinition.objects.filter(is_active=True):
            if m.always_available:
                defaults[m.slug] = True
            elif m.status == 'coming_soon':
                defaults[m.slug] = False
            else:
                defaults[m.slug] = m.default_enabled
        _default_cache.set(_MODULE_DEFAULTS_CACHE_KEY, defaults, _MODULE_DEFAULTS_CACHE_TTL)
    except Exception:
        # Pre-migration or table doesn't exist yet — use sensible defaults
        defaults = {
            'journal': True, 'health': True, 'faith': False, 'life': True,
            'purpose': True, 'finance': False, 'relationships': True,
            'capture': True, 'documents': True, 'meals': True,
        }
    return defaults


def site_context(request):
    """
    Add site-wide context variables.
    """
    from apps.core.models import SiteConfiguration

    try:
        config = SiteConfiguration.get_solo()
        return {
            'site_name': config.site_name or 'Whole Life Journey',
            'site_tagline': config.tagline or 'A calm space for reflection, growth, and faithful living.',
            'site_logo_url': config.logo.url if config.logo else None,
            'site_favicon_url': config.favicon.url if config.favicon else None,
            # reCAPTCHA v3 site key for anti-bot protection
            'recaptcha_site_key': settings.RECAPTCHA_V3_SITE_KEY,
        }
    except Exception:
        # DB connection may be dead — return safe defaults to prevent cascade
        logger.warning("site_context: DB unavailable, using defaults")
        return {
            'site_name': 'Whole Life Journey',
            'site_tagline': 'A calm space for reflection, growth, and faithful living.',
            'site_logo_url': None,
            'site_favicon_url': None,
            'recaptcha_site_key': getattr(settings, 'RECAPTCHA_V3_SITE_KEY', ''),
        }


def theme_context(request):
    """
    Add theme, accent color, and module flags to template context.
    """
    # Build module enablement defaults from catalog (deterministic source of truth)
    _module_defaults = _get_module_enablement_defaults()

    context = {
        'current_theme': 'minimal',
        'accent_color': None,
        # Module flags — defaults derived from catalog
        'journal_enabled': _module_defaults.get('journal', True),
        'faith_enabled': _module_defaults.get('faith', False),
        'health_enabled': _module_defaults.get('health', True),
        'life_enabled': _module_defaults.get('life', True),
        'purpose_enabled': _module_defaults.get('purpose', True),
        'finance_enabled': _module_defaults.get('finance', False),
        'relationships_enabled': _module_defaults.get('relationships', True),
        'capture_enabled': _module_defaults.get('capture', True),
        'documents_enabled': _module_defaults.get('documents', True),
        'meals_enabled': _module_defaults.get('meals', True),
        'sports_enabled': _module_defaults.get('sports', False),
        # AI flags - defaults
        'ai_enabled': False,
        'ai_data_consent': False,
        # Personal Assistant - defaults
        'personal_assistant_enabled': False,
        'personal_assistant_consent': False,
        # Sub-feature toggles - all True by default (opt-out model)
        'features': {
            'health': {},
            'organize': {},
            'goals': {},
            'faith': {},
            'journal': {},
        },
    }

    if request.user.is_authenticated:
        try:
            prefs = request.user.preferences
            context['current_theme'] = prefs.theme or 'minimal'
            context['accent_color'] = prefs.accent_color if prefs.accent_color else None
            # Custom theme colors (when theme='custom')
            if prefs.theme == 'custom':
                context['custom_theme_colors'] = {
                    'primary': prefs.custom_primary or '#6b7280',
                    'accent': prefs.custom_accent or '#6366f1',
                    'background': prefs.custom_background or '#f9fafb',
                    'surface': prefs.custom_surface or '#ffffff',
                    'text': prefs.custom_text or '#1f2937',
                }
            # Navigation behavior
            context['hide_nav_on_scroll'] = prefs.hide_nav_on_scroll
            context['desktop_nav_collapsed'] = prefs.desktop_nav_collapsed
            # Module toggles — derived from canonical module catalog
            from apps.core.module_catalog import is_module_enabled
            context['journal_enabled'] = is_module_enabled(request.user, 'journal')
            context['faith_enabled'] = is_module_enabled(request.user, 'faith')
            context['health_enabled'] = is_module_enabled(request.user, 'health')
            context['life_enabled'] = is_module_enabled(request.user, 'life')
            context['purpose_enabled'] = is_module_enabled(request.user, 'purpose')
            context['finance_enabled'] = is_module_enabled(request.user, 'finance')
            context['relationships_enabled'] = is_module_enabled(request.user, 'relationships')
            context['capture_enabled'] = is_module_enabled(request.user, 'capture')
            context['documents_enabled'] = is_module_enabled(request.user, 'documents')
            context['meals_enabled'] = is_module_enabled(request.user, 'meals')
            context['sports_enabled'] = is_module_enabled(request.user, 'sports')
            # AI toggles
            context['ai_enabled'] = prefs.ai_enabled
            context['ai_data_consent'] = prefs.ai_data_consent
            # Personal Assistant toggles
            context['personal_assistant_enabled'] = prefs.personal_assistant_enabled
            context['personal_assistant_consent'] = prefs.personal_assistant_consent
            context['cos_display_name'] = prefs.get_cos_name()
            context['cos_has_custom_name'] = bool(prefs.cos_display_name.strip())
            # Calibration state for chat auto-start
            context['calibration_active'] = False
            context['calibration_summary'] = ''
            context['calibration_welcome_shown'] = False
            context['calibration_stage'] = 0
            if prefs.personal_assistant_enabled:
                try:
                    from django.core.cache import cache as _cache
                    from apps.core.blueprint.cos_governance import (
                        get_calibration_state,
                        _gather_user_snapshot,
                        _build_data_summary,
                        CALIBRATION_QUESTIONS,
                    )
                    cal_state = get_calibration_state(request.user)
                    if cal_state and cal_state['active'] and not cal_state['paused']:
                        context['calibration_active'] = True
                        context['calibration_welcome_shown'] = cal_state.get(
                            'welcome_shown', False)
                        context['calibration_stage'] = cal_state.get('stage', 0)
                        # Show "I'm Ready" once they've done at least one full pass
                        context['calibration_can_finish'] = (
                            cal_state.get('stage', 0) >= len(CALIBRATION_QUESTIONS)
                        )
                        # Cache calibration summary (expensive: ~15 DB queries)
                        _cal_key = f'cal_summary:{request.user.id}'
                        _cal_summary = _cache.get(_cal_key)
                        if _cal_summary is None:
                            try:
                                snapshot = _gather_user_snapshot(request.user)
                                _cal_summary = _build_data_summary(snapshot)
                                _cache.set(_cal_key, _cal_summary, 600)  # 10 min
                            except Exception:
                                _cal_summary = ''
                        context['calibration_summary'] = _cal_summary
                except Exception:
                    pass
            # Cycle tracking - check if user has opted in (cached 24h)
            try:
                from django.core.cache import cache as _cache
                _cycle_key = f'cycle_tracking:{request.user.id}'
                _cycle_val = _cache.get(_cycle_key)
                if _cycle_val is None:
                    from apps.health.models import CycleSettings
                    cycle_settings = CycleSettings.objects.filter(
                        user=request.user, status='active'
                    ).first()
                    _cycle_val = (
                        cycle_settings.cycle_tracking_enabled if cycle_settings else False
                    )
                    _cache.set(_cycle_key, _cycle_val, 86400)  # 24h
                context['cycle_tracking_enabled'] = _cycle_val
            except Exception:
                context['cycle_tracking_enabled'] = False
            # Chief of Staff alignment badge (lightweight — for nav header)
            if prefs.personal_assistant_enabled:
                try:
                    from django.core.cache import cache as _cache
                    _align_key = f'alignment_score:{request.user.id}'
                    _cached_score = _cache.get(_align_key)
                    if _cached_score is not None:
                        context['command_brief'] = {
                            'active': True,
                            'alignment_score': _cached_score,
                        }
                    else:
                        from apps.core.blueprint.alignment_engine import (
                            compute_alignment_score,
                        )
                        alignment = compute_alignment_score(request.user)
                        _score = round(alignment.score)
                        _cache.set(_align_key, _score, 900)  # 15 min
                        context['command_brief'] = {
                            'active': True,
                            'alignment_score': _score,
                        }
                except Exception:
                    context['command_brief'] = {
                        'active': True,
                        'alignment_score': 100,
                    }
            # User's "today" in their timezone (for date comparisons in templates)
            from apps.core.utils import get_user_today
            context['user_today'] = get_user_today(request.user)
            # User's timezone for datetime conversion in templates
            context['user_timezone'] = prefs.timezone
            # Sub-feature toggles - build dict of feature states per module
            from apps.users.models import UserPreferences
            context['features'] = {
                'health': {key: prefs.is_feature_enabled('health', key)
                           for key in UserPreferences.HEALTH_FEATURES.keys()},
                'organize': {key: prefs.is_feature_enabled('organize', key)
                             for key in UserPreferences.ORGANIZE_FEATURES.keys()},
                'goals': {key: prefs.is_feature_enabled('goals', key)
                          for key in UserPreferences.GOALS_FEATURES.keys()},
                'faith': {key: prefs.is_feature_enabled('faith', key)
                          for key in UserPreferences.FAITH_FEATURES.keys()},
                'journal': {key: prefs.is_feature_enabled('journal', key)
                            for key in UserPreferences.JOURNAL_FEATURES.keys()},
            }
        except Exception:
            pass

    return context


def csp_nonce(request):
    """
    Add CSP nonce to template context for inline scripts.

    CISO Review 2026-01-12: Added for nonce-based CSP protection.

    The nonce is generated by CSPNonceMiddleware and stored on request.csp_nonce.
    Templates should use: <script nonce="{{ csp_nonce }}">...</script>

    Provides:
    - csp_nonce: The per-request nonce for Content-Security-Policy
    """
    return {
        'csp_nonce': getattr(request, 'csp_nonce', ''),
    }


def favorites_context(request):
    """
    Add favorites data to template context for navigation.

    Provides:
    - favorites_menu_data: dict with favorites list, most_used list, count
    - is_current_page_favorite: boolean for star toggle state

    Performance: Favorites data is cached per-user for 60 seconds.
    is_current_page_favorite is NOT cached since it's path-dependent.
    """
    context = {
        'favorites_menu_data': {
            'favorites': [],
            'most_used': [],
            'favorites_count': 0,
        },
        'is_current_page_favorite': False,
    }

    if not request.user.is_authenticated:
        return context

    # Skip for certain paths (API, static, etc.)
    path = request.path
    if any(path.startswith(p) for p in ['/api/', '/static/', '/media/', '/admin/']):
        return context

    try:
        from django.core.cache import cache
        from apps.core.models import FavoritePage, PageView

        # Cache favorites and most_used data (not path-dependent)
        cache_key = f'favorites_menu_user_{request.user.id}'
        cached_menu = cache.get(cache_key)

        if cached_menu is not None:
            context['favorites_menu_data'] = cached_menu
        else:
            # Get favorites (up to max)
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
                most_used = list(PageView.get_most_used_for_user(
                    request.user,
                    limit=most_used_slots,
                    exclude_urls=favorite_urls
                ))

            menu_data = {
                'favorites': list(favorites),
                'most_used': most_used,
                'favorites_count': favorites_count,
            }
            context['favorites_menu_data'] = menu_data

            # Cache for 60 seconds (shorter since favorites change more often)
            cache.set(cache_key, menu_data, 60)

        # Check if current page is a favorite (path-dependent, not cached)
        context['is_current_page_favorite'] = FavoritePage.is_favorite(request.user, path)

    except Exception:
        pass

    return context


def invalidate_favorites_cache(user_id):
    """
    Invalidate favorites cache for a specific user.

    Call this when user adds/removes favorites.
    """
    from django.core.cache import cache
    cache.delete(f'favorites_menu_user_{user_id}')


def quick_links_context(request):
    """
    Add user's external quick links to template context for profile dropdown.

    Provides:
    - quick_links_list: QuerySet of ExternalLink objects for the user

    Performance: Cached per-user for 60 seconds.
    """
    context = {
        'quick_links_list': [],
    }

    if not request.user.is_authenticated:
        return context

    # Skip for API, static, admin paths
    path = request.path
    if any(path.startswith(p) for p in ['/api/', '/static/', '/media/', '/admin/']):
        return context

    try:
        from django.core.cache import cache
        from apps.users.models import ExternalLink

        cache_key = f'quick_links_user_{request.user.id}'
        cached_links = cache.get(cache_key)

        if cached_links is not None:
            context['quick_links_list'] = cached_links
        else:
            links = list(ExternalLink.get_links_for_user(request.user).values(
                'id', 'name', 'url', 'mobile_app_url', 'icon',
                'category', 'open_in_new_tab',
            ))
            context['quick_links_list'] = links
            cache.set(cache_key, links, 60)
    except Exception:
        pass

    return context


def navigation_modules_context(request):
    """
    Add navigation module data to template context for mobile bottom nav and desktop left rail.

    Provides:
    - nav_modules: List of module dicts for mobile bottom nav (up to 3 enabled modules)
    - desktop_rail_modules: List of module dicts for desktop left rail (up to 8 enabled modules)
    - all_user_modules: All user module preferences (for More screen)
    - overflow_modules: Enabled modules beyond the first 3 (for mobile More screen)
    - desktop_overflow_modules: Enabled modules beyond the first 8 (for desktop More screen)

    Mobile bottom nav shows: Home + first 3 enabled modules + More (5 total for comfortable touch targets)
    Desktop left rail shows: Home + all enabled modules + More

    Performance: Uses caching to minimize database queries. Cache is invalidated when
    user updates module preferences.
    """
    context = {
        'nav_modules': [],
        'desktop_rail_modules': [],
        'all_user_modules': [],
        'overflow_modules': [],
        'desktop_overflow_modules': [],
    }

    if not request.user.is_authenticated:
        return context

    # Skip for API, static, admin paths to reduce unnecessary processing
    path = request.path
    if any(path.startswith(p) for p in ['/api/', '/static/', '/media/', '/admin/']):
        return context

    try:
        from django.core.cache import cache
        from apps.users.models import UserModulePreference

        # Cache key specific to this user
        cache_key = f'nav_modules_user_{request.user.id}'
        cached_data = cache.get(cache_key)

        if cached_data is not None:
            # Use cached navigation data
            return cached_data

        # Sync module preferences — creates missing prefs for new modules
        # initialize_for_user() is idempotent: skips modules that already exist
        UserModulePreference.initialize_for_user(request.user)

        # Get all user module preferences
        all_prefs = UserModulePreference.objects.filter(
            user=request.user,
            module__is_active=True,
        ).select_related('module').order_by('sort_order', 'module__default_order')

        # Build list of all modules with their state
        from django.urls import reverse, NoReverseMatch

        # Mapping of slug -> correct route name (fallback if DB has bad data)
        CORRECT_ROUTES = {
            'journal': 'journal:home',
            'health': 'health:landing',  # Landing page at /health/, not /health/physical/
            'faith': 'faith:home',
            'life': 'life:home',
            'purpose': 'purpose:home',
            'finance': 'finance:dashboard',
            'capture': 'capture:list',
            'notes': 'notes:note_list',
            'meals': 'meals:dashboard',
        }

        all_modules = []
        for pref in all_prefs:
            # Get route_name from DB, but fall back to known correct routes
            route_name = pref.module.route_name
            if route_name and ':' not in route_name:
                # Route name is missing namespace - use fallback
                route_name = CORRECT_ROUTES.get(pref.module.slug, route_name)

            # Pre-resolve URL to catch any errors here instead of in template
            try:
                url = reverse(route_name) if route_name else '#'
            except NoReverseMatch:
                # Last resort fallback
                url = f'/{pref.module.slug}/'

            all_modules.append({
                'id': pref.id,
                'slug': pref.module.slug,
                'name': pref.module.name,
                'description': pref.module.description,
                'icon_svg': pref.module.icon_svg,
                'route_name': route_name,
                'url': url,  # Pre-resolved URL
                'is_enabled': pref.is_enabled,
                'sort_order': pref.sort_order,
            })

        context['all_user_modules'] = all_modules

        # Get enabled modules for navigation
        enabled_modules = [m for m in all_modules if m['is_enabled']]

        # Mobile bottom nav: first 3 enabled modules (5 total with Home + More)
        context['nav_modules'] = enabled_modules[:3]

        # Desktop left rail: ALL enabled modules (no limit)
        context['desktop_rail_modules'] = enabled_modules

        # Overflow = enabled modules beyond the first 3 (mobile More screen)
        context['overflow_modules'] = enabled_modules[3:] if len(enabled_modules) > 3 else []

        # Desktop overflow = empty since all modules are in the rail now
        context['desktop_overflow_modules'] = []

        # Cache for 5 minutes (will be invalidated on preference changes)
        cache.set(cache_key, context, 300)

    except Exception:
        # If tables don't exist yet (pre-migration), use fallback
        pass

    return context


def invalidate_navigation_cache(user_id):
    """
    Invalidate navigation cache for a specific user.

    Call this when user updates their module preferences.
    """
    from django.core.cache import cache
    cache.delete(f'nav_modules_user_{user_id}')


def pending_captures_context(request):
    """
    Add pending captures count to template context for global reminder banner.

    Provides:
    - pending_captures_count: number of pending recordings awaiting upload
    - pending_captures_this_device: whether any are from the current device
    """
    context = {
        'pending_captures_count': 0,
        'pending_captures_this_device': False,
    }

    if not request.user.is_authenticated:
        return context

    # Skip for API endpoints and non-HTML requests
    path = request.path
    if any(path.startswith(p) for p in ['/api/', '/static/', '/media/', '/admin/', '/capture/pending/']):
        return context

    try:
        from apps.capture.models import PendingCapture

        pending = PendingCapture.objects.filter(
            user=request.user,
            status__in=[
                PendingCapture.STATUS_PENDING,
                PendingCapture.STATUS_UPLOADING,
                PendingCapture.STATUS_UPLOADED,
                PendingCapture.STATUS_DOWNLOADED,
            ]
        )

        context['pending_captures_count'] = pending.count()

        # Check if any are from this device (based on user-agent fingerprint in cookie)
        # For now, we assume any pending capture could be this device
        # The JavaScript will check IndexedDB for the actual answer
        context['pending_captures_this_device'] = context['pending_captures_count'] > 0

    except Exception:
        pass

    return context


def system_announcements_context(request):
    """
    Add active system announcements to template context.

    Provides:
    - active_announcements: QuerySet of announcements user hasn't dismissed
    - has_active_announcements: Boolean for quick check

    This runs on every authenticated page load. Announcements are shown as modals.
    """
    context = {
        'active_announcements': [],
        'has_active_announcements': False,
    }

    if not request.user.is_authenticated:
        return context

    # Skip for API, static, admin paths
    path = request.path
    if any(path.startswith(p) for p in ['/api/', '/static/', '/media/', '/admin/']):
        return context

    try:
        from apps.admin_console.models import SystemAnnouncement

        announcements = SystemAnnouncement.get_active_for_user(request.user)
        context['active_announcements'] = list(announcements)
        context['has_active_announcements'] = len(context['active_announcements']) > 0

    except Exception:
        pass

    return context


def notifications_context(request):
    """
    Add unread notification count to template context for the notification badge.

    Provides:
    - unread_notification_count: Number of unread notifications (capped display)
    - unread_notification_count_display: String for badge (e.g., "5" or "10+")

    Performance: Cached per-user for 60 seconds to minimize database queries.
    The notifications.js also updates this via API every 60 seconds for real-time updates.
    """
    context = {
        'unread_notification_count': 0,
        'unread_notification_count_display': '',
    }

    if not request.user.is_authenticated:
        return context

    # Skip for API, static, admin paths
    path = request.path
    if any(path.startswith(p) for p in ['/api/', '/static/', '/media/', '/admin/']):
        return context

    try:
        from django.core.cache import cache
        from apps.core.models import Notification

        # Cache the count for 60 seconds
        cache_key = f'notification_count_user_{request.user.id}'
        cached_count = cache.get(cache_key)

        if cached_count is not None:
            count = cached_count
        else:
            count = Notification.get_unread_count(request.user)
            cache.set(cache_key, count, 60)

        context['unread_notification_count'] = count
        # Display "10+" for counts over 10
        if count > 10:
            context['unread_notification_count_display'] = '10+'
        elif count > 0:
            context['unread_notification_count_display'] = str(count)
        else:
            context['unread_notification_count_display'] = ''

    except Exception:
        pass

    return context


def invalidate_notification_count_cache(user_id):
    """
    Invalidate notification count cache for a specific user.

    Call this when notifications are created, read, or deleted.
    Clears both the template context cache and the API endpoint cache.
    """
    from django.core.cache import cache
    cache.delete(f'notification_count_user_{user_id}')
    cache.delete(f'notification_count_{user_id}')


# URL path prefix to help context ID mapping for pages that don't use HelpContextMixin.
# Views that DO use HelpContextMixin will override this value in get_context_data().
# Uses longest-prefix matching so more specific paths win over general ones.
_HELP_CONTEXT_MAP = [
    # Brain Training (Cognitive Health) - function-based views, no mixin
    # Individual game play pages are handled dynamically in help_context()
    ('/health/cognitive/stats', 'HEALTH_COGNITIVE_STATS'),
    ('/health/cognitive/', 'HEALTH_COGNITIVE_HUB'),
    # Health sub-pages missing mixin
    ('/health/physical/steps/', 'HEALTH_STEPS'),
    ('/health/physical/sleep/', 'HEALTH_SLEEP'),
    ('/health/physical/blood-pressure/', 'HEALTH_VITALS'),
    ('/health/physical/blood-oxygen/', 'HEALTH_VITALS'),
    ('/health/physical/body-temperature/', 'HEALTH_VITALS'),
    ('/health/physical/quick-log', 'HEALTH_PHYSICAL_HOME'),
    ('/health/physical/cycle/', 'HEALTH_CYCLE_HOME'),
    ('/health/physical/fitness/', 'HEALTH_FITNESS'),
    ('/health/physical/fasting/', 'HEALTH_FASTING'),
    ('/health/physical/', 'HEALTH_PHYSICAL_HOME'),
    ('/health/', 'HEALTH_LANDING'),
    # Journal sub-pages
    ('/journal/new/', 'JOURNAL_ENTRY_CREATE'),
    ('/journal/entries/', 'JOURNAL_ENTRY_LIST'),
    ('/journal/page-view/', 'JOURNAL_ENTRY_LIST'),
    ('/journal/book-view/', 'JOURNAL_ENTRY_LIST'),
    ('/journal/archived/', 'JOURNAL_ENTRY_LIST'),
    ('/journal/deleted/', 'JOURNAL_ENTRY_LIST'),
    ('/journal/prompts/', 'JOURNAL_HOME'),
    ('/journal/tags/', 'JOURNAL_HOME'),
    ('/journal/calendar/', 'JOURNAL_CALENDAR'),
    ('/journal/', 'JOURNAL_HOME'),
    # Faith sub-pages
    ('/faith/prayers/', 'FAITH_HOME'),
    ('/faith/scripture/', 'FAITH_HOME'),
    ('/faith/milestones/', 'FAITH_HOME'),
    ('/faith/reflections/', 'FAITH_HOME'),
    ('/faith/study/', 'FAITH_STUDY_TOOLS'),
    ('/faith/reading-plans/', 'FAITH_READING_PLANS'),
    ('/faith/', 'FAITH_HOME'),
    # Life sub-pages
    ('/life/tasks/', 'LIFE_TASKS'),
    ('/life/projects/', 'LIFE_HOME'),
    ('/life/calendar/', 'LIFE_HOME'),
    ('/life/events/', 'LIFE_HOME'),
    ('/life/inventory/', 'LIFE_HOME'),
    ('/life/pets/', 'LIFE_HOME'),
    ('/life/recipes/', 'LIFE_HOME'),
    ('/life/maintenance/', 'LIFE_HOME'),
    ('/life/documents/', 'LIFE_HOME'),
    ('/life/significant-events/', 'LIFE_SIGNIFICANT_EVENTS'),
    ('/life/', 'LIFE_HOME'),
    # Purpose sub-pages
    ('/purpose/directions/', 'PURPOSE_HOME'),
    ('/purpose/goals/', 'PURPOSE_HOME'),
    ('/purpose/intentions/', 'PURPOSE_HOME'),
    ('/purpose/reflections/', 'PURPOSE_HOME'),
    ('/purpose/habits/', 'PURPOSE_HOME'),
    ('/purpose/', 'PURPOSE_HOME'),
    # Finance
    ('/finance/', 'FINANCE_HOME'),
    # Capture
    ('/capture/', 'CAPTURE_HOME'),
    # AI Assistant
    ('/assistant/', 'ASSISTANT_HOME'),
    # Settings
    ('/user/preferences/', 'SETTINGS_PREFERENCES'),
    ('/user/profile/', 'SETTINGS_PROFILE'),
    ('/user/data-export/', 'SETTINGS_DATA_EXPORT'),
    ('/user/', 'SETTINGS_PREFERENCES'),
    # Scan
    ('/scan/', 'SCAN_HOME'),
    # Core
    ('/dashboard/', 'DASHBOARD_HOME'),
    ('/notifications/', 'DASHBOARD_HOME'),
    ('/more/', 'DASHBOARD_HOME'),
    ('/favorites/', 'DASHBOARD_HOME'),
    # Admin Console
    ('/admin-console/', 'ADMIN_CONSOLE_HOME'),
]


def help_context(request):
    """
    Auto-provide help_context_id based on URL path for pages missing HelpContextMixin.

    Views that use HelpContextMixin will override this in their get_context_data().
    Uses longest-prefix matching for accurate context assignment.
    """
    import re
    path = request.path

    # Brain training game play pages: /health/cognitive/<slug>/play/
    game_match = re.match(r'^/health/cognitive/([a-z_-]+)/play/', path)
    if game_match:
        game_slug = game_match.group(1).replace('-', '_').upper()
        return {'help_context_id': f'BRAIN_TRAINING_{game_slug}'}

    for prefix, context_id in _HELP_CONTEXT_MAP:
        if path.startswith(prefix):
            return {'help_context_id': context_id}
    return {'help_context_id': 'GENERAL'}
