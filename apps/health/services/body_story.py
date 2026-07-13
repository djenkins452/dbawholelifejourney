# ==============================================================================
# File: apps/health/services/body_story.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: "Your Body Story" — the deterministic Chief-of-Staff executive briefing
#              that sits atop Body Intelligence. Interpretation (Layer 1) over the
#              evidence (Layer 2) the rest of the page already renders.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-13
# ==============================================================================
"""Your Body Story — the one authoritative executive briefing for Body Intelligence.

This is the *interpretation* layer. It answers, in the user's own reading voice,
"what is happening to my body, why, what matters, and what to do next" — while every
chart, measurement, photo, and check-in below it remains the *evidence* that proves it.

Architecture (mirrors the Home Dashboard's `build_executive_summary`):

  * **Deterministic, LLM-last.** Zero inline reasoning. Every sentence is composed from
    truth WLJ already computed at rollup time (fat-loss quality, recomposition, plateau,
    muscle-loss risk, phase, goal pace, measurement wins). No invented causes, no
    hallucinated reasoning — grounded by construction. The frontier model reasons over
    this same truth only when the user *chats* (via the `health.body_intelligence` page
    summary); the page render never calls an LLM.
  * **Request-path-safe.** Pure arrangement of the pre-computed `build_body_intelligence`
    dict — no ORM aggregates, no heavy compute. Every branch collapses gracefully; no
    exception escapes to the request path.
  * **Domain-agnostic framework (built for two years out).** The briefing is assembled
    from typed `BodyStorySignal`s emitted by independent *contributors*. Today's
    contributors read weight, body-composition, measurements, and the weight goal. When
    Sleep, Glucose, Recovery, Nutrition, Workouts, Medications, Labs, or Biomarkers join
    Body Intelligence, they ship a new contributor that emits the same signal type — the
    status/confidence/narrative/wins/watch/recommendation pipeline and the template are
    unchanged. Only the *content* evolves; the framework does not get redesigned.

Returned shape (stable soft contract — keep additive):

    {
        "status":         {"label", "tone", "detail"},   # Overall Status
        "confidence":     {"level", "basis"},             # Confidence
        "narrative":      [str, ...],                      # Body Story (ordered sentences)
        "wins":           [{"title", "detail"}, ...],      # Biggest Wins
        "watch_items":    [{"title", "detail", "tone"}, ...],  # Watch Items
        "recommendation": {"title", "detail"} | None,      # Highest-Leverage Recommendation
        "has_signal":     bool,
        "as_of":          date,
    }

`tone` ∈ {positive, steady, caution, critical, unknown} — presentation only; the
template maps it to colour. WLJ decides the tone deterministically; it never asserts a
tone it did not compute.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

logger = logging.getLogger(__name__)


# ── Knobs ───────────────────────────────────────────────────────────────────
MAX_WINS = 4
MAX_WATCH = 3


# ── The signal — the one currency every domain speaks ───────────────────────
@dataclass
class BodyStorySignal:
    """One deterministic observation a domain contributes to the briefing.

    A contributor emits these; the composer aggregates them into status, confidence,
    narrative, wins, watch items, and the recommendation. This is the seam that lets a
    future domain (sleep, glucose, labs…) join the briefing without touching the
    composer or the template — it just emits signals of this type.
    """

    domain: str                      # "weight" | "composition" | "measurements" | "goal" | future
    kind: str                        # "win" | "watch" | "context"
    tone: str                        # "positive" | "steady" | "caution" | "critical" | "unknown"
    title: str                       # short label — "Recomposition underway"
    detail: str = ""                 # supporting clause — "fat ↓ while lean holds"
    weight: int = 50                 # 0–100 strength; orders lists + drives status/recommendation
    confidence: str = "medium"       # "high" | "medium" | "low"
    narrative: str = ""              # optional full sentence for the Body Story prose
    # A machine tag so the recommendation mapper can key off a specific condition
    # without re-parsing the human title (e.g. "muscle_loss_risk", "plateau").
    tag: str = ""
    extra: dict = field(default_factory=dict)


_TONE_RANK = {"critical": 4, "caution": 3, "unknown": 2, "steady": 1, "positive": 0}


# ── Small helpers ───────────────────────────────────────────────────────────
def _f(val):
    """Coerce to float or None — the pre-computed dict already holds floats/None, but
    stay defensive against a stray Decimal/str."""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _fmt_lb(delta) -> str:
    d = _f(delta)
    if d is None:
        return ""
    return f"{'+' if d > 0 else ''}{d:g} lb"


def _goal_direction(goal: dict | None):
    """Which way is 'toward goal' for weight? Returns "down" | "up" | None.

    Grounds direction in the user's actual weight goal when present. Absent a goal we
    return None and callers fall back to the near-universal body-composition mission that
    the evidence layer already assumes (fat ↓, lean ↑, waist ↓).
    """
    if not goal:
        return None
    g = _f(goal.get("goal"))
    cur = _f(goal.get("current_weight"))
    if g is None or cur is None:
        return None
    if g < cur:
        return "down"
    if g > cur:
        return "up"
    return None


# ── Contributors — each emits signals from the pre-computed truth ───────────
# Add a domain to the briefing by writing one of these and appending it to _CONTRIBUTORS.
# Every contributor MUST be defensive and read only the already-composed `bi` dict.


def _composition_contributor(bi: dict) -> list[BodyStorySignal]:
    """Body-composition intelligence — the richest lens (fat/lean quality, recomposition,
    plateau, muscle-loss risk, phase, pace). All labels are pre-computed at rollup time."""
    bc = bi.get("body_comp") or {}
    if not bc:
        return []

    out: list[BodyStorySignal] = []
    quality = (bc.get("fat_loss_quality_label") or "").upper()
    risk = (bc.get("muscle_loss_risk_level") or "").upper()
    plateau = (bc.get("plateau_status") or "").upper()
    plateau_risk = (bc.get("plateau_risk_label") or "").upper()
    recomp = bool(bc.get("recomposition_flag_14d"))
    speed = (bc.get("fat_loss_speed_label") or "").upper()

    fat_d = _f(bc.get("fat_mass_delta_14d"))
    lean_d = _f(bc.get("lean_mass_delta_14d"))
    ratio = _f(bc.get("fat_loss_ratio_14d"))

    # Confidence for composition signals tracks the pre-computed phase confidence.
    pconf = bc.get("phase_confidence")
    comp_conf = "high" if (pconf and pconf >= 80) else "low" if (pconf and pconf < 70) else "medium"

    # — Recomposition: the strongest positive story a body can tell —
    if recomp:
        detail = "fat mass down while lean mass holds or climbs"
        if fat_d is not None and lean_d is not None:
            detail = f"fat {_fmt_lb(fat_d)}, lean {_fmt_lb(lean_d)} over 14 days"
        out.append(BodyStorySignal(
            domain="composition", kind="win", tone="positive", weight=95,
            title="Recomposition underway", detail=detail, confidence=comp_conf,
            tag="recomposition",
            narrative="Your body is recomposing — losing fat while holding or building "
                      "lean mass, the hardest and most valuable pattern to achieve.",
        ))

    # — Fat-loss quality —
    if quality == "EXCELLENT":
        rt = f" (ratio {ratio:g})" if ratio else ""
        out.append(BodyStorySignal(
            domain="composition", kind="win", tone="positive", weight=80,
            title="Excellent fat-loss quality", detail=f"lean mass preserved{rt}",
            confidence=comp_conf, tag="quality_excellent",
            narrative="What you're losing is almost entirely fat — lean mass is being "
                      "preserved, which is exactly what clean fat loss looks like.",
        ))
    elif quality == "GOOD":
        out.append(BodyStorySignal(
            domain="composition", kind="win", tone="positive", weight=65,
            title="Good fat-loss quality", detail="mostly fat, minimal lean loss",
            confidence=comp_conf, tag="quality_good",
            narrative="Most of what you're losing is fat, with only minimal lean loss.",
        ))
    elif quality == "MUSCLE_LOSS_RISK":
        out.append(BodyStorySignal(
            domain="composition", kind="watch", tone="critical", weight=90,
            title="Fat-loss quality shows muscle-loss risk",
            detail="too much of the loss is lean mass", confidence=comp_conf,
            tag="muscle_loss_risk",
            narrative="The mix of your recent loss suggests some of it is muscle, not fat "
                      "— worth correcting before it compounds.",
        ))
    elif quality == "GAINING":
        # Direction depends on the mission; ground in the goal if we have one.
        direction = _goal_direction(bi.get("goal"))
        if direction == "up":
            out.append(BodyStorySignal(
                domain="composition", kind="win", tone="positive", weight=55,
                title="Gaining toward your goal", detail="mass is trending up, as intended",
                confidence=comp_conf, tag="gaining_intended",
            ))
        else:
            out.append(BodyStorySignal(
                domain="composition", kind="watch", tone="caution", weight=60,
                title="Mass is trending up", detail="fat mass increased over the last 14 days",
                confidence=comp_conf, tag="gaining",
                narrative="Overall mass has been trending up recently — if fat loss is the "
                          "goal, this is the place to look first.",
            ))

    # — Muscle-loss risk (independent of quality label) —
    if risk == "HIGH":
        score = bc.get("muscle_loss_risk_score")
        st = f" (score {score})" if score is not None else ""
        out.append(BodyStorySignal(
            domain="composition", kind="watch", tone="critical", weight=88,
            title="Muscle-loss risk is high", detail=f"protein and recovery are the levers{st}",
            confidence=comp_conf, tag="muscle_loss_risk",
        ))

    # — Plateau (confirmed) and plateau early-warning —
    if plateau == "TRUE_PLATEAU":
        out.append(BodyStorySignal(
            domain="composition", kind="watch", tone="caution", weight=70,
            title="Progress has plateaued", detail="scale and fat mass have held flat",
            confidence=comp_conf, tag="plateau",
            narrative="Your progress has flattened out — the scale and fat mass have held "
                      "steady, which usually means it's time to adjust the approach.",
        ))
    elif plateau == "WATER":
        out.append(BodyStorySignal(
            domain="composition", kind="context", tone="steady", weight=40,
            title="Scale noise is water, not fat", detail="fat mass stable; weight is fluctuating",
            confidence=comp_conf, tag="water",
        ))
    elif plateau_risk == "HIGH":
        window = bc.get("plateau_prediction_window_days")
        wt = f" — est. {window} days out" if window is not None else ""
        out.append(BodyStorySignal(
            domain="composition", kind="watch", tone="caution", weight=62,
            title="A plateau may be forming", detail=f"early warning signs are building{wt}",
            confidence=comp_conf, tag="plateau_risk",
        ))

    # — Pace —
    if speed == "TOO_FAST":
        out.append(BodyStorySignal(
            domain="composition", kind="watch", tone="caution", weight=58,
            title="Weight is coming off too fast", detail="fast loss raises muscle-loss risk",
            confidence=comp_conf, tag="too_fast",
        ))

    return out


def _weight_contributor(bi: dict) -> list[BodyStorySignal]:
    """Weight movement — canonical Weight-domain truth, plus goal pace."""
    weight = bi.get("weight") or {}
    goal = bi.get("goal") or {}
    bc = bi.get("body_comp") or {}
    out: list[BodyStorySignal] = []

    count = weight.get("count") or 0
    conf = "high" if count >= 20 else "medium" if count >= 5 else "low"

    direction = _goal_direction(goal)
    total = _f(weight.get("total_change_lb"))
    recent = _f(bc.get("weight_delta_14d"))
    cur = _f(weight.get("current_lb"))

    # Overall trajectory relative to the goal (or the standard "down is progress" default
    # when there is no goal — matching what the evidence layer already assumes).
    if cur is not None and (total is not None or recent is not None):
        moved = recent if recent is not None else total
        toward = None
        if direction == "down":
            toward = moved is not None and moved < 0
        elif direction == "up":
            toward = moved is not None and moved > 0
        elif direction is None and moved is not None:
            toward = moved < 0  # no goal → treat loss as progress (page default)

        if moved is not None and abs(moved) < 0.3:
            out.append(BodyStorySignal(
                domain="weight", kind="context", tone="steady", weight=45,
                title="Weight is holding steady", detail=f"now {cur:g} lb", confidence=conf,
                tag="weight_flat",
                narrative=f"Your weight is holding steady at {cur:g} lb.",
            ))
        elif toward is True:
            out.append(BodyStorySignal(
                domain="weight", kind="win", tone="positive", weight=60,
                title="Weight moving toward your goal",
                detail=f"{_fmt_lb(moved)} recently, now {cur:g} lb", confidence=conf,
                tag="weight_toward",
                narrative=f"The scale is moving in the right direction — {_fmt_lb(moved)} "
                          f"lately, now {cur:g} lb.",
            ))
        elif toward is False:
            out.append(BodyStorySignal(
                domain="weight", kind="watch", tone="caution", weight=55,
                title="Weight drifting from your goal",
                detail=f"{_fmt_lb(moved)} recently, now {cur:g} lb", confidence=conf,
                tag="weight_away",
                narrative=f"The scale has drifted the wrong way recently ({_fmt_lb(moved)}).",
            ))

    # Goal pace as a standalone win/context.
    pct = _f(goal.get("progress_percent"))
    if pct is not None and goal.get("goal") is not None:
        rem = goal.get("remaining")
        unit = goal.get("unit", "lb")
        detail = f"{pct:g}% there"
        if rem is not None:
            detail += f", {rem} {unit} to go"
        tone = "positive" if pct >= 50 else "steady"
        out.append(BodyStorySignal(
            domain="goal", kind="win" if pct >= 50 else "context", tone=tone, weight=50,
            title=f"{pct:g}% to your weight goal", detail=detail, confidence=conf,
            tag="goal_pace",
        ))

    return out


def _measurement_contributor(bi: dict) -> list[BodyStorySignal]:
    """Tape/composition measurement wins — the snapshot already knows the healthier
    direction per metric, so `largest_improvement` is a mission-aware win."""
    snap = bi.get("snapshot") or {}
    imp = snap.get("largest_improvement")
    if not imp:
        return []
    unit = (snap.get("units") or {}).get(imp.get("metric"), "")
    delta = _f(imp.get("delta"))
    if delta is None:
        return []
    sign = "+" if delta > 0 else ""
    return [BodyStorySignal(
        domain="measurements", kind="win", tone="positive", weight=52,
        title=f"Biggest measurement change: {imp.get('label', '')}".strip(),
        detail=f"{sign}{delta:g}{unit} in the healthier direction",
        confidence="medium", tag="measurement_win",
        narrative=f"Your measurements are moving in the right direction too — "
                  f"{imp.get('label', 'a measurement').lower()} changed "
                  f"{sign}{delta:g} {unit} in the healthier direction.".replace("  ", " "),
    )]


# Ordered registry. A new domain joins Body Intelligence's briefing by appending here.
_CONTRIBUTORS = [
    _composition_contributor,
    _weight_contributor,
    _measurement_contributor,
]


# ── The composer ────────────────────────────────────────────────────────────
def build_body_story(bi: dict) -> dict:
    """Compose "Your Body Story" from the pre-computed Body Intelligence dict.

    Pure arrangement — deterministic, request-path-safe, no LLM. Always returns every
    key with a sane default so the template never has to guard for missing structure.
    """
    as_of = bi.get("as_of") or date.today()
    empty = {
        "status": {"label": "Building your baseline", "tone": "unknown",
                   "detail": "Log a weigh-in, a measurement, or a check-in to begin."},
        "confidence": {"level": "low", "basis": "Not enough data yet."},
        "narrative": ["You've just started tracking. As your weigh-ins, measurements, and "
                      "check-ins build up, this is where your body's story will be told."],
        "wins": [], "watch_items": [], "recommendation": {
            "title": "Log your first check-in",
            "detail": "A weigh-in plus a few tape measurements gives WLJ enough to start "
                      "reading your progress.",
        },
        "has_signal": False, "as_of": as_of,
    }
    if not bi.get("has_any_data"):
        return empty

    # 1) Gather signals — defensively; a broken contributor must never break the page.
    signals: list[BodyStorySignal] = []
    for contributor in _CONTRIBUTORS:
        try:
            signals.extend(contributor(bi) or [])
        except Exception:
            logger.warning("body_story: contributor %s failed",
                           getattr(contributor, "__name__", "?"), exc_info=True)

    wins = sorted([s for s in signals if s.kind == "win"], key=lambda s: -s.weight)
    watch = sorted([s for s in signals if s.kind == "watch"],
                   key=lambda s: (-_TONE_RANK.get(s.tone, 0), -s.weight))

    if not signals:
        # Has data but nothing composed a signal (e.g. a single weigh-in). Give an honest,
        # non-empty briefing rather than the cold-start card.
        base = dict(empty)
        base["has_signal"] = False
        return base

    # 2) Status — the dominant verdict both the badge and the narrative derive from.
    status = _derive_status(wins, watch)

    # 3) Confidence — data density is the floor; the richest signal can only confirm it.
    confidence = _derive_confidence(bi, signals)

    # 4) Narrative — what's happening → why → what deserves attention.
    narrative = _compose_narrative(bi, status, wins, watch, confidence)

    # 5) Recommendation — flows from the top watch item, else the confidence gap.
    recommendation = _derive_recommendation(watch, wins, confidence)

    return {
        "status": status,
        "confidence": confidence,
        "narrative": narrative,
        "wins": [{"title": s.title, "detail": s.detail} for s in wins[:MAX_WINS]],
        "watch_items": [{"title": s.title, "detail": s.detail, "tone": s.tone}
                        for s in watch[:MAX_WATCH]],
        "recommendation": recommendation,
        "has_signal": True,
        "as_of": as_of,
    }


def _derive_status(wins, watch) -> dict:
    """The single dominant-state verdict. Critical watch outranks everything; otherwise a
    clear win leads. Deterministic — the badge and narrative can never disagree."""
    top_watch = watch[0] if watch else None
    top_win = wins[0] if wins else None

    # A critical watch item is the current reality no matter how many wins net out.
    if top_watch and top_watch.tone == "critical":
        return {"label": "Needs attention", "tone": "critical", "detail": top_watch.title}

    # A standout win (recomposition / excellent quality) leads the story.
    if top_win and top_win.weight >= 80:
        label = {"recomposition": "Recomposing",
                 "quality_excellent": "Fat loss on track"}.get(top_win.tag, "Making progress")
        return {"label": label, "tone": "positive", "detail": top_win.title}

    if top_watch and top_watch.tone == "caution":
        # Balance a caution against any real win.
        if top_win and top_win.weight >= 55:
            return {"label": "Mixed signals", "tone": "caution",
                    "detail": f"{top_win.title}, but {top_watch.title.lower()}"}
        return {"label": "Worth a look", "tone": "caution", "detail": top_watch.title}

    if top_win:
        return {"label": "Making progress", "tone": "positive", "detail": top_win.title}

    # Only context signals (steady state).
    return {"label": "Holding steady", "tone": "steady",
            "detail": "No strong movement in either direction right now."}


def _derive_confidence(bi: dict, signals) -> dict:
    """How much WLJ trusts this read — grounded in data density, never inflated by a
    single confident signal. Basis is a plain-language 'why'."""
    weight = bi.get("weight") or {}
    sessions = bi.get("sessions") or {}
    has_comp = bool(bi.get("body_comp"))

    weigh_ins = weight.get("count") or 0
    checkins = sessions.get("count") or 0

    parts = []
    if weigh_ins:
        parts.append(f"{weigh_ins} weigh-in{'s' if weigh_ins != 1 else ''}")
    if checkins:
        parts.append(f"{checkins} check-in{'s' if checkins != 1 else ''}")
    basis = ", ".join(parts) if parts else "limited history"

    # Floor from density.
    if weigh_ins >= 20 and has_comp:
        level = "high"
    elif weigh_ins >= 8 or (weigh_ins >= 5 and has_comp):
        level = "medium"
    else:
        level = "low"

    # A composition read with high phase-confidence can lift medium→high, but density
    # alone can never be overridden upward past what the data supports.
    if level == "medium" and any(s.confidence == "high" and s.domain == "composition"
                                 for s in signals) and has_comp and weigh_ins >= 12:
        level = "high"

    tail = {"high": "a solid read", "medium": "a reasonable read",
            "low": "still forming"}[level]
    return {"level": level, "basis": f"Based on {basis} — {tail}."}


def _compose_narrative(bi, status, wins, watch, confidence) -> list[str]:
    """The Body Story prose: what's happening → why → what deserves attention → (caveat).

    Every sentence is a pre-written fragment tied to a computed signal — no free text,
    no invented cause. Mirrors the Home Dashboard's headline/story synthesis.
    """
    out: list[str] = []

    # Sentence 1 — what's happening (the leading signal's narrative).
    lead = None
    if watch and watch[0].tone == "critical" and watch[0].narrative:
        lead = watch[0].narrative
    elif wins and wins[0].narrative:
        lead = wins[0].narrative
    elif watch and watch[0].narrative:
        lead = watch[0].narrative
    else:
        # Fall back to any context signal's narrative (e.g. weight holding).
        ctx = next((s for s in (wins + watch) if s.narrative), None)
        lead = ctx.narrative if ctx else status.get("detail")
    if lead:
        out.append(lead)

    # Sentence 2 — why / the second-strongest supporting movement.
    used = {lead}
    support = next((s.narrative for s in (wins + watch)
                    if s.narrative and s.narrative not in used), None)
    if support:
        out.append(support)
        used.add(support)

    # Sentence 3 — what deserves attention (top unspoken watch item).
    open_watch = next((s for s in watch if s.narrative not in used), None)
    if open_watch:
        detail = f" — {open_watch.detail}" if open_watch.detail else ""
        out.append(f"The one thing to watch: {open_watch.title.lower()}{detail}.")
    elif not watch and wins:
        out.append("Nothing needs correcting right now — the current approach is working, "
                   "so keep it steady.")

    # Sentence 4 — honest confidence caveat when the read is still forming.
    if confidence.get("level") == "low":
        out.append("This read is still early — a few more weigh-ins and a check-in will "
                   "sharpen it.")

    return out


def _derive_recommendation(watch, wins, confidence) -> dict | None:
    """The single highest-leverage next move — grounded in the dominant watch item, or the
    confidence gap when everything is on track. Never generic; always references the
    actual condition WLJ detected."""
    # Deterministic mapping from the top watch tag → a concrete lever.
    _BY_TAG = {
        "muscle_loss_risk": {
            "title": "Protect your muscle",
            "detail": "Lift with intent and get enough protein — your recent loss is "
                      "carrying more lean mass than it should.",
        },
        "plateau": {
            "title": "Break the plateau",
            "detail": "Progress has stalled — adjust calories or training volume to get "
                      "movement again.",
        },
        "plateau_risk": {
            "title": "Get ahead of a plateau",
            "detail": "Early stall signs are building — a small change now keeps momentum "
                      "before it flattens.",
        },
        "too_fast": {
            "title": "Ease the pace",
            "detail": "You're losing fast enough to risk muscle — a slightly smaller "
                      "deficit protects lean mass.",
        },
        "weight_away": {
            "title": "Reset the trend",
            "detail": "The scale drifted the wrong way — one intentional week usually "
                      "turns it back.",
        },
        "gaining": {
            "title": "Refocus on fat loss",
            "detail": "Mass has been trending up — tighten nutrition to get fat moving "
                      "the right way.",
        },
    }
    if watch:
        top = watch[0]
        rec = _BY_TAG.get(top.tag)
        if rec:
            return rec
        return {"title": f"Address {top.title.lower()}", "detail": top.detail or ""}

    # Everything on track — the leverage is in sharpening the picture or holding course.
    if confidence.get("level") == "low":
        return {"title": "Add a check-in",
                "detail": "You're on track — a fuller check-in (tape + photos) will let "
                          "WLJ read your progress with more confidence."}
    if wins:
        return {"title": "Hold the course",
                "detail": "What you're doing is working — keep the same approach and let "
                          "the trend compound."}
    return None
