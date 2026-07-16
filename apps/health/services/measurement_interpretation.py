"""
Body Intelligence — measurement interpretation (the ONE deterministic authority).

Answers, per body measurement: **"What is this change most likely telling me?"** — and
explains WHY. Three states only:

    🟢 Improving         movement in the healthy direction
    🔴 Needs attention   movement away from the goal
    ⚪ Inconclusive       the deterministic signals do not support a confident conclusion

We deliberately do NOT say "no change" when the real truth is "we cannot confidently
determine what this means" — that is **Inconclusive**, and we say so + tell the user to keep
tracking. Every result also carries the *evidence* it was built from + a one-line conclusion,
so the user understands not just the verdict but the reasoning.

Three interpretation modes, by category (``MEASUREMENT_CATEGORY``):

  * ``decrease_good`` / ``increase_good`` — DIRECT measures of the target. Waist ↓ *is* fat;
    lean mass ↑ *is* muscle. Judged by their own literal direction (high confidence).
  * ``inferred`` — LIMB circumferences (arm / forearm / thigh / calf). A limb change can be
    muscle OR fat, so we do NOT judge it in isolation. We classify the **body's direction**
    from the composition evidence (14-day fat-mass / lean-mass deltas + the precomputed
    recomposition / muscle-loss-risk / muscle-preservation signals) and read the limb change
    in that light. Thin or conflicting evidence → **Inconclusive** (never an uncertain
    inference presented as certain; medium confidence is hedged, "Likely …").
  * ``neutral`` — no directional health goal (chest, shoulders, BMR, body-water %).

The arrow always shows the LITERAL measurement movement; the colour + label say whether that
movement is good, bad, or inconclusive.

All inputs are deterministic truth already computed elsewhere — the canonical snapshot deltas
and the ``DailyHealthSummary`` body-comp panel (background cycle). This module only
INTERPRETS; it issues no new heavy queries (request-path safe). NOTE: a dedicated *strength*
signal is not yet wired request-path-safe, so evidence is built from fat/lean/weight — which
directly measure muscle-vs-fat — not from strength (we never fabricate a signal we don't have).

Rules are documented in ``docs/WLJ_BODY_MEASUREMENT_INTERPRETATION.md``.
"""
from __future__ import annotations

# ── Categories ──────────────────────────────────────────────────────────────
DECREASE_GOOD = "decrease_good"
INCREASE_GOOD = "increase_good"
INFERRED = "inferred"
NEUTRAL = "neutral"

#: Every Body-Intelligence measurement → its interpretation category. Anything not listed
#: defaults to NEUTRAL (never fabricate a health verdict for an unknown metric).
MEASUREMENT_CATEGORY = {
    # Direct fat / risk reducers — smaller is healthier.
    "waist": DECREASE_GOOD,
    "hips": DECREASE_GOOD,
    "neck": DECREASE_GOOD,          # body-fat / sleep-apnea proxy — smaller within reason
    "body_fat_pct": DECREASE_GOOD,
    "fat_mass": DECREASE_GOOD,
    "visceral_fat": DECREASE_GOOD,
    "bmi": DECREASE_GOOD,
    "metabolic_age": DECREASE_GOOD,
    # Direct lean / structural mass — larger is healthier.
    "lean_mass": INCREASE_GOOD,
    "skeletal_muscle_mass": INCREASE_GOOD,
    "bone_mass": INCREASE_GOOD,
    # Limb circumferences — muscle OR fat; judged by the BODY's inferred direction.
    "arm_left": INFERRED,
    "arm_right": INFERRED,
    "forearm_left": INFERRED,
    "forearm_right": INFERRED,
    "thigh_left": INFERRED,
    "thigh_right": INFERRED,
    "calf_left": INFERRED,
    "calf_right": INFERRED,
    # No directional health goal — tracked, never judged.
    "chest": NEUTRAL,
    "shoulders": NEUTRAL,
    "body_water_pct": NEUTRAL,
    "bmr": NEUTRAL,
}

