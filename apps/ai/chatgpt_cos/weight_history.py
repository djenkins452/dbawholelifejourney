# ==============================================================================
# File: apps/ai/chatgpt_cos/weight_history.py
# Capability: HISTORICAL WEIGHT RETRIEVAL (Weight Entity Completeness). Treats Weight
# exactly like Sleep — current weight and "yesterday" already work; specific historical
# dates failed. Resolves an explicit/relative date and reads the canonical weight for
# THAT day (weight_queries.on_date). Deterministic; never inferred or summarized.
# Declines (None) when there is no date reference, so the existing current-weight path
# keeps its job.
# ==============================================================================
import logging

logger = logging.getLogger(__name__)

_WEIGHT_CUES = ("weight", "weigh", "weighed")


def answer(user, message, conversation=None):
    n = (message or "").lower()
    if not any(c in n for c in _WEIGHT_CUES):
        return None
    from apps.ai.chatgpt_cos.date_reference import resolve_reference_date, fmt_date
    target = resolve_reference_date(user, message, include_today=False)
    if target is None:
        return None
    try:
        from apps.health.services.weight_queries import on_date
        rec = on_date(user, target)
    except Exception:
        logger.warning("weight_history: retrieval failed", exc_info=True)
        return None
    if rec is None:
        ans = f"I don't have a weight reading for {fmt_date(target)}."
    else:
        ans = f"On {fmt_date(target)} you weighed {rec['value_lb']} lb."
    return {"answer": ans, "tools_called": [], "tools_advertised": [],
            "lane": "weight_history", "weight_date": target.isoformat()}
