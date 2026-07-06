"""Canonical mission-milestone commentary — ONE deterministic, meaning-first
composer shared by EVERY surface that celebrates a cleared mission milestone.

Why this module exists (the divergence bug, 2026-07-06):
    There were TWO milestone-commentary generators. The dashboard mission card
    (``apps/dashboard_v3/services/composer.py``) was upgraded to meaning-first
    commentary, but the Significant Event Pipeline major-win recommendation
    (``apps/ai/significant_events.py``) was a SEPARATE code path and kept the
    generic "That's milestone 6 of 12 / banking it now / next rung" copy — so
    the "Purpose recommendation" on the live dashboard still read the old way.
    A single canonical composer makes that divergence impossible: both surfaces
    now compose from here.

The three questions every surface must answer — never a bare number:
    1. WHAT happened  — the milestone, named (its title carries the meaning).
    2. WHY it matters — the milestone's OWN meaning (the description the user
                        wrote) PLUS progression framed toward the mission's
                        PURPOSE (the goal title), not "N of M" as the point.
    3. WHAT'S NEXT    — the next rung, now the live focus.

Deterministic; zero LLM. Every clause names real truth (milestone
title/description, mission title, next milestone) — nothing fabricated.
"""


def progression_clause(completed, total) -> str:
    """A MEANINGFUL progression phrase (momentum / position), never a bare
    "N of M" as the point. The count supports the meaning; it isn't the
    headline."""
    completed = completed or 0
    total = total or 0
    if not total:
        return (f"That's {completed} milestone{'s' if completed != 1 else ''} cleared"
                if completed else "")
    if completed >= total:
        return "That completes every milestone this mission set out to reach"
    frac = completed / total
    if frac >= 0.75:
        return f"You're {completed} of {total} — the finish line is in sight"
    if frac >= 0.5:
        return (f"You're {completed} of {total}, past the halfway mark and "
                "building real momentum")
    if frac >= 0.25:
        return (f"You're {completed} of {total} — a quarter of the way in and "
                "finding your rhythm")
    return f"That's {completed} of {total} — the foundation is taking shape"


def why_it_matters(*, mission_title=None, milestone_description=None,
                   completed=0, total=0, milestone_title=None) -> str:
    """WHY this milestone matters for THIS mission: its own meaning (the
    description the user wrote, if any), grounded by progression toward the
    mission's purpose (named). Never generic "a concrete step toward the mission
    you set." Returns "" only if there is genuinely nothing truthful to say."""
    mission = (mission_title or "").strip()
    desc = (milestone_description or "").strip()
    title = (milestone_title or "").strip()
    parts = []
    # The milestone's OWN description is the truest meaning (don't echo the title).
    if desc and desc.lower() != title.lower():
        parts.append(desc if desc[-1:] in ".!?" else f"{desc}.")
    clause = progression_clause(completed, total)
    if clause and mission:
        parts.append(f"{clause} — real progress toward {mission}.")
    elif mission:
        parts.append(f"Real progress toward {mission}.")
    elif clause:
        parts.append(f"{clause}.")
    return " ".join(parts)


def milestone_meaning_text(*, milestone_title, mission_title=None,
                           milestone_description=None, completed=0, total=0,
                           next_title=None) -> str:
    """The single-string meaning-first celebration (dashboard mission card).
    Answers all three questions in one line."""
    title = (milestone_title or "").strip() or "A milestone"
    parts = [f"{title} — completed."]
    why = why_it_matters(
        mission_title=mission_title, milestone_description=milestone_description,
        completed=completed, total=total, milestone_title=title)
    if why:
        parts.append(why)
    nxt = (next_title or "").strip()
    if nxt:
        parts.append(f"Next: {nxt} is now active.")
    return " ".join(parts)
