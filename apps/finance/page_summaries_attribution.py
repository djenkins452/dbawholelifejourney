# ==============================================================================
# File: apps/finance/page_summaries_attribution.py
# Description: Current Context page-summary provider for the attribution workspace.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Deterministic page summary for `/finance/attribution/`.

Reads the SAME `review_counts` the page renders — one deterministic source feeding both
the screen and the Chief of Staff, never two independent derivations. Facts only.
"""
from apps.core.current_context import register_page_summary
from apps.finance.services.attribution_review import review_counts


@register_page_summary("finance.attribution")
def finance_attribution_summary(user, params):
    counts = review_counts(user)
    lines = [
        f"Awaiting a decision: {counts['unattributed']}",
        f"Assigned automatically, not yet confirmed: {counts['inferred']}",
        f"Uncertain (pending or suspected internal transfer): {counts['uncertain']}",
        f"Confirmed by you: {counts['confirmed']}",
    ]
    return {"title": "Attribution Review", "kind": "finance attribution",
            "content": "Who your money belongs to\n" + "\n".join(lines)}


@register_page_summary("finance.entities")
def finance_entities_summary(user, params):
    """The entity setup state — facts only."""
    from apps.finance.models import FinancialEntity
    rows = FinancialEntity.objects.filter(user=user, is_active=True).order_by("name")
    if not rows:
        return {"title": "Financial Entities", "kind": "finance entities",
                "content": "No financial entities set up yet."}
    listed = "\n".join(f"- {e.name} ({e.get_entity_type_display()})" for e in rows)
    return {"title": "Financial Entities", "kind": "finance entities",
            "content": f"Entities money can belong to ({rows.count()}):\n{listed}"}
