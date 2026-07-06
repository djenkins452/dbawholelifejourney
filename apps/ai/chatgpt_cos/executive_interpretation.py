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
    # ── Conversation-reported accomplishments TODAY (merged from the evidence store).
    # The single place downstream consumers learn what the user has already done. ──
    accomplishments: list = field(default_factory=list)
    # ── Items the user has RECONCILED out of today (trustworthy evidence: already done /
    # wrong time of day / canceled / traveling / sick). Merged from the evidence store;
    # every consumer stops treating these as today's priority. [{item, reason, resume}] ──
    deferred: list = field(default_factory=list)
    # ── HEALTH-CRITICAL, time-sensitive actions that outrank routine/convenience today
    # (overdue prescription doses, danger vitals). Deterministic. Consumers LEAD with
    # these before anything else. ──
    health_critical: list = field(default_factory=list)
    # ── The reasoned CONCLUSION that follows from today's read (what it means for
    # priorities). The prompt PRESENTS this; it must not re-derive prioritization. ──
    executive_picture: str = ""
    # ── Whole-Life intelligence WLJ already computed, folded into the ONE executive
    # understanding (persisted Insight/Prediction/DomainCorrelation/GuidanceItem). ──
    risks: list = field(default_factory=list)
    # Positive domain insights ("weight trending down", "protein on track") — these are
    # WINS / evidence of what's going well, NOT opportunities.
    wins: list = field(default_factory=list)
    # The executive OPPORTUNITY — a high-expected-value move available now (leverage ×
    # capacity × timing × probability), derived from executive STATE, not positive
    # insights. {text, basis, action} or None when there's no standout opening.
    opportunity: dict = None
    predictions: list = field(default_factory=list)
    patterns: list = field(default_factory=list)
    # The executive PATTERN — a non-obvious whole-life pattern the user is unlikely to
    # have recognized (EAE derived pattern → CDCE correlation → cross-domain insight/
    # prediction), ranked by executive value, never a raw single-domain dashboard trend.
    # {text, basis, action} or None (honest: no whole-life pattern clears the bar yet;
    # `observation` then names the strongest single-domain trend as NOT a pattern).
    pattern: dict = None
    # EXECUTIVE PRIORITY WEIGHTING — the single action that actually matters most now,
    # ranked by executive VALUE (not schedule order) over the candidate pool, with
    # completed/accomplished/deferred items removed. {text, why, source, kind, score} or
    # None. Chronology is only a tiebreaker. Every "what should I do / next" surface
    # consumes THIS instead of the next-scheduled item.
    priority_action: dict = None
    guidance: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


