"""Template filters for Admin Guide markdown rendering."""
import markdown
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name='render_markdown')
def render_markdown(value):
    """Convert Markdown content to HTML for admin guide articles."""
    if not value:
        return ''
    md = markdown.Markdown(extensions=[
        'extra',          # tables, fenced_code, footnotes, abbreviations, etc.
        'sane_lists',     # better list handling
        'toc',            # table of contents
        'fenced_code',    # ```code``` blocks
    ])
    # Note: nl2br intentionally omitted — it breaks code blocks and tables
    return mark_safe(md.convert(value))
