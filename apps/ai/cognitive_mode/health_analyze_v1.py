"""Health Analyze v1 — question-differentiated, deterministic health reasoning.

Replaces the one-size-fits-all v0 composer. Same hard rule as everything else:
NO LLM, NO invented facts. Every number and every verdict is decided by code.
The improvement over v0 is *differentiation*, not freedom:

  - question type → which signals lead + which reasoning shape
  - ONE ranked signal model (priority order), with a `meaningful` filter that
    stops body-part measurement noise ("Arm Left trending up")
  - time-of-day gating so morning protein=0 is "too early to judge", not "behind"
  - a single highest-leverage lever (not always "increase protein")
  - flowing prose instead of a bullet template

Entry point: build_health_analyze(user, msg_lower) -> str | None
Returns None on insufficient data → caller falls back to v0.
Gated by WLJ_BETH_HEALTH_ANALYZE_V1 (default on).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def analyze_v1_enabled() -> bool:
    try:
        from django.conf import settings
        return bool(getattr(settings, "WLJ_BETH_HEALTH_ANALYZE_V1", True))
    except Exception:
        return True


# ── Question typing ──────────────────────────────────────────────────────

_JUDGMENT_TRIGGERS = (
    "too quickly", "too fast", "losing too", "overtraining",
    "training too much", "overdoing", "pushing too hard", "too hard",
)


def is_health_judgment_request(msg_lower: str) -> bool:
    """Bounded-judgment phrasings ('am I losing too fast', 'overtraining') that
    aren't caught by the generic analyze detector but should reach v1."""
    if not msg_lower:
        return False
    return any(t in msg_lower for t in _JUDGMENT_TRIGGERS)


_CONCERN_TRIGGERS = ("concerns you", "concern you", "worried about", "what worries",
                     "biggest concern", "most concerned", "what concerns")
_ONE_THING_TRIGGERS = ("one thing", "picked one", "pick one", "single most",
                       "if you were me", "what would you do", "most important thing")


def is_health_coaching_request(msg_lower: str) -> bool:
    """Coaching-style phrasings ('what concerns you most', 'if you picked one
    thing') that should route to v1 leverage reasoning."""
    if not msg_lower:
        return False
    return any(t in msg_lower for t in _CONCERN_TRIGGERS + _ONE_THING_TRIGGERS)


def classify_analyze_question(msg_lower: str) -> str:
    m = msg_lower or ""
    if any(t in m for t in ("too quickly", "too fast", "losing too")):
        return "pace_check"
    if any(t in m for t in ("overtraining", "training too much", "overdoing",
                            "pushing too hard", "too hard")):
        return "overtraining"
    if any(t in m for t in _CONCERN_TRIGGERS):
        return "concern"
    if any(t in m for t in _ONE_THING_TRIGGERS):
        return "one_thing"
    if any(t in m for t in ("change anything", "need to change", "do differently",
                            "anything differently", "should i adjust",
                            "be doing differently")):
        return "one_thing"
    if any(t in m for t in ("pattern", "patterns", "notice", "stands out",
                            "noticing")):
        return "patterns"
    if "weight" in m or "losing" in m or "trend" in m or "history" in m:
        return "weight_history"
    if "overall" in m or "my health" in m or "how am i doing" in m or "in general" in m:
        return "overall"
    return "overall"


# ── Time band ────────────────────────────────────────────────────────────

def time_band(user) -> str:
    try:
        from apps.core.utils import get_user_now
        hour = get_user_now(user).hour
    except Exception:
        return "midday"  # safe default — neither suppress nor over-judge
    if hour < 11:
        return "morning"
    if hour < 16:
        return "midday"
    return "evening"


# ── Signal model ─────────────────────────────────────────────────────────

_MEANINGFUL_BC = {
    "waist", "body_fat_pct", "fat_mass", "lean_mass",
    "skeletal_muscle_mass", "visceral_fat",
}


def _state(user, module):
    try:
        from apps.core.ai_state.state_engine import get_module_state
        return get_module_state(user, module) or {}
    except Exception:
        return {}


