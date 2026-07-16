"""
Body Intelligence — measurement interpretation (the ONE deterministic authority).

This reads the **whole journey**, not a single week. For each measurement it asks:

    "What direction has this body part been moving since the start of this journey,
     and does that align with the rest of the body?"

It uses the full per-metric history (baseline = the first logged reading) plus rolling
recent momentum, and the whole-journey body-composition trends (fat / lean / weight) — so
it describes the long-term story like a body coach, and does NOT react to one week's noise.

Four states (three colours):

    🟢 Improving        moving the healthy direction over the journey
    🔴 Needs attention  moving away from the goal over the journey
    ⚪ Stable           a confident "no meaningful long-term change"
    ⚪ Inconclusive     not enough history / conflicting signals to conclude

Each card surfaces the *evidence* — Overall trend, Recent trend, and (for limbs) the
body-composition context — plus a plain-English interpretation, so the user sees the story
AND the reasoning.

Categories (`MEASUREMENT_CATEGORY`):
  * ``decrease_good`` / ``increase_good`` — direct measures; judged by their own journey.
  * ``inferred`` — limb circumferences; a limb change is read against the body's journey
    (a bigger limb while gaining lean = muscle; a smaller limb while losing fat = fat loss;
    a smaller limb while LOSING lean = muscle loss). A limb flat over the journey = Stable.
  * ``neutral`` — no directional health goal (tracked, never judged).

All inputs are deterministic truth already computed elsewhere (the per-metric history series
+ weight history). This module only INTERPRETS. NOTE: a request-path-safe *strength* signal
is not yet wired, so evidence is built from fat / lean / weight (which directly measure
muscle-vs-fat) — never a fabricated "Strength ↑".

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
NEEDS_ATTENTION = "needs_attention"  # red
STABLE = "stable"                 # gray — confident "no meaningful long-term change"
INCONCLUSIVE = "inconclusive"     # gray — not enough history / conflicting

# Meaningful-change thresholds by unit — OVERALL (whole journey) and RECENT (rolling).
# Overall thresholds are larger so single-week noise never sets the long-term story.
_OVERALL = {"in": 0.3, "lb": 1.0, "pct": 0.4, "kcal/day": 30.0, "kcal": 30.0, "": 0.3}
_RECENT = {"in": 0.15, "lb": 0.5, "pct": 0.2, "kcal/day": 20.0, "kcal": 20.0, "": 0.15}
_RECENT_WINDOW_DAYS = 35


def _thr(table, unit):
    return table.get((unit or "").lower(), table[""])


def _to_date(s):
    try:
        y, m, d = (int(x) for x in str(s).split("-")[:3])
        return date(y, m, d)
    except Exception:
        return None


def analyze_trajectory(points, unit) -> dict | None:
    """From a full ``[{date, value}]`` history: overall change (baseline→latest), rolling
    recent change, and span. Deterministic. Returns None with <2 real readings.

    ``points`` must be chronological (oldest first). Baseline is the FIRST reading — the
    start of the journey — unless there's a compelling reason otherwise (there isn't).
    """
    pts = [p for p in (points or []) if p.get("value") is not None]
    if len(pts) < 2:
        return None
    baseline = pts[0]["value"]
    latest = pts[-1]["value"]
    latest_d = _to_date(pts[-1]["date"])
    # Recent reference: the earliest reading within the rolling window (falls back to the
    # immediately-prior reading if the window has only the latest point).
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
    """'Down 6.2 in' / 'Up 0.4 in' / 'Flat' — direction word + magnitude."""
    if change is None:
        return "—"
    thr = _thr(_RECENT, unit)
    u = f" {unit}" if unit else ""
    if abs(change) < thr:
        return "Flat"
    word = "Down" if change < 0 else "Up"
    return f"{word} {abs(change):.2g}{u}"


def classify_body_journey(fat_traj=None, lean_traj=None, weight_traj=None, bf_traj=None) -> dict:
    """The body's OVERALL trajectory (whole journey), used to interpret limb changes.

    Returns ``{status, confidence, evidence, summary}``. Decisive because a whole-journey
    signal is far less noisy than one week. Reuses the fat/lean/weight history — no new
    queries.
    """
    fat_ov = fat_traj["overall"] if fat_traj else None
    lean_ov = lean_traj["overall"] if lean_traj else None
    bf_ov = bf_traj["overall"] if bf_traj else None

    if fat_ov is None and lean_ov is None and bf_ov is None:
        return {"status": INCONCLUSIVE, "confidence": "low", "evidence": [],
                "summary": "Not enough body-composition history yet to interpret limb changes."}

    fat_down = (fat_ov is not None and fat_ov <= -1.0) or (bf_ov is not None and bf_ov <= -0.4)
    fat_up = (fat_ov is not None and fat_ov >= 1.0) or (bf_ov is not None and bf_ov >= 0.4)
    lean_up = lean_ov is not None and lean_ov >= 1.0
    lean_down = lean_ov is not None and lean_ov <= -1.0

    if lean_down:
        ev = ["Lean mass ↓ over your journey"]
        return {"status": NEEDS_ATTENTION, "confidence": "high", "evidence": ev,
                "summary": "lean mass has fallen over your journey"}
    if fat_down and lean_up:
        return {"status": IMPROVING, "confidence": "high",
                "evidence": ["Body fat ↓ over your journey", "Lean mass ↑ over your journey"],
                "summary": "you're losing fat and building muscle"}
    if fat_down:
        return {"status": IMPROVING, "confidence": "high",
                "evidence": ["Body fat ↓ over your journey", "Lean mass steady"],
                "summary": "you're losing fat while holding muscle"}
    if fat_up and lean_up:
        return {"status": INCONCLUSIVE, "confidence": "low",
                "evidence": ["Body fat ↑ over your journey", "Lean mass ↑ over your journey"],
                "summary": "fat and lean are both rising — the body's direction is mixed"}
    return {"status": INCONCLUSIVE, "confidence": "low", "evidence": [],
            "summary": "the body-composition trend is unclear so far"}


def _base(status, label, unit, traj, evidence, reason, *, confidence="high"):
    """Assemble the row-level result, with Overall/Recent trend text from the trajectory."""
    overall_text = _fmt(traj["overall"], unit) if traj else "—"
    recent_text = _fmt(traj["recent"], unit) if traj else "—"
    arrow = "flat"
    if traj and abs(traj["overall"]) >= _thr(_OVERALL, unit):
        arrow = "down" if traj["overall"] < 0 else "up"
    return {
        "status": status, "status_label": label, "arrow": arrow,
        "confidence": confidence,
        "overall_text": overall_text, "recent_text": recent_text,
        "evidence": list(evidence), "reason": reason,
    }


def interpret_measurement(metric: str, unit: str, traj: dict | None, body_journey: dict | None) -> dict:
    """Interpret one measurement's whole-journey trajectory.

    Returns ``{status, status_label, arrow, confidence, overall_text, recent_text,
    evidence, reason}``. Status is driven by the OVERALL trend (noise-resistant); the
    narrative reflects recent momentum (continuing / plateaued / reversing).
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

    # Neutral — tracked, never judged (but the journey trend is still shown).
    if category == NEUTRAL:
        label = "Stable" if overall_flat else "Tracked"
        return _base(STABLE if overall_flat else INCONCLUSIVE, label, unit, traj, [],
                     "No health goal for this measurement — shown for your reference.")

    # Direct measures — judged by the journey; narrative from recent momentum.
    if category in (DECREASE_GOOD, INCREASE_GOOD):
        good = -1 if category == DECREASE_GOOD else 1
        toward = overall * good > 0
        if overall_flat:
            return _base(STABLE, "Stable", unit, traj, [],
                         "Stable — no meaningful long-term change.")
        if toward:
            # Improving over the journey; describe recent momentum.
            if recent * good > 0 and abs(recent) >= rc_thr:
                reason = "Excellent progress — continues moving in the desired direction."
            elif abs(recent) < rc_thr:
                reason = "Strong overall progress; it's plateaued recently — keep going."
            else:
                reason = "Strong overall progress, though it's ticked the wrong way recently — worth watching."
            return _base(IMPROVING, "Improving", unit, traj, [], reason)
        # Moving away from the goal over the journey.
        reason = "Trending away from your goal over your journey — worth attention."
        return _base(NEEDS_ATTENTION, "Needs attention", unit, traj, [], reason)

    # INFERRED (limb) — read the limb's journey against the body's journey.
    if overall_flat:
        return _base(STABLE, "Stable", unit, traj, [],
                     "Stable — no meaningful long-term change.")

    bj = body_journey or {}
    bstatus = bj.get("status", INCONCLUSIVE)
    bconf = bj.get("confidence", "low")
    bev = list(bj.get("evidence", []))
    bsummary = bj.get("summary", "")
    limb_up = overall > 0

    if bconf == "low" or bstatus == INCONCLUSIVE:
        return _base(INCONCLUSIVE, "Inconclusive", unit, traj, bev,
                     "This limb is changing, but the body's overall direction isn't clear enough yet — keep tracking.",
                     confidence="low")

    if bstatus == IMPROVING:
        if limb_up:
            reason = f"Growing while {bsummary} — consistent with muscle development."
        else:
            reason = f"Smaller while {bsummary} — consistent with fat loss, not muscle loss."
        return _base(IMPROVING, "Improving", unit, traj, bev, reason, confidence=bconf)

    if bstatus == NEEDS_ATTENTION:
        if not limb_up:
            reason = f"Shrinking while {bsummary} — possible muscle loss."
            return _base(NEEDS_ATTENTION, "Needs attention", unit, traj, bev, reason, confidence=bconf)
        # Limb up while the body is losing lean — mixed; don't over-claim.
        return _base(INCONCLUSIVE, "Inconclusive", unit, traj, bev,
                     f"Growing even though {bsummary} — a mixed signal; keep tracking.",
                     confidence="low")

    return _base(INCONCLUSIVE, "Inconclusive", unit, traj, bev,
                 "Not enough evidence to interpret this limb yet — keep tracking.", confidence="low")
