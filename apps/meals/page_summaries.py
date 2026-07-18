# ==============================================================================
# File: apps/meals/page_summaries.py
# Project: Whole Life Journey - Meal Intelligence
# Description: Current Context page-summary providers for Meal Intelligence overviews.
# ==============================================================================
"""Deterministic page-summary providers (registered at app-ready).

User-scoped, request-path-safe, facts-only — the SAME deterministic truth the page
renders (via the canonical leftover_queries), so the assistant can never contradict
the screen.
"""
from apps.core.current_context import register_page_summary


@register_page_summary("meals.leftovers")
def leftovers_page_summary(user, params):
    """The Leftovers overview page. Facts only — reads the same leftover_summary the
    page render uses. WLJ exposes counts/servings/dates; the model interprets."""
    from apps.meals.models import HouseholdMembership
    from apps.meals.services.leftover_queries import leftover_summary

    membership = (HouseholdMembership.objects.filter(user=user)
                  .select_related("household").first())
    if not membership:
        return {"title": "Leftovers", "kind": "leftovers overview",
                "content": "Leftovers — no household set up yet."}

    facts = leftover_summary(membership.household)
    if facts["count"] == 0:
        return {"title": "Leftovers", "kind": "leftovers overview",
                "content": "Leftovers — none available right now."}

    lines = [f"Available leftovers: {facts['count']} "
             f"({facts['total_servings']:g} total serving(s))"]
    for it in facts["items"][:12]:
        prep = f", prepared {it['prepared_date']}" if it.get("prepared_date") else ""
        exp = f", expires {it['expiration_date']}" if it.get("expiration_date") else ""
        lines.append(f"- {it['recipe_title']}: {it['servings']:g} serving(s){prep}{exp}")

    return {"title": "Leftovers", "kind": "leftovers overview",
            "content": "Leftovers\n" + "\n".join(lines)}
