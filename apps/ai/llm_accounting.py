# ==============================================================================
# File: apps/ai/llm_accounting.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: ONE accounting seam for every billable OpenAI provider request.
#   Cost governance (2026-08-16): the certified model_interface runtime previously
#   persisted no token/cost telemetry (tool loop + Executive Synthesis bypassed the
#   ledger), so a cost surge was invisible. This module is the single seam called
#   immediately around each provider invocation: it extracts authoritative provider
#   usage and writes ONE owner_finance LLMUsageEvent (the canonical cost ledger) with
#   deterministic provenance — `source` (why the call exists) + `traffic_class`
#   (production / proactive / certification / background). Provenance flows via
#   contextvars set at the entry point (acceptance task, proactive generator, chat
#   view); it is OBSERVABILITY ONLY and never influences the model's reasoning.
#   Best-effort throughout — accounting must NEVER break a model call.
# ==============================================================================
import contextlib
import logging
from contextvars import ContextVar

logger = logging.getLogger(__name__)

# Contextvars carry provenance from the entry point down to the provider seam without
# threading kwargs through every layer. Defaults describe ordinary production traffic.
_traffic_class_var: ContextVar = ContextVar('wlj_llm_traffic_class', default=None)
_source_var: ContextVar = ContextVar('wlj_llm_source', default=None)

# Traffic-class constants mirror LLMUsageEvent (kept here to avoid importing models at
# module import time).
# An unclassified call is NOT evidence of a real user. `unattributed` is the default so a
# missing classification can never masquerade as production traffic (M5 cost forensics).
TRAFFIC_UNATTRIBUTED = 'unattributed'
TRAFFIC_PRODUCTION = 'production'
TRAFFIC_PROACTIVE = 'proactive'
TRAFFIC_CERTIFICATION = 'certification'
TRAFFIC_BACKGROUND = 'background'

# Fine-grained source vocabulary (deterministic — never inferred from prose).
SOURCE_INTERACTIVE_CHAT = 'interactive_chat'
SOURCE_EXECUTIVE_SYNTHESIS = 'executive_synthesis'
SOURCE_DAILY_EXECUTIVE_BRIEF = 'daily_executive_brief'
SOURCE_PROACTIVE_CHECKIN = 'proactive_checkin'
SOURCE_CONVERSATION_FOLLOW_UP = 'conversation_follow_up'
SOURCE_CERTIFICATION = 'certification'
SOURCE_PERCEPTION = 'perception'
SOURCE_REFLECTION = 'reflection'
# M5: interview turns are billed like chat but must be separable, so the cost of
# deliberate teaching can be answered independently of ordinary conversation.
SOURCE_GETTING_TO_KNOW_YOU = 'getting_to_know_you'

# endpoint → owner_finance feature code (secondary axis; source/traffic_class are primary)
_ENDPOINT_TO_FEATURE = {
    'model_interface': 'COS_CHAT',
    'model_interface_synthesis': 'EXEC_BRIEFING',
    'cos_chat': 'COS_CHAT',
    'cos_briefing': 'EXEC_BRIEFING',
    'executive_briefing': 'EXEC_BRIEFING',
    'proactive_briefing': 'EXEC_BRIEFING',
    'proactive_checkin': 'COS_CHAT',
    'intent_recognition': 'INTENT',
    'journal_reflection': 'JOURNAL_REFLECTION',
}


@contextlib.contextmanager
def llm_traffic_context(*, traffic_class=None, source=None):
    """Set the ambient LLM provenance for the duration of the block. Nesting is safe:
    each token is reset on exit. Pass only what you know — unset values fall through to
    the outer context (or the production default at the seam)."""
    t_tok = _traffic_class_var.set(traffic_class) if traffic_class is not None else None
    s_tok = _source_var.set(source) if source is not None else None
    try:
        yield
    finally:
        if s_tok is not None:
            _source_var.reset(s_tok)
        if t_tok is not None:
            _traffic_class_var.reset(t_tok)


