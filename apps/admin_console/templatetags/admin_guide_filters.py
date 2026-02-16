"""Template filters for Admin Guide markdown rendering."""
import markdown
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name='render_markdown')
def render_markdown(value):
    """Convert Markdown content to HTML. Same extensions as help system."""
    if not value:
        return ''
    md = markdown.Markdown(extensions=['extra', 'nl2br', 'sane_lists', 'toc'])
    return mark_safe(md.convert(value))
