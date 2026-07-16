"""
Body Intelligence — measurement interpretation (the ONE deterministic authority).

Answers, per body measurement: **"What is this change most likely telling me?"** —
Improving (green) / Needs attention (red) / No change · inconclusive (gray) — from the
WHOLE body-composition picture, never a circumference in isolation.

Three interpretation modes, by category (``MEASUREMENT_CATEGORY``):

  * ``decrease_good`` / ``increase_good`` — DIRECT measures of the target. Waist ↓ *is*
    fat; lean mass ↑ *is* muscle. The status is simply the literal direction vs the
    healthy direction. High confidence, no inference needed.
  * ``inferred`` — LIMB circumferences (arm / forearm / thigh / calf). A limb change can
    be muscle OR fat, so we do NOT judge it in isolation. We classify the **body's
    direction** from the composition evidence (14-day fat-mass / lean-mass deltas plus the
    precomputed recomposition / muscle-loss-risk / muscle-preservation signals) and read
    the limb change in that light. When evidence is thin or conflicting → **Neutral**, and
    we SAY the confidence — never present an uncertain inference as deterministic truth.
  * ``neutral`` — no directional health goal (chest, shoulders, BMR, body-water %).

The arrow always shows the LITERAL measurement movement; the colour + label say whether
that movement is good, bad, or inconclusive.

All inputs are deterministic truth already computed elsewhere — the canonical snapshot
deltas and the ``DailyHealthSummary`` body-comp panel (populated in the SAME background
cycle). This module only INTERPRETS; it issues no new heavy queries (request-path safe).

Rules are documented in ``docs/WLJ_BODY_MEASUREMENT_INTERPRETATION.md`` so future
measurements inherit the correct behaviour by category.
"""
from __future__ import annotations

# ── Categories ──────────────────────────────────────────────────────────────
DECREASE_GOOD = "decrease_good"
INCREASE_GOOD = "increase_good"
INFERRED = "inferred"
NEUTRAL = "neutral"

#: Every Body-Intelligence measurement → its interpretation category. Anything not
#: listed defaults to NEUTRAL (never fabricate a health verdict for an unknown metric).
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
NO_CHANGE = "no_change"           # gray (no meaningful movement OR no meaningful conclusion)

_STATUS_LABEL = {
    IMPROVING: "Improving",
    NEEDS_ATTENTION: "Needs attention",
    NO_CHANGE: "No change",
}

# Meaningful-movement thresholds. Only a genuine ~0 reads as "No change"; the units used
# in Body Intelligence (in / lb / % / bmi / count) share a small epsilon, kcal is coarser.
def _epsilon(unit: str) -> float:
    u = (unit or "").lower()
    if u in ("kcal/day", "kcal"):
        return 5.0
    return 0.05


# 14-day composition deltas that count as a real move (lb).
_LEAN_MEANINGFUL = 0.5
_FAT_MEANINGFUL = 0.5