def current_traffic_class():
    return _traffic_class_var.get()


def current_source():
    return _source_var.get()


def _extract_usage(response):
    """Pull authoritative token usage from an OpenAI response. Returns
    (prompt, completion, total, cached). Zeros when usage is absent (recorded honestly)."""
    usage = getattr(response, 'usage', None) if response is not None else None
    if not usage:
        return 0, 0, 0, 0
    prompt = getattr(usage, 'prompt_tokens', 0) or 0
    completion = getattr(usage, 'completion_tokens', 0) or 0
    total = getattr(usage, 'total_tokens', 0) or 0
    cached = 0
    details = getattr(usage, 'prompt_tokens_details', None)
    if details is not None:
        cached = getattr(details, 'cached_tokens', 0) or 0
    elif isinstance(usage, dict):
        cached = (usage.get('prompt_tokens_details') or {}).get('cached_tokens', 0) or 0
    return prompt, completion, total, cached


def record_llm_event(*, model, user=None, prompt_tokens=0, completion_tokens=0,
                     total_tokens=None, cached_tokens=0, success=True, latency_ms=0,
                     source=None, traffic_class=None, endpoint=None,
                     conversation_id=None, attempt=1, surface=None, error_class=None):
    """THE accounting seam: write ONE LLMUsageEvent for one billable provider request.

    Precedence: explicit arg > contextvar > default. Never raises; a telemetry failure
    must never break the model path."""
    try:
        from apps.owner_finance.services.telemetry import log_llm_usage

        resolved_traffic = (traffic_class or _traffic_class_var.get()
                            or TRAFFIC_UNATTRIBUTED)
        resolved_source = (source or _source_var.get()
                          or (SOURCE_EXECUTIVE_SYNTHESIS
                              if endpoint == 'model_interface_synthesis'
                              else SOURCE_INTERACTIVE_CHAT
                              if endpoint == 'model_interface' else (endpoint or '')))
        feature = _ENDPOINT_TO_FEATURE.get(endpoint, 'MAIN_RESPONSE')
        meta = {'endpoint': endpoint, 'attempt': attempt}
        # COST GOVERNOR: a paid call made under a development authorization is stamped with
        # the run that permitted it, and is classified as certification/dev traffic — never
        # production. This is what makes development spend attributable after the fact.
        try:
            from apps.ai.llm_admission import current_admitted_run_id
            _run = current_admitted_run_id()
            if _run:
                meta['llm_run_id'] = _run
                resolved_traffic = TRAFFIC_CERTIFICATION
        except Exception:  # pragma: no cover - accounting must never break a call
            pass
        if surface:
            meta['surface'] = surface
        if total_tokens is not None:
            meta['total_tokens'] = total_tokens
        if error_class:
            meta['error_class'] = error_class
        log_llm_usage(
            user=user,
            feature=feature,
            model_name=model,
            source=resolved_source,
            traffic_class=resolved_traffic,
            input_tokens=int(prompt_tokens or 0),
            output_tokens=int(completion_tokens or 0),
            cached_input_tokens=int(cached_tokens or 0),
            latency_ms=int(latency_ms or 0),
            success=success,
            conversation_id=str(conversation_id) if conversation_id else None,
            metadata=meta,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("record_llm_event failed: %s", exc)


def record_llm_event_from_response(response, *, model, user=None, success=True,
                                   latency_ms=0, source=None, traffic_class=None,
                                   endpoint=None, conversation_id=None, attempt=1,
                                   surface=None):
    """Convenience seam: extract usage from a provider response, then record it."""
    prompt, completion, total, cached = _extract_usage(response)
    record_llm_event(
        model=model, user=user, prompt_tokens=prompt, completion_tokens=completion,
        total_tokens=total, cached_tokens=cached, success=success, latency_ms=latency_ms,
        source=source, traffic_class=traffic_class, endpoint=endpoint,
        conversation_id=conversation_id, attempt=attempt, surface=surface,
    )
