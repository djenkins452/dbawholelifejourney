# ==============================================================================
# File: apps/ai/chatgpt_cos/reasoning/engines.py
# Description: Layer 2 reusable reasoning ENGINES — cross-cutting reasoning that every
#   domain shares, built once. They reason OVER Layer 1 truth and NEVER create truth:
#   each reads a Layer 1 fact/value and returns a judgement, leaving the truth untouched.
#   (The Reasoning Lane in this package handles LLM reasoning intents; these are the
#   deterministic reasoning primitives the conversation layer and domains consume.)
# ==============================================================================

# ---------------------------------------------------------------------------
# Reasoning Confidence — a conclusion is only as trustworthy as its weakest input.
# Consumes Layer 1 confidence levels; never re-derives a single fact's confidence.
# ---------------------------------------------------------------------------
_CONF_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}


def reasoning_confidence(*signals):
    """Combine input confidences into the confidence of the CONCLUSION. A reasoning
    chain is only as strong as its weakest link → the minimum. Unknown/empty inputs are
    ignored; with no recognized input, default to 'medium'."""
    levels = [s for s in signals if s in _CONF_ORDER]
    if not levels:
        return "medium"
    return min(levels, key=lambda s: _CONF_ORDER[s])


def confidence_rank(level):
    """Numeric rank of a confidence level (for thresholds/comparison)."""
    return _CONF_ORDER.get(level, _CONF_ORDER["medium"])


# ---------------------------------------------------------------------------
# Risk Engine — read the risk a Layer 1 fact already carries (clinical interpretation,
# temporal warning). It NEVER invents risk; absent an interpretation, risk is 'normal'.
# ---------------------------------------------------------------------------
def assess_risk(fact):
    """Risk verdict for a Layer 1 fact: {level, [advice], [basis]}.
    level ∈ {elevated, uncertain, normal}. Consumes truth, creates none."""
    fact = fact or {}
    interp = fact.get("interpretation") or {}
    if interp.get("concern"):
        return {"level": "elevated",
                "advice": interp.get("advice"),
                "basis": interp.get("display") or "flagged by clinical interpretation"}
    if fact.get("temporal_warning"):
        return {"level": "uncertain", "basis": fact["temporal_warning"]}
    return {"level": "normal"}


# ---------------------------------------------------------------------------
# Priority Engine — rank items by a caller-supplied significance score (what matters
# first). Generic so every domain ranks the same way.
# ---------------------------------------------------------------------------
def prioritize(items, score):
    """Sort items by descending significance `score(item)` (highest first)."""
    return sorted(items, key=lambda it: -float(score(it)))


# ---------------------------------------------------------------------------
# Reasoning Transparency — surface WHY a conclusion was reached. The customer should
# understand the reasoning, not just receive a verdict.
# ---------------------------------------------------------------------------
def explain(conclusion, because=None):
    """Attach the basis to a conclusion: 'X — because Y.' Returns the conclusion
    unchanged when there's nothing to add."""
    conclusion = (conclusion or "").strip()
    because = (because or "").strip()
    if not because:
        return conclusion
    because = because[0].lower() + because[1:]
    return f"{conclusion} — {because}".rstrip(".") + "."
