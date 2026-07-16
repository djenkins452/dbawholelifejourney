"""
Body Intelligence — measurement interpretation (the ONE deterministic authority).

WLJ Truth architecture, applied top-down:

    Facts establish truth.  →  The Whole-Body Assessment establishes meaning.  →  Each card
    explains how its measurement contributes to that assessment.

`build_body_assessment` computes ONE whole-body executive summary (grade + headline + journey
facts + opportunity) from the complete composition truth (fat / lean / weight, overall + recent).
It is computed ONCE. Every measurement card and the Insights list consume it — nothing on the
page independently invents a different story. **No measurement is "neutral / no goal"**: every
measurement contributes evidence toward the one goal (improving the body); some contribute with
lower confidence, but all participate.

Five states (four colours):

    🟢 Improving        moving the healthy direction over the journey
    🟡 Recovering       still short of the goal overall, but recent momentum is correcting
    🔴 Needs attention  moving away from the goal over the journey
    ⚪ Stable           a confident "no meaningful long-term change"
    ⚪ Inconclusive     not enough history / conflicting signals to conclude

Categories (`MEASUREMENT_CATEGORY`):
  * ``decrease_good`` / ``increase_good`` — direct measures with an intrinsic good direction.
  * ``inferred`` — circumferences (arms/forearms/thighs/calves/chest/shoulders), read against the
    assessment (a limb can be muscle or fat).
  * ``supporting`` — contextual metrics (BMR, body-water) that participate as lower-confidence
    supporting evidence, interpreted against the assessment. Never "no goal".

Inputs are deterministic truth already computed (per-metric history + weight history). NOTE: a
request-path-safe *strength* signal is not yet wired, so evidence uses fat / lean / weight — never
a fabricated "Strength ↑". Rules: ``docs/WLJ_BODY_MEASUREMENT_INTERPRETATION.md``.
"""
from __future__ import annotations

from datetime import date

# ── Categories ──────────────────────────────────────────────────────────────
DECREASE_GOOD = "decrease_good"
INCREASE_GOOD = "increase_good"
INFERRED = "inferred"
SUPPORTING = "supporting"

MEASUREMENT_CATEGORY = {
    "waist": DECREASE_GOOD, "hips": DECREASE_GOOD, "neck": DECREASE_GOOD,
    "body_fat_pct": DECREASE_GOOD, "fat_mass": DECREASE_GOOD, "visceral_fat": DECREASE_GOOD,
    "bmi": DECREASE_GOOD, "metabolic_age": DECREASE_GOOD,
    "lean_mass": INCREASE_GOOD, "skeletal_muscle_mass": INCREASE_GOOD, "bone_mass": INCREASE_GOOD,
    "arm_left": INFERRED, "arm_right": INFERRED, "forearm_left": INFERRED, "forearm_right": INFERRED,
    "thigh_left": INFERRED, "thigh_right": INFERRED, "calf_left": INFERRED, "calf_right": INFERRED,
    "chest": INFERRED, "shoulders": INFERRED,   # circumferences → read against the assessment
    "bmr": SUPPORTING, "body_water_pct": SUPPORTING,  # contextual → supporting evidence
}

# ── Statuses ────────────────────────────────────────────────────────────────
IMPROVING = "improving"
RECOVERING = "recovering"
NEEDS_ATTENTION = "needs_attention"
STABLE = "stable"
INCONCLUSIVE = "inconclusive"

_OVERALL = {"in": 0.3, "lb": 1.0, "pct": 0.4, "%": 0.4, "kcal/day": 30.0, "kcal": 30.0, "": 0.3}
_RECENT = {"in": 0.15, "lb": 0.5, "pct": 0.2, "%": 0.2, "kcal/day": 20.0, "kcal": 20.0, "": 0.15}
_RECENT_WINDOW_DAYS = 35
_LEAN_MEANINGFUL = 1.0
_FAT_MEANINGFUL = 1.0
_BF_MEANINGFUL = 0.4
_LEAN_REBUILD = 0.5


