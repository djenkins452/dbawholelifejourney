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
from apps.faith.journey.roadmap import get_roadmap_rows
from apps.faith.journey.services import get_active_journey


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


@register.inclusion_tag("faith/journey/_roadmap.html", takes_context=False)
def journey_roadmap(user):
    """Render the journey roadmap / table of contents.

    Shows all 12 planned arcs (Old Testament + New Testament) with their
    coverage, an evocative one-line teaser, and a status pill
    (Available / In Progress / Coming Soon). When the user has an active
    journey, their current arc is highlighted.

    Renders nothing when the canonical path is not active.
    """
    path_active = JourneyPath.objects.filter(
        slug="walking_with_god", is_active=True
    ).exists()
    if not path_active:
        return {"rows_ot": [], "rows_nt": []}

    current_arc_slug = None
    if user is not None and getattr(user, "is_authenticated", False):
        uj = get_active_journey(user)
        if uj and uj.current_arc:
            current_arc_slug = uj.current_arc.slug

    all_rows = get_roadmap_rows(current_user_arc_slug=current_arc_slug)
    rows_ot = [r for r in all_rows if r["testament"] == "OT"]
    rows_nt = [r for r in all_rows if r["testament"] == "NT"]
    return {
        "rows_ot": rows_ot,
        "rows_nt": rows_nt,
    }
