"""
Owner Finance Telemetry — LLM usage logging with cost computation.

Usage:
    from apps.owner_finance.services.telemetry import log_llm_usage

    log_llm_usage(
        user=request.user,
        feature='MAIN_RESPONSE',
        engine='PGE',
        model_name='gpt-4o-mini',
        input_tokens=500,
        output_tokens=200,
        escalated=False,
    )
"""

import logging
from datetime import date
from decimal import Decimal

logger = logging.getLogger(__name__)


def log_llm_usage(
    *,
    user=None,
    feature: str,
    engine: str = None,
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    escalated: bool = False,
    conversation_id: str = None,
    metadata: dict = None,
):
    """
    Log an LLM usage event with auto-computed cost from the PriceBook.

    Best-effort: never raises. If PriceBook entry is missing, stores cost=0
    with metadata flag missing_pricebook=True.
    """
    try:
        from apps.owner_finance.models import LLMPriceBook, LLMUsageEvent

        cost_usd = Decimal('0')
        meta = dict(metadata or {})
        today = date.today()

        # Look up price book entry
        price = (
            LLMPriceBook.objects
            .filter(
                model_name=model_name,
                is_active=True,
                effective_start__lte=today,
            )
            .filter(
                models_Q_effective_end_null_or_gte(today)
            )
            .order_by('-effective_start')
            .first()
        )

        if price is None:
            # Fallback: try without date bounds
            price = (
                LLMPriceBook.objects
                .filter(model_name=model_name, is_active=True)
                .order_by('-effective_start')
                .first()
            )

        if price:
            input_cost = (
                Decimal(str(input_tokens))
                * price.input_cost_per_1m_tokens_usd
                / Decimal('1000000')
            )
            output_cost = (
                Decimal(str(output_tokens))
                * price.output_cost_per_1m_tokens_usd
                / Decimal('1000000')
            )
            cost_usd = input_cost + output_cost
        else:
            meta['missing_pricebook'] = True
            logger.debug(
                "No PriceBook entry for model=%s, storing cost=0", model_name
            )

        LLMUsageEvent.objects.create(
            user=user,
            feature=feature,
            engine=engine or '',
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            escalated=escalated,
            conversation_id=conversation_id or '',
            metadata=meta,
        )

    except Exception as exc:
        logger.debug("owner_finance telemetry write failed: %s", exc)


def models_Q_effective_end_null_or_gte(today):
    """Return Q object: effective_end is NULL or >= today."""
    from django.db.models import Q
    return Q(effective_end__isnull=True) | Q(effective_end__gte=today)
