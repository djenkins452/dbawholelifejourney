"""
Core Context Processors

These add variables to every template context.
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
