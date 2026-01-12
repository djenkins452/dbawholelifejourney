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
            # Module toggles
            context['journal_enabled'] = prefs.journal_enabled
            context['faith_enabled'] = prefs.faith_enabled
            context['health_enabled'] = prefs.health_enabled
            context['life_enabled'] = prefs.life_enabled
            context['purpose_enabled'] = prefs.purpose_enabled
            context['finance_enabled'] = prefs.finances_enabled
            # AI toggles
            context['ai_enabled'] = prefs.ai_enabled
            context['ai_data_consent'] = prefs.ai_data_consent
            # Personal Assistant toggles
            context['personal_assistant_enabled'] = prefs.personal_assistant_enabled
            context['personal_assistant_consent'] = prefs.personal_assistant_consent
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
        from apps.core.models import FavoritePage, PageView

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

        # Check if current page is a favorite
        is_favorite = FavoritePage.is_favorite(request.user, path)

        context['favorites_menu_data'] = {
            'favorites': list(favorites),
            'most_used': most_used,
            'favorites_count': favorites_count,
        }
        context['is_current_page_favorite'] = is_favorite

    except Exception:
        pass

    return context
