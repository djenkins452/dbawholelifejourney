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

Template Variables Provided:
    - site_name, site_tagline, site_logo_url, site_favicon_url
    - current_theme, accent_color
    - journal_enabled, faith_enabled, health_enabled, life_enabled, purpose_enabled
    - user_today (date in user's timezone for date comparisons)

Dependencies:
    - apps.core.models.SiteConfiguration for site settings
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
            # User's "today" in their timezone (for date comparisons in templates)
            from apps.core.utils import get_user_today
            context['user_today'] = get_user_today(request.user)
        except Exception:
            pass

    return context
