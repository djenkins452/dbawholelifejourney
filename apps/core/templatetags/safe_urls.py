"""
Safe URL Template Tags

Provides URL resolution with fallbacks to prevent template crashes
when URL names change or don't exist.

Location: apps/core/templatetags/safe_urls.py
"""

from django import template
from django.urls import reverse, NoReverseMatch

register = template.Library()


@register.simple_tag
def safe_url(url_name, *args, fallback='#', **kwargs):
    """
    Safely resolve a URL name, returning a fallback if it doesn't exist.
    
    Usage:
        {% safe_url 'life:google_calendar_settings' %}
        {% safe_url 'life:settings' fallback='/life/' %}
        {% safe_url 'life:detail' pk=object.pk fallback='#' %}
    
    Returns the resolved URL or the fallback value if resolution fails.
    """
    try:
        return reverse(url_name, args=args, kwargs=kwargs)
    except NoReverseMatch:
        return fallback


@register.simple_tag
def url_or(primary_url, fallback_url, *args, **kwargs):
    """
    Try primary URL first, fall back to secondary URL if primary doesn't exist.
    
    Usage:
        {% url_or 'life:google_calendar_settings' 'life:home' %}
        {% url_or 'life:settings' 'life:calendar' pk=object.pk %}
    
    Returns the first URL that resolves successfully, or '#' if neither works.
    """
    # Try primary URL
    try:
        return reverse(primary_url, args=args, kwargs=kwargs)
    except NoReverseMatch:
        pass
    
    # Try fallback URL
    try:
        return reverse(fallback_url, args=args, kwargs=kwargs)
    except NoReverseMatch:
        pass
    
    # Neither worked
    return '#'


@register.simple_tag
def first_valid_url(*url_names, **kwargs):
    """
    Return the first URL that resolves from a list of options.
    
    Usage:
        {% first_valid_url 'life:google_calendar_settings' 'life:settings' 'life:home' %}
    
    Useful when URL names might vary across deployments or versions.
    """
    for url_name in url_names:
        try:
            return reverse(url_name, kwargs=kwargs)
        except NoReverseMatch:
            continue
    return '#'


@register.simple_tag(takes_context=True)
def url_exists(context, url_name, *args, **kwargs):
    """
    Check if a URL name exists and can be resolved.
    
    Usage:
        {% url_exists 'life:google_calendar_settings' as has_gcal_settings %}
        {% if has_gcal_settings %}
            <a href="{% url 'life:google_calendar_settings' %}">Settings</a>
        {% endif %}
    """
    try:
        reverse(url_name, args=args, kwargs=kwargs)
        return True
    except NoReverseMatch:
        return False


@register.inclusion_tag('core/components/safe_link.html')
def safe_link(url_name, text, fallback_url='#', css_class='', *args, **kwargs):
    """
    Render a link with safe URL resolution.
    
    Usage:
        {% safe_link 'life:google_calendar_settings' 'Calendar Settings' fallback_url='/life/' css_class='btn btn-primary' %}
    
    Requires template: templates/core/components/safe_link.html
    """
    try:
        url = reverse(url_name, args=args, kwargs=kwargs)
        exists = True
    except NoReverseMatch:
        url = fallback_url
        exists = False
    
    return {
        'url': url,
        'text': text,
        'css_class': css_class,
        'exists': exists,
    }


# =============================================================================
# Common URL Aliases
# =============================================================================
# These provide consistent names that map to actual URLs

URL_ALIASES = {
    # Life module
    'life:calendar_settings': ['life:google_calendar_settings', 'life:calendar', 'life:home'],
    'life:settings': ['life:google_calendar_settings', 'life:home'],
    
    # User module
    'user:settings': ['users:preferences', 'users:profile'],
    'user:profile': ['users:profile', 'users:preferences'],
    
    # Dashboard
    'home': ['dashboard:home', 'dashboard:index', '/'],
}


@register.simple_tag
def aliased_url(alias_name, *args, **kwargs):
    """
    Resolve a URL using predefined aliases with fallbacks.
    
    Usage:
        {% aliased_url 'life:calendar_settings' %}
    
    This will try each URL in the alias list until one resolves.
    If the alias doesn't exist, it tries the name directly.
    """
    # Get the list of URLs to try
    url_list = URL_ALIASES.get(alias_name, [alias_name])
    
    # If it's not a list, make it one
    if isinstance(url_list, str):
        url_list = [url_list]
    
    # Try each URL
    for url_name in url_list:
        try:
            return reverse(url_name, args=args, kwargs=kwargs)
        except NoReverseMatch:
            continue
    
    # Nothing worked
    return '#'