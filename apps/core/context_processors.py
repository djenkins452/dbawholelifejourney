"""
Core Context Processors

These add variables to every template context.
"""

from django.conf import settings


def site_context(request):
    """
    Add site-wide context variables.
    """
    return {
        'site_name': 'Whole Life Journey',
        'site_tagline': 'A calm space for reflection, growth, and faithful living.',
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
        except Exception:
            pass
    
    return context
