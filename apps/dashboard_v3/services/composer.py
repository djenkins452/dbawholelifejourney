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

from django.urls import reverse

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

    Phase 2 dedup: ``build_today_execution`` and
    ``GoalCockpitService.get_cockpit_data`` are deterministic for
    ``(user, today)``. Before this change the v3 composer called each
    multiple times per render (3× and 2× respectively, ~90–120 redundant
    queries). We now fetch each ONCE up front and thread them through
    the downstream builders as explicit ``execution_contract`` /
    ``cockpit_data`` kwargs. No cache, no hidden state — pure
    intra-request deduplication.
    """
    # ── Phase 3: bootstrap SAE for brand-new users (one-shot). ──
    # Downstream gauge readers use allow_rebuild=False (Phase 3 read-
    # only contract). If state_data is entirely empty (a brand-new
    # user) those reads would return {} and the gauges would render
    # as "—". To honor the "no blank gauges" rule we do ONE sync
    # rebuild here for that case only and stash on user._sae_cache so
    # every subsequent get_module_state() in the same request reuses
    # it. After this first render, write-time subscribers keep
    # state_data warm — so the bootstrap path never fires again for
    # the same user.
    _safe(_warm_sae_if_empty, user, default=None)

    # ── Phase 2: fetch the two deterministic hot inputs once. ──
    # Any failure here is non-fatal; downstream builders fall back to
    # fetching their own copy (preserves Phase 1 behavior + back-compat).
    execution_contract = _safe(_load_execution_contract, user, default=None)
    cockpit_domains = _safe(_build_cockpit_domains_raw, user, default=[])

    context: dict[str, Any] = {
        # Raw canonical dial data — matches v2 cockpit_dial.html contract.
        "cockpit_domains": cockpit_domains,
        # Mission spotlight — the headline foundational goal, read-only.
        # None when no foundational goal qualifies (section renders nothing).
        "mission": _safe(_build_mission_card, user, default=None),
        # Composed/fallback gauges (used only when cockpit is empty).
        "gauges": _safe(
            _build_gauges, user,
            cockpit_data=cockpit_domains,
            execution_contract=execution_contract,
            default=[],
        ),
        "executive_summary": _safe(
            _build_executive_summary, user,
            execution_contract=execution_contract,
            default={},
        ),
        "focus_now": None,        # filled below from executive_summary
        "follow_on": [],          # filled below from executive_summary
        "accountability_cards": _safe(
            _build_accountability_cards, user, default=[]
        ),
        "rhythm": _safe(
            _build_rhythm, user,
            execution_contract=execution_contract,
            default={"sections": [], "totals": {}},
        ),
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
    "a1c": "\U0001FA78",           # drop of blood — metabolic / glucose trajectory
}

# ── Phase 6: Clickable Action Drivers ────────────────────────────────────
# Each signal may resolve to ONE meaningful destination. The mapping is by
# signal key only — generic, never hardcoded per user, never keyed off goal
# text. Automated metrics (glucose, steps) point to an INSIGHT view, NOT a
# manual-logging form, because logging them by hand would be wrong. The URL
# is resolved once at build time; an unresolvable name degrades gracefully to
# a non-clickable driver (no crash, no broken link). ``tooltip`` is optional
# hover/title text. ``log`` marks whether the destination is a logging action
# (vs read-only awareness) — used only for the aria-label verb.
_DRIVER_DEST = {
    "weight":    ("health:weight_list",       "Open your weight history",   False),
    "workouts":  ("health:workout_list",      "Open your workouts",         True),
    "movement":  ("health:fitness_home",      "Open your activity",         True),
    "steps":     ("health:fitness_home",      "Open your activity",         False),
    "sleep":     ("health:sleep_list",        "Open your sleep insights",   False),
    "journal":   ("journal:home",             "Open your journal",          True),
    "nutrition": ("health:nutrition_home",    "Open nutrition",             True),
    "a1c":       ("health:glucose_dashboard", "Based on CGM glucose history — not a lab A1C. Open glucose insights", False),
}


def _resolve_driver_dest(key):
    """Resolve a signal key to a (href, tooltip, is_log) destination, or None.

    Read-only, deterministic, and crash-safe: a missing/renamed URL name
    simply yields None so the driver renders as plain (non-clickable) text
    rather than raising NoReverseMatch on the request path.
    """
    spec = _DRIVER_DEST.get(key)
    if not spec:
        return None
    name, tooltip, is_log = spec
    try:
        return {"href": reverse(name), "tooltip": tooltip, "is_log": is_log}
    except Exception:
        return None


# ── Per-mission signal priority (Phase 6.3) ──────────────────────────────────
# Some missions make a particular metric disproportionately important. For a
# metabolic-health mission, Projected A1C (GMI) is the headline trajectory and
# MUST outrank generic lifestyle signals (sleep / steps / nutrition) so the
# 3-per-column display cap can never silently drop it. This is resolved PER
# GOAL — never hardcoded as a global winner — so future missions can pin
# different signals without touching the cap logic. The mapping is keyed by the
# goal's LifeDomain slug; a goal in an un-mapped domain pins nothing and falls
# back to the default fixed signal order.
# For a metabolic-health mission the full deterministic priority is pinned so
# the highest-value signals lead their column. Projected A1C and conditioning
# outrank generic lifestyle signals; journal is last but — since the display
# cap is removed (Phase D) — it can never VANISH, only sort to the end. Keys
# not present as signals are skipped, so a pin never reserves an empty slot.
_MISSION_PRIORITY_BY_DOMAIN = {
    "health": ("a1c", "workouts", "movement", "weight", "sleep", "nutrition", "journal"),
}


def _mission_priority_keys(goal, signals) -> tuple:
    """Ordered tuple of signal keys to lift to the front of their polarity
    column for THIS goal, before the per-column cap is applied.

    Read-only and crash-safe. Only keys that are actually present as signals
    are returned, so a pin never reserves a slot for a metric that isn't there.
    """
    present = {s.get("key") for s in signals}
    domain = getattr(goal, "domain", None)
    slug = getattr(domain, "slug", None)
    keys = _MISSION_PRIORITY_BY_DOMAIN.get(slug, ()) if slug else ()
    return tuple(k for k in keys if k in present)


def _apply_priority(column: list[dict], pinned: tuple) -> list[dict]:
    """Reorder one polarity column so pinned keys come first (in pin order),
    preserving the relative order of everything else. Pure, no mutation."""
    if not pinned:
        return column
    head = [s for k in pinned for s in column if s.get("key") == k]
    tail = [s for s in column if s.get("key") not in pinned]
    return head + tail

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
# Progress-aware states (Mission Progress Maturity). The states above read HABIT
# momentum (behaviours). These read MISSION PROGRESS (milestone events + pace vs
# plan) — the axis an executive actually judges the mission by. A milestone
# reached, or a milestone target that slipped, is a stronger "how are things
# going" signal than a stable habit trend, so these DOMINATE the classification
# when a real progress event exists. Both derive from deterministic milestone
# truth already on the goal (completed_date, target_date) — no scoring, no
# fabrication, no new architecture.
_STATE_AHEAD_OF_PLAN = "AHEAD_OF_PLAN"     # a milestone landed on/before its target date
_STATE_MILESTONE_WIN = "MILESTONE_WIN"     # a milestone was just reached (late but done)
_STATE_BEHIND_PLAN = "BEHIND_PLAN"         # a milestone target passed without completing

# Ring centre word — answers "what am I doing right now" without a number.
_RING_WORD = {
    _STATE_GETTING_STARTED: "BUILDING",
    _STATE_BUILDING_MOMENTUM: "MOMENTUM",
    _STATE_IMPROVING: "ON TRACK",
    _STATE_MAINTAINING: "STEADY",
    _STATE_SLIPPING: "RECOVER",
    _STATE_AT_RISK: "REFOCUS",
    _STATE_AHEAD_OF_PLAN: "AHEAD",
    _STATE_MILESTONE_WIN: "MILESTONE",
    _STATE_BEHIND_PLAN: "REFOCUS",
}

# Human label for the status pill.
_STATE_LABEL = {
    _STATE_GETTING_STARTED: "Getting started",
    _STATE_BUILDING_MOMENTUM: "Building momentum",
    _STATE_IMPROVING: "Improving",
    _STATE_MAINTAINING: "Maintaining",
    _STATE_SLIPPING: "Slipping",
    _STATE_AT_RISK: "Needs attention",
    _STATE_AHEAD_OF_PLAN: "Ahead of plan",
    _STATE_MILESTONE_WIN: "Milestone reached",
    _STATE_BEHIND_PLAN: "Behind plan",
}

# Tone reuses the existing momentum indicator classes (up / flat / down).
_STATE_TONE = {
    _STATE_GETTING_STARTED: "flat",
    _STATE_BUILDING_MOMENTUM: "up",
    _STATE_IMPROVING: "up",
    _STATE_MAINTAINING: "flat",
    _STATE_SLIPPING: "down",
    _STATE_AT_RISK: "down",
    _STATE_AHEAD_OF_PLAN: "up",
    _STATE_MILESTONE_WIN: "up",
    _STATE_BEHIND_PLAN: "down",
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
    _STATE_AHEAD_OF_PLAN: (
        "You're ahead of your own plan — the last milestone landed on or before "
        "its target date. Keep the routine that got you here."
    ),
    _STATE_MILESTONE_WIN: (
        "You just cleared a mission milestone — real forward progress. Bank it "
        "and carry the momentum into the next rung."
    ),
    _STATE_BEHIND_PLAN: (
        "A milestone target passed without completing. This is recoverable — "
        "refocus on the single rung in front of you and protect the routine "
        "that moves it."
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
    "a1c": {
        "help": "Your glucose trend is improving, which supports your long-term health goals.",
        "watch": "Your glucose is holding steady — staying consistent here protects your long-term health.",
        "need": "Your glucose trend has drifted up lately — small, steady habits bring it back down.",
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

    # Current metric truth (weight) — so mission commentary reconciles a
    # milestone reached in the PAST against the mission's CURRENT state
    # (Dashboard Truth). Read-only; the SAE cache is primed so this is ~free and
    # reads the same canonical snapshot the Weight Status block below uses.
    _current_weight = None
    try:
        from apps.core.ai_state.state_engine import get_module_state
        _current_weight = (
            get_module_state(user, "health", allow_rebuild=False) or {}
        ).get("weight_current")
    except Exception:
        logger.debug("mission: current-weight read skipped", exc_info=True)

    # Deterministic MISSION-PROGRESS read (milestone events + pace vs plan) —
    # the executive axis that complements habit-momentum. Computed ONCE here and
    # shared by both the panel and the status classifier so they always agree.
    progress_read = _mission_progress_read(
        goal, nm, today, current_weight=_current_weight
    )

    # "How things are going" panel — always present for an active mission. A
    # live progress event (milestone reached / behind plan) LEADS; otherwise it
    # prefers the persisted momentum trend, then a milestone-grounded fallback.
    panel = _build_mission_panel(goal, snap, progress_read)

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

    # Key Drivers + status classifier are OPTIONAL supporting signals. The
    # mission hero card must NEVER disappear because a signal read failed —
    # its core (goal, focus, momentum, panel, progress, why, victories) does
    # not depend on SAE module state. A failure anywhere in the freshness
    # guard / signal read / classifier degrades to an empty drivers row and a
    # neutral status, and the card still renders. (Regression origin: Phase 6.5
    # — a request-path read raised and the whole card vanished.)
    drivers: list[dict] = []
    status = None
    weight_status = None
    try:
        # Read the pre-computed SAE module states ONCE (read-only) and reuse
        # them for both the drivers row and the mission-status classifier.
        states = _read_mission_states(user)
        drivers = _build_mission_drivers(states)
        # Phase 3 — Mission Intelligence: deterministic state classification +
        # grounded coaching narrative + helping/needs split, from the same SAE
        # signals (no extra queries) and the persisted momentum trend only.
        # Phase 3.5 — the milestone PHASE shapes how movement is judged.
        phase = _mission_movement_phase(goal)
        signals = _evaluate_mission_signals(states, phase)
        status = _build_mission_status(goal, snap, signals, today, progress_read)
        # Always-on Weight Status block — read-only over the SAE health snapshot
        # already read above + the next milestone already evaluated above.
        # Returns None for non-weight missions; that omits the block in
        # template. Zero new queries; defensive (any read failure degrades the
        # block, never the whole card).
        weight_status = _build_mission_weight_status(goal, states.get("health", {}), nm)
    except Exception:
        logger.warning(
            "MISSION user=%s — optional signal read failed; rendering hero "
            "card without drivers/status",
            getattr(user, "id", "?"), exc_info=True,
        )

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
        "weight_status": weight_status,
        "days_remaining": days_remaining,
        "progress": progress,
        "why": why,
        "hero_image_url": hero_image_url,
        "mission_links": mission_links,
        "victories": victories,
        "goal_id": goal.id,
    }


def _build_mission_panel(goal, snap, progress: dict | None = None) -> dict:
    """The "How things are going" panel — always present for an active mission.

    Precedence:
      1. A live MISSION-PROGRESS event (a milestone just cleared, or a milestone
         target that slipped) — the strongest, most concrete "how are things
         going" answer, composed deterministically from milestone truth.
      2. Otherwise a real persisted ``GoalMomentumSnapshot`` trend, narrated with
         the fixed, pre-approved coaching line for that trend.
      3. Otherwise a NEUTRAL ("flat") milestone-grounded fallback — we never
         invent a rising/falling direction. ``is_fallback`` tones it down.
    """
    prog = progress or {}
    if prog.get("event") == "milestone_reached":
        # Dashboard Truth: reached in the past, but the current metric no longer
        # holds it → describe the CURRENT state, achievement as context.
        if prog.get("last_holds") is False:
            fluc = (prog.get("last_overage") or 0.0) <= _WEIGHT_FLUCTUATION_LB
            return {
                "label": "Holding steady" if fluc else "Slipping",
                "trend": "flat" if fluc else "down",
                "narrative": _reconciled_milestone_text(prog),
                "is_fallback": False,
            }
        if prog.get("pace") == "ahead":
            traj = "You're ahead of your plan."
        else:
            traj = "Momentum is back — carry it into the next rung."
        nxt = (f" Next: {prog['next_title']}." if prog.get("next_title")
               else " Set your next milestone to keep a concrete target.")
        return {
            "label": "Milestone reached",
            "trend": "up",
            "narrative": f"You cleared “{prog.get('last_title')}”. {traj}{nxt}",
            "is_fallback": False,
        }
    if prog.get("event") == "behind":
        od = prog.get("next_days_overdue") or 0
        unit = "day" if od == 1 else "days"
        return {
            "label": "Behind plan",
            "trend": "down",
            "narrative": (f"“{prog.get('next_title')}” passed its target "
                          f"{od} {unit} ago without completing. Recoverable — "
                          f"refocus on that one rung."),
            "is_fallback": False,
        }

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

    READ-ONLY for device/aggregate modules (health, fitness): pulls only the
    nightly / SAME-cycle SAE snapshot, NEVER live-computing the heavy builders
    on the request path.

    For MANUAL-ENTRY modules (journal, nutrition) it first runs a bounded
    freshness guard: if the user logged a journal entry or food item after the
    snapshot was last built — and the async Celery refresh hasn't landed yet —
    the guard does a cheap single-module rebuild so the mission card reflects
    what the user just entered (no "did my data save?" lag). This rebuilds the
    SIGNAL via the SAE builder, then reads the signal — it never reads raw rows
    into narrative logic. See apps/core/ai_state/state_freshness.py.
    """
    from apps.core.ai_state.state_engine import get_module_state
    from apps.core.ai_state.state_freshness import ensure_fresh

    # Repair only the manual-entry signals; health/fitness stay background-only.
    # ensure_fresh never raises, but guard it anyway so the mission card
    # never depends on it.
    try:
        ensure_fresh(user, ["journal", "nutrition"])
    except Exception:
        logger.warning(
            "MISSION user=%s — freshness guard raised; reading stale snapshot",
            getattr(user, "id", "?"), exc_info=True,
        )

    # Each read is independently guarded so one module's failure can't
    # lose the others. Phase 3: allow_rebuild=False — request-path
    # readers never trigger a synchronous SAE rebuild. If state_data
    # is missing the gauge falls back to "—"; the composer's
    # _warm_sae_if_empty bootstrap protects brand-new users from
    # that case on first render.
    def _read(module):
        try:
            return get_module_state(user, module, allow_rebuild=False) or {}
        except Exception:
            logger.warning(
                "MISSION user=%s module=%s — state read failed",
                getattr(user, "id", "?"), module, exc_info=True,
            )
            return {}

    return {
        "health":    _read("health"),
        "fitness":   _read("fitness"),
        "journal":   _read("journal"),
        "nutrition": _read("nutrition"),
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

    # Nutrition consistency. Show macro compliance ONLY when there is real intake
    # today (macro_compliance_score floors at 0.0 on a zero-intake day, which is
    # not a meaningful "0% macros" — see _evaluate_mission_signals). Otherwise
    # fall back to the canonical logging signal so an actively-logging user is
    # reflected, never blanked or shown a misleading 0%.
    if nutrition.get("enabled"):
        macros = nutrition.get("macro_compliance_score")
        logged_today = nutrition.get("food_entries_today") or 0
        logged_7d = nutrition.get("food_entries_7d") or 0
        if macros is not None and logged_today > 0:
            add("nutrition", "Nutrition", f"{macros:.0f}% macros")
        elif logged_today > 0:
            noun = "item" if logged_today == 1 else "items"
            add("nutrition", "Nutrition", f"{logged_today} {noun} today")
        elif logged_7d > 0:
            add("nutrition", "Nutrition", f"{logged_7d}/wk logged")

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

    def emit(key, label, value, polarity, tooltip=None, note=None):
        # Each signal carries all three grounded clauses (help / watch / need);
        # the status builder picks the one matching the column it lands in. A
        # "neutral" signal is a genuine middle state — Worth Watching — not a
        # weaker need, so it is never folded into the needs column. ``tooltip``
        # optionally overrides the static per-key destination tooltip (used to
        # make the A1C hover text confidence-aware). ``note`` is an optional
        # second-line sub-label rendered under the value (used by A1C to state
        # confidence / sync-status truthfully — e.g. "Waiting for glucose sync").
        frags = _SIGNAL_FRAGMENTS.get(key, {})
        signals.append(
            {
                "key": key,
                "icon": _DRIVER_ICONS.get(key, ""),
                "label": label,
                "value": value,
                "polarity": polarity,
                "tooltip": tooltip,
                "note": note,
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

    # Projected A1C / GMI (Phase 6.1 + 6.3) — metabolic trajectory. Read-only:
    # number, confidence, trend are pre-computed in the nightly health state
    # builder, never here. The displayed number is the standard GMI equation on
    # the simple mean (the builder never blends or trend-adjusts it).
    #
    # TRUTH RULE (Phase 6.3/6.4): for a glucose-tracking user the A1C slot must
    # NEVER silently disappear. "No signal" is itself a signal — the user must
    # always be able to tell apart: a real number / sync lag / thin history /
    # engine failure. So whenever confidence is set (i.e. any glucose history or
    # a connected CGM exists), we ALWAYS emit a driver, varying only the value
    # and the second-line ``note``:
    #   high   → "6.5%"        note "Estimated from CGM data"
    #   medium → "~6.5%"       note "Using recent available glucose data"
    #   low+stale_sync → "—"   note "Waiting for glucose sync"
    #   low+thin       → "—"   note "Need more glucose history"
    #   error          → "Unavailable" note "Glucose insights temporarily unavailable"
    # Confidence is None only when there's genuinely no CGM/history — then (and
    # only then) the slot is absent, which is itself truthful.
    #
    # WHAT THIS IS (medical truth — Phase 6.4): the number is the CGM-derived
    # GMI (Glucose Management Indicator), GMI(%) = 3.31 + 0.02392 × mean glucose
    # mg/dL (ADA / Dexcom CGM standard). It is an ESTIMATE from CGM data, NOT a
    # laboratory A1C. The label always reads "Projected A1C (GMI)" and the note +
    # tooltip make the CGM-estimate basis explicit so the UI never implies a lab
    # value.
    #
    # CLASSIFICATION (Phase 6.4): polarity uses BOTH the current level AND the
    # trend — never auto-Helping — to avoid false reassurance:
    #   improving                     → Helping
    #   stable                        → Worth Watching (neutral)
    #   worsening & in-target (≤7.0)  → Worth Watching (neutral, not punitive)
    #   worsening & above-target      → Needs Attention
    a1c = health.get("projected_a1c")
    a1c_conf = health.get("projected_a1c_confidence")
    if a1c_conf == "error":
        # Engine failure must be visible, never mistaken for "no data".
        emit(
            "a1c", "Projected A1C (GMI)", "Unavailable", "neutral",
            tooltip="Glucose insights are temporarily unavailable. We're on it.",
            note="Glucose insights temporarily unavailable",
        )
    elif a1c is not None and a1c_conf in ("high", "medium"):
        a1c_trend = health.get("projected_a1c_trend") or "stable"
        if a1c_trend == "improving":
            polarity = "helping"
        elif a1c_trend == "worsening":
            polarity = "needs" if a1c > 7.0 else "neutral"
        else:  # stable — holding steady is "worth watching", never auto-helping
            polarity = "neutral"
        if a1c_conf == "medium":
            # Tilde signals an estimate on possibly-delayed sync; the note and
            # tooltip explain the basis without sounding like user failure.
            value = f"~{a1c}%"
            tooltip = "Estimated from recent available CGM glucose data — not a lab A1C."
            note = "Using recent available glucose data"
        else:
            value = f"{a1c}%"
            tooltip = None  # keep the default "not a lab A1C" destination tooltip
            note = "Estimated from CGM data"
        emit("a1c", "Projected A1C (GMI)", value, polarity, tooltip=tooltip, note=note)
    elif a1c_conf == "low":
        # Glucose history (or a connected CGM) exists but it is too stale/sparse
        # to publish a defensible number. Show the slot with an em-dash value and
        # an honest note. Distinguish sync lag (not a failure) from thin history —
        # never silently disappear when any history/connection exists.
        if health.get("projected_a1c_low_reason") == "stale_sync":
            emit(
                "a1c", "Projected A1C (GMI)", "—", "neutral",
                tooltip="WLJ has glucose history, but recent CGM data has not synced.",
                note="Waiting for glucose sync",
            )
        else:
            emit(
                "a1c", "Projected A1C (GMI)", "—", "neutral",
                tooltip="A few more days of glucose readings will unlock your GMI.",
                note="Need more glucose history",
            )

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

    # Nutrition — prefer macro compliance when targets exist. With no targets,
    # reflect the canonical logging signal (food_entries_today / _7d): an
    # actively-logging user is "tracked" (neutral), never an objective "need".
    # Only a user with NO logging at all is the untracked need.
    if nutrition.get("enabled"):
        macros = nutrition.get("macro_compliance_score")
        logged_today = nutrition.get("food_entries_today") or 0
        logged_7d = nutrition.get("food_entries_7d") or 0
        # macro_compliance_score is computed from TODAY's intake vs the user's
        # macro targets. On a zero-intake day (e.g. before logging, or a stale
        # snapshot) it floors at 0.0 — NOT None — which previously rendered a
        # misleading "0% macros" even for a user who logs daily. Phase D: the
        # macro % is shown ONLY when there is real intake today to be compliant
        # about (food_entries_today > 0). Otherwise we lead with the canonical
        # LOGGING signal so an actively-logging user is reflected, never blanked
        # or punished for not having eaten yet today / not having macro targets.
        if macros is not None and logged_today > 0:
            band = _SIGNAL_BANDS["nutrition"]
            # One-sided band (no numeric "need" floor): >=help helping, else a
            # neutral Worth-Watching signal (tracked but not yet strong).
            polarity = "helping" if macros >= band["help"] else "neutral"
            emit("nutrition", "Nutrition", f"{macros:.0f}% macros", polarity)
        elif logged_today > 0:
            noun = "item" if logged_today == 1 else "items"
            emit("nutrition", "Nutrition", f"{logged_today} {noun} today", "neutral")
        elif logged_7d > 0:
            emit("nutrition", "Nutrition", f"{logged_7d}/wk logged", "neutral")
        else:
            emit("nutrition", "Nutrition", "Not tracked", "needs")

    return signals


_RECENT_MILESTONE_DAYS = 14  # a completion within this window is "what changed"

# A weight this far ABOVE a just-cleared weight target reads as normal daily
# variance (water weight swings ~1–3 lb), not a real regression. Deterministic,
# defensible line for the Dashboard-Truth reconciliation below.
_WEIGHT_FLUCTUATION_LB = 2.0


def _reconcile_last_milestone(out, milestone, current_weight) -> None:
    """Dashboard Truth: decide whether the most-recent CLEARED milestone still
    describes the mission's CURRENT state, or is only historically true.

    A milestone completion is one-way for title-form weight rungs (they never
    auto-uncomplete — see objective_weight_milestones), so ``completed=True`` can
    outlive the metric that earned it. Here we re-check the last cleared WEIGHT
    milestone against the CURRENT weight (read-only, no write):

      · ``last_holds=True``  — current weight still ≤ the cleared target (a real,
        current win).
      · ``last_holds=False`` — weight has climbed back above it; the achievement
        is context, not the present state. Consumers reframe.
      · ``last_holds=None``  — not a measurable weight milestone, or no current
        weight; behaviour is unchanged (we never contradict without truth).
    """
    if current_weight is None or milestone is None:
        return
    try:
        from decimal import Decimal
        from apps.purpose.services.objective_weight_milestones import (
            _parse_weight_target_from_title,
        )
        target = milestone.objective_target_value
        if target is None:
            # Title-form weight rung ("Goal Weight of 284.9") — same conservative
            # parse the evaluator + goal_pace use, so we agree on the target.
            target = _parse_weight_target_from_title(milestone.title)
        if target is None:
            return  # Not a weight-measurable milestone — leave celebratory read.
        cur = Decimal(str(current_weight))
        tgt = Decimal(str(target))
        out["last_current"] = float(cur)
        out["last_target"] = float(tgt)
        out["last_holds"] = cur <= tgt   # weight goal → 'lte' (reach a lower #)
        out["last_overage"] = float(cur - tgt) if cur > tgt else 0.0
    except Exception:
        logger.debug("mission milestone reconcile failed", exc_info=True)


def _when_phrase(days) -> str:
    return ("today" if days is not None and days <= 0
            else "yesterday" if days == 1 else f"{days} days ago")


def _reconciled_milestone_text(prog) -> str:
    """Dashboard-Truth narrative for a milestone reached in the past that the
    CURRENT metric no longer holds: acknowledge the achievement (as context),
    state the current value, interpret the gap deterministically, name the next
    focus. Shared by the panel and the status classifier so they always agree.
    Every clause names real, deterministic truth — nothing fabricated.
    """
    when = _when_phrase(prog.get("last_days_ago"))
    cur = prog.get("last_current")
    over = prog.get("last_overage") or 0.0
    cur_txt = f"{cur:g}" if isinstance(cur, (int, float)) else "—"
    if over <= _WEIGHT_FLUCTUATION_LB:
        interp = "a normal short-term fluctuation"
    else:
        interp = f"{over:g} lb above it — worth refocusing"
    parts = [
        f"You reached “{prog.get('last_title')}” {when}. "
        f"Current weight is {cur_txt}, {interp}."
    ]
    if prog.get("next_title"):
        parts.append(f"Keep an eye on the trend toward {prog['next_title']}.")
    return " ".join(parts)


def _mission_progress_read(goal, next_milestone, today, current_weight=None) -> dict:
    """Deterministic MISSION-PROGRESS assessment — the axis an executive judges a
    mission by (milestones cleared / pace vs plan), complementing the HABIT
    momentum signals. Reads only GoalMilestone truth already on the goal
    (completed_date, target_date). No scoring, no fabrication, no new queries
    beyond one indexed lookup for the most-recent completion.

    Returns ``{event, last_title, last_days_ago, last_on_time, completed, total,
    next_title, next_overdue, next_days_overdue, pace}`` where ``event`` is
    ``"milestone_reached"`` (a completion within the recent window),
    ``"behind"`` (the next milestone's target date has passed, uncompleted), or
    ``None``.
    """
    out = {
        "event": None, "last_title": None, "last_days_ago": None,
        "last_on_time": None, "completed": 0, "total": 0,
        "next_title": None, "next_overdue": False, "next_days_overdue": None,
        "pace": None,
        # Dashboard-Truth reconciliation of the last cleared milestone vs the
        # CURRENT metric (see _reconcile_last_milestone). last_holds: True (still
        # held) / False (regressed above it) / None (not measurable / unknown).
        "last_holds": None, "last_current": None, "last_target": None,
        "last_overage": None,
    }
    try:
        out["total"] = goal.milestone_count
        out["completed"] = goal.completed_milestone_count

        # Most-recent DATED completion. (Test fixtures create completed=True with
        # no completed_date; those legitimately don't count as a fresh event —
        # production completions always stamp completed_date.)
        last = (goal.milestones
                .filter(completed=True, completed_date__isnull=False)
                .order_by("-completed_date").first())
        if last is not None:
            out["last_title"] = last.title
            out["last_days_ago"] = (today - last.completed_date).days
            if last.target_date is not None:
                out["last_on_time"] = last.completed_date <= last.target_date

        # Next milestone timing.
        nm = next_milestone
        if nm is not None:
            out["next_title"] = nm.title
            if nm.target_date is not None and nm.target_date < today:
                out["next_overdue"] = True
                out["next_days_overdue"] = (today - nm.target_date).days

        # Resolve the executive event. A recent WIN is the more salient "what
        # changed" and wins over an overdue-next (target dates that are close).
        # -1 lower bound tolerates a ±1 day user-timezone skew vs completed_date.
        if out["last_days_ago"] is not None and \
                -1 <= out["last_days_ago"] <= _RECENT_MILESTONE_DAYS:
            out["event"] = "milestone_reached"
            out["pace"] = "ahead" if out["last_on_time"] else "recovering"
            # Dashboard Truth: reconcile the cleared milestone against the
            # CURRENT metric. A weight milestone the current weight no longer
            # satisfies is history (context), not the mission's present state.
            _reconcile_last_milestone(out, last, current_weight)
        elif out["next_overdue"]:
            out["event"] = "behind"
            out["pace"] = "behind"
    except Exception:
        # Progress-awareness is additive: any read failure degrades to the
        # habit-trend classification, never breaks the card.
        logger.warning("MISSION progress read failed for goal=%s",
                       getattr(goal, "id", "?"), exc_info=True)
    return out


def _mission_status_narrative(state, prog, helping, watching, needs) -> str:
    """Compose the executive narrative deterministically: what changed · why /
    trajectory · next focus · one grounded habit clause. A progress state LEADS
    with the concrete milestone change (actual title + count) and names the next
    focus; habit states keep the original base+signal composition unchanged.
    Nothing is fabricated — every clause names real truth."""
    prog = prog or {}
    event = prog.get("event")

    if event == "milestone_reached":
        # Dashboard Truth: if the current metric no longer holds the cleared
        # milestone, the present state — not the past achievement — drives it.
        if prog.get("last_holds") is False:
            return _reconciled_milestone_text(prog)
        days = prog.get("last_days_ago")
        when = ("today" if days is not None and days <= 0
                else "yesterday" if days == 1 else f"{days} days ago")
        completed, total = prog.get("completed", 0), prog.get("total", 0)
        count = f" ({completed} of {total})" if total else ""
        parts = [f"Milestone reached — you cleared “{prog.get('last_title')}” "
                 f"{when}{count}.", _STATE_BASE[state]]
        if prog.get("next_title"):
            parts.append(f"Next focus: {prog['next_title']}.")
        if helping and helping[0].get("help_frag"):
            parts.append(helping[0]["help_frag"])
        return " ".join(p for p in parts if p)

    if event == "behind":
        od = prog.get("next_days_overdue") or 0
        unit = "day" if od == 1 else "days"
        parts = [f"Behind plan — “{prog.get('next_title')}” was due {od} "
                 f"{unit} ago and isn't complete yet.", _STATE_BASE[state]]
        if needs and needs[0].get("need_frag"):
            parts.append(needs[0]["need_frag"])
        elif helping and helping[0].get("help_frag"):
            parts.append(helping[0]["help_frag"])
        return " ".join(p for p in parts if p)

    # Habit-trend states — the ORIGINAL composition, unchanged.
    parts = [_STATE_BASE[state]]
    if helping and helping[0].get("help_frag"):
        parts.append(helping[0]["help_frag"])
    if needs and needs[0].get("need_frag"):
        parts.append(needs[0]["need_frag"])
    elif watching and watching[0].get("watch_frag"):
        parts.append(watching[0]["watch_frag"])
    return " ".join(parts)


def _build_mission_status(goal, snap, signals: list[dict], today,
                          progress: dict | None = None) -> dict:
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
    # Phase 6.3 — lift any mission-priority signal (e.g. Projected A1C for a
    # metabolic mission) to the front of whichever column it lands in, BEFORE
    # the 3-per-column cap, so a high-value metric can never be silently
    # displaced by lower-value fillers.
    pinned = _mission_priority_keys(goal, signals)
    helping = _apply_priority(helping, pinned)
    watching = _apply_priority(watching, pinned)
    needs = _apply_priority(needs, pinned)
    trend = snap.momentum_trend if snap and snap.momentum_trend else None
    prog = progress or {}
    prog_event = prog.get("event")

    # ── PROGRESS DOMINATES ─────────────────────────────────────────────
    # A milestone just cleared, or a milestone target that slipped, is a
    # stronger executive read than a habit trend — an executive who just hit a
    # mission milestone must never see "Maintaining". These are real,
    # deterministic events, so they take precedence; we fall through to the
    # habit-trend classification ONLY when there is no live progress event.
    if prog_event == "milestone_reached":
        if prog.get("last_holds") is False:
            # Reached historically, but the current metric has regressed above
            # it — NOT a present win. Steady for a small fluctuation, Slipping
            # for a real drift. The narrative reconciles the two.
            over = prog.get("last_overage") or 0.0
            state = (_STATE_MAINTAINING if over <= _WEIGHT_FLUCTUATION_LB
                     else _STATE_SLIPPING)
        else:
            state = (_STATE_AHEAD_OF_PLAN if prog.get("pace") == "ahead"
                     else _STATE_MILESTONE_WIN)
    elif prog_event == "behind":
        state = _STATE_BEHIND_PLAN
    elif trend == "rising":
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

    # Executive narrative — what changed · why/trajectory · next focus · one
    # grounded habit clause. Deterministic; every clause names ACTUAL truth.
    narrative = _mission_status_narrative(state, prog, helping, watching, needs)

    # Display — one column per polarity, in the mission-priority order from
    # _apply_priority (pinned signals first) then the fixed signal order. Phase D:
    # NO per-column cap. Mission truth > layout neatness — a real signal (Journal,
    # Projected A1C) may never be silently dropped because a column already holds
    # three higher-priority signals. Signals can move columns (by polarity); they
    # can never vanish. Layout wrapping is the template/CSS's job, not data loss.
    # Phase 6 — each displayed driver may carry ONE clickable destination
    # (resolved read-only, crash-safe). A driver with no meaningful action,
    # or whose URL cannot be resolved, renders as plain text (dest=None).
    def _shape(items):
        out = []
        for s in items:
            dest = _resolve_driver_dest(s.get("key"))
            # A signal may override the destination's hover text (e.g. the
            # A1C tooltip varies with confidence). The destination href stays
            # the same — only the tooltip copy changes.
            if dest and s.get("tooltip"):
                dest = {**dest, "tooltip": s["tooltip"]}
            out.append({
                "icon": s["icon"],
                "label": s["label"],
                "value": s["value"],
                "note": s.get("note"),
                "dest": dest,
            })
        return out

    return {
        "state": state,
        "ring_word": _RING_WORD[state],
        "state_label": _STATE_LABEL[state],
        "tone": _STATE_TONE[state],
        "narrative": narrative,
        "helping": _shape(helping),
        "watching": _shape(watching),
        "needs": _shape(needs),
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


# ── Mission Weight Status — always-on truth block ─────────────────────────
#
# Truth contract: weight must be visible in every state — good, bad, stalled,
# sync-stale, no-data. The only state that may use completion-resembling
# styling ("--ok" tone with the ✓ glyph) is when the data layer confirms
# `current <= next_target`. Every other state uses tonal accents only, never
# completion visuals (Visual Truth Contract, docs/WLJ_VISUAL_TRUTH_CONTRACT.md).
#
# Zero new queries: consumes only data already loaded by `_build_mission_card`
# (the next_milestone evaluated for `current_focus` + the `states["health"]`
# dict already returned by `_read_mission_states`). NEVER calls
# HealthProfile.get_weight_progress() — that would re-query WeightEntry and
# couple the mission card to HealthProfile shape; the mission's own milestone
# chain is the canonical target source (Phase 1 objective milestones).
def _build_mission_weight_status(goal, health_state: dict, next_milestone) -> dict | None:
    """Always-on weight status block — read-only over already-loaded data.

    Returns ``None`` when the mission has no objective-weight milestone at
    all (non-weight missions skip cleanly — the block is not forced into
    contexts where it has nothing to say).

    When the mission IS weight-driven, the block ALWAYS renders — even with
    no weigh-ins, stale sync, or upward trend. No hiding, no softening.

    Output shape (consumed by templates/dashboard_v3/sections/mission.html):

      ``{ has_data, current, unit, target, to_next, trend, trend_glyph,
          change_30d, change_sign, sync_stale, tone, headline, subline }``

    Tone vocabulary:
      - ``"ok"``   — current <= target (the ONLY completion-resembling state)
      - ``"down"`` — above target, trending toward goal (encouraging accent
                     only, no ✓ glyph)
      - ``"flat"`` — stable or insufficient data (neutral)
      - ``"up"``   — above target, trending away from goal (truthful red)
    """
    # Find an objective-weight target on this goal. Prefer the next incomplete
    # milestone (matches the "Next milestone" row directly above us). Fall
    # back to ANY objective-weight milestone on the goal so we still render
    # for fully-completed weight missions (the at-target state).
    target = None
    if (
        next_milestone is not None
        and getattr(next_milestone, "objective_metric", None) == "weight_lb"
        and getattr(next_milestone, "objective_target_value", None) is not None
    ):
        target = float(next_milestone.objective_target_value)
    else:
        # Reuse the milestones reverse relation already iterated for the ring;
        # this filter hits the cached queryset if Django has it. One bounded
        # scan over the goal's own milestones (typically <20 rows).
        for m in goal.milestones.all():
            if (
                getattr(m, "objective_metric", None) == "weight_lb"
                and getattr(m, "objective_target_value", None) is not None
            ):
                # Lowest target value = the ultimate weight goal for this mission.
                tv = float(m.objective_target_value)
                if target is None or tv < target:
                    target = tv

    if target is None:
        # Mission isn't weight-driven. Block is omitted in template.
        return None

    current = health_state.get("weight_current")
    unit = health_state.get("weight_unit") or "lb"
    trend_raw = health_state.get("weight_trend") or "insufficient_data"
    change_30d = health_state.get("weight_change_30d")
    sync_stale = bool(health_state.get("weight_sync_stale"))

    # Map SAE trend → display.
    trend_label = {
        "decreasing": "Trending down",
        "stable": "Stable",
        "increasing": "Trending up",
        "insufficient_data": "Not enough data",
    }.get(trend_raw, "Not enough data")
    trend_glyph = {
        "decreasing": "↓",
        "stable": "→",
        "increasing": "↑",
        "insufficient_data": "·",
    }.get(trend_raw, "·")

    # Format 30-day delta with explicit sign — truth requires the direction
    # be unmistakable. "0.0 lb (30d)" for genuine stability is fine.
    change_sign = None
    change_display = None
    if change_30d is not None:
        try:
            cv = float(change_30d)
            if cv > 0.05:
                change_sign = "up"
                change_display = f"+{cv:.1f} {unit} (30d)"
            elif cv < -0.05:
                change_sign = "down"
                change_display = f"{cv:.1f} {unit} (30d)"
            else:
                change_sign = "flat"
                change_display = f"0.0 {unit} (30d)"
        except (TypeError, ValueError):
            change_display = None

    # ── No recent weigh-in branch ─────────────────────────────────────
    if current is None:
        return {
            "has_data": False,
            "current": None,
            "unit": unit,
            "target": round(target, 1),
            "to_next": None,
            "trend": trend_raw,
            "trend_label": trend_label,
            "trend_glyph": trend_glyph,
            "change_30d": None,
            "change_sign": None,
            "change_display": None,
            "sync_stale": sync_stale,
            "tone": "flat",
            "headline": "No recent weigh-in",
            "subline": f"Next milestone target: {target:.1f} {unit}",
        }

    # ── Real data branches ────────────────────────────────────────────
    try:
        current_f = float(current)
    except (TypeError, ValueError):
        # Defensive: malformed SAE value. Degrade to no-data branch shape.
        return {
            "has_data": False,
            "current": None,
            "unit": unit,
            "target": round(target, 1),
            "to_next": None,
            "trend": trend_raw,
            "trend_label": trend_label,
            "trend_glyph": trend_glyph,
            "change_30d": None,
            "change_sign": None,
            "change_display": None,
            "sync_stale": sync_stale,
            "tone": "flat",
            "headline": "No recent weigh-in",
            "subline": f"Next milestone target: {target:.1f} {unit}",
        }

    # Phase 1 milestone operator is `lte` — target is a ceiling. Distance
    # remaining is current - target (positive = above target).
    to_next = round(current_f - target, 1)

    if to_next <= 0:
        # At-or-under-target: the ONLY completion-resembling state. The user
        # has objectively reached the target by canonical data.
        tone = "ok"
        headline = "At milestone target"
        subline = f"Target: {target:.1f} {unit} ✓"
    else:
        # Above target — tone follows trend, NOT distance. Truth before
        # encouragement: trending up gets the truthful "up" tone even close
        # to target; trending down gets the "down" tone even far from target.
        if trend_raw == "decreasing":
            tone = "down"
        elif trend_raw == "increasing":
            tone = "up"
        else:
            tone = "flat"  # stable OR insufficient_data
        headline = f"{to_next:.1f} {unit} to next milestone"
        subline = f"Target: {target:.1f} {unit}"

    return {
        "has_data": True,
        "current": round(current_f, 1),
        "unit": unit,
        "target": round(target, 1),
        "to_next": to_next,
        "trend": trend_raw,
        "trend_label": trend_label,
        "trend_glyph": trend_glyph,
        "change_30d": change_30d,
        "change_sign": change_sign,
        "change_display": change_display,
        "sync_stale": sync_stale,
        "tone": tone,
        "headline": headline,
        "subline": subline,
    }


def _build_gauges(user, cockpit_data=None, execution_contract=None) -> list[dict]:
    """Reuse GoalCockpitService — deterministic, goal-driven domain scores.

    Decorates each entry with a 'trend_label' and a short 'drivers' list
    (from components) for the gauge card template.

    Fallback: when the user has no active LifeGoals/HabitGoals the cockpit
    is empty. We don't show a "no domains" empty state — we render a
    canonical baseline (Health / Faith / Life Execution / Purpose) built
    READ-ONLY from existing SAE state. No new metric computation, no LLM.

    Phase 2 dedup: ``cockpit_data`` and ``execution_contract`` may be
    pre-fetched at the top of ``build_dashboard_v3_context``. When
    provided we reuse them — saves a second GoalCockpitService call and
    a third build_today_execution call per render. When omitted (any
    other caller / Phase 1 path) we fetch our own.
    """
    if cockpit_data is None:
        from apps.dashboard_v2.services.cockpit_service import GoalCockpitService
        raw = GoalCockpitService(user).get_cockpit_data() or []
    else:
        raw = cockpit_data or []
    if not raw:
        return _fallback_gauges_from_sae(user, execution_contract=execution_contract)

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


def _fallback_gauges_from_sae(user, execution_contract=None) -> list[dict]:
    """Baseline gauges derived from already-built SAE state.

    Every value comes from an existing canonical field — no aggregation
    or recomputation happens here. If a domain has no data, its gauge
    shows "—" instead of being hidden, so the dashboard always feels
    populated.

    Phase 2 dedup: when ``execution_contract`` is provided (composer
    pre-fetched it), the Life Execution gauge reuses it instead of
    calling ``build_today_execution`` a second time. When omitted (any
    other caller) we fetch our own — full back-compat.
    """
    from apps.core.ai_state.state_engine import get_module_state

    gauges: list[dict] = []

    # Phase 3: all SAE reads use allow_rebuild=False — request path
    # never triggers a sync rebuild. Brand-new users are bootstrapped
    # by _warm_sae_if_empty at composer entry (one-time cost).
    # ── Health ────────────────────────────────────────────────────
    try:
        health = get_module_state(user, "health", allow_rebuild=False) or {}
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
        faith = get_module_state(user, "faith", allow_rebuild=False) or {}
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
        if execution_contract is None:
            from apps.core.execution.today_execution import build_today_execution
            contract = build_today_execution(user)
        else:
            contract = execution_contract
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
        goals = get_module_state(user, "goals", allow_rebuild=False) or {}
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


def _warm_sae_if_empty(user) -> None:
    """Phase 3 bootstrap — when ``UserState.state_data`` is entirely
    empty for this user (brand-new account, never had a write fire a
    warm task), do ONE synchronous rebuild and stash the result on
    ``user._sae_cache`` so every downstream ``get_module_state`` in
    this request reuses it.

    This is the trade-off that lets us honor BOTH:
      - "No blank '—' gauges" (a populated _sae_cache makes the
        gauge readers find real values)
      - "Dashboard request path read-only against warm SAE"
        (after this first render the state_data persists in the DB
        and subsequent renders never enter this branch).

    Fast path (the common case): state_data exists → noop, returns
    immediately, the downstream readers (which use allow_rebuild=
    False) read straight from the DB row.

    Slow path (first ever render only): one rebuild_user_state on
    the request thread. Same cost users used to pay on every render
    pre-Phase-3 — but now only ONCE per user.
    """
    try:
        from apps.core.ai_state.models import UserState
        # Fast existence check: do we have populated state_data?
        row = UserState.objects.filter(user=user).only("state_data").first()
        if row is not None and row.state_data:
            # Prime the per-request SAE cache with the snapshot we just read.
            # Every downstream get_module_state()/get_user_state() checks
            # user._sae_cache first, so this collapses the ~30+ identical
            # UserState SELECTs a single render otherwise issues (one per module
            # read) into ZERO further queries. Read-only, request-scoped.
            try:
                user._sae_cache = row.state_data
            except Exception:
                pass
            return  # Common path — already warm.

        # Brand-new user — bootstrap once. allow_rebuild=True is the
        # default; this is the ONE place in the request path that's
        # intentionally allowed to rebuild. The result is stashed on
        # user._sae_cache so the rest of the render is read-only.
        from apps.core.ai_state.state_engine import rebuild_user_state
        state = rebuild_user_state(user)
        try:
            user._sae_cache = state
        except Exception:
            pass
    except Exception:
        logger.warning(
            "SAE bootstrap (Phase 3) failed user=%s — downstream readers "
            "may show empty gauges this render; next domain write will "
            "queue a warm task",
            getattr(user, "id", "?"), exc_info=True,
        )


def _load_execution_contract(user) -> dict | None:
    """Phase 2 dedup — fetch today's execution contract ONCE per render.

    Returned dict is threaded to ``_build_executive_summary``,
    ``_build_rhythm``, and ``_fallback_gauges_from_sae`` so each
    consumer reuses the same 30-40 queries instead of refetching.
    Returns ``None`` on failure — downstream builders fall back to
    fetching their own copy (full back-compat).

    Phase 3: if the view layer has already pre-fetched the contract
    and stashed it on ``user._dashboard_exec_contract`` (see
    ``DashboardV3View.get_context_data``), reuse it — saves the 4th
    fetch.
    """
    cached = getattr(user, "_dashboard_exec_contract", None)
    if cached is not None:
        return cached
    from apps.core.execution.today_execution import build_today_execution
    return build_today_execution(user)


def _build_executive_summary(user, execution_contract=None) -> dict:
    from apps.core.cos_briefing import build_executive_summary
    return build_executive_summary(user, execution_contract=execution_contract)


def _build_rhythm(user, execution_contract=None) -> dict:
    from apps.core.cos_briefing import build_rhythm_sections
    return build_rhythm_sections(user, execution_contract=execution_contract)


# ── Phase A trust fix: defensive greeting strip ──────────────────────
# Pre-fix GuidanceItem rows were stored with persona greetings baked
# into the body ("Good morning! You've been training consistently…").
# Hours later, the dashboard surfaced "Good morning!" at 8 PM. The
# fix at storage time (apps/core/ai_guidance/guidance_logger.py) stops
# new rows from carrying greetings; this defensive sanitizer cleans
# existing rows already in the DB and protects against future drift.
# Strips ONLY a leading greeting phrase — never aggressive enough to
# clip substantive content.
_LEADING_GREETING_RE = re.compile(
    r"""^\s*
        (?:Good\s+morning|Good\s+afternoon|Good\s+evening
           |Good\s+day|Hey|Hi|Hello)
        [!,.\s]+
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _strip_leading_greeting(text: str) -> str:
    """Remove a leading persona greeting from a guidance message.

    No-op when no greeting is present (common case for new rows post
    the storage-side fix). Cheap, deterministic, never alters body
    content beyond the greeting prefix.
    """
    if not text:
        return text
    return _LEADING_GREETING_RE.sub("", text, count=1).strip()


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
    # Phase 3: read-only against SAE on the request path.
    try:
        from apps.core.ai_state.state_engine import get_module_state
        _health = get_module_state(user, "health", allow_rebuild=False) or {}
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
        # Executive consolidation (same helper the briefing uses): collapse
        # repeated same-subject warnings ("Protein intake 53% / 55% / 72% of
        # target") into ONE synthesized item so the card summarizes, not repeats.
        from apps.core.cos_briefing.consolidation import consolidate_findings
        _dom_attention = consolidate_findings([
            i for i in domain_insights
            if i.severity in ("warning", "critical")
        ])
        from apps.core.action_router import route_for_finding
        needs_attention = [
            {
                "title": i.title, "message": i.message, "severity": i.severity,
                "route": route_for_finding(i).as_dict(),
            }
            for i in _dom_attention
        ][:3]

        domain_guidance = [g for g in fresh_guidance if g.module == domain]
        recommendation = None
        if domain_guidance:
            top = domain_guidance[0]
            recommendation = {
                "id": top.id,
                "title": top.title,
                # Defensive greeting strip (2026-06-01 trust fix).
                # Pre-Phase-A rows in production carry baked-in persona
                # greetings ("Good morning! …") that go stale within
                # hours. We strip a leading greeting at render time so
                # the dashboard never surfaces time-of-day phrasing
                # inside an accountability card. New rows (post-fix in
                # guidance_logger.py) are stored neutral; this filter
                # protects existing rows + future regressions.
                "message": _strip_leading_greeting(top.message),
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


def _safe(fn, *args, default, **kwargs):
    """Run a section builder and degrade gracefully on failure.

    Accepts kwargs (Phase 2: pre-fetched ``execution_contract`` /
    ``cockpit_data`` are passed to downstream builders).
    """
    try:
        return fn(*args, **kwargs)
    except Exception:
        logger.warning("dashboard_v3 section build failed: %s", fn.__name__,
                       exc_info=True)
        return default