def infer_body_direction(body_comp: dict | None) -> dict:
    """Deterministic overall body-composition trajectory from the precomputed panel.

    Returns ``{"verdict", "status", "confidence", "summary"}``. The verdict drives how a
    LIMB circumference change is read. Thin or conflicting evidence → Neutral + low
    confidence — we never assert an uncertain inference as fact.

    Reuses the ``DailyHealthSummary`` body-comp panel (14-day fat/lean deltas +
    ``recomposition_flag_14d`` / ``muscle_loss_risk_level`` / ``muscle_preservation_status``),
    all computed in the background cycle — no new request-path queries.
    """
    bc = body_comp or {}
    lean = bc.get("lean_mass_delta_14d")
    fat = bc.get("fat_mass_delta_14d")
    risk = (bc.get("muscle_loss_risk_level") or "").lower()
    recomp = bool(bc.get("recomposition_flag_14d"))
    preservation = (bc.get("muscle_preservation_status") or "").lower()

    # Need both fat and lean movement to say anything about muscle-vs-fat.
    if lean is None or fat is None:
        return {
            "verdict": "insufficient", "status": NO_CHANGE, "confidence": "low",
            "summary": "Not enough recent fat/lean data to interpret limb changes yet.",
        }

    fat_down = fat <= -_FAT_MEANINGFUL
    fat_up = fat >= _FAT_MEANINGFUL
    lean_up = lean >= _LEAN_MEANINGFUL
    lean_down = lean <= -_LEAN_MEANINGFUL

    # 1. Losing muscle → Needs attention (the risk we most want to surface).
    if risk in ("high", "elevated") or lean_down:
        conf = "high" if (risk in ("high", "elevated") and lean_down) else "medium"
        return {
            "verdict": "muscle_loss", "status": NEEDS_ATTENTION, "confidence": conf,
            "summary": "Lean mass is trending down — a limb getting smaller is most likely muscle loss.",
        }
    # 2. Recomposition (fat down + lean up) → Improving.
    if recomp or (fat_down and lean_up):
        return {
            "verdict": "recomposition", "status": IMPROVING, "confidence": "high",
            "summary": "You're losing fat and building lean mass — limb changes reflect recomposition.",
        }
    # 3. Fat loss with muscle preserved → Improving.
    if fat_down and not lean_down:
        conf = "high" if preservation in ("good", "preserved", "excellent", "strong") else "medium"
        return {
            "verdict": "fat_loss_preserving", "status": IMPROVING, "confidence": conf,
            "summary": "You're losing fat while holding lean mass — a smaller limb is fat loss, not muscle loss.",
        }
    # 4. Mixed / unclear → Neutral (say so).
    if fat_up and lean_up:
        return {
            "verdict": "mixed_gain", "status": NO_CHANGE, "confidence": "low",
            "summary": "Fat and lean are both rising — not enough to call a limb change good or bad.",
        }
    return {
        "verdict": "unclear", "status": NO_CHANGE, "confidence": "low",
        "summary": "Body-composition signals are mixed — not enough evidence to interpret limb changes.",
    }


def interpret_measurement(metric: str, delta, unit: str, body_direction: dict | None) -> dict:
    """Interpret one measurement change.

    Returns ``{"status", "status_label", "arrow", "confidence", "reason"}``:
      * ``arrow`` — the LITERAL movement: ``up`` / ``down`` / ``flat``.
      * ``status`` — ``improving`` / ``needs_attention`` / ``no_change`` (drives colour).
      * ``status_label`` — the word shown ("Improving", "Needs attention", "No change",
        "No goal", "Not enough evidence", or "Likely …" when confidence is only medium).
      * ``confidence`` — ``high`` / ``medium`` / ``low``.
      * ``reason`` — short plain-English "what this is most likely telling you".
    """
    category = MEASUREMENT_CATEGORY.get(metric, NEUTRAL)
    eps = _epsilon(unit)
    moved = delta is not None and abs(delta) >= eps
    arrow = "flat" if not moved else ("up" if delta > 0 else "down")

    # No meaningful movement → gray "No change" for every category.
    if not moved:
        return {"status": NO_CHANGE, "status_label": "No change", "arrow": "flat",
                "confidence": "high", "reason": "No meaningful change since your last reading."}

    # Neutral metric — tracked, but no health goal to judge against.
    if category == NEUTRAL:
        return {"status": NO_CHANGE, "status_label": "No goal", "arrow": arrow,
                "confidence": "high", "reason": "No directional health goal for this measurement."}

    # Direct measure of the target — literal direction vs the healthy direction.
    if category in (DECREASE_GOOD, INCREASE_GOOD):
        healthy = (delta < 0 and category == DECREASE_GOOD) or (delta > 0 and category == INCREASE_GOOD)
        status = IMPROVING if healthy else NEEDS_ATTENTION
        return {"status": status, "status_label": _STATUS_LABEL[status], "arrow": arrow,
                "confidence": "high", "reason": ""}

    # INFERRED (limb) — read the change through the body's inferred direction.
    bd = body_direction or {}
    status = bd.get("status", NO_CHANGE)
    confidence = bd.get("confidence", "low")
    summary = bd.get("summary", "Not enough evidence to interpret this yet.")

    # Low confidence → do NOT assert a verdict; present as inconclusive (gray).
    if confidence == "low" or status == NO_CHANGE:
        return {"status": NO_CHANGE, "status_label": "Not enough evidence", "arrow": arrow,
                "confidence": "low", "reason": summary}

    label = _STATUS_LABEL.get(status, "No change")
    if confidence == "medium":
        # Honestly hedge a medium-confidence inference.
        label = "Likely " + label.lower()
    return {"status": status, "status_label": label, "arrow": arrow,
            "confidence": confidence, "reason": summary}
