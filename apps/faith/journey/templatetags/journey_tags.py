"""
Template tags for the Journey feature.

Provides a single inclusion tag, `journey_dashboard_card`, that renders the
modest Faith-page journey card when the user has an active journey, and
nothing otherwise. Designed to be drop-in from `templates/faith/home.html`
without requiring changes to FaithHomeView.

Usage:
    {% load journey_tags %}
    {% journey_dashboard_card request.user %}
"""

from django import template

from apps.faith.journey.dashboard import get_dashboard_card_data
from apps.faith.journey.models import JourneyPath


register = template.Library()


@register.inclusion_tag("faith/journey/_dashboard_card.html", takes_context=False)
def journey_dashboard_card(user):
    """Render the Faith-dashboard Journey card, or empty when not applicable."""
    return {"card": get_dashboard_card_data(user)}


@register.inclusion_tag("faith/journey/_reading_plans_card.html", takes_context=False)
def journey_reading_plans_card(user, show_new_badge=True):
    """Render the Reading Plans page Journey card.

    Two render modes:
      1. User has an active journey → show "Current Arc / Day / Continue Journey"
      2. Path is active but user hasn't started → show "Begin the Journey"
    Empty (no card rendered) only when the canonical path is not active.
    """
    card = get_dashboard_card_data(user)
    path_active = JourneyPath.objects.filter(
        slug="walking_with_god", is_active=True
    ).exists()
    return {
        "card": card,
        "path_active": path_active,
        "show_new_badge": show_new_badge,
    }