# ── Statuses (drive the card colour) ────────────────────────────────────────
IMPROVING = "improving"           # green
NEEDS_ATTENTION = "needs_attention"  # red
INCONCLUSIVE = "inconclusive"     # gray — signals don't support a confident conclusion


def _epsilon(unit: str) -> float:
    """Meaningful-movement threshold. Only a genuine ~0 reads as no movement."""
    u = (unit or "").lower()
    if u in ("kcal/day", "kcal"):
        return 5.0
    return 0.05


# 14-day composition deltas that count as a real move (lb).
_LEAN_MEANINGFUL = 0.5
_FAT_MEANINGFUL = 0.5
_WEIGHT_FAST = 3.0  # lb lost / 14d that reads as "rapid"

_KEEP_TRACKING = (
    "Current measurements don't provide enough evidence. "
    "Continue tracking over the next few check-ins."
)


def infer_body_direction(body_comp: dict | None) -> dict:
    """Deterministic overall body-composition trajectory from the precomputed panel.

    Returns ``{"verdict", "status", "confidence", "evidence", "summary"}``. ``evidence`` is
    the list of signals it was built from (e.g. ``["Body fat ↓", "Lean mass ↑"]``); ``summary``
    is the plain-English conclusion. Thin or conflicting evidence → Inconclusive + low
    confidence — never an uncertain inference asserted as fact.

    Reuses the ``DailyHealthSummary`` body-comp panel (14-day fat/lean deltas +
    ``recomposition_flag_14d`` / ``muscle_loss_risk_level`` / ``muscle_preservation_status``),
    all computed in the background cycle — no new request-path queries.
    """
    bc = body_comp or {}
    lean = bc.get("lean_mass_delta_14d")
    fat = bc.get("fat_mass_delta_14d")
    weight = bc.get("weight_delta_14d")
    risk = (bc.get("muscle_loss_risk_level") or "").lower()
    recomp = bool(bc.get("recomposition_flag_14d"))
    preservation = (bc.get("muscle_preservation_status") or "").lower()

    # Need both fat and lean movement to say anything about muscle-vs-fat.
    if lean is None or fat is None:
        return {"verdict": "insufficient", "status": INCONCLUSIVE, "confidence": "low",
                "evidence": [], "summary": _KEEP_TRACKING}

    fat_down = fat <= -_FAT_MEANINGFUL
    fat_up = fat >= _FAT_MEANINGFUL
    lean_up = lean >= _LEAN_MEANINGFUL
    lean_down = lean <= -_LEAN_MEANINGFUL
    weight_down_fast = weight is not None and weight <= -_WEIGHT_FAST

    # 1. Losing muscle → Needs attention (the risk we most want to surface).
    if risk in ("high", "elevated") or lean_down:
        ev = ["Lean mass ↓"]
        if weight_down_fast:
            ev.append("Weight ↓ quickly")
        conf = "high" if (risk in ("high", "elevated") and lean_down) else "medium"
        return {"verdict": "muscle_loss", "status": NEEDS_ATTENTION, "confidence": conf,
                "evidence": ev, "summary": "Possible muscle loss."}
    # 2. Recomposition (fat down + lean up) → Improving.
    if recomp or (fat_down and lean_up):
        return {"verdict": "recomposition", "status": IMPROVING, "confidence": "high",
                "evidence": ["Body fat ↓", "Lean mass ↑"],
                "summary": "Likely muscle gain while losing fat."}
    # 3. Fat loss with muscle preserved → Improving.
    if fat_down and not lean_down:
        conf = "high" if preservation in ("good", "preserved", "excellent", "strong") else "medium"
        return {"verdict": "fat_loss_preserving", "status": IMPROVING, "confidence": conf,
                "evidence": ["Body fat ↓", "Lean mass steady"],
                "summary": "Losing fat while holding muscle."}
    # 4. Mixed / unclear → Inconclusive (say so).
    if fat_up and lean_up:
        return {"verdict": "mixed_gain", "status": INCONCLUSIVE, "confidence": "low",
                "evidence": ["Body fat ↑", "Lean mass ↑"],
                "summary": "Fat and lean are both rising — not enough to draw a confident conclusion. "
                           "Continue tracking over the next few check-ins."}
    return {"verdict": "unclear", "status": INCONCLUSIVE, "confidence": "low",
            "evidence": [], "summary": _KEEP_TRACKING}


