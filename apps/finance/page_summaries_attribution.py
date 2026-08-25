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
