# ==============================================================================
# File: apps/ai/chatgpt_cos/naturalize.py
# Capability: NATURAL EXECUTIVE VOICE — translate internal reasoning vocabulary into
# the words an experienced human Chief of Staff would actually say, at the single
# choke point every composed response passes through (lanes.route_message).
#
# Beth may reason internally with whatever concepts help (workload bands, "backlog",
# "energy-management day", "lived experience"). The CUSTOMER must never hear that
# vocabulary — it sounds like software, not a trusted right hand. This is the
# deterministic last-mile pass (a sibling of response_coherence.harmonize) that catches
# leaked jargon regardless of which composer — deterministic beat or LLM narration —
# produced it. Surgical and substance-preserving: it only swaps known internal terms
# for natural equivalents; it never changes the meaning.
# ==============================================================================
import logging
import re

logger = logging.getLogger(__name__)

# (pattern, replacement) — ORDER MATTERS (more specific phrases first). Case-insensitive;
# each replacement is chosen to read naturally in the positions these terms actually
# appear. Keep this list tight and high-confidence — a wrong swap is worse than a leak.
_RULES = [
    # Clause-level internal framings (belt-and-suspenders; sources are also fixed).
    (r"\bi trust your lived experience\b", "good"),
    (r"\byour lived experience\b", "how you're feeling"),
    (r"\blived experience\b", "how you're feeling"),
    (r"\ban energy-management day\b", "a day to watch your energy"),
    (r"\benergy-management day\b", "a day to watch your energy"),
    (r"\ba recovery-management day\b", "a day to protect your recovery"),
    (r"\brecovery-management day\b", "a day to protect your recovery"),
    (r"\brecovery latitude\b", "room to ease off"),
    # Internal AGGREGATION / diagnostic artifacts that must never reach a customer.
    (r"[.,;]?\s*consolidated from \d+ readings into one concern\.?", "."),
    (r"\s*[—–-]\s*range \d[\d.]*[–-]\d[\d.]*%,?\s*average \d[\d.]*%\.?", "."),
    (r"\s*\bconsolidated from \d+ readings\b\.?", ""),
    # Operational / software terminology customers don't think in.
    (r"\bstrategic backlog\b", "longer-term list"),
    (r"\btask backlog\b", "list of open items"),
    (r"\bbacklog of\b", "pile of"),
    (r"\bbacklog\b", "open items"),
]
_COMPILED = [(re.compile(p, re.IGNORECASE), r) for p, r in _RULES]


# PLAN-AWARE RECOVERY REFRAME (last-mile guard). The plan-aware `OvertrainingRiskRule`
# only reframes NEW insights; OLD persisted rows keep the raw "N workouts in 7 days.
# Recovery is compromised — consider a rest day or lighter session." wording, which is
# then re-read verbatim by several consumers. This catches that exact wording ANYWHERE it
# reaches the user and reframes it — but ONLY when the user's structured training plan
# actually has a built-in recovery day (otherwise the rest-day advice is legitimate).
_OVERTRAIN_RE = re.compile(
    r"(?:sleep\s+averaging[^.]*\.\s*)?[^.]*?\b\d+\s+workouts?\s+in\s+\d+\s+days?\b[^.]*?\.\s*"
    r"recovery is compromised[^.]*\.",
    re.IGNORECASE)
_PLAN_AWARE_RECOVERY = ("Sleep's been running short lately, so the move is protecting "
                        "tonight's sleep to keep your training plan on track.")


def recovery_reframe(text, user):
    """Reframe the stale overtraining "consider a rest day" wording to plan-aware
    coaching when the user's structured training plan already has a built-in recovery
    day. Never raises. No-op when the wording isn't present or the plan can't be read."""
    if not text or "recovery is compromised" not in text.lower():
        return text
    try:
        from apps.health.services.training_plan import read_training_plan
        if not read_training_plan(user).get("has_recovery_day"):
            return text                    # no built-in rest day → rest-day advice stands
    except Exception:
        return text
    try:
        return _OVERTRAIN_RE.sub(_PLAN_AWARE_RECOVERY, text)
    except Exception:
        logger.warning("recovery_reframe failed", exc_info=True)
        return text


def naturalize(text):
    """Return `text` with internal reasoning vocabulary translated into natural
    executive language. Never raises — a voice pass must never break a response."""
    if not text:
        return text
    try:
        out = text
        for rx, repl in _COMPILED:
            out = rx.sub(repl, out)
        return out
    except Exception:
        logger.warning("naturalize failed", exc_info=True)
        return text
