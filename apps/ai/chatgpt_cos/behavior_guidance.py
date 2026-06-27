# ==============================================================================
# File: apps/ai/chatgpt_cos/behavior_guidance.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Personal Knowledge — Layer 4 (Behavior Guidance), P36. The provider
#   for learned BehaviorDirectives: learn (with COMPRESSION — one row per key),
#   reinforce, contradict, and the active-directive map the Executive Interpretation
#   Engine consumes to ADAPT behavior. Knowledge here exists ONLY because it changes
#   a future recommendation/conversation/decision; explainability is first-class.
#   Design: docs/BETH_PERSONAL_KNOWLEDGE_DESIGN.md.
# ==============================================================================
import logging

logger = logging.getLogger(__name__)

# A directive only influences behavior once it is at least modestly confident.
MIN_ACTIONABLE_CONFIDENCE = 0.5


def get_active_directives(user):
    """Active directives for a user, most-confident first. Deterministic, defensive."""
    try:
        from apps.core.ai_memory.models import BehaviorDirective
        return list(BehaviorDirective.objects.filter(user=user, status="active")
                    .order_by("-confidence", "-evidence_count"))
    except Exception:
        logger.warning("behavior_guidance: read failed", exc_info=True)
        return []


def directive_map(user):
    """{key: directive} for ACTIONABLE (active, confident) directives — the seam the
    Interpretation Engine reads to change behavior."""
    return {d.key: d for d in get_active_directives(user)
            if d.confidence >= MIN_ACTIONABLE_CONFIDENCE}


def learn(user, key, *, observation, behavior_change, layer="preference",
          meaning="", source="observed", evidence="", base_confidence=None):
    """Learn (or REINFORCE) a behavior directive. COMPRESSION: one row per (user,key)
    — re-learning the same understanding strengthens it (confidence + evidence_count)
    rather than creating a duplicate. Knowledge gets richer, not larger."""
    try:
        from apps.core.ai_memory.models import BehaviorDirective
    except Exception:
        logger.warning("behavior_guidance: model import failed", exc_info=True)
        return None
    key = (key or "").strip()
    if not key:
        return None
    start = base_confidence if base_confidence is not None else \
        BehaviorDirective.SOURCE_WEIGHT.get(source, 0.5)
    obj = BehaviorDirective.objects.filter(user=user, key=key).first()
    if obj is None:
        from django.utils import timezone
        return BehaviorDirective.objects.create(
            user=user, key=key, layer=layer, observation=observation, meaning=meaning,
            behavior_change=behavior_change, confidence=round(float(start), 3),
            source=source, evidence=evidence, evidence_count=1, status="active",
            last_reinforced_at=timezone.now())
    # Existing -> reinforce (compression). Keep the richest text we have.
    obj.reinforce(source=source)
    if evidence and evidence not in (obj.evidence or ""):
        obj.evidence = ((obj.evidence + " | ") if obj.evidence else "") + evidence
    if meaning and not obj.meaning:
        obj.meaning = meaning
    if behavior_change and len(behavior_change) > len(obj.behavior_change or ""):
        obj.behavior_change = behavior_change
    obj.save()
    return obj


def contradict(user, key, *, by=0.3, source=None, note=""):
    """A contradicted observation WEAKENS the prior conclusion (confidence ↓ → weak →
    retired). Beth becomes wiser, not just larger."""
    try:
        from apps.core.ai_memory.models import BehaviorDirective
        obj = BehaviorDirective.objects.filter(user=user, key=key).first()
    except Exception:
        logger.warning("behavior_guidance: contradict failed", exc_info=True)
        return None
    if obj is None:
        return None
    obj.weaken(by=by)
    if source:
        obj.source = source
    if note:
        obj.evidence = ((obj.evidence + " | ") if obj.evidence else "") + note
    obj.save()
    return obj


def explain(user, key):
    """Why Beth behaves this way — traces to evidence (never invented)."""
    try:
        from apps.core.ai_memory.models import BehaviorDirective
        obj = BehaviorDirective.objects.filter(user=user, key=key).first()
        return obj.explain() if obj else ""
    except Exception:
        return ""
