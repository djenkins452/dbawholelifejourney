"""
Supporting facts — conversation-object completeness.

A natural follow-up ("what did I eat?" after "how many calories?") should be answered
from facts already gathered, not a fresh retrieval or LLM reasoning. So a PRIMARY fact
declares the SUPPORTING facts a follow-up will need; they are fetched ONCE with the
primary answer and stored on the active conversation object. The follow-up then reads
them from memory.

Generalized (domain-agnostic): any deterministic fact may register supporting facts.
Calories is the first consumer — NOT a special case. To add support for another fact,
add a row to `_SUPPORTING`.
"""
import logging

logger = logging.getLogger(__name__)

# primary fact_key -> tuple of (label, source, provider_key)
#   source: "execution" → execution_facts · "health" → health_facts
_SUPPORTING = {
    "calories_today": (
        ("meals", "execution", "meals_today"),
        ("protein", "health", "protein_today"),
    ),
    "calories_yesterday": (
        ("meals", "execution", "meals_yesterday"),
    ),
}


def gather_supporting(user, fact_key):
    """Return {label: {"key": provider_key, "fact": fact}} for `fact_key`. Empty when
    the fact declares no supporting facts. Deterministic; no LLM."""
    out = {}
    for label, source, provider_key in _SUPPORTING.get(fact_key, ()):
        try:
            if source == "execution":
                from apps.ai.cos_services.execution_facts import (
                    get_foundational_execution_facts,
                )
                f = get_foundational_execution_facts(user, [provider_key]).get(provider_key)
            else:
                from apps.ai.cos_services.health_facts import get_foundational_health_facts
                f = get_foundational_health_facts(user, [provider_key]).get(provider_key)
            if f:
                out[label] = {"key": provider_key, "fact": f}
        except Exception:
            logger.warning("supporting_facts: gather failed key=%s label=%s",
                           fact_key, label, exc_info=True)
    return out
