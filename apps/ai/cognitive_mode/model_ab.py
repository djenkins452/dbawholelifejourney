"""Model A/B evaluation — Phase 0 SCAFFOLD ONLY.

This module defines the *shape* of the model A/B harness. It deliberately does
NOT call any model API. `generate_candidate()` is a hard stop: it raises unless
both (a) the feature flag is on AND (b) an explicit `approved=True` is passed —
neither of which Phase 0's inert build supplies.

Goal of the eventual A/B: hold the grounded context CONSTANT and vary only the
model, to decide whether `gpt-4o` is the reasoning ceiling. We score grounded
executive judgment (groundedness, specificity, hallucination risk) — NOT fluency.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

# Scoring axes — the decisive ones are groundedness + specificity + hallucination_risk.
SCORE_AXES = (
    "groundedness",
    "helpfulness",
    "specificity",
    "hallucination_risk",   # higher = worse
    "context_use",
    "tone",
    "actionability",
)

DECISIVE_AXES = ("groundedness", "specificity", "hallucination_risk")


@dataclass
class ABPair:
    prompt_ref: str
    message_hash: str
    context_fingerprint: str
    model_a: str = "gpt-4o"
    model_b: str = ""
    answer_a: str = ""
    answer_b: str = ""
    scores_a: dict = field(default_factory=dict)
    scores_b: dict = field(default_factory=dict)
    auto_flags: list = field(default_factory=list)


def context_fingerprint(context_payload) -> str:
    """Stable hash of the grounded context, so we can prove both models saw
    the SAME inputs."""
    try:
        blob = json.dumps(context_payload, sort_keys=True, default=str)
    except Exception:
        blob = str(context_payload)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


class ModelABNotApproved(RuntimeError):
    """Raised if candidate generation is attempted without explicit approval."""


def _ab_enabled() -> bool:
    """Reads the flag lazily so this module imports without Django configured."""
    try:
        from django.conf import settings
        return bool(getattr(settings, "WLJ_BETH_MODEL_AB_ENABLED", False))
    except Exception:
        return False


def generate_candidate(prompt, context_payload, model_id, *, approved: bool = False) -> str:
    """HARD STOP in Phase 0. Will not call any API.

    The real implementation (post-approval) will call the model provider with the
    SAME context Beth already sends today. Until then this raises to guarantee no
    accidental spend or data egress.
    """
    if not approved or not _ab_enabled() or not model_id:
        raise ModelABNotApproved(
            "Model A/B candidate generation is not approved/enabled. "
            "Requires WLJ_BETH_MODEL_AB_ENABLED=True, a candidate model id, and "
            "explicit approved=True. See docs/BETH_PHASE0_SHADOW_CLASSIFIER_PLAN.md §12."
        )
    # ---- TODO (post-approval): actual provider call goes here ----
    raise NotImplementedError("Candidate generation body intentionally unimplemented in Phase 0.")


def score_answer(answer: str, context_payload) -> dict:
    """Programmatic auto-checks only (the LLM-judge pass is added post-approval).

    Returns a partial score dict + auto_flags. Pure, no API.
    """
    flags = []
    text = answer or ""
    # Cheap groundedness heuristic placeholder: flag if the answer is empty.
    if not text.strip():
        flags.append("empty_answer")
    # Generic-phrase smell (specificity proxy).
    generic_markers = ("make sure to", "it's important to", "consider tracking",
                       "stay consistent", "as a general rule")
    if any(g in text.lower() for g in generic_markers):
        flags.append("generic_language")
    return {"auto_flags": flags}


def build_pair(prompt_ref, message, context_payload, candidate_model) -> ABPair:
    """Construct an (unexecuted) A/B pair record. Does not generate answers."""
    return ABPair(
        prompt_ref=prompt_ref,
        message_hash=hashlib.sha256((message or "").encode("utf-8")).hexdigest(),
        context_fingerprint=context_fingerprint(context_payload),
        model_b=candidate_model or "",
    )