def _thr(table, unit):
    return table.get((unit or "").lower(), table[""])


def _to_date(s):
    try:
        y, m, d = (int(x) for x in str(s).split("-")[:3])
        return date(y, m, d)
    except Exception:
        return None


def analyze_trajectory(points, unit) -> dict | None:
    pts = [p for p in (points or []) if p.get("value") is not None]
    if len(pts) < 2:
        return None
    baseline = pts[0]["value"]
    latest = pts[-1]["value"]
    latest_d = _to_date(pts[-1]["date"])
    recent_ref = pts[-2]["value"]
    if latest_d is not None:
        for p in pts[:-1]:
            pd = _to_date(p["date"])
            if pd is not None and (latest_d - pd).days <= _RECENT_WINDOW_DAYS:
                recent_ref = p["value"]
                break
    first_d = _to_date(pts[0]["date"])
    return {
        "baseline": baseline, "latest": latest,
        "overall": round(latest - baseline, 2),
        "recent": round(latest - recent_ref, 2),
        "n": len(pts),
        "span_days": (latest_d - first_d).days if (latest_d and first_d) else None,
    }


def _fmt(change, unit) -> str:
    if change is None:
        return "—"
    u = f" {unit}" if unit else ""
    if abs(change) < _thr(_RECENT, unit):
        return "Flat"
    return f"{'Down' if change < 0 else 'Up'} {abs(change):.2g}{u}"


def _fact(label, traj, unit) -> str | None:
    if not traj or abs(traj["overall"]) < _thr(_OVERALL, unit):
        return None
    ov = traj["overall"]
    u = f" {unit}" if unit else ""
    return f"{label} {'↓' if ov < 0 else '↑'} {abs(ov):.2g}{u}"


# The ONE canonical executive voice per verdict — coaching narrative (Why), overall
# assessment, and what to focus on next (recommendations). Encouraging tone.
_VERDICT_COPY = {
    "recomposition": {
        "headline": "You're losing fat and building lean mass at the same time — the hardest, most valuable pattern.",
        "narrative": [
            "This is textbook recomposition: fat is coming off while lean mass climbs.",
            "It's the most difficult outcome to achieve, and it means your training and nutrition are dialled in.",
        ],
        "overall": "Your body is moving exactly where you want it to.",
        "focus": ["Keep your training and protein steady — don't change what's working.",
                  "Stay patient; recomposition is slow, but it's the highest-quality result."],
    },
    "recovering": {
        "headline": "You're successfully losing fat while preserving and beginning to rebuild lean mass.",
        "narrative": [
            "You've done the hard work of losing significant fat.",
            "You gave up some lean mass along the way — but your recent measurements show the trend has turned, and you're rebuilding it.",
        ],
        "overall": "Your body is continuing to move in the desired direction.",
        "focus": ["Prioritise protein and resistance training to accelerate lean-mass recovery.",
                  "Keep the fat-loss habits that are clearly working."],
    },
    "fat_loss_preserving": {
        "headline": "You're losing fat while holding on to your lean mass — clean, high-quality fat loss.",
        "narrative": ["What you're losing is almost entirely fat; your lean mass is holding.",
                      "That's exactly what healthy, sustainable fat loss looks like."],
        "overall": "Your body is moving in the desired direction.",
        "focus": ["Add or intensify resistance training to start building lean mass, not just preserving it.",
                  "Keep protein high to protect the muscle you have."],
    },
    "muscle_loss": {
        "headline": "You're losing lean mass over your journey — the part of your body worth protecting.",
        "narrative": ["Your lean mass is below where you started, which usually means the deficit is too aggressive or training/protein is too low.",
                      "This is very fixable, and it's worth addressing now."],
        "overall": "Your body needs attention.",
        "focus": ["Raise protein and add resistance training to protect muscle.",
                  "Consider a smaller calorie deficit so weight loss comes from fat, not muscle."],
    },
    "mixed_gain": {
        "headline": "Both fat and lean mass are rising — a mixed picture.",
        "narrative": ["You're gaining, and right now it's a mix of muscle and fat."],
        "overall": "Your body's direction is mixed.",
        "focus": ["Pick a clear phase — a lean bulk or a cut — so the trend has one direction.",
                  "Tighten nutrition to steer the mix toward muscle."],
    },
    "unclear": {
        "headline": "Your body-composition trend isn't clear yet.",
        "narrative": ["There isn't a strong enough pattern yet to call your direction."],
        "overall": "There isn't enough of a pattern to call your direction yet.",
        "focus": ["Keep logging weight and measurements consistently to sharpen the picture."],
    },
    "insufficient": {
        "headline": "Keep logging to build your assessment.",
        "narrative": ["A few more check-ins will unlock your whole-body story."],
        "overall": "A few more check-ins will unlock your whole-body story.",
        "focus": ["Log weight and body composition over the next few check-ins."],
    },
}


