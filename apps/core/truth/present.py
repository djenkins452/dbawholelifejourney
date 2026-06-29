"""
Human Presentation Standard — one reusable presentation layer for every Conversation
Object. Truth in, human-readable out: rounded numbers, collapsed duplicates, grouped
lists, and remaining-to-goal. Never special-cased per domain — meals, sleep, steps,
weight, finance, etc. all render through these primitives.

Complements `render.py` (date/time). Deterministic — same truth → same presentation.
Modes are extensible (conversational is the default); the primitives below are the
building blocks every mode composes.
"""


def humanize_number(value, decimals=0):
    """Round for humans with thousands separators: 31.2 → '31', 1850.0 → '1,850',
    180.0 → '180'. `decimals>0` keeps that many only when non-integer."""
    if value is None or value == "":
        return ""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if decimals <= 0 or float(round(f, decimals)).is_integer():
        return f"{int(round(f)):,}"
    return f"{round(f, decimals):,}"


def collapse_items(items):
    """['Pizza','Pizza','Salad'] → [('Pizza', 2), ('Salad', 1)], first-seen order,
    case-insensitive grouping (keeps the first spelling)."""
    order, seen = [], {}
    for raw in items:
        name = str(raw).strip()
        if not name:
            continue
        k = name.lower()
        if k not in seen:
            seen[k] = [name, 0]
            order.append(k)
        seen[k][1] += 1
    return [(seen[k][0], seen[k][1]) for k in order]


def bullet_list(items, *, serving_word="serving"):
    """Collapsed bulleted list: 'Pizza, Pizza' → '• Pizza (2 servings)'."""
    lines = []
    for name, count in collapse_items(items):
        suffix = f" ({count} {serving_word}s)" if count > 1 else ""
        lines.append(f"• {name}{suffix}")
    return lines


def present_groups(groups, *, lead="", serving_word="serving"):
    """Grouped, bulleted, collapsed presentation:

        Today you've logged:

        Snack
        • Pistachios
        • Cashews

        Dinner
        • Homemade Pizza (2 servings)

    `groups` = ordered iterable of (title, [items]). Empty groups are dropped.
    """
    populated = [(t, list(items)) for t, items in groups if items]
    if not populated:
        return ""
    out = [lead, ""] if lead else []
    for title, items in populated:
        out.append(str(title).capitalize())
        out.extend(bullet_list(items, serving_word=serving_word))
        out.append("")
    return "\n".join(out).rstrip()


def present_remaining(label, consumed, goal, unit=""):
    """'Protein: 31 g consumed · 149 g remaining (goal 180 g)'. No goal → just the total."""
    c = humanize_number(consumed)
    u = (" " + unit) if unit else ""
    if goal in (None, "", 0):
        return f"{label}: {c}{u} so far"
    try:
        remaining = max(0.0, float(goal) - float(consumed or 0))
    except (TypeError, ValueError):
        return f"{label}: {c}{u} so far"
    return (f"{label}: {c}{u} consumed · {humanize_number(remaining)}{u} remaining "
            f"(goal {humanize_number(goal)}{u})")
