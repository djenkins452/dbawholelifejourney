"""Universal Action Routing — one contract every WLJ surface honors.

PROBLEM: actionable items are shown all over WLJ (dashboard, Executive Briefing,
Beth, check-ins, notifications, Action Center) but each surface decided on its
own — or not at all — how to help the user DO the thing. Most only described it.

CAPABILITY: any actionable item resolves to ONE ``ActionRoute`` so the
interaction is identical everywhere:

  • informational  — nothing to do (e.g. "Weight trending down").
  • complete_here  — can be completed immediately; carries a completion endpoint
                     (Shower, Take Medication, Make Bed → a POST url).
  • open_workflow  — navigate to the workflow that performs it (Log Nutrition,
                     Journal, Log Weight, Read Today's Verse → a destination url).

Destinations are resolved against the canonical ``TeachingDestination`` registry
— the SAME keyword→URL map the Teaching Tool uses to answer "where do I log my
weight?" — so there is ONE source of truth and no per-screen hardcoding. Adding
a new destination is a registry row, not code.

Read-only and crash-safe: an unresolvable subject degrades to ``informational``;
this module NEVER raises into a request/render path.

USAGE (any surface):

    from apps.core.action_router import route_for_finding, resolve_route

    # An Insight / briefing finding (dict or model) → route:
    route = route_for_finding(item)          # ActionRoute
    item["route"] = route.as_dict()          # hand to the template

    # An item that is completable inline (has a POST endpoint):
    route = resolve_route(text=title, complete_url=toggle_url)

Every template/serializer then honors ``route.action_type`` identically.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ActionType:
    INFORMATIONAL = "informational"
    COMPLETE_HERE = "complete_here"
    OPEN_WORKFLOW = "open_workflow"


@dataclass
class ActionRoute:
    """The canonical, surface-agnostic description of how to act on an item."""

    action_type: str = ActionType.INFORMATIONAL
    # open_workflow — where to navigate.
    destination_url: Optional[str] = None
    destination_label: Optional[str] = None
    # complete_here — the POST endpoint that marks it done.
    complete_url: Optional[str] = None
    complete_label: str = "Mark Complete"
    # hover / aria text.
    tooltip: Optional[str] = None
    # provenance (which destination_id / subject resolved it) — for debugging.
    source: Optional[str] = None

    @property
    def is_actionable(self) -> bool:
        return self.action_type != ActionType.INFORMATIONAL

    def as_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "destination_url": self.destination_url,
            "destination_label": self.destination_label,
            "complete_url": self.complete_url,
            "complete_label": self.complete_label,
            "tooltip": self.tooltip,
            "is_actionable": self.is_actionable,
        }


# ── Subject normalization ────────────────────────────────────────────────
# Map the words that show up in findings/signals to a canonical SUBJECT, and
# each subject to the keyword phrase we match against the TeachingDestination
# registry. This is the ONE place a metric's "where do I act on it" lives.
# Keyed by subject → (regex of trigger words, registry match phrase, module).
_SUBJECT_RULES: list[tuple[str, "re.Pattern[str]", str, str]] = [
    ("nutrition",  re.compile(r"\b(protein|calorie|calories|macro|macros|nutrition|carb|carbs|fat intake|eating|meal|meals|diet)\b", re.I), "log nutrition food", "health"),
    ("weight",     re.compile(r"\bweight\b", re.I),                                   "log weight", "health"),
    ("sleep",      re.compile(r"\bsleep\b", re.I),                                    "sleep", "health"),
    ("glucose",    re.compile(r"\b(glucose|a1c|gmi|blood sugar|cgm)\b", re.I),        "glucose", "health"),
    ("blood_pressure", re.compile(r"\b(blood pressure|bp|systolic|diastolic)\b", re.I), "blood pressure", "health"),
    ("medication", re.compile(r"\b(medication|medicine|dose|adherence|pill|prescription|supplement)\b", re.I), "medication medicine", "health"),
    ("workout",    re.compile(r"\b(workout|training|exercise|lift|cardio|run)\b", re.I), "workout exercise", "health"),
    ("movement",   re.compile(r"\b(steps|movement|activity|walk|active)\b", re.I),    "activity steps", "health"),
    ("hydration",  re.compile(r"\b(water|hydration|hydrate|electrolyte)\b", re.I),    "water hydration", "health"),
    ("journal",    re.compile(r"\b(journal|reflection|reflect|gratitude)\b", re.I),   "journal", "journal"),
    ("prayer",     re.compile(r"\b(prayer|pray)\b", re.I),                            "prayer", "faith"),
    ("bible",      re.compile(r"\b(bible|scripture|verse|reading plan|devotion)\b", re.I), "bible reading verse", "faith"),
    ("goal",       re.compile(r"\b(goal|milestone|mission)\b", re.I),                 "goals", "purpose"),
    ("calendar",   re.compile(r"\b(calendar|schedule|appointment|event)\b", re.I),    "calendar schedule", "life"),
    ("task",       re.compile(r"\b(task|to-?do|project)\b", re.I),                    "tasks", "life"),
    ("finance",    re.compile(r"\b(budget|spending|finance|expense|money)\b", re.I),  "finance budget", "finance"),
]


def infer_subject(text: str, module: str | None = None) -> tuple[str | None, str | None, str | None]:
    """Return (subject, match_phrase, module) inferred from free text, or the
    module fallback when no specific subject matches. (None, None, None) when
    nothing is derivable."""
    t = text or ""
    for subject, pattern, phrase, mod in _SUBJECT_RULES:
        if pattern.search(t):
            return subject, phrase, module or mod
    if module:
        # No specific subject — fall back to the module's home destination.
        return None, module, module
    return None, None, None


# ── Deterministic subject → destination fallback (reverse-based, no DB) ───
# The canonical registry (TeachingDestination) is the SOURCE OF TRUTH, but it is
# DB-backed and may be empty on a fresh install / dev DB. This hardcoded map
# guarantees the core subjects that actually appear as findings/signals ALWAYS
# route, with zero queries. Only verified URL names live here (a bad name
# degrades to the module home, then informational — never a broken link).
_SUBJECT_FALLBACK: dict[str, tuple[str, str]] = {
    "nutrition":  ("health:nutrition_home",    "Log nutrition"),
    "weight":     ("health:weight_list",       "Log weight"),
    "sleep":      ("health:sleep_list",        "Open sleep"),
    "glucose":    ("health:glucose_dashboard", "Open glucose"),
    "workout":    ("health:workout_list",      "Log a workout"),
    "movement":   ("health:fitness_home",      "Open activity"),
    "hydration":  ("health:home",              "Open health"),
    "blood_pressure": ("health:home",          "Open vitals"),
    "medication": ("health:home",              "Open medications"),
    "journal":    ("journal:home",             "Open your journal"),
    "prayer":     ("faith:prayer_list",        "Open prayers"),
    "bible":      ("faith:reading_plans",      "Open Bible reading"),
    "goal":       ("purpose:goal_list",        "Open goals"),
    "calendar":   ("life:calendar",            "Open calendar"),
    "task":       ("life:task_list",           "Open tasks"),
}
_MODULE_HOME: dict[str, tuple[str, str]] = {
    "health":  ("health:home",   "Open health"),
    "faith":   ("faith:home",    "Open faith"),
    "purpose": ("purpose:home",  "Open goals"),
    "journal": ("journal:home",  "Open your journal"),
    "life":    ("life:home",     "Open organize"),
}


def _safe_reverse(name: str) -> str | None:
    try:
        from django.urls import reverse
        return reverse(name)
    except Exception:
        return None


# ── Destination resolution against the TeachingDestination registry ───────

# Stopwords include generic action verbs / filler so a single weak token (e.g.
# "log", "open") can never drive a registry match — only CONTENT words (protein,
# weight, sleep …) should.
_STOP = {
    "the", "a", "an", "to", "of", "your", "my", "for", "and", "is", "on", "in",
    "log", "open", "view", "track", "check", "see", "go", "home", "today",
    "target", "below", "above", "over", "under", "avg", "average", "range",
    "day", "days", "readings", "reading",  # "reading" alone is filler; "bible reading" handled by subject rules
}


def _tokens(s: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", (s or "").lower()) if w and w not in _STOP}


def _best_destination(match_phrase: str, module: str | None):
    """Best TeachingDestination for a match phrase (+ optional module bonus).

    Deterministic keyword-overlap scoring against the cached, active registry.
    Returns the destination object or None. Never raises.
    """
    try:
        from apps.help.models import TeachingDestination
        dests = TeachingDestination.get_all_active()
    except Exception:
        return None

    want = _tokens(match_phrase)
    if not want:
        return None

    best, best_score = None, 0
    for d in dests:
        kw = set()
        for k in getattr(d, "keywords_list", []):
            kw |= _tokens(k)
        kw |= _tokens(getattr(d, "name", ""))
        overlap = len(want & kw)
        if overlap == 0:
            continue
        score = overlap * 10
        if module and (getattr(d, "module", "") or "").lower() == module.lower():
            score += 3
        # Prefer shorter/more-specific destinations on ties (lower sort_order).
        score -= min(getattr(d, "sort_order", 0) or 0, 9) * 0.01
        if score > best_score:
            best, best_score = d, score
    return best


def _resolve_destination(*, text, subject, module):
    """Return (url, label, tooltip, source) for a navigable destination, or
    (None, …) — trying the canonical registry first, then the deterministic
    subject fallback, then the module home. Never raises."""
    subj, phrase, mod = infer_subject(text or subject or "", module)

    # 1. Registry (canonical, user-curated source of truth). Empty in dev.
    #    Match against the RAW finding text (precise content keywords like
    #    "protein") PLUS the normalized subject phrase, so a curated destination
    #    with the exact keyword wins over the generic fallback.
    dest = _best_destination(
        " ".join(p for p in (text, subject, phrase) if p), mod,
    )
    if dest is not None and getattr(dest, "url", None):
        return (dest.url, getattr(dest, "name", None),
                getattr(dest, "explanation", None) or None,
                getattr(dest, "destination_id", None))

    # 2. Deterministic subject fallback — always works, zero queries.
    key = subj or (subject or "").strip().lower()
    spec = _SUBJECT_FALLBACK.get(key)
    if spec:
        url = _safe_reverse(spec[0])
        if url:
            return url, spec[1], None, key

    # 3. Module home — a sensible landing when the subject is unknown.
    home = _MODULE_HOME.get((mod or module or "").strip().lower())
    if home:
        url = _safe_reverse(home[0])
        if url:
            return url, home[1], None, "module_home"

    return None, None, None, None


def resolve_route(
    *,
    text: str | None = None,
    subject: str | None = None,
    module: str | None = None,
    complete_url: str | None = None,
    complete_label: str | None = None,
    destination_url: str | None = None,
    destination_label: str | None = None,
) -> ActionRoute:
    """Resolve any actionable item to a single ActionRoute.

    Precedence:
      1. ``complete_url`` present            → COMPLETE_HERE (may ALSO carry a
                                               navigate destination).
      2. explicit ``destination_url``        → OPEN_WORKFLOW.
      3. resolve a destination from subject/ → OPEN_WORKFLOW.
         text/module via the registry
      4. nothing resolvable                  → INFORMATIONAL.
    """
    try:
        # Resolve a navigate destination from text/subject if not given.
        nav_url, nav_label, nav_tip, source = destination_url, destination_label, None, None
        if not nav_url and (subject or text or module):
            nav_url, _lbl, nav_tip, source = _resolve_destination(
                text=text, subject=subject, module=module,
            )
            nav_label = nav_label or _lbl

        if complete_url:
            return ActionRoute(
                action_type=ActionType.COMPLETE_HERE,
                complete_url=complete_url,
                complete_label=complete_label or "Mark Complete",
                destination_url=nav_url,
                destination_label=nav_label,
                tooltip=nav_tip,
                source=source,
            )
        if nav_url:
            return ActionRoute(
                action_type=ActionType.OPEN_WORKFLOW,
                destination_url=nav_url,
                destination_label=nav_label or "Open",
                tooltip=nav_tip,
                source=source,
            )
        return ActionRoute(action_type=ActionType.INFORMATIONAL)
    except Exception:
        logger.debug("resolve_route failed for text=%r module=%r", text, module,
                     exc_info=True)
        return ActionRoute(action_type=ActionType.INFORMATIONAL)


def route_for_finding(item) -> ActionRoute:
    """Route an Insight / briefing finding (a dict or a model) by its title +
    module. Findings are OPEN_WORKFLOW (navigate to where you'd act) or
    INFORMATIONAL (no destination) — never complete_here (they aren't a discrete
    checkbox). Crash-safe."""
    try:
        if isinstance(item, dict):
            title = item.get("title") or ""
            message = item.get("message") or ""
            module = item.get("module")
        else:
            title = getattr(item, "title", "") or ""
            message = getattr(item, "message", "") or ""
            module = getattr(item, "module", None)
        return resolve_route(text=f"{title} {message}", module=module)
    except Exception:
        logger.debug("route_for_finding failed", exc_info=True)
        return ActionRoute(action_type=ActionType.INFORMATIONAL)
