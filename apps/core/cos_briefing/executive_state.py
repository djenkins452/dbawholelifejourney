"""State-based executive reasoning adapter (state-adapter sprint, 2026-06-18).

Beth's executive briefing historically reasoned from EVENTS (Insights /
Predictions) — transient, rule-fired, 7-day-windowed. Standing achievements
(down N lbs, glucose improving, a 15-day reading streak) decayed out of that
window and went invisible, while ongoing deficits (declining sleep) stayed
perpetually fresh. A Chief of Staff should reason primarily from STATE.

This THIN adapter reads standing state that ALREADY exists (SAE module state,
canonical glucose summary, weight entries / HealthProfile, GoalMomentumSnapshot,
faith & medicine state) and normalizes it into ``ExecutiveStateSignal`` objects
so the briefing's executive lenses (biggest win / improvement / decline / most
important trend) can reason from "what is currently true," not only "what
recently happened."

Rules honored (per the sprint brief):
  - Reads EXISTING state only. Never invents data. Omits a signal when its
    grounding is unavailable — honest degradation, never fabrication.
  - No new scoring system: ranking is a coarse confidence tier + a small
    deterministic domain tiebreak, NOT a numeric salience score. Cross-domain
    magnitudes are display-only and never compared.
  - Deterministic, read-only, request-path safe (cached SAE state + indexed
    rows). Never raises to the caller.
  - SUPPLEMENTS events; does not replace Insights / Predictions / GuidanceItem.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_CONF_RANK = {"high": 3, "medium": 2, "low": 1, "": 0}

# Deterministic TIEBREAK only (not a salience score): when two signals share a
# confidence tier, this stable order decides which leads. Earlier = leads.
_DOMAIN_TIEBREAK = [
    "weight", "glucose", "sleep", "medication", "faith", "goals",
    "fitness", "nutrition",
]


@dataclass
class ExecutiveStateSignal:
    domain: str
    lens: str            # win | improvement | decline | risk | opportunity | trend
    direction: str       # improving | declining | stable | risk | opportunity
    magnitude: float | None
    confidence: str      # high | medium | low
    title: str
    message: str
    evidence: list = field(default_factory=list)
    source: str = ""
    # Leverage = improving THIS domain cascades into others (sleep → weight,
    # glucose, energy). Drives the OPPORTUNITY lens ("where does one unit of
    # effort create the largest return?"). A simple deterministic flag — NOT a
    # scoring engine. Approved leverage domains: sleep/recovery, nutrition/
    # protein, activity/fitness, medication adherence.
    leverage: bool = False
    # Full-board status (every domain reports every cycle, even when quiet).
    status: str = ""        # strong|improving|stable|declining|neglected|unknown
    polarity: str = ""      # positive|neutral|negative|unknown
    consider_for: str = ""  # risk|opportunity|progress|context


_LEVERAGE_DOMAINS = frozenset({
    "sleep", "recovery", "nutrition", "protein", "fitness", "activity",
    "medication",
})


def to_dict(signal):
    """ExecutiveStateSignal → plain dict (or None) for the briefing contract."""
    if signal is None:
        return None
    return {
        "domain": signal.domain,
        "lens": signal.lens,
        "direction": signal.direction,
        "magnitude": signal.magnitude,
        "confidence": signal.confidence,
        "title": signal.title,
        "message": signal.message,
        "evidence": list(signal.evidence or []),
        "source": signal.source,
        "leverage": signal.leverage,
        "status": signal.status,
        "polarity": signal.polarity,
        "consider_for": signal.consider_for,
    }


def _module(user, name):
    from apps.core.ai_state.state_engine import get_module_state
    try:
        return get_module_state(user, name) or {}
    except Exception:
        logger.debug("state adapter: module %s read failed", name, exc_info=True)
        return {}


# ── Per-domain standing-state signal builders ───────────────────────────
# Each is defensive: returns [] on any failure or missing grounding.

def _weight_signals(user, health):
    out = []
    try:
        from apps.health.models import WeightEntry
        qs = (WeightEntry.objects.filter(user=user, status="active")
              .order_by("recorded_at"))
        first = qs.first()
        last = qs.last()
        if not first or not last:
            return out
        start = float(first.value_in_lb)
        current = float(last.value_in_lb)
        loss = round(start - current, 1)
        entries = health.get("weight_entries_90d") or qs.count()
        conf = "high" if entries >= 20 else "medium" if entries >= 5 else "low"
        remaining = health.get("weight_goal_remaining")
        if loss >= 1.0:  # a real standing achievement (lower is the goal)
            msg = (f"Down {loss:.1f} lb since you started tracking "
                   f"({start:.0f} → {current:.0f} lb).")
            if remaining:
                msg += f" {float(remaining):.0f} lb to your goal."
            out.append(ExecutiveStateSignal(
                domain="weight", lens="win", direction="improving",
                magnitude=loss, confidence=conf,
                title=f"Weight down {loss:.1f} lb", message=msg,
                evidence=[f"start {start:.0f} → current {current:.0f} lb",
                          f"{entries} entries"],
                source="weight_entries+health_state"))
        elif loss <= -1.0:
            out.append(ExecutiveStateSignal(
                domain="weight", lens="decline", direction="declining",
                magnitude=loss, confidence=conf,
                title=f"Weight up {abs(loss):.1f} lb",
                message=(f"Up {abs(loss):.1f} lb since you started tracking "
                         f"({start:.0f} → {current:.0f} lb)."),
                evidence=[f"start {start:.0f} → current {current:.0f} lb"],
                source="weight_entries+health_state"))
    except Exception:
        logger.debug("state adapter: weight signal failed", exc_info=True)
    return out


def _glucose_signals(user):
    out = []
    try:
        from apps.health.services.glucose_snapshot import build_glucose_summary
        s = build_glucose_summary(user) or {}
        trend = s.get("trend_7d_vs_30d") or ""
        a7, a30 = s.get("average_7d"), s.get("average_30d")
        a1c = s.get("projected_a1c")
        conf = s.get("projected_a1c_confidence") or "low"
        mag = abs(a7 - a30) if (a7 is not None and a30 is not None) else None
        if trend == "improving":
            msg = "Your glucose is trending down"
            if a7 is not None and a30 is not None:
                msg += f" (7-day avg {a7} vs 30-day {a30} mg/dL)"
            if a1c is not None:
                msg += f"; projected A1C ~{a1c}"
            msg += "."
            out.append(ExecutiveStateSignal(
                domain="glucose", lens="improvement", direction="improving",
                magnitude=mag, confidence=conf, title="Glucose improving",
                message=msg,
                evidence=[f"7d {a7} vs 30d {a30} mg/dL", f"A1C ~{a1c}"],
                source="glucose_summary"))
        elif trend == "worsening":
            out.append(ExecutiveStateSignal(
                domain="glucose", lens="decline", direction="declining",
                magnitude=mag, confidence=conf, title="Glucose drifting up",
                message=(f"Your glucose is trending up (7-day avg {a7} vs "
                         f"30-day {a30} mg/dL)."),
                evidence=[f"7d {a7} vs 30d {a30} mg/dL"],
                source="glucose_summary"))
    except Exception:
        logger.debug("state adapter: glucose signal failed", exc_info=True)
    return out


def _sleep_signals(health):
    out = []
    try:
        trend = health.get("sleep_trend")
        cons = health.get("sleep_consistency_score")
        hrs = health.get("sleep_avg_hours_7d")
        if trend in ("decreasing", "declining"):
            msg = "Your sleep is trending down"
            if hrs is not None:
                msg += f" (averaging {hrs}h"
                msg += f", consistency {int(cons)}/100)" if cons is not None else ")"
            elif cons is not None:
                msg += f" (consistency {int(cons)}/100)"
            msg += "."
            out.append(ExecutiveStateSignal(
                domain="sleep", lens="decline", direction="declining",
                magnitude=None,
                confidence="high" if cons is not None else "medium",
                title="Sleep consistency slipping", message=msg,
                evidence=[f"avg {hrs}h", f"consistency {cons}"],
                source="health_state"))
        elif cons is not None and cons < 50:
            out.append(ExecutiveStateSignal(
                domain="sleep", lens="risk", direction="risk", magnitude=None,
                confidence="medium", title="Sleep consistency low",
                message=f"Sleep consistency is {int(cons)}/100.",
                evidence=[f"consistency {cons}"], source="health_state"))
        elif trend in ("increasing", "improving"):
            out.append(ExecutiveStateSignal(
                domain="sleep", lens="improvement", direction="improving",
                magnitude=None, confidence="medium", title="Sleep improving",
                message=(f"Your sleep is trending up"
                         + (f" (averaging {hrs}h)" if hrs is not None else "")
                         + "."),
                evidence=[f"avg {hrs}h"], source="health_state"))
    except Exception:
        logger.debug("state adapter: sleep signal failed", exc_info=True)
    return out


def _medication_signals(user):
    out = []
    try:
        ms = _module(user, "medicine")
        adh = ms.get("adherence_7d")
        if adh is None:
            return out
        adh = float(adh)
        if adh >= 90:
            out.append(ExecutiveStateSignal(
                domain="medication", lens="win", direction="improving",
                magnitude=adh, confidence="high",
                title="Medication adherence strong",
                message=(f"You've taken your medications {int(adh)}% of the "
                         f"time this week."),
                evidence=[f"adherence {int(adh)}%"], source="medicine_state"))
        elif adh < 70:
            out.append(ExecutiveStateSignal(
                domain="medication", lens="decline", direction="declining",
                magnitude=adh, confidence="high",
                title="Medication adherence low",
                message=f"Medication adherence is {int(adh)}% this week.",
                evidence=[f"adherence {int(adh)}%"], source="medicine_state"))
    except Exception:
        logger.debug("state adapter: medication signal failed", exc_info=True)
    return out


def _faith_signals(user):
    out = []
    try:
        fs = _module(user, "faith")
        streak = fs.get("reading_streak") or 0
        dsr = fs.get("days_since_reading")
        if streak >= 7 and (dsr is None or dsr <= 2):
            out.append(ExecutiveStateSignal(
                domain="faith", lens="win", direction="improving",
                magnitude=float(streak), confidence="high",
                title=f"Bible reading streak: {streak} days",
                message=f"You're on a {streak}-day Bible reading streak.",
                evidence=[f"streak {streak}", f"days since reading {dsr}"],
                source="faith_state"))
        elif dsr is not None and dsr >= 7:
            out.append(ExecutiveStateSignal(
                domain="faith", lens="decline", direction="declining",
                magnitude=float(dsr), confidence="medium",
                title="Bible reading has lapsed",
                message=f"It's been {dsr} days since your last reading.",
                evidence=[f"days since reading {dsr}"], source="faith_state"))
    except Exception:
        logger.debug("state adapter: faith signal failed", exc_info=True)
    return out


def _goal_signals(user):
    out = []
    try:
        from apps.purpose.mission_selection import select_active_mission_goal
        goal = select_active_mission_goal(user)
        if goal is None:
            return out
        snap = goal.momentum_snapshots.first()  # nightly, read-only
        trend = getattr(snap, "momentum_trend", None)
        if trend == "rising":
            out.append(ExecutiveStateSignal(
                domain="goals", lens="improvement", direction="improving",
                magnitude=None, confidence="medium",
                title=f"Momentum building: {goal.title}",
                message=f"Your mission '{goal.title}' has rising momentum.",
                evidence=["momentum trend rising"], source="goal_momentum"))
        elif trend == "falling":
            out.append(ExecutiveStateSignal(
                domain="goals", lens="decline", direction="declining",
                magnitude=None, confidence="medium",
                title=f"Momentum slipping: {goal.title}",
                message=f"Your mission '{goal.title}' momentum is falling.",
                evidence=["momentum trend falling"], source="goal_momentum"))
    except Exception:
        logger.debug("state adapter: goal signal failed", exc_info=True)
    return out


def _relationship_signals(user):
    """Relationship-drift signal from the EXISTING relationships standing
    contract (neglected_count / days_since_contact). Grounded only — omitted
    honestly when the contract has no data. Never fabricates relationship risk."""
    out = []
    try:
        rel = _module(user, "relationships")
        contract = rel.get("_contract") or {}
        summary = contract.get("summary") or {}
        neglected_count = summary.get("neglected_count") or 0
        if neglected_count <= 0:
            return out
        neglected = (contract.get("alerts") or {}).get("neglected") or []
        names = [n.get("name") for n in neglected[:2] if n.get("name")]
        who = (" — e.g. " + ", ".join(names)) if names else ""
        out.append(ExecutiveStateSignal(
            domain="relationships", lens="decline", direction="declining",
            magnitude=float(neglected_count), confidence="medium",
            title=f"{neglected_count} relationship"
                  f"{'s' if neglected_count != 1 else ''} drifting",
            message=(f"{neglected_count} connection"
                     f"{'s' if neglected_count != 1 else ''} you haven't "
                     f"reached out to in a while{who}."),
            evidence=[f"neglected_count {neglected_count}"],
            source="relationships_contract"))
    except Exception:
        logger.debug("state adapter: relationship signal failed", exc_info=True)
    return out


# ── Full-board steady-state layer ───────────────────────────────────────
# Every canonical domain reports a STATUS every cycle, even when quiet — so the
# board is complete (stable / neglected / unknown included), never silently
# empty. These are CONTEXT signals (lens='context', direction='steady'): they
# carry status/polarity/consider_for for the board, and deliberately do NOT
# enter the win/decline/opportunity lenses (purely additive — no change to
# existing reasoning in this step).
_FULL_BOARD = (
    "weight", "sleep", "glucose", "medication", "nutrition", "workouts",
    "faith", "relationships", "goals", "accountability", "routines",
    "finances", "work",
)
# status → (polarity, consider_for)
_STATUS_META = {
    "strong": ("positive", "progress"),
    "improving": ("positive", "progress"),
    "stable": ("neutral", "context"),
    "declining": ("negative", "risk"),
    "neglected": ("negative", "risk"),
    "unknown": ("unknown", "context"),
}
# lens → status for notable signals (so they report a full-board status too)
_LENS_STATUS = {
    "win": "strong", "improvement": "improving", "opportunity": "improving",
    "decline": "declining", "risk": "declining",
}


def _ctx(domain, status, conf, title, message, evidence=None):
    polarity, consider_for = _STATUS_META.get(status, ("unknown", "context"))
    return ExecutiveStateSignal(
        domain=domain, lens="context", direction="steady", magnitude=None,
        confidence=conf, title=title, message=message, evidence=evidence or [],
        source=f"{domain}_steady_state", leverage=False,
        status=status, polarity=polarity, consider_for=consider_for)


def _emit_domain_status(user, health, domain):
    """Return a steady-state ExecutiveStateSignal for `domain` (always one).
    Lightweight, grounded reads; 'unknown' when there's no data."""
    if domain == "weight":
        from apps.health.models import WeightEntry
        n = WeightEntry.objects.filter(user=user, status="active").count()
        return (_ctx("weight", "stable", "medium", "Weight holding steady",
                     f"Weight is roughly flat right now ({n} entries logged).",
                     [f"{n} entries"]) if n else
                _ctx("weight", "unknown", "low", "No weight data",
                     "No weight logged yet."))
    if domain == "sleep":
        from apps.health.models import SleepEntry
        from datetime import timedelta
        from django.utils import timezone
        n = SleepEntry.objects.filter(
            user=user, sleep_date__gte=(timezone.now() - timedelta(days=7)).date()
        ).count()
        return (_ctx("sleep", "stable", "medium", "Sleep steady",
                     f"Sleep is holding steady ({n} nights logged this week).",
                     [f"{n} nights/7d"]) if n else
                _ctx("sleep", "unknown", "low", "No recent sleep data",
                     "No sleep logged in the last week."))
    if domain == "glucose":
        try:
            from apps.health.services.glucose_snapshot import build_glucose_summary
            s = build_glucose_summary(user) or {}
            a7 = s.get("average_7d")
            if a7 is not None:
                healthy = a7 < 140
                return _ctx("glucose", "strong" if healthy else "stable",
                            "medium",
                            "Glucose in range" if healthy else "Glucose steady",
                            f"Glucose is {'stable and in a healthy range' if healthy else 'stable'} "
                            f"(7-day avg {a7} mg/dL).", [f"7d avg {a7}"])
        except Exception:
            pass
        return _ctx("glucose", "unknown", "low", "No glucose data",
                    "No recent glucose readings.")
    if domain == "medication":
        ms = _module(user, "medicine")
        adh = ms.get("adherence_7d")
        if adh is not None:
            return _ctx("medication", "stable", "medium",
                        "Medication adherence steady",
                        f"Adherence is steady at {int(float(adh))}% this week.",
                        [f"adherence {int(float(adh))}%"])
        return _ctx("medication", "unknown", "low", "No medication data",
                    "No medication adherence data this week.")
    if domain == "nutrition":
        try:
            from apps.health.models import FoodEntry
            from django.utils import timezone
            today = timezone.now().date()
            n = FoodEntry.objects.filter(
                user=user, status="active", created_at__date=today).count()
            return (_ctx("nutrition", "stable", "medium", "Nutrition logged today",
                         f"You've logged {n} food item{'s' if n != 1 else ''} today.",
                         [f"{n} today"]) if n else
                    _ctx("nutrition", "unknown", "low", "Nutrition not logged",
                         "No food logged today — can't read nutrition yet."))
        except Exception:
            return _ctx("nutrition", "unknown", "low", "Nutrition unavailable",
                        "No nutrition data available.")
    if domain == "workouts":
        try:
            from apps.health.models import WorkoutSession, WorkoutPlan
            from datetime import timedelta
            from django.utils import timezone
            recent = WorkoutSession.objects.filter(
                user=user,
                created_at__gte=timezone.now() - timedelta(days=7)).count()
            if recent >= 3:
                return _ctx("workouts", "strong", "medium", "Training consistent",
                            f"{recent} workouts in the last week — strong "
                            f"consistency.", [f"{recent}/7d"])
            if recent:
                return _ctx("workouts", "stable", "medium", "Training steady",
                            f"{recent} workout{'s' if recent != 1 else ''} this "
                            f"week.", [f"{recent}/7d"])
            has_plan = WorkoutPlan.objects.filter(user=user, is_active=True).exists()
            return (_ctx("workouts", "declining", "medium", "Training has stalled",
                         "You have an active plan but no workouts logged this "
                         "week.", ["0/7d, active plan"]) if has_plan else
                    _ctx("workouts", "unknown", "low", "No training data",
                         "No workouts or active plan."))
        except Exception:
            return _ctx("workouts", "unknown", "low", "Training unavailable",
                        "No workout data available.")
    if domain == "faith":
        fa = _module(user, "faith")
        streak = (fa.get("reading_streak") or fa.get("streak") or 0)
        if streak and streak > 0:
            return _ctx("faith", "strong", "medium", "Faith streak active",
                        f"Active reading streak ({streak} days).",
                        [f"streak {streak}"])
        return (_ctx("faith", "stable", "low", "Faith steady",
                     "Faith routine tracking, no notable change.")
                if fa else
                _ctx("faith", "unknown", "low", "No faith data",
                     "No faith activity tracked."))
    if domain == "relationships":
        rel = _module(user, "relationships")
        contract = rel.get("_contract") or {}
        summary = contract.get("summary") or {}
        total = summary.get("total_count") or summary.get("people_count")
        if total:
            return _ctx("relationships", "stable", "medium",
                        "Relationships steady",
                        f"{total} relationships tracked, none currently drifting.",
                        [f"{total} tracked"])
        return _ctx("relationships", "unknown", "low", "No relationship data",
                    "No relationships tracked yet.")
    if domain == "goals":
        try:
            from apps.health.models import HealthProfile
            hp = HealthProfile.objects.filter(user=user).first()
            wp = hp.get_weight_progress() if hp else None
            if wp and wp.get("goal"):
                on = wp.get("on_track")
                if on is True:
                    return _ctx("goals", "improving", "medium", "Goal on track",
                                "Your weight goal is on track.", ["on_track"])
                if on is False:
                    return _ctx("goals", "declining", "medium",
                                "Goal behind pace",
                                "Your weight goal is behind pace.", ["off_track"])
                return _ctx("goals", "stable", "low", "Goal set",
                            "A weight goal is set; pace not yet determinable.")
        except Exception:
            pass
        return _ctx("goals", "unknown", "low", "No goal data",
                    "No active goal with enough data to judge pace.")
    if domain == "accountability":
        try:
            from apps.core.ai_guidance.models import GuidanceItem
            n = GuidanceItem.objects.filter(
                user=user, guidance_type="cos_constraint", is_active=True).count()
            if n:
                return _ctx("accountability", "stable", "medium",
                            "Tracking a recommendation",
                            f"{n} standing recommendation{'s' if n != 1 else ''} "
                            f"being tracked for effectiveness.", [f"{n} active"])
        except Exception:
            pass
        return _ctx("accountability", "unknown", "low",
                    "No standing recommendation",
                    "No recommendation is being tracked yet.")
    if domain == "routines":
        # Light only — operational overdue is handled by the event stream; avoid
        # the heavy build_execution_state on this (request) path.
        return _ctx("routines", "stable", "low", "Routines tracking",
                    "Routine commitments are being tracked; the action queue "
                    "surfaces anything overdue.")
    if domain == "finances":
        fin = _module(user, "finance")
        if fin:
            return _ctx("finances", "stable", "low", "Finances tracked",
                        "Financial data is present and tracking.")
        return _ctx("finances", "unknown", "low", "No finance data",
                    "No financial data — outside what I can see.")
    if domain == "work":
        return _ctx("work", "unknown", "low", "No work data",
                    "No work data — outside what I can see.")
    return _ctx(domain, "unknown", "low", f"{domain} — no read",
                f"No current read on {domain}.")