def build_body_assessment(traj_by_metric=None, weight_traj=None) -> dict:
    """The ONE whole-body executive assessment. Computed once; consumed by every card + the
    Insights list. Returns verdict/status/confidence (for cards) plus the executive summary
    (grade, headline, journey facts, overall, opportunity)."""
    t = traj_by_metric or {}
    fat_traj, lean_traj = t.get("fat_mass"), t.get("lean_mass")
    bf_traj, waist_traj = t.get("body_fat_pct"), t.get("waist")

    fat_ov = fat_traj["overall"] if fat_traj else None
    lean_ov = lean_traj["overall"] if lean_traj else None
    lean_rc = lean_traj["recent"] if lean_traj else None
    bf_ov = bf_traj["overall"] if bf_traj else None

    fat_down = (fat_ov is not None and fat_ov <= -_FAT_MEANINGFUL) or (bf_ov is not None and bf_ov <= -_BF_MEANINGFUL)
    fat_up = (fat_ov is not None and fat_ov >= _FAT_MEANINGFUL) or (bf_ov is not None and bf_ov >= _BF_MEANINGFUL)
    big_fat = (fat_ov is not None and fat_ov <= -8.0) or (bf_ov is not None and bf_ov <= -3.0)
    lean_up = lean_ov is not None and lean_ov >= _LEAN_MEANINGFUL
    lean_down = lean_ov is not None and lean_ov <= -_LEAN_MEANINGFUL
    lean_rebuilding = lean_rc is not None and lean_rc >= _LEAN_REBUILD

    if fat_ov is None and lean_ov is None and bf_ov is None:
        verdict, status, conf, summary, ev = "insufficient", INCONCLUSIVE, "low", "not enough body-composition history yet", []
    elif fat_down and lean_up:
        verdict, status, conf = "recomposition", IMPROVING, "high"
        summary = "you're losing fat and building lean mass"
        ev = ["Body fat ↓ over your journey", "Lean mass ↑ over your journey"]
    elif lean_down and lean_rebuilding:
        verdict, status, conf = "recovering", RECOVERING, "high"
        summary = "you lost lean mass earlier but recent readings show you rebuilding it"
        ev = ["Lean mass ↓ over your journey", "Lean mass ↑ recently"]
    elif lean_down:
        verdict, status, conf = "muscle_loss", NEEDS_ATTENTION, "high"
        summary = "your lean mass is below your starting point"
        ev = ["Lean mass ↓ over your journey"]
    elif fat_down:
        verdict, status, conf = "fat_loss_preserving", IMPROVING, "high"
        summary = "you're losing fat while holding lean mass"
        ev = ["Body fat ↓ over your journey", "Lean mass steady"]
    elif fat_up and lean_up:
        verdict, status, conf = "mixed_gain", INCONCLUSIVE, "low"
        summary = "fat and lean are both rising"
        ev = ["Body fat ↑ over your journey", "Lean mass ↑ over your journey"]
    else:
        verdict, status, conf, summary, ev = "unclear", INCONCLUSIVE, "low", "the body-composition trend is mixed so far", []

    # Grade (Overall Progress).
    grade = {
        "recomposition": "Excellent",
        "recovering": "Excellent" if big_fat else "Good",
        "fat_loss_preserving": "Great",
        "muscle_loss": "Needs attention",
        "mixed_gain": "Mixed",
        "unclear": "Building",
        "insufficient": "Getting started",
    }[verdict]

    copy = _VERDICT_COPY[verdict]

    # Journey facts (the evidence — deterministic highlights since baseline).
    facts = []
    for label, traj, unit in (("Weight", weight_traj, "lb"), ("Waist", waist_traj, "in"),
                              ("Fat Mass", fat_traj, "lb")):
        f = _fact(label, traj, unit)
        if f:
            facts.append(f)
    if lean_traj:
        if lean_down and lean_rebuilding:
            facts.append("Lean Mass remains below your starting point but has begun recovering over recent measurements.")
        elif lean_up:
            facts.append(f"Lean Mass ↑ {abs(lean_ov):.2g} lb")
        elif lean_down:
            facts.append(f"Lean Mass ↓ {abs(lean_ov):.2g} lb (needs rebuilding)")

    # What's going well (from the data).
    wins = []
    if big_fat:
        wins.append("Major fat loss")
    elif fat_down:
        wins.append("Fat is trending down")
    if waist_traj and waist_traj["overall"] <= -_thr(_OVERALL, "in"):
        wins.append("Waist is shrinking")
    if lean_up:
        wins.append("Building lean mass")
    elif lean_down and lean_rebuilding:
        wins.append("Lean mass has turned the corner and is rebuilding")

    # Confidence basis (how much history backs the call).
    ref = lean_traj or fat_traj or weight_traj
    if ref and ref.get("n"):
        span = ref.get("span_days")
        basis = f"Based on {ref['n']} check-ins" + (f" over {span} days." if span else ".")
    else:
        basis = "Not enough check-ins yet to be confident."

    return {
        "verdict": verdict, "status": status, "confidence": conf, "confidence_basis": basis,
        "grade": grade, "headline": copy["headline"], "narrative": list(copy["narrative"]),
        "overall": copy["overall"], "focus": list(copy["focus"]),
        "opportunity": copy["focus"][0] if copy["focus"] else "",  # back-compat
        "facts": facts, "wins": wins, "summary": summary, "evidence": ev,
    }


