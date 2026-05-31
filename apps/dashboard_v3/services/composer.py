"""
Dashboard V3 Composer — assembles the page context from canonical sources.

This is a thin orchestrator. ALL truth comes from existing engines:

    Gauges                  ← GoalCockpitService (already deterministic,
                                domain-driven by active LifeGoals/HabitGoals)
    Executive Summary       ← apps.core.cos_briefing.build_executive_summary
    Focus Right Now         ← same composer (which reuses get_next_action)
    Accountability Cards    ← per-domain composition from SAE state +
                                Insights + GuidanceItem (deterministic)
    Rhythm Sections         ← apps.core.cos_briefing.build_rhythm_sections
    Weather                 ← apps.dashboard.services.weather

NO new business logic. NO LLM. Only reshaping for the presentation layer.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Domain order for accountability cards (presentation-only).
ACCOUNTABILITY_DOMAIN_ORDER = [
    "health",
    "faith",
    "purpose",
    "relationships",
    "life",
    "finance",
]

DOMAIN_LABELS = {
    "health": "Health",
    "faith": "Faith",
    "purpose": "Purpose",
    "relationships": "Relationships",
    "life": "Life Execution",
    "finance": "Finance",
    "work": "Work",
}

DOMAIN_ICONS = {
    "health": "💪",
    "faith": "✝️",
    "purpose": "🎯",
    "relationships": "👥",
    "life": "🧭",
    "finance": "💼",
    "work": "📋",
}


def build_dashboard_v3_context(user) -> dict[str, Any]:
    """Build the full dashboard_v3 page context.

    Read-only. Safe on the request path. Returns a dict that the template
    consumes directly — no further compute happens in templates.
    """
    cockpit_domains = _safe(_build_cockpit_domains_raw, user, default=[])

    context: dict[str, Any] = {
        # Raw canonical dial data — matches v2 cockpit_dial.html contract.
        "cockpit_domains": cockpit_domains,
        # Mission spotlight — the headline foundational goal, read-only.
        # None when no foundational goal qualifies (section renders nothing).
        "mission": _safe(_build_mission_card, user, default=None),
        # Composed/fallback gauges (used only when cockpit is empty).
        "gauges": _safe(_build_gauges, user, default=[]),
        "executive_summary": _safe(_build_executive_summary, user, default={}),
        "focus_now": None,        # filled below from executive_summary
        "follow_on": [],          # filled below from executive_summary
        "accountability_cards": _safe(
            _build_accountability_cards, user, default=[]
        ),
        "rhythm": _safe(_build_rhythm, user, default={"sections": [], "totals": {}}),
        "utilities": _safe(_build_utilities, user, default={}),
    }

    exec_summary = context["executive_summary"] or {}
    context["focus_now"] = exec_summary.get("focus_now")
    context["follow_on"] = exec_summary.get("follow_on") or []

    # ── Self-critique fix: drop biggest_risk if it duplicates focus_now.
    risk = exec_summary.get("biggest_risk")
    focus = context["focus_now"]
    if risk and focus and risk.get("title") == focus.get("title"):
        # The user is already looking at this in Focus Now — no value in
        # repeating it in the briefing.
        exec_summary["biggest_risk"] = None

    return context


def _build_cockpit_domains_raw(user) -> list[dict]:
    """Return the GoalCockpitService output unchanged.

    v3 renders these via the canonical v2 cockpit_dial.html partial so the
    visual matches v2 (which is what the user actually wants at the top of
    the page). No transformation — same shape, same source of truth.
    """
    from apps.dashboard_v2.services.cockpit_service import GoalCockpitService
    return GoalCockpitService(user).get_cockpit_data() or []


# ── Section builders ──────────────────────────────────────────────────


# Truthful momentum labels — only ever set from a real GoalMomentumSnapshot
# trend. No optimistic default; absence of a snapshot omits the row entirely.
_MOMENTUM_DISPLAY = {
    "rising": {"label": "Improving", "trend": "up"},
    "stable": {"label": "Steady", "trend": "flat"},
    "falling": {"label": "Declining", "trend": "down"},
}

# Fixed, deterministic coaching lines for the "How things are going" panel.
# Selected ONLY by the persisted momentum trend — never generated, never
# health-conclusion. These are the exact approved sentences; the panel renders
# nothing when there is no momentum trend to ground them.
_MISSION_PANEL_NARRATIVE = {
    "rising": (
        "Your consistency is building momentum. "
        "Keep focusing on your foundation phase."
    ),
    "stable": (
        "Progress is steady. Small actions continue compounding."
    ),
    "falling": (
        "Momentum has slowed. Protect consistency and focus on your "
        "current milestone."
    ),
}

# Icon glyphs for the Key Drivers row — purely decorative labels for known
# deterministic signals (no inference, fixed per signal key).
_DRIVER_ICONS = {
    "weight": "⚖️",      # balance scale
    "workouts": "\U0001F3CB️",  # weight lifter
    "steps": "\U0001F45F",         # running shoe
    "movement": "\U0001F3C3",      # runner — conditioning / movement (not step-only)
    "sleep": "\U0001F634",         # sleeping face
    "journal": "✍️",      # writing hand
    "nutrition": "\U0001F957",     # salad
}

# ── Phase 3: Mission Intelligence ────────────────────────────────────────
# Deterministic, explainable mission state. NO percentages, NO hidden scoring.
# The state is derived from (a) the persisted GoalMomentumSnapshot trend (the
# ONLY source allowed to claim a direction) and (b) objective behaviour signals
# read from pre-computed SAE module state. Every state maps 1:1 to a ring word,
# a label, a tone (reusing the momentum CSS classes), and a fixed base coaching
# line. The narrative appends grounded clauses that reference the ACTUAL top
# helping / needs signal — never fabricated personalisation.
_STATE_GETTING_STARTED = "GETTING_STARTED"
_STATE_BUILDING_MOMENTUM = "BUILDING_MOMENTUM"
_STATE_IMPROVING = "IMPROVING"
_STATE_MAINTAINING = "MAINTAINING"
_STATE_SLIPPING = "SLIPPING"
_STATE_AT_RISK = "AT_RISK"

# Ring centre word — answers "what am I doing right now" without a number.
_RING_WORD = {
    _STATE_GETTING_STARTED: "BUILDING",
    _STATE_BUILDING_MOMENTUM: "MOMENTUM",
    _STATE_IMPROVING: "ON TRACK",
    _STATE_MAINTAINING: "STEADY",
    _STATE_SLIPPING: "RECOVER",
    _STATE_AT_RISK: "REFOCUS",
}

# Human label for the status pill.
_STATE_LABEL = {
    _STATE_GETTING_STARTED: "Getting started",
    _STATE_BUILDING_MOMENTUM: "Building momentum",
    _STATE_IMPROVING: "Improving",
    _STATE_MAINTAINING: "Maintaining",
    _STATE_SLIPPING: "Slipping",
    _STATE_AT_RISK: "Needs attention",
}

# Tone reuses the existing momentum indicator classes (up / flat / down).
_STATE_TONE = {
    _STATE_GETTING_STARTED: "flat",
    _STATE_BUILDING_MOMENTUM: "up",
    _STATE_IMPROVING: "up",
    _STATE_MAINTAINING: "flat",
    _STATE_SLIPPING: "down",
    _STATE_AT_RISK: "down",
}

# Fixed base coaching line per state — executive-coach tone, approved verbatim.
# NEVER generated. Grounded signal clauses are appended at render time.
_STATE_BASE = {
    _STATE_GETTING_STARTED: (
        "You've committed to the mission. Right now the win is consistency — "
        "small actions create momentum long before race day."
    ),
    _STATE_BUILDING_MOMENTUM: (
        "Momentum is forming. Your recent habits are moving you in the right "
        "direction. Protect consistency more than intensity."
    ),
    _STATE_IMPROVING: (
        "You are moving in the right direction. The work you're doing now "
        "compounds over time — France is built in ordinary days."
    ),
    _STATE_MAINTAINING: (
        "You're holding steady. The opportunity now is building from "
        "maintenance into meaningful forward progress."
    ),
    _STATE_SLIPPING: (
        "Some important habits have softened recently. This is recoverable — "
        "focus on rebuilding consistency before intensity."
    ),
    _STATE_AT_RISK: (
        "Several mission drivers need attention. The good news: momentum can "
        "return quickly when small routines come back online."
    ),
}

# Documented, defensible signal thresholds. These are the explicit lines that
# split a tracked behaviour into "helping momentum" vs "needs attention".
# Objective-absence (zero workouts, zero journal entries, nutrition untracked)
# is always a "need" — never an invented threshold. Anything between the two
# bands is neutral (surfaced as a plain driver, claimed for neither side).
_SIGNAL_BANDS = {
    "workouts": {"help": 3, "need": 1},      # >=3/wk helping; ==0 needs
    "steps": {"help": 8000, "need": 4000},   # >=8k helping; <4k needs
    "sleep": {"help": 7.0, "need": 5.5},     # >=7h helping; 5.5-6.99 watch; <5.5 needs
    "journal": {"help": 3, "need": 1},       # >=3/wk helping; ==0 needs
    "nutrition": {"help": 70, "need": None},  # >=70% helping; untracked needs
}

# Adaptive Movement Model (Phase 3.5). The "Movement" signal replaces raw
# step-only logic so a user who is genuinely active through workouts / biking /
# strength is NOT penalised for low daily steps (e.g. pain-aware training). It
# aggregates real tracked activity — structured workouts (and their minutes) +
# daily steps — and is interpreted by the mission's current PHASE. Documented,
# defensible thresholds only; nothing invented, nothing hardcoded per user.
_MOVEMENT_BANDS = {
    "workouts_active": 2,   # >=2 structured sessions/wk = meaningful movement
    "steps_help": 8000,     # daily-step bands reused from _SIGNAL_BANDS["steps"]
    "steps_need": 4000,
}

# Grounded clause fragments appended to the base coaching line. help_frag is
# used when the signal is the top "helping" driver; need_frag when it is the
# top "needs" driver. Each references the ACTUAL tracked behaviour only.
_SIGNAL_FRAGMENTS = {
    "workouts": {
        "help": "Your training is consistent right now — that's the engine.",
        "watch": "Workouts are happening — settling into a steady rhythm builds the engine.",
        "need": "Workouts have gone quiet — that's the place to restart.",
    },
    "journal": {
        "help": "You're journaling regularly, which keeps you anchored to the why.",
        "watch": "You're journaling now and then — a short daily note deepens the habit.",
        "need": "Journaling has dropped off — a short daily note rebuilds the habit.",
    },
    "weight": {
        "help": "Your weight is trending the right way.",
        "watch": "Weight is holding steady — small consistency keeps it moving your way.",
        "need": "Weight has drifted up recently — worth a gentle reset.",
    },
    "sleep": {
        "help": "Recovery is supporting momentum — sleep is helping your energy and consistency.",
        "watch": "Recovery could improve, but current sleep is enough to maintain momentum.",
        "need": "Recovery may be limiting energy, consistency and glucose stability — sleep is the first lever.",
    },
    "steps": {
        "help": "Daily movement is strong.",
        "need": "Daily movement has dropped off lately.",
    },
    "movement": {
        "help": "Your workouts are keeping you genuinely active, even on lighter-step days.",
        "watch": "You're staying active, but daily movement is still light — short, joint-friendly sessions add up.",
        "need": "Activity is light right now — small, joint-friendly movement is the place to rebuild.",
    },
    "nutrition": {
        "help": "Nutrition is dialled in.",
        "watch": "Nutrition is tracked but has room to climb toward your targets.",
        "need": "Nutrition isn't being tracked yet — that's the next lever.",
    },
}


def _latest_momentum(goal):
    """Latest persisted momentum snapshot for a goal (read-only).

    Reads the nightly-computed GoalMomentumSnapshot. NEVER triggers live
    momentum_service computation on the request path.
    """
    return goal.momentum_snapshots.first()  # ordered -snapshot_date


# Conservative leading-emoji matcher: regional-indicator flag pairs, the
# main pictograph/symbol blocks, dingbats, and the joiners (VS16 / ZWJ) that
# bind multi-codepoint emoji. Used ONLY to lift a user-typed emoji out of a
# goal title — never to infer one from words. ("France" matches nothing.)
_LEADING_EMOJI_RE = re.compile(
    r"^("
    r"[\U0001F1E6-\U0001F1FF]{2}"          # flag (two regional indicators)
    r"|[\U0001F300-\U0001FAFF☀-➿⬀-⯿⌀-⏿]"
    r"[️‍\U0001F300-\U0001FAFF]*"  # + variation selectors / ZWJ joins
    r")\s*"
)


def _resolve_mission_icon(goal):
    """Resolve the Mission card icon WITHOUT hardcoding or inference.

    Priority (per approved hierarchy):
      1. Explicit ``mission_icon`` metadata the user set.
      2. A leading emoji the user typed at the start of the title (lifted out
         so it is not shown twice).
      3. Graceful fallback: no icon (None) — the card renders cleanly.

    Returns ``(icon_or_none, display_title)``. NEVER keys off title words
    (no ``if "France" in title``).
    """
    raw_title = (goal.title or "").strip()

    explicit = (goal.mission_icon or "").strip()
    if explicit:
        return explicit, raw_title

    match = _LEADING_EMOJI_RE.match(raw_title)
    if match:
        icon = match.group(1)
        display_title = raw_title[match.end():].strip() or raw_title
        return icon, display_title

    return None, raw_title


def _build_mission_card(user) -> dict | None:
    """Mission spotlight built ONLY from existing deterministic state.

    Reuse: LifeGoal + GoalMilestone + GoalMomentumSnapshot. Read-only, no
    scoring, no readiness %, no coaching, no fabrication. Returns None when
    the user has not selected an active Primary Mission — the section then
    renders nothing (no placeholder, no "choose a mission" prompt).

    Selection is delegated to the shared purpose-domain selector so the
    dashboard mission and Beth's mission are always the SAME goal.
    """
    from apps.purpose.mission_selection import select_active_mission_goal
    from apps.core.utils import get_user_now

    today = get_user_now(user).date()

    goal = select_active_mission_goal(user)
    if goal is None:
        return None

    icon, display_title = _resolve_mission_icon(goal)

    # Current focus — next incomplete milestone (NOT a fabricated "phase").
    nm = goal.next_milestone
    current_focus = nm.title if nm else None
    next_milestone_date = (
        nm.target_date.strftime("%b %d, %Y") if nm and nm.target_date else None
    )
    # Days until that milestone — only for a real future target date. Distinct
    # from the mission-level days_remaining (this is per-milestone timing).
    next_milestone_days = None
    if nm and nm.target_date and nm.target_date > today:
        next_milestone_days = (nm.target_date - today).days

    # Momentum — latest snapshot trend only. Omit when no snapshot/trend.
    snap = _latest_momentum(goal)
    momentum = None
    if snap and snap.momentum_trend:
        momentum = _MOMENTUM_DISPLAY.get(snap.momentum_trend)

    # "How things are going" panel — always present for an active mission.
    # Prefers the real persisted momentum trend; falls back to a deterministic,
    # milestone-grounded state (neutral trend, never a fabricated direction)
    # when the nightly momentum snapshot has not been computed yet.
    panel = _build_mission_panel(goal, snap)

    # Days remaining — only when a real future target date exists.
    days_remaining = None
    if goal.target_date and goal.target_date > today:
        days_remaining = (goal.target_date - today).days

    # Hero ring — milestone PROGRESSION, not readiness. This is a literal,
    # defensible count ("3 of 7 milestones complete"), never a fabricated
    # percentage or health verdict. When no milestones exist the ring is a
    # plain decorative anchor with no numeric claim.
    progress = _build_mission_progress(goal)

    # Optional supporting line — the user's own "why", excerpted. Never
    # generated; rendered only when they wrote one.
    why = (goal.why_it_matters or "").strip() or None

    # Short tagline under the title — the user's own description, if any.
    subtitle = (goal.description or "").strip() or None

    # Read the pre-computed SAE module states ONCE (read-only) and reuse them
    # for both the deterministic drivers row and the mission-status classifier.
    states = _read_mission_states(user)

    # Key Drivers — deterministic behaviour signals, read-only, gracefully
    # omitted when unavailable. Kept for back-compat with existing consumers.
    drivers = _build_mission_drivers(states)

    # Phase 3 — Mission Intelligence. Deterministic state classification +
    # grounded coaching narrative + helping/needs split. Built from the same
    # SAE signals (no extra queries) and the persisted momentum trend only.
    # Phase 3.5 — the mission's milestone PHASE shapes how movement is judged
    # (early phases reward consistency over step volume).
    phase = _mission_movement_phase(goal)
    signals = _evaluate_mission_signals(states, phase)
    status = _build_mission_status(goal, snap, signals, today)

    # Phase 5 — emotional motivation layer. Read-only metadata, no scoring.
    # These touch a SINGLE mission goal's relations (links + wins), so it is a
    # constant two extra queries — never an N+1 over rows.
    hero_image_url = goal.hero_image.url if goal.hero_image else None
    mission_links = [
        {"title": link.title, "url": link.url, "icon": link.icon}
        for link in goal.motivation_links.all()[:6]
    ]
    wins = list(goal.victory_milestones.all())
    victories = None
    if wins:
        victories = {
            "total": len(wins),
            "completed": sum(1 for w in wins if w.completed),
        }

    return {
        "icon": icon,
        "title": display_title,
        "subtitle": subtitle,
        "is_primary": True,  # selector guarantees an active Primary Mission
        "current_focus": current_focus,
        "next_milestone_date": next_milestone_date,
        "next_milestone_days": next_milestone_days,
        "momentum": momentum,
        "panel": panel,
        "drivers": drivers,
        "status": status,
        "days_remaining": days_remaining,
        "progress": progress,
        "why": why,
        "hero_image_url": hero_image_url,
        "mission_links": mission_links,
        "victories": victories,
        "goal_id": goal.id,
    }


def _build_mission_panel(goal, snap) -> dict:
    """The "How things are going" panel — always present for an active mission.

    Truth contract: the trend direction may ONLY come from a real persisted
    ``GoalMomentumSnapshot``. When one exists we narrate it with the fixed,
    pre-approved coaching line for that trend. When the nightly snapshot has
    not been computed yet we still render the panel, but with a NEUTRAL ("flat")
    indicator and a milestone-grounded line — we never invent a rising/falling
    direction. ``is_fallback`` lets the template tone the indicator down.
    """
    if snap and snap.momentum_trend in _MISSION_PANEL_NARRATIVE:
        md = _MOMENTUM_DISPLAY.get(snap.momentum_trend, {})
        return {
            "label": md.get("label", ""),
            "trend": md.get("trend", "flat"),
            "narrative": _MISSION_PANEL_NARRATIVE[snap.momentum_trend],
            "is_fallback": False,
        }

    # No snapshot yet — deterministic, milestone-grounded fallback. No trend
    # direction is claimed (always the neutral "flat" indicator).
    if goal.completed_milestone_count > 0:
        return {
            "label": "Underway",
            "trend": "flat",
            "narrative": _MISSION_PANEL_NARRATIVE["stable"],
            "is_fallback": True,
        }
    return {
        "label": "Getting started",
        "trend": "flat",
        "narrative": (
            "Your mission is set. Consistency from here builds momentum. "
            "Focus on your current milestone."
        ),
        "is_fallback": True,
    }


def _read_mission_states(user) -> dict:
    """Read the four pre-computed SAE module states a mission depends on, ONCE.

    READ-ONLY: pulls only the nightly / SAME-cycle SAE snapshot. NEVER
    live-computes on the request path. Returned as a plain dict so both the
    drivers row and the status classifier can share a single read.
    """
    from apps.core.ai_state.state_engine import get_module_state

    return {
        "health": get_module_state(user, "health") or {},
        "fitness": get_module_state(user, "fitness") or {},
        "journal": get_module_state(user, "journal") or {},
        "nutrition": get_module_state(user, "nutrition") or {},
    }


def _build_mission_drivers(states: dict) -> list[dict]:
    """Deterministic behaviour signals for the Key Drivers row.

    READ-ONLY: consumes the pre-read SAE module state. NEVER live-computes on
    the request path, NEVER fabricates a value or a percentage. Each driver is
    included ONLY when its underlying field is present in state; a missing
    signal is gracefully omitted (no zero-fill, no placeholder). Order is fixed
    and meaningful.
    """
    health = states.get("health") or {}
    fitness = states.get("fitness") or {}
    journal = states.get("journal") or {}
    nutrition = states.get("nutrition") or {}

    drivers: list[dict] = []

    def add(key, label, value, trend=None):
        drivers.append(
            {
                "key": key,
                "icon": _DRIVER_ICONS.get(key, ""),
                "label": label,
                "value": value,
                "trend": trend,
            }
        )

    # Weight — the only signal carrying a real persisted trend direction.
    wchange = health.get("weight_change_30d")
    if wchange is not None:
        wtrend = health.get("weight_trend")
        trend = {"decreasing": "down", "increasing": "up", "stable": "flat"}.get(
            wtrend
        )
        sign = "+" if wchange > 0 else ""
        add("weight", "Weight", f"{sign}{wchange} lb / 30d", trend)

    # Workout consistency.
    workouts = fitness.get("workouts_7d")
    if workouts is not None:
        add("workouts", "Workouts", f"{workouts}/wk")

    # Steps.
    steps = health.get("steps_avg_7d")
    if steps is not None:
        add("steps", "Steps", f"{steps:,}/day")

    # Sleep.
    sleep = health.get("sleep_avg_hours_7d")
    if sleep is not None:
        add("sleep", "Sleep", f"{sleep}h avg")

    # Journal consistency.
    entries = journal.get("entries_7d")
    if entries is not None:
        add("journal", "Journal", f"{entries}/wk")

    # Nutrition consistency.
    if nutrition.get("enabled"):
        macros = nutrition.get("macro_compliance_score")
        if macros is not None:
            add("nutrition", "Nutrition", f"{macros:.0f}% macros")

    return drivers


def _mission_movement_phase(goal) -> str:
    """Deterministic mission phase from milestone progression (Phase 3.5C).

    The mission's milestone position decides what movement success looks like:

      · "foundation" (early) — consistency / conditioning matter more than step
        volume. A user active through workouts is NOT penalised for low steps.
      · "readiness" (later)  — walking tolerance / step volume re-enter as a
        real signal (e.g. building toward a run).

    Generic and explainable: no hardcoded milestone titles, no per-user logic.
    The mission is in "foundation" until at least half its milestones are done.
    A mission with no milestones is treated as foundation (still building).
    """
    total = goal.milestone_count
    if total <= 0:
        return "foundation"
    completed = goal.completed_milestone_count
    return "foundation" if completed * 2 < total else "readiness"


def _evaluate_movement_signal(fitness: dict, health: dict, phase: str) -> dict | None:
    """Adaptive Movement signal — movement-despite-limitations (Phase 3.5B).

    Replaces step-only logic. Aggregates REAL tracked activity (structured
    workouts + their minutes + daily steps) and interprets it by mission phase.
    Returns a signal dict shaped like the others, or None when there is no
    movement data at all (graceful omit — never zero-filled).

    Deterministic rules (no hidden scoring, no fabricated readiness):
      foundation phase — movement consistency > step volume:
        · active (>=2 sessions/wk)        → helping  (low steps do NOT penalise)
        · no workouts AND low/absent steps → needs    (genuinely inactive)
        · otherwise                        → neutral
      readiness phase — step tolerance re-enters:
        · active AND strong steps          → helping
        · no workouts OR low steps         → needs
        · otherwise                        → neutral
    """
    workouts = fitness.get("workouts_7d")
    minutes = fitness.get("workout_minutes_7d")
    steps = health.get("steps_avg_7d")

    # No movement data tracked at all → omit, exactly like other signals.
    if workouts is None and steps is None:
        return None

    w = workouts or 0
    bands = _MOVEMENT_BANDS
    active = w >= bands["workouts_active"]
    inactive = w == 0
    steps_strong = steps is not None and steps >= bands["steps_help"]
    steps_low = steps is None or steps < bands["steps_need"]

    if phase == "readiness":
        if active and steps_strong:
            polarity = "helping"
        elif inactive or steps_low:
            polarity = "needs"
        else:
            polarity = "neutral"
    else:  # foundation
        if active:
            polarity = "helping"
        elif inactive and steps_low:
            polarity = "needs"
        else:
            polarity = "neutral"

    # Display value — aggregate, preferring active minutes, then session count,
    # then daily steps. Never fabricated; only shows what is actually tracked.
    if w > 0:
        if minutes:
            value = f"{minutes} min/wk"
        else:
            value = f"{w} session{'s' if w != 1 else ''}/wk"
    elif steps is not None:
        value = f"{steps:,} steps/day"
    else:
        value = "No activity logged"

    frags = _SIGNAL_FRAGMENTS["movement"]
    return {
        "key": "movement",
        "icon": _DRIVER_ICONS["movement"],
        "label": "Movement",
        "value": value,
        "polarity": polarity,
        "help_frag": frags["help"],
        "watch_frag": frags.get("watch", ""),
        "need_frag": frags["need"],
    }


def _evaluate_mission_signals(states: dict, phase: str = "foundation") -> list[dict]:
    """Classify each tracked behaviour signal as helping / needs / neutral.

    READ-ONLY and fully deterministic. Polarity is decided by the documented
    ``_SIGNAL_BANDS`` thresholds and objective absence (zero workouts, zero
    journal entries, untracked nutrition are always "needs"). A signal is only
    evaluated when its underlying field is actually present in state — nothing
    is inferred or zero-filled. ``phase`` shapes the adaptive Movement signal
    (early phases reward consistency over step volume). Returns a list of dicts
    in a fixed priority order, each shaped for both the drivers split and the
    narrative builder::

        {key, icon, label, value, polarity, help_frag, need_frag}
    """
    health = states.get("health") or {}
    fitness = states.get("fitness") or {}
    journal = states.get("journal") or {}
    nutrition = states.get("nutrition") or {}

    signals: list[dict] = []

    def emit(key, label, value, polarity):
        # Each signal carries all three grounded clauses (help / watch / need);
        # the status builder picks the one matching the column it lands in. A
        # "neutral" signal is a genuine middle state — Worth Watching — not a
        # weaker need, so it is never folded into the needs column.
        frags = _SIGNAL_FRAGMENTS.get(key, {})
        signals.append(
            {
                "key": key,
                "icon": _DRIVER_ICONS.get(key, ""),
                "label": label,
                "value": value,
                "polarity": polarity,
                "help_frag": frags.get("help", ""),
                "watch_frag": frags.get("watch", ""),
                "need_frag": frags.get("need", ""),
            }
        )

    def _band_polarity(value, band):
        """helping / needs / neutral from a documented two-sided band."""
        if value >= band["help"]:
            return "helping"
        if value < band["need"]:
            return "needs"
        return "neutral"

    # Workouts — objective absence (0/wk) is always a need; >=3/wk is helping.
    workouts = fitness.get("workouts_7d")
    if workouts is not None:
        band = _SIGNAL_BANDS["workouts"]
        polarity = _band_polarity(workouts, band)
        emit("workouts", "Workouts", f"{workouts}/wk", polarity)

    # Weight — the persisted trend direction is the only truth we lean on.
    wchange = health.get("weight_change_30d")
    if wchange is not None:
        wtrend = health.get("weight_trend")
        if wtrend == "decreasing":
            polarity = "helping"
        elif wtrend == "increasing":
            polarity = "needs"
        else:
            polarity = "neutral"  # stable weight is a watch, not a need
        sign = "+" if wchange > 0 else ""
        emit("weight", "Weight", f"{sign}{wchange} lb / 30d", polarity)

    # Movement (Phase 3.5) — adaptive, phase-aware. REPLACES the step-only
    # signal: a user active through workouts is not penalised for low steps.
    # Ranked high (right after weight) so conditioning surfaces ahead of sleep.
    movement = _evaluate_movement_signal(fitness, health, phase)
    if movement is not None:
        signals.append(movement)

    # Sleep — recovery lever.
    sleep = health.get("sleep_avg_hours_7d")
    if sleep is not None:
        band = _SIGNAL_BANDS["sleep"]
        polarity = _band_polarity(sleep, band)
        emit("sleep", "Sleep", f"{sleep}h avg", polarity)

    # Journal — objective absence (0/wk) is always a need.
    entries = journal.get("entries_7d")
    if entries is not None:
        band = _SIGNAL_BANDS["journal"]
        polarity = _band_polarity(entries, band)
        emit("journal", "Journal", f"{entries}/wk", polarity)

    # Nutrition — untracked is an objective need (the next lever), not a guess.
    if nutrition.get("enabled"):
        macros = nutrition.get("macro_compliance_score")
        if macros is None:
            emit("nutrition", "Nutrition", "Not tracked", "needs")
        else:
            band = _SIGNAL_BANDS["nutrition"]
            # One-sided band (no numeric "need" floor): >=help helping, else a
            # neutral Worth-Watching signal (tracked but not yet strong).
            polarity = "helping" if macros >= band["help"] else "neutral"
            emit("nutrition", "Nutrition", f"{macros:.0f}% macros", polarity)

    return signals


def _build_mission_status(goal, snap, signals: list[dict], today) -> dict:
    """Deterministic, explainable mission-state classifier (Phase 3A/3B).

    Truth rules:
      · A *direction* (improving / slipping / at-risk) may ONLY be claimed when
        a persisted ``GoalMomentumSnapshot`` trend exists. Without a snapshot we
        restrict to the two no-direction states (GETTING_STARTED /
        BUILDING_MOMENTUM) — we never fabricate a trajectory.
      · Classification reads only objective inputs: the snapshot trend and the
        helping / needs signal counts. NO percentages, NO hidden scoring.
      · The coaching narrative is a fixed base line per state plus grounded
        clauses that name the ACTUAL top helping / needs signal — never invented
        personalisation.

    Returns ``{state, ring_word, state_label, tone, narrative, helping,
    watching, needs}`` where each list is display-ready signal dicts (max 3).
    The three columns map 1:1 to signal polarity — helping (green), neutral /
    Worth Watching (amber), needs (red) — so a genuine middle state can no
    longer masquerade as a failure.
    """
    # Classification uses ONLY the strong-signal polarity counts (unchanged
    # truth rules). NEUTRAL (Worth Watching) signals never sway the state —
    # they are a real middle category, not a softened need, so e.g. ~6h sleep
    # cannot push the mission toward Slipping / Needs attention.
    helping = [s for s in signals if s["polarity"] == "helping"]
    watching = [s for s in signals if s["polarity"] == "neutral"]
    needs = [s for s in signals if s["polarity"] == "needs"]
    trend = snap.momentum_trend if snap and snap.momentum_trend else None

    if trend == "rising":
        state = _STATE_IMPROVING if helping else _STATE_BUILDING_MOMENTUM
    elif trend == "falling":
        state = _STATE_AT_RISK if len(needs) >= 3 else _STATE_SLIPPING
    elif trend == "stable":
        if len(needs) >= 3:
            state = _STATE_SLIPPING
        elif len(helping) >= 2:
            state = _STATE_MAINTAINING
        else:
            state = _STATE_BUILDING_MOMENTUM
    else:
        # No persisted trend — cannot truthfully claim a direction. At least one
        # positive tracked behaviour means momentum is forming; otherwise the
        # honest state is "getting started".
        state = _STATE_BUILDING_MOMENTUM if helping else _STATE_GETTING_STARTED

    # Grounded narrative — truthful + encouraging. Fixed base line + the single
    # most relevant helping clause + ONE forward clause: a real need when one
    # exists, otherwise a constructive "worth watching" clause so the card never
    # ends on a flat note (and never piles a watch clause on top of a need).
    # Every clause names an ACTUAL tracked signal; nothing is fabricated.
    parts = [_STATE_BASE[state]]
    if helping and helping[0].get("help_frag"):
        parts.append(helping[0]["help_frag"])
    if needs and needs[0].get("need_frag"):
        parts.append(needs[0]["need_frag"])
    elif watching and watching[0].get("watch_frag"):
        parts.append(watching[0]["watch_frag"])
    narrative = " ".join(parts)

    # Display — one column per polarity, each capped at 3 and in the fixed
    # priority order from _evaluate_mission_signals. Strong signals can never be
    # displaced by neutral fillers because the columns no longer share slots.
    def _trim(items):
        return [
            {"icon": s["icon"], "label": s["label"], "value": s["value"]}
            for s in items[:3]
        ]

    return {
        "state": state,
        "ring_word": _RING_WORD[state],
        "state_label": _STATE_LABEL[state],
        "tone": _STATE_TONE[state],
        "narrative": narrative,
        "helping": _trim(helping),
        "watching": _trim(watching),
        "needs": _trim(needs),
    }


def _build_mission_progress(goal) -> dict:
    """Deterministic milestone progression for the hero ring.

    Pure count of completed vs total milestones — explainable and truthful.
    NO readiness, NO health weighting, NO arbitrary scoring. ``filled`` is a
    0–100 fraction used only to draw the SVG arc length.
    """
    total = goal.milestone_count
    completed = goal.completed_milestone_count
    if total <= 0:
        return {"has_milestones": False, "completed": 0, "total": 0, "filled": 0}

    filled = int(round((completed / total) * 100))
    return {
        "has_milestones": True,
        "completed": completed,
        "total": total,
        "filled": max(0, min(100, filled)),
    }


def _build_gauges(user) -> list[dict]:
    """Reuse GoalCockpitService — deterministic, goal-driven domain scores.

    Decorates each entry with a 'trend_label' and a short 'drivers' list
    (from components) for the gauge card template.

    Fallback: when the user has no active LifeGoals/HabitGoals the cockpit
    is empty. We don't show a "no domains" empty state — we render a
    canonical baseline (Health / Faith / Life Execution / Purpose) built
    READ-ONLY from existing SAE state. No new metric computation, no LLM.
    """
    from apps.dashboard_v2.services.cockpit_service import GoalCockpitService

    raw = GoalCockpitService(user).get_cockpit_data() or []
    if not raw:
        return _fallback_gauges_from_sae(user)

    out = []
    for d in raw:
        trend_delta = d.get("trend_delta") or 0
        if trend_delta > 0:
            trend_label = f"+{trend_delta}"
        elif trend_delta < 0:
            trend_label = f"{trend_delta}"
        else:
            trend_label = "—"

        components = d.get("components") or []
        drivers = [
            {
                "label": c.get("label", ""),
                "status": c.get("status", "info"),
                "detail": c.get("detail", ""),
            }
            for c in components[:3]
        ]

        out.append({
            "slug": d.get("slug"),
            "label": d.get("label"),
            "icon": d.get("icon"),
            "color": d.get("color"),
            "score": d.get("score"),
            "trend": d.get("trend"),
            "trend_delta": trend_delta,
            "trend_label": trend_label,
            "drivers": drivers,
            "priority": d.get("priority"),
            "source": "cockpit",
        })
    return out


# ── Fallback gauges (canonical SAE-driven, no fabrication) ────────────


def _fallback_gauges_from_sae(user) -> list[dict]:
    """Baseline gauges derived from already-built SAE state.

    Every value comes from an existing canonical field — no aggregation
    or recomputation happens here. If a domain has no data, its gauge
    shows "—" instead of being hidden, so the dashboard always feels
    populated.
    """
    from apps.core.ai_state.state_engine import get_module_state

    gauges: list[dict] = []

    # ── Health ────────────────────────────────────────────────────
    try:
        health = get_module_state(user, "health") or {}
        gauges.append(_status_gauge(
            slug="health",
            label="Health",
            icon="💪",
            statuses=[
                ("Sleep", health.get("sleep_status")),
                ("Water", health.get("water_status")),
                ("Glucose", health.get("glucose_status")),
                ("Steps", health.get("steps_status")),
            ],
        ))
    except Exception:
        logger.debug("fallback health gauge failed", exc_info=True)

    # ── Faith ─────────────────────────────────────────────────────
    try:
        faith = get_module_state(user, "faith") or {}
        streak = faith.get("reading_streak") or 0
        plans = faith.get("active_reading_plans") or 0
        # Streak-driven 0-100; capped at 21-day plateau.
        score = min(100, int(streak * 5)) if streak else (40 if plans else None)
        drivers = []
        if streak:
            drivers.append({"label": f"{streak}-day streak", "status": "good"})
        if plans:
            drivers.append({"label": f"{plans} active plan{'s' if plans != 1 else ''}", "status": "good"})
        if not drivers:
            drivers.append({"label": "No plan active yet", "status": "info"})
        gauges.append({
            "slug": "faith", "label": "Faith", "icon": "✝️",
            "score": score, "trend": "flat", "trend_delta": 0,
            "trend_label": "—", "drivers": drivers,
            "source": "sae_fallback",
        })
    except Exception:
        logger.debug("fallback faith gauge failed", exc_info=True)

    # ── Life Execution — completion% of today's actionable items ──
    try:
        from apps.core.execution.today_execution import build_today_execution
        contract = build_today_execution(user)
        items = contract.get("items", []) or []
        actionable = [i for i in items if i.get("is_actionable")]
        completed = sum(1 for i in actionable if i.get("completed_today"))
        total = len(actionable)
        score = int(round((completed / total) * 100)) if total else None
        overdue = sum(
            1 for i in actionable
            if not i.get("completed_today") and i.get("urgency") == "overdue"
        )
        at_risk = sum(
            1 for i in actionable
            if not i.get("completed_today")
            and i.get("execution_status") == "AT_RISK"
        )
        drivers = [
            {"label": f"{completed}/{total} done today",
             "status": "good" if total and completed >= total * 0.75 else "info"},
        ]
        if overdue:
            drivers.append({"label": f"{overdue} overdue", "status": "warn"})
        if at_risk:
            drivers.append({"label": f"{at_risk} at risk", "status": "warn"})
        gauges.append({
            "slug": "life", "label": "Life Execution", "icon": "🧭",
            "score": score, "trend": "flat", "trend_delta": 0,
            "trend_label": "—", "drivers": drivers,
            "source": "sae_fallback",
        })
    except Exception:
        logger.debug("fallback life-execution gauge failed", exc_info=True)

    # ── Purpose ───────────────────────────────────────────────────
    try:
        goals = get_module_state(user, "goals") or {}
        count = goals.get("active_goal_count") or 0
        # Presence-driven: 0 goals → no score; 1+ goals → 50 + 10/goal cap 90.
        score = None if count == 0 else min(90, 50 + count * 10)
        drivers = [{
            "label": f"{count} active goal{'s' if count != 1 else ''}",
            "status": "good" if count else "info",
        }]
        gauges.append({
            "slug": "purpose", "label": "Purpose", "icon": "🎯",
            "score": score, "trend": "flat", "trend_delta": 0,
            "trend_label": "—", "drivers": drivers,
            "source": "sae_fallback",
        })
    except Exception:
        logger.debug("fallback purpose gauge failed", exc_info=True)

    return gauges


# Maps SAE *_status values → (numeric weight, presentation status).
_STATUS_TO_WEIGHT = {
    "excellent": (100, "good"),
    "good": (80, "good"),
    "fair": (55, "warn"),
    "poor": (25, "poor"),
    "no_data": (None, "info"),
    None: (None, "info"),
    "": (None, "info"),
}


def _status_gauge(slug, label, icon, statuses):
    """Average available _status values into a 0-100 score with drivers."""
    weights = []
    drivers = []
    for driver_label, status in statuses:
        weight, vis = _STATUS_TO_WEIGHT.get(status, (None, "info"))
        if weight is not None:
            weights.append(weight)
        drivers.append({
            "label": driver_label,
            "status": vis,
            "detail": status or "no data",
        })
    score = int(round(sum(weights) / len(weights))) if weights else None
    return {
        "slug": slug, "label": label, "icon": icon,
        "score": score, "trend": "flat", "trend_delta": 0,
        "trend_label": "—", "drivers": drivers,
        "source": "sae_fallback",
    }


def _build_executive_summary(user) -> dict:
    from apps.core.cos_briefing import build_executive_summary
    return build_executive_summary(user)


def _build_rhythm(user) -> dict:
    from apps.core.cos_briefing import build_rhythm_sections
    return build_rhythm_sections(user)


def _build_accountability_cards(user) -> list[dict]:
    """For each enabled domain, compose a card from SAE state + insights.

    Composition is deterministic and references the SAME going_well /
    needs_attention / recommendations data the exec summary uses — just
    filtered per-domain so the cards align with their gauges.
    """
    from apps.core.ai_insights.models import Insight
    from apps.core.ai_guidance.models import GuidanceItem
    from datetime import timedelta
    from django.utils import timezone

    prefs = getattr(user, "preferences", None)
    enabled_flags = {
        "health": getattr(prefs, "health_enabled", True),
        "faith": getattr(prefs, "faith_enabled", True),
        "purpose": getattr(prefs, "purpose_enabled", True),
        "life": getattr(prefs, "life_enabled", True),
        "relationships": True,
        "finance": True,
    }

    cutoff = timezone.now() - timedelta(days=7)
    # Fetch once; filter in Python — small datasets and avoids N+1.
    fresh_insights = list(
        Insight.objects.filter(
            user=user,
            status__in=("new", "read"),
            created_at__gte=cutoff,
        ).order_by("-created_at")
    )

    # Convergence guard: SAE is the canonical freshness layer Beth reads.
    # The accountability card reads persisted Insight rows. If an Insight's
    # underlying condition has cleared in SAE, suppress it here so the
    # dashboard never tells the user something Beth contradicts.
    try:
        from apps.core.ai_state.state_engine import get_module_state
        _health = get_module_state(user, "health") or {}
        if not _health.get("weight_sync_stale", True):
            _gap = _health.get("weight_sync_gap_days")
            if _gap is not None and _gap < 3:
                fresh_insights = [
                    i for i in fresh_insights
                    if i.insight_type != "missing_weight_logging"
                ]
    except Exception:
        logger.debug("convergence guard: SAE read failed", exc_info=True)

    fresh_guidance = list(
        GuidanceItem.objects.filter(user=user, is_active=True)
        .order_by("priority", "-created_at")
    )

    cards: list[dict] = []
    for domain in ACCOUNTABILITY_DOMAIN_ORDER:
        if not enabled_flags.get(domain, True):
            continue

        domain_insights = [i for i in fresh_insights if i.module == domain]
        going_well = [
            {"title": i.title, "message": i.message}
            for i in domain_insights if i.severity == "positive"
        ][:3]
        needs_attention = [
            {"title": i.title, "message": i.message, "severity": i.severity}
            for i in domain_insights
            if i.severity in ("warning", "critical")
        ][:3]

        domain_guidance = [g for g in fresh_guidance if g.module == domain]
        recommendation = None
        if domain_guidance:
            top = domain_guidance[0]
            recommendation = {
                "title": top.title,
                "message": top.message,
                "priority": top.priority,
            }

        insight = _accountability_insight(
            going_well, needs_attention, recommendation
        )

        # Skip cards that are entirely empty — surfaces only what has signal.
        if not (going_well or needs_attention or recommendation):
            continue

        cards.append({
            "slug": domain,
            "label": DOMAIN_LABELS.get(domain, domain.title()),
            "icon": DOMAIN_ICONS.get(domain, "•"),
            "going_well": going_well,
            "needs_attention": needs_attention,
            "insight": insight,
            "recommendation": recommendation,
        })

    return cards


def _accountability_insight(going_well, needs_attention, recommendation) -> str | None:
    """Deterministic one-line interpretation. No LLM, fully rule-based.

    Returns None when there's nothing meaningful to say — caller skips the
    insight block entirely instead of showing a "not enough signal" line
    next to a substantive recommendation (the contradiction the user
    flagged in the v3 review).
    """
    pos = len(going_well or [])
    neg = len(needs_attention or [])

    if neg == 0 and pos > 0:
        return "Healthy momentum. Keep the rhythm consistent."
    if neg > 0 and pos == 0:
        return "Drift detected — accountability needed here."
    if neg > 0 and pos > 0 and neg >= pos:
        return "Mixed signals. Wins are real, but drift is outpacing them."
    if neg > 0 and pos > 0:
        return "Steady progress — protect the wins and address the drift."
    # No going_well, no needs_attention. If we have a recommendation, the
    # rec speaks for itself — don't undercut it with a "no signal" line.
    if recommendation:
        return None
    return "Not enough signal yet — log more and patterns will emerge."


def build_weather_tile(user) -> dict:
    """Always-returns weather payload for the header tile.

    Shape: {'available': bool, 'data': dict | None, 'message': str | None}

    Guarantees the header pill always renders something — either real
    weather, or a "set location" hint — so the dashboard never feels
    half-built.
    """
    prefs = getattr(user, "preferences", None)
    location_city = (prefs and getattr(prefs, "location_city", "")) or ""
    if not location_city:
        return {
            "available": False,
            "data": None,
            "message": "Set location",
        }
    try:
        from apps.dashboard.services.weather import weather_service
        weather_data = weather_service.get_weather_data(location_city)
        if weather_data:
            return {
                "available": True,
                "data": weather_data.to_dict(),
                "message": None,
            }
    except Exception:
        logger.debug("v3: weather lookup failed", exc_info=True)
    return {"available": False, "data": None, "message": "Weather unavailable"}


def _build_utilities(user) -> dict:
    """Small supporting tiles — water only. Weather lives in the header."""
    util: dict[str, Any] = {}
    prefs = getattr(user, "preferences", None)

    if prefs and getattr(prefs, "health_enabled", True):
        try:
            from apps.core.utils import get_user_now
            from apps.health.models import WaterEntry

            today = get_user_now(user).date()
            progress = WaterEntry.get_daily_goal_progress(user, today)
            util["water"] = {
                "total_oz": progress["total_oz"],
                "goal_oz": progress["goal_oz"],
                "percentage": progress["percentage"],
                "goal_met": progress["goal_met"],
            }
        except Exception:
            logger.debug("v3: water lookup failed", exc_info=True)

    return util


# ── Internals ─────────────────────────────────────────────────────────


def _safe(fn, *args, default):
    """Run a section builder and degrade gracefully on failure."""
    try:
        return fn(*args)
    except Exception:
        logger.warning("dashboard_v3 section build failed: %s", fn.__name__,
                       exc_info=True)
        return default