def build_signals(user, band: str) -> dict:
    """Deterministic ranked signal set. Each value is a dict with at least
    {present, priority}. Missing signals are simply absent."""
    health = _state(user, "health")
    fitness = _state(user, "fitness")
    nutrition = _state(user, "nutrition")
    s = {}

    # 1 — weight trend / velocity. Current weight is read LIVE (latest
    # WeightEntry) to avoid the stale-SAE regression; trend/change stay from SAE.
    try:
        from apps.ai.cognitive_mode.health_truth import get_fresh_weight
        _fw, _fu = get_fresh_weight(user)
    except Exception:
        _fw, _fu = None, None
    w = _fw if _fw is not None else health.get("weight_current")
    if w is not None:
        unit = _fu if _fw is not None else health.get("weight_unit", "lb")
        chg = health.get("weight_change_30d")
        vel_wk = (chg / 30.0 * 7.0) if isinstance(chg, (int, float)) else None
        pct_wk = (abs(vel_wk) / float(w) * 100.0) if vel_wk else None
        s["weight"] = {
            "present": True, "priority": 1,
            "current": float(w), "unit": unit,
            "trend": health.get("weight_trend"), "change_30d": chg,
            "vel_wk": vel_wk, "pct_wk": pct_wk,
        }

    # 2 — glucose
    gs = health.get("glucose_summary") or {}
    avg7 = gs.get("average_7d") or health.get("glucose_avg_7d")
    if gs or avg7 is not None:
        s["glucose"] = {
            "present": True, "priority": 2,
            "trend": gs.get("trend_7d_vs_30d") or "",
            "avg7": avg7, "context": health.get("glucose_context"),
            "tir": gs.get("time_in_range_pct_7d"),
        }

    # 3 / 4 — body composition (waist/body-fat, then lean mass) — meaningful only
    bc = health.get("body_composition") or {}
    delta = bc.get("delta") or {}
    li = bc.get("largest_improvement") or {}
    lr = bc.get("largest_regression") or {}
    for metric, key, prio in (
        ("waist", "waist", 3), ("body_fat_pct", "body_fat", 3),
        ("lean_mass", "lean", 4), ("skeletal_muscle_mass", "lean", 4),
    ):
        d = delta.get(metric)
        if isinstance(d, (int, float)) and abs(d) > 0:
            s.setdefault("bodycomp_" + key, {
                "present": True, "priority": prio, "metric": metric, "delta": d,
            })
    # The single most meaningful body-comp move (for surfacing), filtered to the
    # meaningful set — this is what stops "Arm Left trending up" noise.
    _big = li if li.get("metric") in _MEANINGFUL_BC else (
        lr if lr.get("metric") in _MEANINGFUL_BC else None)
    if _big:
        s["bodycomp_headline"] = {
            "present": True, "priority": 3, "metric": _big.get("metric"),
            "label": _big.get("label"),
        }

    # 5 — workouts (also the resistance-training / muscle-retention proxy)
    wk = fitness.get("workouts_7d")
    if isinstance(wk, int):
        s["workouts"] = {"present": True, "priority": 5, "count": wk,
                         "adherence": fitness.get("workout_adherence_score")}

    # 6 — sleep
    sa = health.get("sleep_avg_hours_7d")
    if sa is not None:
        s["sleep"] = {
            "present": True, "priority": 6, "avg": float(sa),
            "trend": health.get("sleep_trend"),
            "consistency": health.get("sleep_consistency_score"),
        }

    # 7 — nutrition (TIME-GATED)
    pc = nutrition.get("protein_compliance_pct")
    if isinstance(pc, (int, float)):
        s["nutrition"] = {"present": True, "priority": 7,
                          "protein_pct": float(pc), "band": band}

    return s


# ── Verdict helpers (deterministic) ──────────────────────────────────────

def _weight_verdict(weight):
    """sustainable | fast | gaining | flat | None"""
    if not weight:
        return None
    trend = weight.get("trend")
    pct = weight.get("pct_wk")
    if trend == "increasing":
        return "gaining"
    if trend == "decreasing":
        # >1.25%/week of body weight is the "watch" zone; ≤1% is the sustainable
        # target for a 55-yo managing diabetes (protect muscle, avoid rebound).
        if pct is not None and pct > 1.25:
            return "fast"
        return "sustainable"
    return "flat"