def _base(status, label, unit, traj, evidence, reason, *, confidence="high"):
    return {
        "status": status, "status_label": label, "confidence": confidence,
        "arrow": ("flat" if not traj or abs(traj["overall"]) < _thr(_OVERALL, unit)
                  else ("down" if traj["overall"] < 0 else "up")),
        "overall_text": _fmt(traj["overall"], unit) if traj else "—",
        "recent_text": _fmt(traj["recent"], unit) if traj else "—",
        "evidence": list(evidence), "reason": reason,
    }


def interpret_measurement(metric: str, unit: str, traj: dict | None, assessment: dict | None) -> dict:
    """FACTS (overall/recent) + how this measurement contributes to the ONE assessment."""
    category = MEASUREMENT_CATEGORY.get(metric, SUPPORTING)

    if traj is None:
        return {"status": INCONCLUSIVE, "status_label": "Inconclusive", "arrow": "flat",
                "confidence": "low", "overall_text": "—", "recent_text": "—", "evidence": [],
                "reason": "Keep logging — a few readings are needed to see your trajectory."}

    overall, recent = traj["overall"], traj["recent"]
    ov_thr, rc_thr = _thr(_OVERALL, unit), _thr(_RECENT, unit)
    overall_flat = abs(overall) < ov_thr

    # Direct measures — judged by their own journey; recent momentum adds Recovering.
    if category in (DECREASE_GOOD, INCREASE_GOOD):
        good = -1 if category == DECREASE_GOOD else 1
        if overall_flat:
            return _base(STABLE, "Stable", unit, traj, [], "Stable — no meaningful long-term change.")
        if overall * good > 0:
            if recent * good > 0 and abs(recent) >= rc_thr:
                reason = "Excellent long-term progress — continues moving in the desired direction."
            elif abs(recent) < rc_thr:
                reason = "Strong overall progress; it's plateaued recently — keep going."
            else:
                reason = "Strong overall progress, though it's eased off recently — worth watching."
            return _base(IMPROVING, "Improving", unit, traj, [], reason)
        if recent * good > 0 and abs(recent) >= rc_thr:
            reason = ("Still below your starting point, but recent readings show you rebuilding."
                      if category == INCREASE_GOOD
                      else "Still above your starting point, but recently moving the right way again.")
            return _base(RECOVERING, "Recovering", unit, traj, [], reason)
        return _base(NEEDS_ATTENTION, "Needs attention", unit, traj, [],
                     "Trending away from your goal over your journey — worth attention.")

    # Contextual / circumference — read against the ONE assessment.
    if overall_flat:
        return _base(STABLE, "Stable", unit, traj, [], "Stable — no meaningful long-term change.")

    a = assessment or {}
    astatus = a.get("status", INCONCLUSIVE)
    aconf = a.get("confidence", "low")
    aev = list(a.get("evidence", []))
    asum = a.get("summary", "")
    up = overall > 0

    if category == SUPPORTING:
        if astatus in (IMPROVING, RECOVERING, NEEDS_ATTENTION):
            label = {IMPROVING: "Improving", RECOVERING: "Recovering", NEEDS_ATTENTION: "Needs attention"}[astatus]
            return _base(astatus, label, unit, traj, [],
                         f"Supporting evidence — consistent with your overall progress ({asum}).",
                         confidence="low")
        return _base(INCONCLUSIVE, "Inconclusive", unit, traj, [],
                     "Contributes to your overall picture, but doesn't point a clear direction on its own yet.",
                     confidence="low")

    # INFERRED circumference.
    if aconf == "low" or astatus == INCONCLUSIVE:
        return _base(INCONCLUSIVE, "Inconclusive", unit, traj, aev,
                     "This is changing, but your body's overall direction isn't clear enough yet — keep tracking.",
                     confidence="low")
    if astatus == IMPROVING:
        reason = (f"Growing while {asum} — consistent with muscle development." if up
                  else f"Slimming while {asum} — consistent with fat loss, not muscle loss.")
        return _base(IMPROVING, "Improving", unit, traj, aev, reason, confidence=aconf)
    if astatus == RECOVERING:
        reason = (f"Growing as {asum}." if up else f"Still slimming while {asum} — likely catching up.")
        return _base(RECOVERING, "Recovering", unit, traj, aev, reason, confidence=aconf)
    if astatus == NEEDS_ATTENTION:
        if not up:
            return _base(NEEDS_ATTENTION, "Needs attention", unit, traj, aev,
                         f"Shrinking while {asum} — possible muscle loss.", confidence=aconf)
        return _base(INCONCLUSIVE, "Inconclusive", unit, traj, aev,
                     f"Growing even though {asum} — a mixed signal; keep tracking.", confidence="low")
    return _base(INCONCLUSIVE, "Inconclusive", unit, traj, aev,
                 "Not enough evidence to interpret this yet — keep tracking.", confidence="low")


def build_insights(rows) -> list:
    """One consistent Insights list, generated FROM the interpreted rows so it can never
    contradict a card. Ordered by attention."""
    order = {NEEDS_ATTENTION: 0, RECOVERING: 1, IMPROVING: 2, STABLE: 3, INCONCLUSIVE: 4}
    out = []
    for r in sorted(rows, key=lambda r: (order.get(r.get("status"), 5), r.get("label", ""))):
        ov = r.get("overall_text")
        if not ov or ov == "—":
            continue
        out.append(f'{r["label"]}: {r["status_label"]} — {ov} overall')
    return out
