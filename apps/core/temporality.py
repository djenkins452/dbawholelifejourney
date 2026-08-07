# =============================================================================
# File: apps/core/temporality.py
# Purpose: CARD TEMPORALITY — a reusable declaration of WHICH KIND OF TRUTH a
#   workspace card represents, so a date-parameterized workspace (Dashboard(date)
#   today; any future date-aware workspace) can decide how to render each card for
#   a selected date WITHOUT the workspace itself switching "modes".
#
#   The card declares its temporality; the renderer decides what to do with it.
#   This keeps "one Dashboard parameterized by a date" — not "a Today dashboard
#   and a Past dashboard" — and the concept transfers unchanged to any other
#   workspace that later becomes date-aware.
# =============================================================================
"""Card temporality — the type of truth a workspace card represents.

Three categories:

* ``DATE_SCOPED`` — reconstructs deterministic truth for the *selected* date and
  simply consumes that date (completion score, rhythm, outstanding, completed,
  nutrition, water, sleep, exercise, journal, faith, medications, habits, tasks,
  daily metrics). Renders for today AND any past day.

* ``LIVE`` — intentionally represents "right now" and must NOT be reconstructed
  for a past date (executive summary, mission spotlight, goal cockpit, current
  priorities / momentum / risks). When a non-today date is viewed the renderer
  hides it (or, if a workspace opts in, badges it "Current") — it NEVER fabricates
  a historical version. A later "Executive Retrospective" would be a *new*
  DATE_SCOPED card that replaces the LIVE summary for historical dates — it does
  not turn this LIVE card into a historical one.

* ``FUTURE`` — RESERVED. Cards that will require snapshots or genuine historical
  analysis. Deliberately unimplemented; declared only so the architecture never
  assumes every future card is either LIVE or DATE_SCOPED. The renderer never
  shows a FUTURE card until it is actually built.
"""

from __future__ import annotations

from enum import Enum


class Temporality(str, Enum):
    """The kind of truth a card represents. ``str`` mixin → template/JSON safe."""

    DATE_SCOPED = "date_scoped"
    LIVE = "live"
    FUTURE = "future"  # reserved; not implemented


class RenderMode(str, Enum):
    """What the renderer should do with a card for the viewed date."""

    SHOW = "show"                  # render normally
    SHOW_CURRENT = "show_current"  # render, badged as "Current" (live truth on a past-date page)
    HIDE = "hide"                  # do not render


def render_mode(
    temporality: Temporality | str,
    *,
    is_today: bool,
    live_on_past: str = "hide",
) -> RenderMode:
    """Decide how to render a card, from its declared temporality alone.

    A pure declaration — no side effects, no I/O.

    Args:
        temporality: the card's declared :class:`Temporality`.
        is_today: whether the viewed date is the user's today.
        live_on_past: how a LIVE card behaves on a past date — ``"hide"``
            (default; the Dashboard's two-mode choice) or ``"badge"`` (render
            with a visible "Current" badge). Never "reconstruct" — a LIVE card
            has no historical form.

    Returns:
        A :class:`RenderMode`.
    """
    # Today: every implemented card renders as itself.
    if is_today:
        if temporality == Temporality.FUTURE:
            return RenderMode.HIDE
        return RenderMode.SHOW

    # A past (or otherwise non-today) date is being viewed.
    if temporality == Temporality.DATE_SCOPED:
        return RenderMode.SHOW
    if temporality == Temporality.LIVE:
        return RenderMode.SHOW_CURRENT if live_on_past == "badge" else RenderMode.HIDE
    # FUTURE (reserved) — never rendered until implemented.
    return RenderMode.HIDE
