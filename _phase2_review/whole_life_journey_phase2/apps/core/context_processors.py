"""
Context Processors - Make data available to all templates.

These processors inject common data into every template context:
- Theme settings (colors, icons based on user preferences)
- User preferences
- App-wide settings
"""

from django.conf import settings


def theme_context(request):
    """
    Inject theme-related context into all templates.
    
    Provides:
    - current_theme: The user's selected theme (or default)
    - theme_config: Full configuration for the current theme
    - accent_color: User's custom accent color (or theme default)
    - faith_enabled: Whether Faith module is enabled for this user
    - ai_enabled: Whether AI features are enabled for this user
    """
    context = {
        "themes": settings.WLJ_SETTINGS["THEMES"],
        "default_theme": settings.WLJ_SETTINGS["DEFAULT_THEME"],
    }

    # Default values for anonymous users
    current_theme = settings.WLJ_SETTINGS["DEFAULT_THEME"]
    theme_config = settings.WLJ_SETTINGS["THEMES"][current_theme]
    accent_color = theme_config["accent"]
    faith_enabled = False
    ai_enabled = False

    # Override with user preferences if authenticated
    if request.user.is_authenticated:
        try:
            prefs = request.user.preferences
            current_theme = prefs.theme or current_theme
            theme_config = settings.WLJ_SETTINGS["THEMES"].get(
                current_theme, 
                settings.WLJ_SETTINGS["THEMES"][settings.WLJ_SETTINGS["DEFAULT_THEME"]]
            )
            accent_color = prefs.accent_color or theme_config["accent"]
            faith_enabled = prefs.faith_enabled
            ai_enabled = prefs.ai_enabled
        except AttributeError:
            # User doesn't have preferences yet
            pass

    context.update({
        "current_theme": current_theme,
        "theme_config": theme_config,
        "accent_color": accent_color,
        "faith_enabled": faith_enabled,
        "ai_enabled": ai_enabled,
    })

    return context
