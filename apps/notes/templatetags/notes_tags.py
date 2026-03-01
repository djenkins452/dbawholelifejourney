"""
Template tags for the Notes app.
"""

import re

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name="safe_headline")
def safe_headline(value):
    """
    Render a SearchHeadline value, allowing only <mark> and </mark> tags.

    All other HTML is escaped. This prevents XSS from user-generated content
    while still showing highlighted search matches.
    """
    if not value:
        return ""
    # Escape all HTML first by converting to string
    text = str(value)
    # Temporarily replace <mark> and </mark> with placeholders
    text = text.replace("<mark>", "\x00MARK_OPEN\x00")
    text = text.replace("</mark>", "\x00MARK_CLOSE\x00")
    # Escape remaining HTML
    from django.utils.html import escape

    text = escape(text)
    # Restore mark tags
    text = text.replace("\x00MARK_OPEN\x00", "<mark>")
    text = text.replace("\x00MARK_CLOSE\x00", "</mark>")
    return mark_safe(text)
