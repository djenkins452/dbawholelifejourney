"""
Capture Template Filters

Provides filters for rendering capture content, including markdown-to-HTML
conversion for AI-generated summaries.

Location: apps/capture/templatetags/capture_filters.py
"""

import re

import markdown
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name='render_summary')
def render_summary(value):
    """
    Convert markdown summary to polished HTML.

    Converts AI-generated markdown summaries into clean, styled HTML
    suitable for display and email sharing.

    Usage:
        {{ entry.summary|render_summary }}

    Features:
    - Converts ## headers to styled section headers
    - Converts **bold** to <strong>
    - Converts - lists to proper <ul><li> elements
    - Handles line breaks appropriately
    - Sanitizes output for safe HTML rendering
    """
    if not value:
        return ''

    # Use markdown library with safe extensions
    md = markdown.Markdown(
        extensions=[
            'markdown.extensions.nl2br',  # Convert newlines to <br>
            'markdown.extensions.sane_lists',  # Better list handling
        ]
    )

    html = md.convert(value)

    # Add CSS classes for styling
    # Style section headers (h2)
    html = re.sub(
        r'<h2>(.*?)</h2>',
        r'<h3 class="summary-section-header">\1</h3>',
        html
    )

    # Style h1 if present (BLUF title)
    html = re.sub(
        r'<h1>(.*?)</h1>',
        r'<h2 class="summary-main-header">\1</h2>',
        html
    )

    # Add class to paragraphs
    html = re.sub(
        r'<p>',
        r'<p class="summary-paragraph">',
        html
    )

    # Add class to lists
    html = re.sub(
        r'<ul>',
        r'<ul class="summary-list">',
        html
    )

    return mark_safe(html)


@register.filter(name='summary_plain_text')
def summary_plain_text(value):
    """
    Convert markdown summary to clean plain text.

    Strips markdown formatting for use in plain text contexts
    like email subject lines or notifications.

    Usage:
        {{ entry.summary|summary_plain_text|truncatewords:20 }}
    """
    if not value:
        return ''

    # Remove markdown headers
    text = re.sub(r'^#{1,6}\s+', '', value, flags=re.MULTILINE)

    # Remove bold/italic markers
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)

    # Remove list markers
    text = re.sub(r'^[-*+]\s+', '', text, flags=re.MULTILINE)

    # Clean up extra whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    return text
