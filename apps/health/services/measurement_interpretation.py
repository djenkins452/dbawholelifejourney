"""
Body Intelligence — measurement interpretation (the ONE deterministic authority).

WLJ Truth architecture: **facts establish truth; interpretation explains truth.** This module
NEVER competes with the facts — it reads the deterministic per-metric history (Current, Overall
trend since the first reading, Recent momentum) and explains it.

Interpretation is **holistic**: `build_body_assessment` produces ONE whole-body verdict from the
complete composition truth (fat / lean / weight, overall + recent), and every card's interpretation
is generated from that single assessment. So no card independently infers a conclusion that
conflicts with another — the whole page tells one story.

Five states (four colours):

    🟢 Improving        moving the healthy direction over the journey
    🟡 Recovering       still short of the goal overall, but recent momentum is correcting
    🔴 Needs attention  moving away from the goal over the journey
    ⚪ Stable           a confident "no meaningful long-term change"
    ⚪ Inconclusive     not enough history / conflicting signals to conclude

Status is driven by the OVERALL trend (noise-resistant); the narrative reflects recent momentum
(continuing / plateaued / recovering). The interpretation must never contradict the facts above it.

Categories (`MEASUREMENT_CATEGORY`): ``decrease_good`` / ``increase_good`` (direct measures, judged
by their own journey), ``inferred`` (limbs — read against the body assessment), ``neutral`` (no goal).

Inputs are deterministic truth already computed (per-metric history + weight history). NOTE: a
request-path-safe *strength* signal is not yet wired, so evidence uses fat / lean / weight (which
directly measure muscle-vs-fat) — never a fabricated "Strength ↑".

Rules documented in ``docs/WLJ_BODY_MEASUREMENT_INTERPRETATION.md``.
"""
from __future__ import annotations

from datetime import date

# ── Categories ──────────────────────────────────────────────────────────────
DECREASE_GOOD = "decrease_good"
INCREASE_GOOD = "increase_good"
INFERRED = "inferred"
NEUTRAL = "neutral"

MEASUREMENT_CATEGORY = {
    "waist": DECREASE_GOOD, "hips": DECREASE_GOOD, "neck": DECREASE_GOOD,
    "body_fat_pct": DECREASE_GOOD, "fat_mass": DECREASE_GOOD, "visceral_fat": DECREASE_GOOD,
    "bmi": DECREASE_GOOD, "metabolic_age": DECREASE_GOOD,
    "lean_mass": INCREASE_GOOD, "skeletal_muscle_mass": INCREASE_GOOD, "bone_mass": INCREASE_GOOD,
    "arm_left": INFERRED, "arm_right": INFERRED, "forearm_left": INFERRED, "forearm_right": INFERRED,
    "thigh_left": INFERRED, "thigh_right": INFERRED, "calf_left": INFERRED, "calf_right": INFERRED,
    "chest": NEUTRAL, "shoulders": NEUTRAL, "body_water_pct": NEUTRAL, "bmr": NEUTRAL,
}

# ── Statuses ────────────────────────────────────────────────────────────────
IMPROVING = "improving"           # green
RECOVERING = "recovering"         # amber — behind overall, but correcting recently
NEEDS_ATTENTION = "needs_attention"  # red
STABLE = "stable"                 # gray — confident "no meaningful long-term change"
INCONCLUSIVE = "inconclusive"     # gray — not enough history / conflicting

_OVERALL = {"in": 0.3, "lb": 1.0, "pct": 0.4, "kcal/day": 30.0, "kcal": 30.0, "": 0.3}
_RECENT = {"in": 0.15, "lb": 0.5, "pct": 0.2, "kcal/day": 20.0, "kcal": 20.0, "": 0.15}
_RECENT_WINDOW_DAYS = 35
_LEAN_MEANINGFUL = 1.0
_FAT_MEANINGFUL = 1.0
_BF_MEANINGFUL = 0.4
_LEAN_REBUILD = 0.5  # recent lean gain (lb) that reads as "rebuilding"


def _thr(table, unit):
    return table.get((unit or "").lower(), table[""])


def _to_date(s):
    try:
        y, m, d = (int(x) for x in str(s).split("-")[:3])
        return date(y, m, d)
    except Exception:
        return None


def analyze_trajectory(points, unit) -> dict | None:
    """From a full ``[{date, value}]`` history: overall change (baseline→latest, the start of
    the journey), rolling recent change, and span. None with <2 real readings."""
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
    span = (latest_d - first_d).days if (latest_d and first_d) else None
    return {
        "baseline": baseline, "latest": latest,
        "overall": round(latest - baseline, 2),
        "recent": round(latest - recent_ref, 2),
        "n": len(pts), "span_days": span,
    }


