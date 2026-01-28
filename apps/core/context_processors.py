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

from django.conf import settings
from django.utils import timezone


def site_context(request):
    """
    Add site-wide context variables.
    """
    from apps.core.models import SiteConfiguration

    config = SiteConfiguration.get_solo()

    return {
        'site_name': config.site_name or 'Whole Life Journey',
        'site_tagline': config.tagline or 'A calm space for reflection, growth, and faithful living.',
        'site_logo_url': config.logo.url if config.logo else None,
        'site_favicon_url': config.favicon.url if config.favicon else None,
        # reCAPTCHA v3 site key for anti-bot protection
        'recaptcha_site_key': settings.RECAPTCHA_V3_SITE_KEY,
    }


def theme_context(request):
    """
    Add theme, accent color, and module flags to template context.
    """
    context = {
        'current_theme': 'minimal',
        'accent_color': None,
        # Module flags - defaults
        'journal_enabled': True,
        'faith_enabled': False,
        'health_enabled': True,
        'life_enabled': True,
        'purpose_enabled': True,
        'finance_enabled': False,
        'capture_enabled': True,
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
            # Module toggles
            context['journal_enabled'] = prefs.journal_enabled
            context['faith_enabled'] = prefs.faith_enabled
            context['health_enabled'] = prefs.health_enabled
            context['life_enabled'] = prefs.life_enabled
            context['purpose_enabled'] = prefs.purpose_enabled
            context['finance_enabled'] = prefs.finances_enabled
            context['capture_enabled'] = prefs.capture_enabled
            # AI toggles
            context['ai_enabled'] = prefs.ai_enabled
            context['ai_data_consent'] = prefs.ai_data_consent
            # Personal Assistant toggles
            context['personal_assistant_enabled'] = prefs.personal_assistant_enabled
            context['personal_assistant_consent'] = prefs.personal_assistant_consent
            # Cycle tracking - check if user has opted in
            try:
                from apps.health.models import CycleSettings
                cycle_settings = CycleSettings.objects.filter(
                    user=request.user, status='active'
                ).first()
                context['cycle_tracking_enabled'] = (
                    cycle_settings.cycle_tracking_enabled if cycle_settings else False
                )
            except Exception:
                context['cycle_tracking_enabled'] = False
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


def navigation_modules_context(request):
    """
    Add navigation module data to template context for mobile bottom nav and desktop left rail.

    Provides:
    - nav_modules: List of module dicts for mobile bottom nav (up to 4 enabled modules)
    - desktop_rail_modules: List of module dicts for desktop left rail (up to 8 enabled modules)
    - all_user_modules: All user module preferences (for More screen)
    - overflow_modules: Enabled modules beyond the first 4 (for mobile More screen)
    - desktop_overflow_modules: Enabled modules beyond the first 8 (for desktop More screen)

    Mobile bottom nav shows: Home + first 4 enabled modules + More
    Desktop left rail shows: Home + first 8 enabled modules + More

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
        from apps.users.models import UserModulePreference, ModuleDefinition

        # Cache key specific to this user
        cache_key = f'nav_modules_user_{request.user.id}'
        cached_data = cache.get(cache_key)

        if cached_data is not None:
            # Use cached navigation data
            return cached_data

        # Initialize module preferences for user if needed
        # Use exists() instead of count() - more efficient
        if not UserModulePreference.objects.filter(user=request.user).exists():
            # Initialize for user (first time)
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

        # Mobile bottom nav: first 4 enabled modules
        context['nav_modules'] = enabled_modules[:4]

        # Desktop left rail: ALL enabled modules (no limit)
        context['desktop_rail_modules'] = enabled_modules

        # Overflow = enabled modules beyond the first 4 (mobile More screen)
        context['overflow_modules'] = enabled_modules[4:] if len(enabled_modules) > 4 else []

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