def _muscle_proxy(signals):
    """Is muscle likely protected? Uses lean-mass delta if present, else training."""
    lean = signals.get("bodycomp_lean")
    if lean and isinstance(lean.get("delta"), (int, float)):
        return "holding" if lean["delta"] >= -0.3 else "at_risk"
    wk = signals.get("workouts")
    if wk and wk.get("count", 0) >= 2:
        return "training"  # resistance present — reasonable proxy
    return "unknown"


def _nutrition_phrase(signals):
    """Time-gated protein phrase, or None."""
    n = signals.get("nutrition")
    if not n:
        return None
    band = n.get("band")
    pct = n.get("protein_pct")
    if band == "morning":
        return None  # too early to judge — never say "behind" in the morning
    if pct is None:
        return None
    if band == "midday":
        if pct < 60:
            return "protein is pacing behind target so far today"
        return None
    # evening
    if pct < 80:
        return "protein finished under target today"
    return "protein landed on target today"


def leverage_ranked(signals, band):
    """Coach-priority leverage list (highest leverage FIRST). This is NOT
    'lowest score wins' — it's 'what one change creates the biggest downstream
    effect'. When weight loss is going well, muscle preservation leads; nutrition
    refinement is the LAST lever, and only when we can fairly judge it (not
    morning). Returns a list of (rank, phrase, why).
    """
    items = []
    w = signals.get("weight")
    losing_well = bool(
        w and w.get("trend") == "decreasing"
        and (w.get("pct_wk") is None or w["pct_wk"] <= 1.25)
    )

    # 1 — muscle preservation is the top PROTECT during any successful cut (a
    # proactive priority, not a deficit to fix): keep protein + resistance
    # training so the weight that comes off is fat, not muscle.
    if losing_well:
        items.append((
            1,
            "protecting muscle while the weight comes down — consistent protein "
            "plus resistance training",
            "muscle is the thing most at risk while you're losing weight, and "
            "keeping it protects your metabolism and glucose"))
    # 2 — sleep consistency
    sl = signals.get("sleep")
    if sl and (sl.get("trend") == "declining"
               or (sl.get("avg") is not None and sl["avg"] < 7)
               or (isinstance(sl.get("consistency"), (int, float)) and sl["consistency"] < 50)):
        items.append((2, "improving sleep consistency",
                      "sleep is the recovery lever that quietly affects everything else"))
    # 3 — workout consistency
    wk = signals.get("workouts")
    if wk and wk.get("count", 0) <= 1:
        items.append((3, "getting workout frequency back up",
                      "training drives both your weight trend and muscle retention"))
    # 4 — glucose stability
    g = signals.get("glucose")
    if g and g.get("trend") == "worsening":
        items.append((4, "steadying glucose", "glucose drift is worth catching early"))
    # 5 — nutrition refinement (LAST, and only when fairly judgeable)
    n = signals.get("nutrition")
    if band != "morning" and n and n.get("protein_pct") is not None and n["protein_pct"] < 80:
        items.append((5, "making protein more consistent, especially on workout days",
                      "protein supports the muscle you're working to keep"))

    items.sort(key=lambda x: x[0])
    return items


def select_primary_lever(signals, band):
    """The single highest-leverage adjustment phrase, or None."""
    ranked = leverage_ranked(signals, band)
    return ranked[0][1] if ranked else None


# ── Composers (one per question type) — flowing prose, not bullets ───────

def _has_min_data(signals):
    return any(k in signals for k in ("weight", "glucose", "workouts", "sleep"))


