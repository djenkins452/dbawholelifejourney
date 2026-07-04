# ==============================================================================
# File: apps/ai/chatgpt_cos/executive_interpretation.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Executive Interpretation Engine (P33). A DETERMINISTIC judgment layer
#   that converts raw deterministic facts into EXECUTIVE SIGNALS *before* they reach
#   the Conversation Planner / Executive Brief Composer. It is NOT a planner, engine,
#   composer, or prioritizer — it reuses existing deterministic providers (TaskQueries
#   horizons, health/goals SAE state, executive_summary) and INTERPRETS them like a
#   Chief of Staff would: workload is today's commitments + overdue (NOT total pending
#   count); a strategic backlog is never an overload conclusion. Output: ExecutiveSignals.
# ==============================================================================
import logging
from dataclasses import dataclass, asdict, field

logger = logging.getLogger(__name__)


@dataclass
class ExecutiveSignals:
    workload: str = "light"            # light|manageable|full|heavy|overloaded
    workload_summary: str = ""         # narration: "1 due today; 21 open are backlog"
    today_count: int = 0
    overdue_count: int = 0
    soon_count: int = 0                # due within 7 days (near-term)
    backlog_count: int = 0            # no due date — strategic/someday
    total_pending: int = 0
    cognitive_load: str = "low"        # low|moderate|high
    recovery_needed: bool = False
    health_read: str = "stable"        # improving|stable|declining
    biggest_risk: str = ""
    highest_leverage: str = ""
    strategic_focus: str = ""
    intervention_required: bool = False
    confidence: str = "medium"         # low|medium|high
    headline: str = ""                 # the one-line executive thesis
    sleep_hours: float = None          # last-night sleep (evidence for the energy story)
    # ── Executive JUDGMENTS the composer must NARRATE, not invent (P35) ──
    primary_challenge: str = "none"    # energy | workload | none — what's the real limiter
    challenge_reason: str = ""         # the conclusion (e.g. "more than the open-item count")
    disposition: str = ""              # the strategic stance ("don't try to catch up …")
    recommendation_levers: list = field(default_factory=list)  # chosen priorities/levers
    backlog_can_wait: bool = False     # the disposition of the backlog
    ease_load: bool = False            # keep the day's load light (recovery)
    # ── Learned personal knowledge that ADAPTS behavior (P36 Layer 4) ──
    deprioritized: list = field(default_factory=list)  # things NOT to elevate (learned)
    tone: str = ""                     # learned communication preference (e.g. "direct")
    directive_explanations: list = field(default_factory=list)  # "why do you think that?"
    # ── Listening & Evidence Reconciliation: how the user's OWN report reconciled
    # with the objective read. "" | positive_over_debt | confirmed_good |
    # confirmed_low | negative_no_debt ──
    reconciliation: str = ""

    def to_dict(self):
        return asdict(self)


# ── Subjective evidence: the user's OWN report of how they feel. This is EVIDENCE the
# reconciliation weighs against the objective sleep read — never ignored. ──────────
_POSITIVE_ENERGY = (
    "refreshed", "rested", "energized", "energetic", "good", "great", "fantastic",
    "wonderful", "ready", "strong", "solid", "recharged", "clear headed",
    "clear-headed", "sharp", "alert", "fresh", "well rested", "feel fine", "feeling fine",
    "feel good", "feeling good", "feel great", "on top of it",
)
_NEGATIVE_ENERGY = (
    "tired", "exhausted", "drained", "wiped", "rough", "worn out", "worn-out",
    "groggy", "sluggish", "low energy", "no energy", "beat", "spent", "awful",
    "terrible", "foggy", "run down", "run-down", "wrecked", "shattered", "depleted",
    "dragging", "burnt out", "burned out", "not good", "not great", "not rested",
    "didn't sleep", "barely slept", "can't focus", "cant focus",
)