def _steady_state_signals(user, health, covered):
    out = []
    for d in _FULL_BOARD:
        if d in covered:
            continue
        try:
            out.append(_emit_domain_status(user, health, d))
        except Exception:
            logger.debug("steady-state %s failed", d, exc_info=True)
            out.append(_ctx(d, "unknown", "low", f"{d} — no read",
                            f"No current read on {d}."))
    return out


def build_executive_state_signals(user):
    """Read existing standing state and return normalized ExecutiveStateSignals.

    Full-board: every notable signal PLUS a steady-state status for every quiet
    domain, so the board is complete (stable/neglected/unknown included).
    Deterministic, read-only, never raises."""
    health = _module(user, "health")
    signals = []
    signals += _weight_signals(user, health)
    signals += _glucose_signals(user)
    signals += _sleep_signals(health)
    signals += _medication_signals(user)
    signals += _faith_signals(user)
    signals += _goal_signals(user)
    signals += _relationship_signals(user)
    # Notable signals report a full-board status too (derived from their lens).
    for s in signals:
        if not s.status:
            s.status = _LENS_STATUS.get(s.lens, "stable")
            s.polarity, s.consider_for = _STATUS_META.get(
                s.status, ("neutral", "context"))
    # Tag leverage centrally (one place) — improving these domains cascades
    # into others, so they drive the OPPORTUNITY lens.
    for s in signals:
        if s.domain in _LEVERAGE_DOMAINS:
            s.leverage = True
    # Full-board steady-state: a status for every quiet/stable/unknown domain.
    covered = {s.domain for s in signals}
    signals += _steady_state_signals(user, health, covered)
    return signals