def interpret_measurement(metric: str, delta, unit: str, body_direction: dict | None) -> dict:
    """Interpret one measurement change.

    Returns ``{"status", "status_label", "arrow", "confidence", "evidence", "reason"}``:
      * ``arrow`` — the LITERAL movement: ``up`` / ``down`` / ``flat``.
      * ``status`` — ``improving`` / ``needs_attention`` / ``inconclusive`` (drives colour).
      * ``status_label`` — the word shown ("Improving", "Needs attention", "Inconclusive",
        or "Likely …" when a limb inference is only medium confidence).
      * ``evidence`` — the signals behind the verdict (limb cards; else empty).
      * ``reason`` — the plain-English "what this is most likely telling you" conclusion.
    """
    category = MEASUREMENT_CATEGORY.get(metric, NEUTRAL)
    eps = _epsilon(unit)
    moved = delta is not None and abs(delta) >= eps
    arrow = "flat" if not moved else ("up" if delta > 0 else "down")

    # No meaningful movement → Inconclusive (nothing to interpret yet).
    if not moved:
        return {"status": INCONCLUSIVE, "status_label": "Inconclusive", "arrow": "flat",
                "confidence": "high", "evidence": [],
                "reason": "No meaningful change since your last reading — keep tracking."}

    # Neutral metric — tracked, but no health goal to interpret against.
    if category == NEUTRAL:
        return {"status": INCONCLUSIVE, "status_label": "Inconclusive", "arrow": arrow,
                "confidence": "high", "evidence": [],
                "reason": "No established healthy direction for this measurement."}

    # Direct measure of the target — literal direction vs the healthy direction.
    if category in (DECREASE_GOOD, INCREASE_GOOD):
        healthy = (delta < 0 and category == DECREASE_GOOD) or (delta > 0 and category == INCREASE_GOOD)
        if healthy:
            reason = ("Getting smaller — the healthy direction." if category == DECREASE_GOOD
                      else "Getting larger — the healthy direction.")
            return {"status": IMPROVING, "status_label": "Improving", "arrow": arrow,
                    "confidence": "high", "evidence": [], "reason": reason}
        reason = ("Getting larger — moving away from your goal." if category == DECREASE_GOOD
                  else "Getting smaller — moving away from your goal.")
        return {"status": NEEDS_ATTENTION, "status_label": "Needs attention", "arrow": arrow,
                "confidence": "high", "evidence": [], "reason": reason}

    # INFERRED (limb) — read the change through the body's inferred direction.
    bd = body_direction or {}
    status = bd.get("status", INCONCLUSIVE)
    confidence = bd.get("confidence", "low")
    evidence = list(bd.get("evidence", []))
    summary = bd.get("summary") or _KEEP_TRACKING

    # Low confidence (or already inconclusive) → don't assert a verdict; say so.
    if confidence == "low" or status == INCONCLUSIVE:
        return {"status": INCONCLUSIVE, "status_label": "Inconclusive", "arrow": arrow,
                "confidence": "low", "evidence": evidence, "reason": summary}

    label = {IMPROVING: "Improving", NEEDS_ATTENTION: "Needs attention"}.get(status, "Inconclusive")
    if confidence == "medium":
        label = "Likely " + label.lower()
    return {"status": status, "status_label": label, "arrow": arrow,
            "confidence": confidence, "evidence": evidence, "reason": summary}
