"""Template filter for First Light procedural cover art.

Usage:  {% load fl_covers %}   ...   {{ plan|fl_cover }}
Returns a complete, safe <svg> scene chosen from the plan's own content.
"""

from django import template
from django.utils.safestring import mark_safe

from apps.faith.first_light.covers import cover_svg

register = template.Library()


@register.filter(name="fl_cover")
def fl_cover(plan):
    try:
        return mark_safe(cover_svg(plan))
    except Exception:
        return ""