def classify_subjective_energy(text):
    """Classify the user's reported energy from their own words → 'positive' /
    'negative' / None. Negatives win ties (err toward caution — a mixed 'ok but tired'
    is a concern). This is the SUBJECTIVE half of the evidence the reconciliation
    weighs; it is deterministic and never overrides the number silently."""
    t = (text or "").lower()
    if not t:
        return None
    if any(w in t for w in _NEGATIVE_ENERGY):
        return "negative"
    if any(w in t for w in _POSITIVE_ENERGY):
        return "positive"
    return None


def _text(item):
    if not item:
        return ""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return (item.get("message") or item.get("title") or item.get("phrase")
                or item.get("concern") or "").strip()
    return str(item).strip()


# ── Existing deterministic providers (reused; never duplicated) ────────────
def _task_horizons(user):
    """Task counts BY HORIZON via the canonical TaskQueries — the executive unit,
    not a single 'pending' lump. Defensive: any failure yields zeros."""
    out = {"today": 0, "overdue": 0, "soon": 0, "backlog": 0, "total": 0}
    try:
        from datetime import timedelta
        from apps.life.services.task_queries import TaskQueries
        from apps.core.utils import get_user_now
        now = get_user_now(user)
        out["today"] = TaskQueries.due_today(user).count()
        out["overdue"] = TaskQueries.overdue(user).count()
        out["soon"] = TaskQueries.due_within(user, now + timedelta(days=7)).count()
        out["backlog"] = TaskQueries.no_due_date(user).count()
        out["total"] = TaskQueries.pending(user).count()
    except Exception:
        logger.warning("interpretation: task horizons failed", exc_info=True)
    return out


def _exec_summary(user):
    try:
        from apps.core.cos_briefing.executive_summary import build_executive_summary
        es = build_executive_summary(user)
        return es if isinstance(es, dict) else {}
    except Exception:
        logger.warning("interpretation: exec summary failed", exc_info=True)
        return {}


def _health_read(user):
    out = {"recovery_needed": False, "read": "stable", "note": "", "sleep_hours": None}
    try:
        from apps.ai.cos_services import get_domain_state
        h = (get_domain_state(user, "health").get("state") or {})
        sleep = h.get("sleep_last_night_hours") or h.get("sleep_avg_hours_7d")
        if isinstance(sleep, (int, float)) and 0 < sleep < 6.5:
            out["recovery_needed"] = True
            out["note"] = "sleep is short"
            out["sleep_hours"] = sleep
        trend = (h.get("weight_trend") or "").lower()
        if "down" in trend or "improv" in trend:
            out["read"] = "improving"
    except Exception:
        logger.warning("interpretation: health read failed", exc_info=True)
    return out


def _strategic_focus(user):
    try:
        from apps.ai.cos_services import get_domain_state
        st = (get_domain_state(user, "purpose").get("state") or {})
        m = st.get("mission")
        if isinstance(m, dict):
            return m.get("title") or ""
    except Exception:
        pass
    return ""


# ── Interpretation (the JUDGMENT — workload from horizon, not count) ───────
def _interpret_workload(tw):
    """Workload = what actually demands attention TODAY (due today + overdue) — NOT
    the total pending count. A strategic/someday backlog is not today's workload."""
    active = tw["today"] + tw["overdue"]
    if active == 0:
        wl = "light"
    elif active <= 3:
        wl = "manageable"
    elif active <= 6:
        wl = "full"
    elif active <= 10:
        wl = "heavy"
    else:
        wl = "overloaded"
    strategic = max(0, tw["total"] - active)
    parts = []
    if tw["today"]:
        parts.append(f"{tw['today']} due today")
    if tw["overdue"]:
        parts.append(f"{tw['overdue']} overdue")
    if not parts:
        parts.append("nothing due today")
    summary = "; ".join(parts)
    if strategic > 0:
        summary += (f"; the other {strategic} open item"
                    f"{'s are' if strategic != 1 else ' is'} upcoming or longer-term "
                    "backlog, not today's load")
    return wl, summary


