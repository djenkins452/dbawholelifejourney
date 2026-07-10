"""
CoS journey context block — passive context for Beth.

Pure function: takes a user, returns the journey context block that the faith
CoS context builder will merge under `faith_summary.journey` (or a top-level
`journey` key, depending on integration).

CRITICAL BOUNDARY (Phase 1):
    - Beth is SILENT on the journey reading surface.
    - This context block is **passive awareness only** — Beth may reference
      it factually when invoked elsewhere ("you're on Day 6 of arc 1"), but
      MUST NOT proactively initiate journey conversation.
    - `momentum_score` is internal-only — Beth must not recite it.

The block is intentionally smaller than the SAE state block: it includes only
fields appropriate for Beth's narrative reference. `momentum_score` and
`application_committed_this_week` are deliberately omitted from Beth-facing
context (they're for internal observability dashboards, not Beth).
"""

from __future__ import annotations

from typing import Any

from apps.faith.journey.state import build_journey_state


def build_journey_context_block(user) -> dict[str, Any]:
    """Return the journey context block for CoS.

    Returns `{"active": False}` when the user has no active journey.
    Beth's prompt should branch on `active` before referencing other fields.
    """
    state = build_journey_state(user)
    if not state["active"]:
        return {"active": False}

    return {
        "active": True,
        "journey_name": state["journey_path_name"],
        "arc_name": state["current_arc_name"],
        "arc_day": state["current_arc_day"],
        "arc_total_days": state["current_arc_total_days"],
        "preferred_difficulty": state["preferred_difficulty"],
        "days_since_last_read": state["days_since_last_read"],
        # NOTE: momentum_score and application_committed_this_week
        # deliberately omitted. Internal-only. Beth never sees them.
    }


# ==============================================================================
# CURRENT CONTEXT — deterministic scripture truth for the Bible Reading page.
#
# WLJ already knows EXACTLY what scripture is on screen: the reading plan, the day, the
# references (e.g. "Malachi 3:1-7", "Malachi 4:1-6"), the translation, and the verse text.
# This composes that into the uniform Narratable shape {title, content, kind} so the
# conversational model never has to infer scripture from page text. Pure and deterministic
# — no LLM, no reasoning; just exposure of truth the page is already displaying. Consumed
# by UserJourneyDayProgress.get_context_summary() via the Current Context Contract.
# ==============================================================================

_PASSAGE_CAP = 2500
_AUTHORED_CAP = 800


def narrate_journey_day(day) -> dict | None:
    """Return {title, content, kind} of deterministic scripture context for `day` (a
    JourneyDay), or None. Reads only the day's authored fields — no user data."""
    if day is None:
        return None

    arc = getattr(day, "arc", None)
    path = getattr(arc, "journey_path", None)
    plan_name = (getattr(path, "name", "") or getattr(arc, "name", "")
                 or "Reading plan").strip()
    day_number = getattr(day, "day_number", None)
    title = f"{plan_name} — Day {day_number}" if day_number else plan_name

    refs = day.scripture_refs if isinstance(day.scripture_refs, list) else []
    content_json = day.scripture_content if isinstance(day.scripture_content, dict) else {}
    translation = str(content_json.get("translation") or "").strip()
    blocks = content_json.get("blocks")
    blocks = blocks if isinstance(blocks, list) else []

    lines = [title, f"Reading plan: {plan_name}"]
    if day_number:
        lines.append(f"Day: {day_number}")
    if refs:
        # The refs ARE the deterministic book / chapter / verse-range truth on screen.
        lines.append("Scripture on screen: " + ", ".join(str(r) for r in refs))
    if translation:
        lines.append(f"Translation: {translation}")

    verses = []
    for b in blocks:
        if isinstance(b, dict):
            text = str(b.get("text") or "").strip()
            if text:
                ref = str(b.get("ref") or "").strip()
                verses.append((f"{ref} " if ref else "") + text)
    if verses:
        lines.append("Passage:\n" + "\n".join(verses)[:_PASSAGE_CAP])

    for label, attr in (("Context", "context_before"),
                        ("Key insight", "key_insight"),
                        ("Reflection prompt", "reflection_prompt")):
        val = str(getattr(day, attr, "") or "").strip()
        if val:
            lines.append(f"{label}: {val[:_AUTHORED_CAP]}")

    return {"title": title, "content": "\n\n".join(lines).strip(),
            "kind": "scripture reading"}