# ── Subjective evidence: the user's OWN report of how they feel. This is EVIDENCE the
# reconciliation weighs against the objective sleep read — never ignored. ──────────
_POSITIVE_ENERGY = (
    "refreshed", "rested", "energized", "energetic", "good", "great", "fantastic",
    "wonderful", "ready", "strong", "solid", "recharged", "clear headed",
    "clear-headed", "sharp", "alert", "fresh", "well rested", "feel fine", "feeling fine",
    "feel good", "feeling good", "feel great", "on top of it", "full of energy",
    "lots of energy", "so much energy", "tons of energy", "felt great", "felt good",
    "plenty of energy",
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


def _health_critical_actions(user):
    """Deterministic HEALTH-CRITICAL, time-sensitive actions that must outrank routine
    and convenience items today. NOT a medication special-case — it is the general
    "clinical safety first" rule, sourced from canonical domain truth. Today it reads
    overdue prescription doses (the domain's own `today_doses` status == 'overdue');
    it extends to danger vitals / missed clinical appointments the same way. Returns
    ``[{text, why, kind}]`` most-urgent-first, or ``[]``. Bounded, degrade-safe."""
    out = []
    try:
        from apps.health.services.medicine_queries import MedicineQueries
        overdue = [d for d in MedicineQueries.today_doses(user)
                   if d.get("status") == "overdue"]
        if overdue:
            names = ", ".join(sorted({d["medication"] for d in overdue}))
            n = len(overdue)
            phrase = (f"your prescription medication is overdue ({names})" if n <= 3
                      else f"{n} prescription doses are overdue")
            out.append({"kind": "medication_overdue", "text": phrase,
                        "why": "it directly affects your health and it's time-sensitive"})
    except Exception:
        logger.warning("interpret: health-critical read failed", exc_info=True)
    return out


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


def _opportunity_assessment(*, workload, ease_load, strategic, tw, reconciliation,
                            subjective, accomplishments):
    """The single highest-EXPECTED-VALUE executive opportunity today — leverage ×
    capacity × timing × PROBABILITY of success — derived from executive STATE, never
    from positive domain insights. "What action, taken now, creates disproportionate
    value?" Each candidate requires deterministic evidence and carries its own basis +
    recommended action; the winner is the highest expected value (a medium-leverage,
    near-certain move can beat a high-leverage, low-probability one). Returns
    ``{text, basis, action}`` or ``None`` — and None is honest: no standout opening, so
    today is for disciplined execution, not opportunism."""
    light = (workload in ("light", "manageable")) and not ease_load
    cands = []   # (expected_value, text, basis, action)
    # 1) Open capacity + real strategic leverage → make disproportionate progress.
    if light and strategic:
        cands.append((0.90 * 0.85,
                      f"a genuinely open day and real leverage in {strategic}",
                      "your required load is light today and your strategic focus is clear",
                      f"protect a real block and move {strategic} forward while the calendar "
                      "cooperates — that compounds far beyond routine work"))
    # 2) Ahead of plan → pull the next milestone forward / bank the buffer.
    if accomplishments:
        cands.append((0.80 * 0.75,
                      "you're already ahead of plan today",
                      "you've logged accomplishments beyond what today required",
                      "pull your next milestone forward or bank the buffer rather than coast"))
    # 3) Real energy → take on the hard, deferred problem (energy is the enabler).
    if subjective == "positive" or reconciliation in ("positive_over_debt", "confirmed_good"):
        cands.append((0.80 * 0.80,
                      "unusually good energy today",
                      "your own report that you're feeling strong",
                      "spend it on the hardest problem you've been deferring — a good day is "
                      "wasted on routine work"))
    # 4) A cluster of small items → clear the drag (medium leverage, near-certain).
    small = tw["soon"] if tw["soon"] >= 3 else (tw["backlog"] if tw["backlog"] >= 5 else 0)
    if small:
        cands.append((0.40 * 0.95,
                      f"a cluster of {small} small items you could clear in one pass",
                      "several low-effort tasks are stacking up",
                      "batch them now to eliminate the drag — near-certain success for a light lift"))
    if not cands:
        return None
    cands.sort(key=lambda c: -c[0])
    _, text, basis, action = cands[0]
    return {"text": text, "basis": basis, "action": action}


def _pattern_assessment(user):
    """The single EXECUTIVE PATTERN today — a non-obvious whole-life pattern the user is
    unlikely to have recognized, drawn from ALREADY-COMPUTED whole-life sources in
    priority order (EAE derived patterns → CDCE correlations → cross-domain insight/
    prediction) and ranked by executive value, NOT domain count. A raw single-domain
    dashboard trend (protein low, weight down, sleep average) can never be the pattern —
    it's an observation, held aside. Returns ``{text, basis, action}`` when a pattern
    clears the evidence threshold, else ``{observation: {text, module}|None}`` so the
    honest-empty answer can name the strongest domain trend and say why it isn't a
    pattern. Never invents a connection to fill the answer."""
    try:
        from apps.ai.cos_intelligence import whole_life_patterns, _PATTERN_SRC_RANK, _PATTERN_CONF_FLOOR
    except Exception:
        logger.warning("pattern_assessment: reader import failed", exc_info=True)
        return {"observation": None}
    try:
        data = whole_life_patterns(user)
    except Exception:
        logger.warning("pattern_assessment: whole_life_patterns failed", exc_info=True)
        return {"observation": None}
    qualifying = [c for c in data.get("candidates", [])
                  if float(c.get("confidence") or 0.0) >= _PATTERN_CONF_FLOOR]
    if qualifying:
        # Prefer by source priority (EAE > CDCE > cross-domain), then by confidence.
        qualifying.sort(key=lambda c: (_PATTERN_SRC_RANK.get(c.get("source"), 9),
                                       -float(c.get("confidence") or 0.0)))
        top = qualifying[0]
        return {"text": top["text"], "basis": top["basis"], "action": top["action"]}
    return {"observation": data.get("observation")}


# ── Executive Priority Weighting ──────────────────────────────────────────────────
# Rank the candidate ACTIONS by executive VALUE, never by chronology. Tiers are the
# base value; modifiers (consequence-of-delay, recovery cost) adjust; scheduled_time is
# ONLY a tiebreaker. A routine item never outranks strategic/health work just because it
# is overdue or earliest on the clock. Deterministic; request-path safe (reads the
# pre-computed execution/rhythm truth, never rebuilds).
# Health adherence (a PRESCRIPTION still due today) outranks strategic progress; a
# supplement is a minor health obligation; hygiene/routine is lowest. CONTEXT MATTERS:
# in the evening, strategic deep work is no longer the best move and remaining same-day
# health obligations rise.
_PA_TIER = {"health_critical": 100, "health_obligation": 70, "strategic": 62,
            "opportunity": 52, "task": 44, "commitment": 40, "routine": 20}
_PA_EVENING_HOUR = 18


def _pa_norm(s):
    return " ".join((s or "").split()).strip().lower()


def _pa_hour(user):
    try:
        from apps.core.utils import get_user_now
        return get_user_now(user).hour
    except Exception:
        return 12


def _pa_classify(item):
    """(tier, base) for a candidate by its REAL nature — prescription/supplement/task/
    routine — never its schedule position. Prescription doses are a HEALTH OBLIGATION
    (above strategic); supplements & hygiene are 'routine'. Checked BEFORE is_foundational
    so a med dose is never mis-tiered as strategic."""
    st = (item.get("source_type") or "").lower()
    domain = (item.get("domain") or "").lower()
    if st == "medication_dose":                       # a PRESCRIPTION due today
        return "health_obligation", _PA_TIER["health_obligation"]
    if st == "supplement_dose":
        return "routine", _PA_TIER["routine"]
    if item.get("is_foundational"):
        return "strategic", _PA_TIER["strategic"]
    if st == "task":
        return "task", _PA_TIER["task"]
    if st == "routine_item":
        return "routine", _PA_TIER["routine"]
    if domain in ("calendar", "event", "appointment"):
        return "commitment", _PA_TIER["commitment"]
    return "task", _PA_TIER["task"] - 8


def _pa_why(item, tier):
    st = (item.get("source_type") or "").lower()
    if tier == "health_obligation":
        return "a prescription still due today — adherence comes first"
    if tier == "strategic":
        return "foundational to your mission"
    if (item.get("urgency") or "").lower() == "overdue":
        return "overdue"
    if st == "supplement_dose":
        return "a supplement still due today"
    return "a routine item" if tier == "routine" else "on today's plan"


def _rank_priority_actions(user, *, health_critical, opportunity, strategic_text,
                           deferred_labels, accomplishments, recovery_needed, hour=12):
    """Rank every candidate action by EXECUTIVE VALUE **in context** → (top, ranked_list).
    Candidates: health-critical actions, the strategic/leverage move, the executive
    opportunity, and today's INCOMPLETE rhythm/execution items. Completed / accomplished /
    deferred items are removed (Req 3). CONTEXT: in the evening, strategic/opportunity work
    is demoted (not the best move late) and remaining same-day health obligations rise —
    a prescription due today is never buried under strategic work. Chronology is a
    tiebreaker only."""
    evening = hour is not None and hour >= _PA_EVENING_HOUR
    cands, hc_titles = [], set()
    for hc in (health_critical or []):
        t = (hc.get("text") or "").strip()
        if not t:
            continue
        hc_titles.add(_pa_norm(t))
        cands.append({"text": t, "why": (hc.get("why") or "health-critical"),
                      "source": "health_critical", "kind": "health_critical",
                      "score": _PA_TIER["health_critical"], "sched": ""})
    if strategic_text:
        s = _PA_TIER["strategic"] + 4
        if evening:
            s -= 40                                # deep strategic work is not the evening's best move
        cands.append({"text": strategic_text, "why": "moves your primary mission forward",
                      "source": "strategic", "kind": "strategic", "score": s, "sched": ""})
    if opportunity and opportunity.get("action"):
        o = _PA_TIER["opportunity"] - (30 if evening else 0)
        cands.append({"text": (opportunity.get("text") or opportunity.get("action")),
                      "why": (opportunity.get("basis") or "high expected value"),
                      "source": "opportunity", "kind": "opportunity", "score": o, "sched": ""})
    # Completion match is STEM-based so a reported "journaled" filters a "Journal your
    # day" item (word forms differ) — the production "recommended journaling after done".
    done_stems = {w[:5] for a in (accomplishments or []) for w in _pa_norm(a).split()
                  if len(w) >= 5}
    defr = {_pa_norm(d) for d in (deferred_labels or []) if d}
    try:
        from apps.core.cos_briefing.rhythm_api import get_remaining_rhythm_items
        for it in (get_remaining_rhythm_items(user) or []):
            title = (it.get("title") or "").strip()
            nt = _pa_norm(title)
            if not title or it.get("completed_today"):    # Req 3 — completion
                continue
            if nt in hc_titles:                            # already surfaced as health-critical
                continue
            title_stems = {w[:5] for w in nt.split() if len(w) >= 5}
            if done_stems & title_stems:                   # already accomplished today
                continue
            if any(lbl and lbl in nt for lbl in defr):     # user corrected it away
                continue
            tier, base = _pa_classify(it)
            st = (it.get("source_type") or "").lower()
            score, urg = base, (it.get("urgency") or "").lower()
            if tier == "health_obligation":
                # A prescription due today beats strategic when it's DUE (now/overdue) or
                # as the day closes; earlier in the day (due later) it's on the radar but
                # not yet THE thing to do this moment.
                if not (evening or urg in ("now", "overdue")):
                    score = 50
            elif urg == "overdue":                          # consequence of delay — weighted by KIND
                score += 15 if tier in ("strategic", "task") else 4
            elif urg == "now":
                score += 6
            if evening and st == "supplement_dose":         # a remaining health obligation as day closes
                score += 14
            if recovery_needed and (it.get("domain") or "").lower() == "workout":
                score -= 18                                 # recovery cost
            cands.append({"text": title, "why": _pa_why(it, tier), "source": "execution",
                          "kind": tier, "score": score, "sched": it.get("scheduled_time") or ""})
    except Exception:
        logger.warning("priority_weighting: rhythm read failed", exc_info=True)
    if not cands:
        return None, []
    # RANK BY VALUE; scheduled_time is ONLY the tiebreaker among equal-value candidates.
    cands.sort(key=lambda c: (-c["score"], c.get("sched") == "", c.get("sched") or ""))
    return dict(cands[0]), cands


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

    # ── MERGE conversation-reported evidence into the ONE picture ────────────────
    # What the user told Beth today (subjective state, accomplishments) lives in the
    # shared executive-evidence store, NOT the deterministic SAE. Reading it HERE — the
    # single construction point — is what lets every consumer (brief, decision support,
    # summary, goal review) reflect the same evolving understanding without each one
    # reading caches. When the store is empty, behavior is byte-identical to before.
    try:
        from apps.ai.chatgpt_cos.executive_evidence import today as _reported_today
        _reported = _reported_today(user)
    except Exception:
        _reported = {"accomplishments": [], "subjective": None, "deferrals": []}
    reported_accomplishments = _reported.get("accomplishments") or []
    reported_deferrals = _reported.get("deferrals") or []
    _deferred_labels = {(x.get("item") or "").strip().lower()
                        for x in reported_deferrals if x.get("item")}
    if subjective is None:
        subjective = _reported.get("subjective")   # an explicit param still overrides

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

    # Accomplishments already banked today are part of the picture: the user is ahead
    # of plan, which earns recovery latitude. The MERGE happens here, once; consumers
    # simply present `accomplishments` in their own context.
    if reported_accomplishments:
        ease_load = True

    # ── ADAPT behavior from learned personal knowledge (P36) ──
    deprioritized, tone, directive_explanations = _behavior_adapt(user)
    if deprioritized and primary_challenge == "energy":
        ease_load = True

    # Intervention is a JUDGMENT, not a count: only real risk warrants it, never a
    # large-but-harmless backlog.
    intervention = (tw["overdue"] >= 5 or workload == "overloaded"
                    or bool(es.get("biggest_risk")))
    confidence = "high" if (tw["total"] or es) else "low"

    # HEADLINE = the single most significant FACT about today. EXECUTIVE_PICTURE = the
    # reasoned CONCLUSION that follows from it (what it means for priorities). Both are
    # produced HERE — this is where executive prioritization is decided. The prompt only
    # PRESENTS them; it must not re-derive prioritization in wording.
    headline = _headline(workload, recovery, has_backlog)
    executive_picture = ""
    if reported_accomplishments:
        joined = (reported_accomplishments[0] if len(reported_accomplishments) == 1
                  else ", ".join(reported_accomplishments[:-1]) + " and "
                  + reported_accomplishments[-1])
        headline = f"You've already {joined} today — ahead of plan."
        executive_picture = (
            "Because today's planned effort has already been exceeded, recovery is now the "
            "highest-leverage decision, and the rest of the day is supporting detail rather "
            "than the story.")
    elif reconciliation == "positive_over_debt":
        executive_picture = (
            "Despite a short night on paper, Danny's own report is good, so today is a "
            "normal day to use — not an energy-management day; watch how energy holds "
            "rather than managing it.")
    elif reconciliation in ("confirmed_low", "negative_no_debt"):
        executive_picture = (
            "Energy is the real limiter today by Danny's own report, so protecting it and "
            "keeping the load light is the highest-leverage move.")
    elif primary_challenge == "energy":
        executive_picture = (
            "Recovery is today's limiting factor, so protecting energy is the highest-"
            "leverage move before pushing performance.")
    elif primary_challenge == "workload":
        executive_picture = (
            "Volume is today's constraint, so sequencing the few things that truly matter "
            "is the highest-leverage move.")

    # ── WHOLE-LIFE INTELLIGENCE — fold the deterministic intelligence WLJ already
    # computed into the ONE executive understanding (persisted records, bounded, no
    # request-path recompute). The top risk enriches biggest_risk / executive_picture
    # when today has no bigger headline (an accomplishment or a voiced report outranks a
    # background risk); it never overrides them. interpret() remains the sole authority. ──
    _risks = _wins = _predictions = _patterns = _guidance = None
    try:
        from apps.ai.cos_intelligence import active_intelligence
        _intel = active_intelligence(user)
        # Positive insights are WINS (what's going well), not opportunities.
        _risks, _wins = _intel.get("risks") or [], _intel.get("wins") or []
        _predictions = _intel.get("predictions") or []
        _patterns, _guidance = _intel.get("patterns") or [], _intel.get("guidance") or []
    except Exception:
        logger.warning("interpret: intelligence read failed", exc_info=True)
        _risks = _wins = _predictions = _patterns = _guidance = []
    # EXECUTIVE OPPORTUNITY — computed from executive STATE (leverage × capacity × timing
    # × probability), NEVER from positive insights.
    _opportunity = _opportunity_assessment(
        workload=workload, ease_load=ease_load, strategic=strategic, tw=tw,
        reconciliation=reconciliation, subjective=subjective,
        accomplishments=reported_accomplishments)
    # EXECUTIVE PATTERN — a non-obvious whole-life pattern from already-computed sources
    # (EAE → CDCE → cross-domain), ranked by executive value, never a single-domain trend.
    _pattern = _pattern_assessment(user)
    if not biggest_risk and _risks:
        biggest_risk = _risks[0].get("text", "") or biggest_risk
    if not executive_picture:
        if _risks:
            _b = _risks[0].get("basis")
            executive_picture = ("The thing to watch is " + _risks[0].get("text", "")
                                 + (f" (basis: {_b})." if _b else "."))
        elif _opportunity:
            executive_picture = ("Worth seizing: " + _opportunity["text"] + " — "
                                 + _opportunity["action"] + ".")

    # HEALTH-CRITICAL FIRST: a time-sensitive clinical action outranks everything else
    # today — even a celebration or a good-energy report. Lead the picture with it so
    # every consumer opens on it; the rest of the read follows.
    _health_critical = _health_critical_actions(user)
    # RECONCILIATION: an item the user credibly deferred today (already took it / not
    # appropriate now) is no longer today's priority — drop it from the lead picture.
    if _health_critical and _deferred_labels:
        _health_critical = [h for h in _health_critical
                            if not any(lbl and lbl in (h.get("text", "").lower())
                                       for lbl in _deferred_labels)]
    if _health_critical:
        _hc = _health_critical[0]
        executive_picture = (
            f"Highest priority right now: {_hc['text']} — {_hc['why']}. That outranks "
            "everything else today; it comes first. "
            + (executive_picture or "")).strip()

    # EXECUTIVE PRIORITY WEIGHTING — the single action that actually matters most now,
    # ranked by value across ALL candidates (health-critical, strategic/leverage,
    # opportunity, today's incomplete items), completion-aware, chronology only a
    # tiebreaker. Every "what should I do / next" surface consumes this.
    _priority_action, _ = _rank_priority_actions(
        user, health_critical=_health_critical, opportunity=_opportunity,
        strategic_text=(highest_leverage or "").strip(),
        deferred_labels=_deferred_labels, accomplishments=reported_accomplishments,
        recovery_needed=bool(recovery), hour=_pa_hour(user))

    return ExecutiveSignals(
        risks=_risks, wins=_wins, opportunity=_opportunity, predictions=_predictions,
        patterns=_patterns, pattern=_pattern, priority_action=_priority_action,
        guidance=_guidance, health_critical=_health_critical,
        workload=workload, workload_summary=wsummary,
        today_count=tw["today"], overdue_count=tw["overdue"], soon_count=tw["soon"],
        backlog_count=tw["backlog"], total_pending=tw["total"],
        cognitive_load=_cognitive_load(tw, health), recovery_needed=recovery,
        deferred=reported_deferrals,
        health_read=health["read"], biggest_risk=biggest_risk,
        highest_leverage=highest_leverage, strategic_focus=strategic,
        intervention_required=intervention, confidence=confidence,
        headline=headline, executive_picture=executive_picture,
        sleep_hours=health.get("sleep_hours"),
        primary_challenge=primary_challenge, challenge_reason=challenge_reason,
        disposition=disposition, recommendation_levers=levers,
        backlog_can_wait=has_backlog, ease_load=ease_load,
        deprioritized=deprioritized, tone=tone,
        directive_explanations=directive_explanations,
        reconciliation=reconciliation,
        accomplishments=reported_accomplishments)


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