def _cognitive_load(tw, health):
    active = tw["today"] + tw["overdue"]
    if health["recovery_needed"] and active >= 3:
        return "high"
    if active <= 2:
        return "low"
    if active <= 6:
        return "moderate"
    return "high"


def _looks_justified(rec):
    """A leverage statement is 'justified' if it explains WHY (contains a because/so/—
    rationale), so a bare routine task never reads as highest leverage on its own."""
    r = (rec or "").lower()
    return any(c in r for c in ("because", " so ", " — ", "keeps", "protects",
                                "moves", "leverage", "compounds", "highest"))


def _headline(workload, recovery, has_backlog):
    if workload in ("light", "manageable") and has_backlog:
        base = f"Today's workload is {workload} despite a healthy strategic backlog"
    elif workload in ("heavy", "overloaded"):
        base = f"Today is a {workload} day — guard your focus"
    elif workload in ("light", "manageable"):
        base = f"Today's workload is {workload}"
    else:
        base = f"Today is a {workload} day"
    if recovery:
        base += ("; recovery is today's limiting factor, so protect your energy "
                 "before pushing performance")
    return base + "."


def interpret(user, low_energy=False, subjective=None):
    """Produce ExecutiveSignals — ALL executive judgment — from deterministic facts
    plus the user's OWN reported state. The Composer narrates these conclusions; it
    never invents them (P35). Deterministic, request-path-safe, degrades gracefully.

    LISTENING & EVIDENCE RECONCILIATION: `subjective` ('positive'/'negative'/None,
    owned by the check-in) is the user's lived report — EVIDENCE, not noise. We
    reconcile it with the objective sleep read rather than blindly trusting either. A
    short night the user says felt refreshing is NOT an energy-management day; a normal
    night the user says felt terrible IS. The number is never silently overridden, but
    lived experience is never ignored (`low_energy=True` folds into a negative report)."""
    tw = _task_horizons(user)
    es = _exec_summary(user)
    health = _health_read(user)

    workload, wsummary = _interpret_workload(tw)
    has_backlog = (tw["total"] - (tw["today"] + tw["overdue"])) >= 3

    # Reconcile the user's EXPLICIT report with the objective sleep-debt read. The
    # reconciliation narrative fires only for an explicit `subjective` report; the
    # legacy `low_energy` flag (used by other callers) keeps its original meaning.
    objective_recovery = bool(health["recovery_needed"])
    reconciliation = ""
    if subjective == "positive" and objective_recovery:
        # Short night on paper, but the user reports feeling good/refreshed → do NOT
        # assert an energy-management day; trust the lived experience, watch & adjust.
        reconciliation, recovery = "positive_over_debt", False
    elif subjective == "positive":
        reconciliation, recovery = "confirmed_good", False
    elif subjective == "negative":
        # The user reports low energy — trust it, whether or not the number agrees.
        recovery = True
        reconciliation = "confirmed_low" if objective_recovery else "negative_no_debt"
    else:
        # No explicit report → legacy behavior: objective read OR the low_energy flag.
        recovery = bool(objective_recovery or low_energy)

    biggest_risk = _text(es.get("biggest_risk"))
    if not biggest_risk and recovery:
        biggest_risk = "sleep debt is the main thing to watch"

    strategic = _strategic_focus(user)
    # Highest leverage is a JUDGMENT, not the first available task (P33.1: a routine
    # task must not outrank strategic leverage without justification). Priority:
    # recovery (when it's the limiting factor) > a real risk-driven move > the
    # strategic mission > a routine recommendation, and a routine pick is justified.
    recs = es.get("recommendations") or []
    rec = next((_text(x) for x in recs if _text(x)), "")
    if recovery:
        highest_leverage = ("protecting your sleep and energy today — that compounds "
                            "into everything else")
    elif strategic:
        highest_leverage = (f"moving {strategic} forward — that's where the leverage "
                            "is today, not the routine items")
    elif rec:
        highest_leverage = rec + (" — it keeps today's momentum"
                                  if not _looks_justified(rec) else "")
    else:
        highest_leverage = ""
    # ── Executive JUDGMENTS (the Chief-of-Staff opinions — owned HERE, P35) ──
    # What is the real limiter today, and the stance/levers that follow from it.
    primary_challenge, challenge_reason, disposition, levers = "none", "", "", []
    if reconciliation == "positive_over_debt":
        # The user's report contests the sleep-debt read — honor it. Energy is NOT the
        # framed challenge today; we watch it rather than manage it.
        primary_challenge = "none"
        challenge_reason = "your lived experience matters more than the raw number this morning"
        disposition = ("I'd take your word that you feel good and treat today as a normal "
                       "day — watching your energy rather than managing it")
    elif recovery:
        primary_challenge = "energy"
        challenge_reason = (
            "you're telling me you're running low, and I trust that over the number"
            if reconciliation == "negative_no_debt"
            else "more than the number of open items")
        disposition = "I wouldn't try to catch up on everything today"
        levers = ["protect your energy", "keep nutrition steady",
                  "take care of the one thing that's genuinely due"]
    elif workload in ("heavy", "overloaded"):
        primary_challenge = "workload"
        challenge_reason = "the volume is the constraint, so sequencing matters"
        disposition = "I'd protect the few things that truly matter and let the rest slide"
    ease_load = recovery

    # ── ADAPT behavior from learned personal knowledge (P36) ──
    deprioritized, tone, directive_explanations = _behavior_adapt(user)
    if deprioritized and primary_challenge == "energy":
        ease_load = True

    # Intervention is a JUDGMENT, not a count: only real risk warrants it, never a
    # large-but-harmless backlog.
    intervention = (tw["overdue"] >= 5 or workload == "overloaded"
                    or bool(es.get("biggest_risk")))
    confidence = "high" if (tw["total"] or es) else "low"

    return ExecutiveSignals(
        workload=workload, workload_summary=wsummary,
        today_count=tw["today"], overdue_count=tw["overdue"], soon_count=tw["soon"],
        backlog_count=tw["backlog"], total_pending=tw["total"],
        cognitive_load=_cognitive_load(tw, health), recovery_needed=recovery,
        health_read=health["read"], biggest_risk=biggest_risk,
        highest_leverage=highest_leverage, strategic_focus=strategic,
        intervention_required=intervention, confidence=confidence,
        headline=_headline(workload, recovery, has_backlog),
        sleep_hours=health.get("sleep_hours"),
        primary_challenge=primary_challenge, challenge_reason=challenge_reason,
        disposition=disposition, recommendation_levers=levers,
        backlog_can_wait=has_backlog, ease_load=ease_load,
        deprioritized=deprioritized, tone=tone,
        directive_explanations=directive_explanations,
        reconciliation=reconciliation)


def _behavior_adapt(user):
    """Read learned BehaviorDirectives (P36 Layer 4) and translate the structured keys
    into behavior changes the brief honors. Defensive: no directives -> no change, so
    behavior is byte-identical for users with nothing learned yet. Returns
    (deprioritized:list, tone:str, explanations:list)."""
    deprioritized, tone, explanations = [], "", []
    try:
        from apps.ai.chatgpt_cos.behavior_guidance import directive_map
        dm = directive_map(user)
    except Exception:
        return deprioritized, tone, explanations
    for key, d in dm.items():
        if key.startswith("deprioritize:"):
            token = key.split(":", 1)[1].strip()
            if token:
                deprioritized.append(token)
        elif key.startswith("tone:") and not tone:
            tone = key.split(":", 1)[1].strip()
        try:
            explanations.append(d.explain())
        except Exception:
            pass
    return deprioritized, tone, explanations
