"""Brain Training template tags and filters."""

from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary using key."""
    if dictionary is None:
        return None
    return dictionary.get(key)
