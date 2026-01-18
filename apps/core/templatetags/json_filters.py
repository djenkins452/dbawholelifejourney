"""
JSON Template Filters

Provides filters for converting Python objects to JSON for use in templates,
particularly for passing data to JavaScript.

Location: apps/core/templatetags/json_filters.py
"""

import json

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name='jsonify')
def jsonify(value):
    """
    Convert a Python object to a JSON string safe for use in HTML attributes.

    Usage:
        <div data-config='{{ config_dict|jsonify }}'>

    The output is HTML-safe and can be used in data attributes or script tags.
    """
    if value is None:
        return '{}'

    try:
        # Use separators to minimize whitespace
        json_str = json.dumps(value, separators=(',', ':'))
        return mark_safe(json_str)
    except (TypeError, ValueError):
        return '{}'


@register.filter(name='json_script_safe')
def json_script_safe(value):
    """
    Convert a Python object to JSON safe for embedding in <script> tags.

    This escapes characters that could break out of script contexts.

    Usage:
        <script>
            const data = {{ my_data|json_script_safe }};
        </script>
    """
    if value is None:
        return 'null'

    try:
        json_str = json.dumps(value)
        # Escape characters that could break script tags
        json_str = json_str.replace('<', '\\u003c')
        json_str = json_str.replace('>', '\\u003e')
        json_str = json_str.replace('&', '\\u0026')
        return mark_safe(json_str)
    except (TypeError, ValueError):
        return 'null'
