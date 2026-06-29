"""
Intent Fulfillment.

A Conversation Goal says what the customer wants; fulfillment decides whether the
response actually ACCOMPLISHES it. For a COMPARE goal, the comparison itself is the
answer — the differences and overlaps — not two raw lists. Numeric topics fulfill via
the delta (compose_comparison); structured topics (meals) fulfill via derived insights.

Deterministic. No new retrieval, no LLM — composed from facts already on the object.
"""


def _join(names):
    names = list(names)
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def fulfill_meal_comparison(a_label, a_meals, b_label, b_meals):
    """Compose the COMPARISON of two days' meals — meal-type gaps, shared items, and
    relative volume — so the comparison is the answer. Returns None when there's nothing
    to compare (caller falls back to showing the data)."""
    a_meals = a_meals or {}
    b_meals = b_meals or {}
    a_items = [n for items in a_meals.values() for n in items]
    b_items = [n for items in b_meals.values() for n in items]
    if not a_items and not b_items:
        return None

    al, bl = a_label, b_label
    insights = []

    # 1) Meal-type gaps — what one day has that the other doesn't.
    a_types = [t for t, v in a_meals.items() if v]
    b_types = [t for t, v in b_meals.items() if v]
    for t in a_types:
        if t not in b_types:
            tail = " yet" if bl.lower() == "today" else ""
            insights.append(f"{al} included {t}, but {bl.lower()} doesn't{tail}.")
    for t in b_types:
        if t not in a_types:
            tail = " yet" if al.lower() == "today" else ""
            insights.append(f"{bl} included {t}, but {al.lower()} didn't{tail}.")

    # 1b) Same meal type both days, but different items — say what differed.
    for t in a_types:
        if t in b_types:
            bset = {n.lower() for n in b_meals[t]}
            aset = {n.lower() for n in a_meals[t]}
            a_only = [n for n in a_meals[t] if n.lower() not in bset]
            b_only = [n for n in b_meals[t] if n.lower() not in aset]
            if a_only and b_only:
                insights.append(f"{t.capitalize()} differed — {_join(a_only)} {al.lower()} "
                                f"vs {_join(b_only)} {bl.lower()}.")

    # 2) Shared items — what appears on both days.
    b_low = {n.lower() for n in b_items}
    seen, both = set(), []
    for n in a_items:
        k = n.lower()
        if k in b_low and k not in seen:
            seen.add(k)
            both.append(n)
    if both:
        verb = "appears" if len(both) == 1 else "appear"
        insights.append(f"{_join(both)} {verb} on both days.")

    # 3) Relative volume — which day was heavier.
    na, nb = len(a_items), len(b_items)
    if na != nb:
        heavier, h, lighter, lo = ((al, na, bl, nb) if na > nb else (bl, nb, al, na))
        lighter_clause = (f"{lighter.lower()} is lighter so far"
                          if lighter.lower() == "today" else f"{lighter.lower()} was lighter")
        insights.append(f"{heavier} was heavier ({h} items vs {lo}) — {lighter_clause}.")
    elif na and na == nb:
        insights.append(f"Both days had {na} items logged.")

    if not insights:
        return None
    return " ".join(insights)