def _fmt(change, unit) -> str:
    """'Down 6.2 in' / 'Up 0.4 in' / 'Flat'."""
    if change is None:
        return "—"
    thr = _thr(_RECENT, unit)
    u = f" {unit}" if unit else ""
    if abs(change) < thr:
        return "Flat"
    return f"{'Down' if change < 0 else 'Up'} {abs(change):.2g}{u}"


def build_body_assessment(fat_traj=None, lean_traj=None, weight_traj=None, bf_traj=None) -> dict:
    """The ONE whole-body assessment (overall + recent), from which every limb card's
    interpretation is generated. Considers RECENT momentum, so lean below baseline but
    rebuilding reads as **Recovering**, not muscle loss.

    Returns ``{verdict, status, confidence, evidence, summary}``.
    """
    fat_ov = fat_traj["overall"] if fat_traj else None
    lean_ov = lean_traj["overall"] if lean_traj else None
    lean_rc = lean_traj["recent"] if lean_traj else None
    bf_ov = bf_traj["overall"] if bf_traj else None

    if fat_ov is None and lean_ov is None and bf_ov is None:
        return {"verdict": "insufficient", "status": INCONCLUSIVE, "confidence": "low",
                "evidence": [], "summary": "not enough body-composition history yet"}

    fat_down = (fat_ov is not None and fat_ov <= -_FAT_MEANINGFUL) or (bf_ov is not None and bf_ov <= -_BF_MEANINGFUL)
    fat_up = (fat_ov is not None and fat_ov >= _FAT_MEANINGFUL) or (bf_ov is not None and bf_ov >= _BF_MEANINGFUL)
    lean_up = lean_ov is not None and lean_ov >= _LEAN_MEANINGFUL
    lean_down = lean_ov is not None and lean_ov <= -_LEAN_MEANINGFUL
    lean_rebuilding = lean_rc is not None and lean_rc >= _LEAN_REBUILD

    if fat_down and lean_up:
        return {"verdict": "recomposition", "status": IMPROVING, "confidence": "high",
                "evidence": ["Body fat ↓ over your journey", "Lean mass ↑ over your journey"],
                "summary": "you're losing fat and building lean mass"}
    if lean_down and lean_rebuilding:
        return {"verdict": "recovering", "status": RECOVERING, "confidence": "high",
                "evidence": ["Lean mass ↓ over your journey", "Lean mass ↑ recently"],
                "summary": "you lost lean mass earlier but recent readings show you rebuilding it"}
    if lean_down:
        return {"verdict": "muscle_loss", "status": NEEDS_ATTENTION, "confidence": "high",
                "evidence": ["Lean mass ↓ over your journey"],
                "summary": "your lean mass is below your starting point"}
    if fat_down:
        return {"verdict": "fat_loss_preserving", "status": IMPROVING, "confidence": "high",
                "evidence": ["Body fat ↓ over your journey", "Lean mass steady"],
                "summary": "you're losing fat while holding lean mass"}
    if fat_up and lean_up:
        return {"verdict": "mixed_gain", "status": INCONCLUSIVE, "confidence": "low",
                "evidence": ["Body fat ↑ over your journey", "Lean mass ↑ over your journey"],
                "summary": "fat and lean are both rising — the body's direction is mixed"}
    return {"verdict": "unclear", "status": INCONCLUSIVE, "confidence": "low", "evidence": [],
            "summary": "the body-composition trend is mixed so far"}


def _base(status, label, unit, traj, evidence, reason, *, confidence="high"):
    """Assemble the row result: FACTS (Overall/Recent trend text) + INTERPRETATION."""
    return {
        "status": status, "status_label": label, "confidence": confidence,
        "arrow": ("flat" if not traj or abs(traj["overall"]) < _thr(_OVERALL, unit)
                  else ("down" if traj["overall"] < 0 else "up")),
        "overall_text": _fmt(traj["overall"], unit) if traj else "—",
        "recent_text": _fmt(traj["recent"], unit) if traj else "—",
        "evidence": list(evidence), "reason": reason,
    }