def _compose_weight_history(signals):
    w = signals.get("weight")
    if not w:
        return None
    verdict = _weight_verdict(w)
    unit = w["unit"]
    parts = []
    if verdict == "sustainable":
        parts.append("Your weight trend looks sustainable.")
        vel = w.get("vel_wk")
        chg = w.get("change_30d")
        if chg is not None:
            parts.append(
                f"You're steadily trending down ({chg:+.1f} {unit} over 30 days) "
                f"without signs of extreme acceleration, which keeps my concern "
                f"about muscle loss or rebound low.")
        g = signals.get("glucose")
        if g and g.get("trend") == "improving":
            parts.append("Glucose is improving alongside it, which suggests this "
                         "is real change rather than short-term fluctuation.")
        muscle = _muscle_proxy(signals)
        if muscle in ("training", "holding"):
            parts.append("If anything, I'd focus more on protecting muscle "
                         "through protein consistency and resistance training "
                         "than on losing faster.")
    elif verdict == "fast":
        parts.append("Your weight is coming down quickly.")
        chg = w.get("change_30d")
        if chg is not None:
            parts.append(f"That's {chg:+.1f} {unit} over 30 days — meaningful, "
                         f"and worth watching so it stays sustainable.")
        if _muscle_proxy(signals) == "unknown":
            parts.append("My main caution would be protecting muscle: keep "
                         "resistance training and protein steady.")
    elif verdict == "gaining":
        parts.append("Your weight has been trending up recently.")
        chg = w.get("change_30d")
        if chg is not None:
            parts.append(f"That's {chg:+.1f} {unit} over the last 30 days.")
    else:
        parts.append("Your weight has been fairly flat lately.")
    return " ".join(parts)


def _compose_overall(signals):
    if not _has_min_data(signals):
        return None
    parts = []
    w = signals.get("weight")
    g = signals.get("glucose")
    momentum = []
    if w and w.get("trend") == "decreasing":
        momentum.append("weight")
    if g and g.get("trend") == "improving":
        momentum.append("glucose")
    wk = signals.get("workouts")
    if wk and wk.get("count", 0) >= 3:
        momentum.append("workout consistency")
    if momentum:
        joined = ", ".join(momentum[:-1]) + (" and " + momentum[-1] if len(momentum) > 1 else momentum[0])
        parts.append(f"Overall, you're moving in a positive direction — {joined} "
                     f"{'are' if len(momentum) > 1 else 'is'} improving.")
    else:
        parts.append("Overall, your health signals are holding steady right now.")
    # The opportunity (recovery/consistency, not effort)
    opp = []
    sl = signals.get("sleep")
    if sl and sl.get("avg") is not None and sl["avg"] < 7:
        opp.append("sleep is still slightly below target")
    n = signals.get("nutrition")
    if n and n.get("band") != "morning" and n.get("protein_pct") is not None and n["protein_pct"] < 80:
        opp.append("nutrition tends to vary more than your training")
    if opp:
        parts.append("The biggest opportunity I see isn't effort — it's recovery "
                     "and consistency: " + " and ".join(opp) + ".")
    parts.append("I don't think you need dramatic changes right now — mostly "
                 "tightening consistency.")
    return " ".join(parts)


def _compose_patterns(signals):
    if not _has_min_data(signals):
        return None
    parts = []
    wk = signals.get("workouts")
    g = signals.get("glucose")
    if wk and g and wk.get("count", 0) >= 3 and g.get("trend") in ("improving", "stable"):
        parts.append("A pattern I notice is that when your workouts stay "
                     "consistent, glucose tends to hold steadier and weight "
                     "momentum improves.")
    w = signals.get("weight")
    if w and w.get("trend") == "decreasing":
        parts.append("Your downward weight trend has been steady rather than "
                     "jumpy, which usually signals a sustainable pattern.")
    sl = signals.get("sleep")
    if sl and (sl.get("trend") == "declining" or
               (sl.get("avg") is not None and sl["avg"] < 7)):
        parts.append("The weakest recurring lever still looks like sleep — it "
                     "lags the other areas more often than not.")
    if not parts:
        return None
    return " ".join(parts)


def _compose_one_thing(signals, band):
    """'If you picked one thing' / 'do I need to change anything' — leads with the
    highest-leverage lever (not lowest metric), and respects time of day."""
    if not _has_min_data(signals):
        return None
    ranked = leverage_ranked(signals, band)
    parts = []
    if band == "morning":
        parts.append("This early in the day, I'm less worried about nutrition "
                     "compliance — you've got the whole day ahead.")
    if not ranked:
        parts.append("I wouldn't change anything major right now — it's more "
                     "about staying consistent than making a correction.")
        return " ".join(parts)
    parts.append(f"If I picked one thing, I'd focus on {ranked[0][1]} — that's "
                 f"the highest-leverage move I see. Everything else is more "
                 f"refinement than a real correction.")
    return " ".join(parts)


