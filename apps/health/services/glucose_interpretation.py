"""
Clinical INTERPRETATION layer for glucose (Truth → Interpretation → Narration).

Truth ("the value is 43 mg/dL") and Interpretation ("is that safe?") are DIFFERENT
responsibilities. Beth must never invent clinical reassurance over a dangerous value
— a release blocker occurred when the narration LLM appended "(in a good range)" to a
43 mg/dL reading (severe hypoglycemia). This module is the single canonical source of
glucose band classification; the GlucoseEntry model, the SAE state, and Beth's
foundational facts all delegate here, so no path can produce an unsafe interpretation.

Bands are ADA-aligned (mg/dL). `safety` drives narration: a `danger`/`caution` band
must be surfaced honestly and may recommend verification — never reassured away.
"""

# Narration guidance per band — deterministic, so the verdict is decided BEFORE the LLM.
_BANDS = (
    # (max_exclusive, band, display, safety, advice)
    (54,    "very_low",  "Very Low",  "danger",
     "This is a dangerously low reading (severe hypoglycemia). If accurate it needs "
     "immediate attention — please verify with a fingerstick and treat if needed."),
    (70,    "low",       "Low",       "caution",
     "This is below the typical range. Consider verifying, and treat if you have "
     "symptoms of a low."),
    (181,   "normal",    "In Range",  "ok",     ""),
    (251,   "high",      "High",      "caution",
     "This is above the typical range."),
    (10_000, "very_high", "Very High", "danger",
     "This is well above the typical range. If accurate, please verify and follow your "
     "care plan."),
)


def classify_glucose_mg_dl(mg_dl):
    """Return the clinical interpretation for a glucose value in mg/dL, or None.

    {band, display, safety ('ok'|'caution'|'danger'), concern (bool), advice}.
    """
    if mg_dl is None:
        return None
    try:
        v = float(mg_dl)
    except (TypeError, ValueError):
        return None
    for ceiling, band, display, safety, advice in _BANDS:
        if v < ceiling:
            return {"band": band, "display": display, "safety": safety,
                    "concern": safety in ("danger", "caution"), "advice": advice}
    return None


def to_mg_dl(value, unit):
    """Normalize a glucose value to mg/dL (mmol/L → mg/dL ≈ ×18.0182)."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if unit and "mmol" in str(unit).lower():
        return v * 18.0182
    return v


def interpret(value, unit="mg/dL"):
    """Convenience: interpret a value in any supported unit."""
    return classify_glucose_mg_dl(to_mg_dl(value, unit))