def interpret_measurement(metric: str, unit: str, traj: dict | None, assessment: dict | None) -> dict:
    """Interpret one measurement's whole-journey trajectory from the holistic assessment.

    Returns FACTS (``overall_text``, ``recent_text``, ``arrow``) + INTERPRETATION
    (``status``, ``status_label``, ``evidence``, ``reason``, ``confidence``). The
    interpretation never contradicts the facts.
    """
    category = MEASUREMENT_CATEGORY.get(metric, NEUTRAL)

    if traj is None:
        return {"status": INCONCLUSIVE, "status_label": "Inconclusive", "arrow": "flat",
                "confidence": "low", "overall_text": "—", "recent_text": "—", "evidence": [],
                "reason": "Keep logging — a few readings are needed to see your trajectory."}

    overall = traj["overall"]
    recent = traj["recent"]
    ov_thr = _thr(_OVERALL, unit)
    rc_thr = _thr(_RECENT, unit)
    overall_flat = abs(overall) < ov_thr

    # Neutral — tracked, never judged.
    if category == NEUTRAL:
        if overall_flat:
            return _base(STABLE, "Stable", unit, traj, [], "Stable — no meaningful long-term change.")
        return _base(INCONCLUSIVE, "Tracked", unit, traj, [],
                     "No health goal for this measurement — shown for your reference.")

    # Direct measures — judged by their own journey; recent momentum adds Recovering.
    if category in (DECREASE_GOOD, INCREASE_GOOD):
        good = -1 if category == DECREASE_GOOD else 1
        if overall_flat:
            return _base(STABLE, "Stable", unit, traj, [], "Stable — no meaningful long-term change.")
        if overall * good > 0:  # overall toward the goal
            if recent * good > 0 and abs(recent) >= rc_thr:
                reason = "Excellent long-term progress — continues moving in the desired direction."
            elif abs(recent) < rc_thr:
                reason = "Strong overall progress; it's plateaued recently — keep going."
            else:
                reason = "Strong overall progress, though it's eased off recently — worth watching."
            return _base(IMPROVING, "Improving", unit, traj, [], reason)
        # Overall on the wrong side of baseline.
        if recent * good > 0 and abs(recent) >= rc_thr:  # recent is correcting
            if category == INCREASE_GOOD:
                reason = "Still below your starting point, but recent readings show you rebuilding."
            else:
                reason = "Still above your starting point, but recently moving the right way again."
            return _base(RECOVERING, "Recovering", unit, traj, [], reason)
        return _base(NEEDS_ATTENTION, "Needs attention", unit, traj, [],
                     "Trending away from your goal over your journey — worth attention.")

    # INFERRED (limb) — read the limb's journey against the ONE body assessment.
    if overall_flat:
        return _base(STABLE, "Stable", unit, traj, [], "Stable — no meaningful long-term change.")

    a = assessment or {}
    astatus = a.get("status", INCONCLUSIVE)
    aconf = a.get("confidence", "low")
    aev = list(a.get("evidence", []))
    asum = a.get("summary", "")
    limb_up = overall > 0

    if aconf == "low" or astatus == INCONCLUSIVE:
        return _base(INCONCLUSIVE, "Inconclusive", unit, traj, aev,
                     "This limb is changing, but your body's overall direction isn't clear enough yet — keep tracking.",
                     confidence="low")
    if astatus == IMPROVING:
        reason = (f"Growing while {asum} — consistent with muscle development." if limb_up
                  else f"Slimming while {asum} — consistent with fat loss, not muscle loss.")
        return _base(IMPROVING, "Improving", unit, traj, aev, reason, confidence=aconf)
    if astatus == RECOVERING:
        reason = (f"Growing as {asum}." if limb_up
                  else f"Still slimming while {asum} — likely catching up.")
        return _base(RECOVERING, "Recovering", unit, traj, aev, reason, confidence=aconf)
    if astatus == NEEDS_ATTENTION:
        if not limb_up:
            return _base(NEEDS_ATTENTION, "Needs attention", unit, traj, aev,
                         f"Shrinking while {asum} — possible muscle loss.", confidence=aconf)
        return _base(INCONCLUSIVE, "Inconclusive", unit, traj, aev,
                     f"Growing even though {asum} — a mixed signal; keep tracking.", confidence="low")
    return _base(INCONCLUSIVE, "Inconclusive", unit, traj, aev,
                 "Not enough evidence to interpret this limb yet — keep tracking.", confidence="low")


def build_insights(rows) -> list:
    """One consistent Insights list, generated FROM the interpreted rows so it can never
    contradict a card. Ordered by attention (needs attention → recovering → improving →
    stable), then label."""
    order = {NEEDS_ATTENTION: 0, RECOVERING: 1, IMPROVING: 2, STABLE: 3, INCONCLUSIVE: 4}
    out = []
    for r in sorted(rows, key=lambda r: (order.get(r.get("status"), 5), r.get("label", ""))):
        ov = r.get("overall_text")
        if not ov or ov == "—":
            continue
        out.append(f'{r["label"]}: {r["status_label"]} — {ov} overall')
    return out
