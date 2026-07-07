# ==============================================================================
# File: apps/ai/reflection/engine.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Executive Reflection lifecycle orchestrator + disposition actions.
# ==============================================================================
"""
reflect_on_turn() runs the ratified lifecycle off the request path:

  Trigger -> Evidence -> Reconstruction -> Assessment -> Classification -> Decision

and routes to exactly one disposition. It is fail-OPEN for the user (never breaks
a conversation) but fail-VISIBLE in logs. Every reflection is recorded to the
append-only ReflectionEvent log (audit + recurrence + scorecard input).

Learning is DEFAULT-DENY. The classifier already excludes truth/reasoning/execution
from the learn path; the gate here is a second, independent guard (defense in
depth): Beth may learn ONLY when the locus is communication/preference/trust-repair
AND evidence is sufficient. Anything else that reached 'learn' is downgraded to
insufficient-evidence rather than risk learning around a defect (P2/P3).
"""

import logging

from apps.ai.reflection.classifier import classify

logger = logging.getLogger(__name__)

_LEARNABLE_LOCI = {"communication", "preference", "trust_repair"}
_MIN_LEARN_CONFIDENCE = 0.5


def reflect_on_turn(user, message, response_text, conversation):
    """Reflect on one completed turn. Fail-open; returns the ReflectionEvent or None."""
    if not user or not message:
        return None
    try:
        is_corr = _is_correction(message)
        result = classify(user, message, response_text, is_corr)
        disposition = result["disposition"]
        directive_key = ""
        eio = None

        if disposition == "learn":
            if _gate_allows_learning(result):
                directive_key = _apply_learning(user, result, message) or ""
                _approve_correction_readback(user, message)
            else:
                # Default-deny: a 'learn' that fails the gate never learns.
                disposition = "insufficient_evidence"
                logger.info("reflection: learn blocked by gate locus=%s conf=%.2f",
                            result.get("locus"), result.get("confidence", 0.0))
        elif disposition == "reinforce":
            _apply_reinforcement(user, result)
        elif disposition == "eio":
            eio = _create_or_update_eio(user, result, message, response_text)

        return _record(user, message, response_text, result, disposition,
                       directive_key, eio, is_corr)
    except Exception:
        # Fail-open for the user, fail-visible in logs.
        logger.warning("reflect_on_turn failed user=%s", getattr(user, "id", "?"),
                       exc_info=True)
        return None


# --- helpers -----------------------------------------------------------------

def _is_correction(message):
    try:
        from apps.ai.correction_service import detect_correction
        if detect_correction(message):
            return True
    except Exception:
        pass
    try:
        from apps.ai.chatgpt_cos.correction import is_factual_correction
        return bool(is_factual_correction(message))
    except Exception:
        return False


def _gate_allows_learning(result):
    """The five-condition default-deny gate. Truth/reasoning/execution are already
    excluded upstream (they never reach locus communication/preference); this
    enforces the remaining conditions and is the last line of defense."""
    return (
        result.get("disposition") == "learn"
        and result.get("locus") in _LEARNABLE_LOCI
        and result.get("confidence", 0.0) >= _MIN_LEARN_CONFIDENCE
    )


def _apply_learning(user, result, message):
    """Persist a BOUNDED behavior directive (never a truth value). Returns the key."""
    locus = result["locus"]
    phrase = (result.get("evidence") or {}).get("phrase", "")
    key = f"{locus}:{_slug(phrase) or 'general'}"
    behavior_change = (
        "Adjust delivery style per the user's stated communication preference."
        if locus == "communication"
        else "Apply the user's stated personalization preference."
    )
    try:
        from apps.ai.chatgpt_cos import behavior_guidance
        d = behavior_guidance.learn(
            user, key,
            observation=(message or "")[:300],
            behavior_change=behavior_change,
            layer=locus,
            source="corrected",
            evidence=f"reflection: {phrase}"[:300],
        )
        return getattr(d, "key", key)
    except Exception:
        logger.warning("reflection: behavior_guidance.learn failed", exc_info=True)
        return ""


def _apply_reinforcement(user, result):
    """Positive outcome — strengthen an EXISTING bounded directive if one matches.
    NEVER creates truth and never fabricates a directive from a single positive
    turn (P4). No-op is a valid, common outcome."""
    # Reinforcement of specific directives is intentionally conservative: with no
    # matching directive there is nothing to strengthen, and we must not invent
    # one. The positive signal is still captured in the ReflectionEvent (which the
    # Executive Scorecard reads). Future: reinforce PredictionAccuracyProfile.
    return None


