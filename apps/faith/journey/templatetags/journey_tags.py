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


register = template.Library()


@register.inclusion_tag("faith/journey/_dashboard_card.html", takes_context=False)
def journey_dashboard_card(user):
    """Render the Faith-dashboard Journey card, or empty when not applicable."""
    return {"card": get_dashboard_card_data(user)}