def _compose_concern(signals, band):
    """'What concerns you most?' — prioritizes the highest-leverage PROTECT, with
    encouragement when the overall trend is positive. NOT 'lowest metric wins'."""
    if not _has_min_data(signals):
        return None
    w = signals.get("weight")
    g = signals.get("glucose")
    positive = (w and w.get("trend") == "decreasing") or (g and g.get("trend") == "improving")
    ranked = leverage_ranked(signals, band)
    parts = []
    if positive:
        parts.append("Honestly, I'm more encouraged than concerned right now — "
                     "your trend is working.")
    if ranked:
        top = ranked[0]
        parts.append(f"The one thing I'd protect most is {top[1]}, because {top[2]}.")
    else:
        parts.append("Nothing really stands out as a concern — it's mostly about "
                     "staying consistent.")
    if positive:
        parts.append("I wouldn't try to lose faster; the pace is working.")
    return " ".join(parts)


def _compose_pace_check(signals):
    w = signals.get("weight")
    if not w:
        return None
    verdict = _weight_verdict(w)
    if verdict in ("sustainable", "flat"):
        parts = ["No, I don't think you're losing too quickly."]
        g = signals.get("glucose")
        reassure = []
        if _muscle_proxy(signals) in ("training", "holding"):
            reassure.append("you're still training")
        if g and g.get("context") in ("Normal", "Stable") or (g and g.get("trend") == "improving"):
            reassure.append("glucose looks stable")
        if reassure:
            parts.append("The pace looks meaningful but still sustainable, "
                         "especially since " + " and ".join(reassure) + ".")
        parts.append("My bigger focus would be protecting muscle mass rather "
                     "than slowing down.")
        return " ".join(parts)
    if verdict == "fast":
        parts = ["Your pace is on the faster side, so it's worth keeping an eye on."]
        if _muscle_proxy(signals) == "unknown":
            parts.append("I'd want to make sure resistance training and protein "
                         "stay steady so the loss is fat, not muscle.")
        return " ".join(parts)
    return None


def _compose_overtraining(signals):
    wk = signals.get("workouts")
    sl = signals.get("sleep")
    if not wk and not sl:
        return None
    flags = []
    if wk and wk.get("count", 0) >= 6:
        flags.append("training volume is high this week")
    if sl and (sl.get("trend") == "declining" or
               (sl.get("avg") is not None and sl["avg"] < 6.5)):
        flags.append("sleep and recovery are lagging")
    if len(flags) >= 2:
        return ("There are a couple of early signs worth watching: "
                + " and ".join(flags) + ". I'd protect recovery — keep sleep up "
                "and consider an easier day before adding more load.")
    if wk and wk.get("count", 0) <= 4:
        return ("I don't see signs of overtraining — your frequency is "
                "reasonable and recovery looks okay. You've got room if you want it.")
    return ("Training load looks manageable. Keep an eye on sleep and energy — "
            "those are the first things to dip if you're overdoing it.")


_COMPOSERS = {
    "weight_history": lambda s, b: _compose_weight_history(s),
    "overall": lambda s, b: _compose_overall(s),
    "patterns": lambda s, b: _compose_patterns(s),
    "one_thing": lambda s, b: _compose_one_thing(s, b),
    "concern": lambda s, b: _compose_concern(s, b),
    "pace_check": lambda s, b: _compose_pace_check(s),
    "overtraining": lambda s, b: _compose_overtraining(s),
}


# ── Conversational continuity (bounded, cache-based, TTL = current thread) ──
# When a health analysis is produced we stash a tiny context object keyed by
# conversation id. Follow-ups ("why?", "tell me more", "what would you do?")
# inherit it instead of re-running from scratch. No model, no migration; the
# 30-min TTL + conversation-scoped key keeps it strictly bounded.