def _create_or_update_eio(user, result, message, response_text):
    """Route a deterministic-faculty failure to an Executive Improvement
    Opportunity (extends the existing ImprovementTaskModel ledger). Dedupe by
    (user, locus, topic) among OPEN reflection EIOs -> bump recurrence instead of
    spawning duplicates. Never auto-actioned; surfaced to Danny (P7)."""
    try:
        from assistant.models import ImprovementTaskModel as ITM
    except Exception:
        logger.warning("reflection: ImprovementTaskModel import failed", exc_info=True)
        return None

    locus = result["locus"]
    topic = result.get("topic", "")
    open_statuses = [ITM.STATUS_NEW, ITM.STATUS_PENDING_APPROVAL,
                     ITM.STATUS_APPROVED, ITM.STATUS_IN_PROGRESS]
    try:
        existing = (
            ITM.objects.filter(
                source=ITM.SOURCE_REFLECTION,
                triggered_by_user=user,
                functional_locus=locus,
                status__in=open_statuses,
            )
            .filter(title__endswith=(topic or "unclassified"))
            .order_by("-created_at")
            .first()
        )
        if existing:
            existing.recurrence_count = (existing.recurrence_count or 1) + 1
            existing.save(update_fields=["recurrence_count", "updated_at"])
            return existing

        reconstruction = _reconstruct(locus, topic, result, message)
        hypothesis = _hypothesis(locus, result)
        return ITM.create_from_reflection(
            user=user,
            functional_locus=locus,
            engineering_category=result.get("engineering_category", "") or "other",
            topic=topic,
            evidence=result.get("evidence", {}),
            reconstruction=reconstruction,
            hypothesis=hypothesis,
        )
    except Exception:
        logger.warning("reflection: EIO create/update failed", exc_info=True)
        return None


def _approve_correction_readback(user, message):
    """Mark the just-stored CorrectionRecord for this message as read-back
    approved. Only reached for a classifier-approved (preference/communication)
    learning — truth-domain corrections never get here, so they are never
    re-injected into the CoS prompt (P3, default-deny read-back)."""
    try:
        from apps.ai.models import CorrectionRecord
        rec = (
            CorrectionRecord.objects.filter(user=user)
            .order_by("-created_at")
            .first()
        )
        if rec and (message or "")[:200] in (rec.user_correction or "") \
                and not rec.readback_approved:
            rec.readback_approved = True
            rec.save(update_fields=["readback_approved"])
    except Exception:
        logger.debug("reflection: correction read-back approval skipped",
                     exc_info=True)


def _record(user, message, response_text, result, disposition, directive_key,
            eio, is_corr):
    from apps.ai.models import ReflectionEvent
    trigger = "correction" if is_corr else (
        "positive" if result["outcome"] == "success" else "other")
    return ReflectionEvent.objects.create(
        user=user,
        trigger=trigger,
        outcome=result["outcome"],
        trust_delta=result["trust_delta"],
        locus=result["locus"],
        disposition=disposition,
        confidence=result["confidence"],
        topic=result.get("topic", "")[:64],
        user_message=(message or "")[:2000],
        response_excerpt=(response_text or "")[:1000],
        evidence=result.get("evidence", {}),
        directive_key=directive_key[:128],
        eio=eio,
    )


def _slug(text):
    import re
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")[:48]


def _reconstruct(locus, topic, result, message):
    ev = result.get("evidence", {})
    note = ev.get("note", "")
    return (
        f"On a '{topic}' correction, reflection classified the locus as {locus}. "
        f"{note}. User said: \"{(message or '')[:200]}\". "
        f"Beth must not learn this correction — it belongs in Phases 1–3."
    )


def _hypothesis(locus, result):
    cat = result.get("engineering_category", "") or "other"
    return {
        "truth_retrieval": f"Deterministic truth was missing/stale/wrong ({cat}). "
                           f"Fix retrieval/state/serialization in Phase 1.",
        "reasoning": "Truth was available but the reasoning step ignored it. "
                     "Fix the reasoning/pipeline in Phase 2.",
        "execution": "An action did not land. Fix execution (UAIO) in Phase 3.",
        "confidence_calibration": "Stated confidence did not match reality. "
                                  "Review confidence composition.",
    }.get(locus, "Capability gap — review the implicated faculty.")
