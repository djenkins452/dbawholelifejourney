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


@register_page_summary("meals.dashboard")
def meals_dashboard_summary(user, params):
    """The Meals workspace — deterministic facts only. Reads the ONE shared source
    (build_meals_home_summary), which is request-path-safe (SAE snapshot only). WLJ
    exposes counts / names / dates; the model decides what they mean."""
    from apps.meals.services.meals_home_summary import build_meals_home_summary

    facts = build_meals_home_summary(user)

    if facts.get("status") == "pending":
        return {"title": "Meals", "kind": "meals overview",
                "content": "Your meals — being prepared (up-to-date figures load momentarily)."}

    if not facts.get("has_household"):
        return {"title": "Meals", "kind": "meals overview",
                "content": "Meals — no household set up yet."}

    lines = [f"Pantry items on hand: {facts.get('pantry_item_count', 0)}"]
    exp_ct = facts.get("pantry_expiring_count", 0)
    if exp_ct:
        names = facts.get("expiring_item_names") or []
        detail = f" ({', '.join(names)})" if names else ""
        lines.append(f"Expiring within 3 days: {exp_ct}{detail}")
    if facts.get("has_dinner_planned"):
        recipe = facts.get("dinner_recipe")
        lines.append(f"Dinner planned tonight: {recipe}" if recipe
                     else "Dinner planned tonight: yes")
    else:
        lines.append("Dinner planned tonight: none")
    if facts.get("grocery_cycle_days"):
        lines.append(f"Grocery cycle: every {facts['grocery_cycle_days']} days")
    if facts.get("protein_target_daily") is not None:
        lines.append(f"Daily protein target: {facts['protein_target_daily']:g} g")
    if facts.get("carb_limit_daily") is not None:
        lines.append(f"Daily carb limit: {facts['carb_limit_daily']:g} g")

    return {"title": "Meals", "kind": "meals overview",
            "content": "Meals overview\n" + "\n".join(lines)}


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