def _ordered(signals):
    """Stable order: highest confidence first, then the deterministic domain
    tiebreak. NOT a salience score — magnitudes are never compared."""
    def key(s):
        order = (_DOMAIN_TIEBREAK.index(s.domain)
                 if s.domain in _DOMAIN_TIEBREAK else len(_DOMAIN_TIEBREAK))
        return (-_CONF_RANK.get(s.confidence, 0), order)
    return sorted(signals, key=key)


def select_executive_lenses(signals):
    """Select the signal-level picks for each executive lens — DISTINCT
    judgments, not one signal reused.

      win         — top realized achievement (lens=='win')
      improvement — top positive TREND (lens=='improvement'), distinct domain
      decline     — top deteriorating signal
      opportunity — top LEVERAGE constraint (where one unit of effort returns
                    the most); MAY share Decline's domain — the worsening
                    leverage area is often the highest-return fix (allowed).

    Anti-fixation: a domain leads AT MOST ONE of win/improvement/decline unless
    it's the only signal. Opportunity is exempt (intentional overlap with
    Decline). ``most_important_trend`` is NOT a pick here — it is synthesized in
    executive_summary (a two-part trajectory statement), never a lone signal.
    """
    improving = _ordered([s for s in signals if s.direction == "improving"])
    declining = _ordered(
        [s for s in signals if s.direction in ("declining", "risk")])
    used = set()

    def take(pool):
        for s in pool:
            if s.domain not in used:
                used.add(s.domain)
                return s
        return None

    win = take([s for s in improving if s.lens == "win"]) or take(improving)
    # Prefer a trend-type improvement for the improvement lens; else next
    # distinct improving signal.
    improvement = (take([s for s in improving if s.lens == "improvement"])
                   or take(improving))
    decline = take(declining)
    # Opportunity = highest-leverage area to improve (the gating constraint).
    # NOT subject to the anti-fixation `used` set — it may equal Decline.
    leverage_pool = _ordered([
        s for s in signals
        if s.direction in ("declining", "risk") and s.leverage])
    opportunity = leverage_pool[0] if leverage_pool else None
    return {
        "biggest_win": win,
        "biggest_improvement": improvement,
        "biggest_decline": decline,
        "biggest_opportunity": opportunity,
    }