_FOLLOWUP_PHRASES = (
    "tell me more", "go deeper", "what do you mean", "what would you do",
    "if you were me", "explain that", "expand on that", "why do you think",
    "say more", "go on",
)
_BARE_FOLLOWUPS = {
    "why", "and", "so", "more", "deeper", "explain", "elaborate", "expand",
    "why is that", "why that", "go deeper", "tell me more", "why do you think that",
}


def is_health_followup(msg_lower: str) -> bool:
    """A short continuation of the current health thread. Bare 'why' only counts
    on a short message, to avoid hijacking unrelated questions."""
    m = (msg_lower or "").strip()
    if not m:
        return False
    bare = m.rstrip("?.! ")
    if len(m.split()) <= 5 and bare in _BARE_FOLLOWUPS:
        return True
    return any(p in m for p in _FOLLOWUP_PHRASES)


def continuity_enabled() -> bool:
    try:
        from django.conf import settings
        return bool(getattr(settings, "WLJ_BETH_HEALTH_CONTINUITY", True))
    except Exception:
        return True


def _ctx_key(conversation):
    cid = getattr(conversation, "id", None)
    return f"beth:hctx:{cid}" if cid else None


def store_health_context(conversation, qtype, signals, band):
    if not continuity_enabled():
        return
    try:
        from django.core.cache import cache
        key = _ctx_key(conversation)
        if not key:
            return
        ranked = leverage_ranked(signals, band)
        w = signals.get("weight")
        cache.set(key, {
            "qtype": qtype,
            "verdict": _weight_verdict(w),
            "top_lever": ranked[0] if ranked else None,
            "next_lever": ranked[1] if len(ranked) > 1 else None,
            "positive": bool(w and w.get("trend") == "decreasing"),
        }, 1800)
    except Exception:
        logger.debug("store_health_context failed", exc_info=True)


def get_health_context(conversation):
    if not continuity_enabled():
        return None
    try:
        from django.core.cache import cache
        key = _ctx_key(conversation)
        return cache.get(key) if key else None
    except Exception:
        return None


def build_deepen(user, msg_lower, conversation) -> str | None:
    """Continue the active health thread for a follow-up. None if no context."""
    ctx = get_health_context(conversation)
    if not ctx:
        return None
    m = msg_lower or ""
    top = ctx.get("top_lever")  # (rank, phrase, why)
    if "what would you do" in m or "if you were me" in m:
        if top:
            return f"If I were you, I'd focus on {top[1]}. {top[2][:1].upper()}{top[2][1:]}."
        return ("If I were you, I'd mostly keep doing what's working — the trend "
                "is fine, so consistency matters more than changes.")
    bare = m.strip().rstrip("?.! ")
    if bare in ("why", "why is that", "why that", "why do you think that") or \
            "why do you think" in m or "what do you mean" in m:
        if top:
            return (f"{top[2][:1].upper()}{top[2][1:]}. That's why I'd put "
                    f"{top[1]} ahead of fine-tuning anything else right now.")
        return ("Mostly because your trend is already working — there's no urgent "
                "problem to fix, so consistency matters more than changes.")
    # tell me more / go deeper / expand
    parts = []
    if top:
        parts.append(f"The main thing is {top[1]} — {top[2]}.")
    nxt = ctx.get("next_lever")
    if nxt:
        parts.append(f"After that, the next lever would be {nxt[1]}.")
    return " ".join(parts) if parts else None


def build_health_analyze(user, msg_lower, conversation=None) -> str | None:
    """Question-differentiated deterministic health analysis. None → fall back.
    Stores thread context (for follow-ups) when a conversation is provided."""
    if not analyze_v1_enabled():
        return None
    try:
        qtype = classify_analyze_question(msg_lower or "")
        band = time_band(user)
        signals = build_signals(user, band)
        if not _has_min_data(signals):
            return None
        composer = _COMPOSERS.get(qtype, _COMPOSERS["overall"])
        resp = composer(signals, band)
        if resp and conversation is not None:
            store_health_context(conversation, qtype, signals, band)
        return resp
    except Exception:
        logger.warning("build_health_analyze v1 failed — falling back", exc_info=True)
        return None
