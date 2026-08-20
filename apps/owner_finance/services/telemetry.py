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
    source: str = '',
    traffic_class: str = None,
    cached_input_tokens: int = 0,
    latency_ms: int = 0,
    success: bool = True,
):
    """
    Log an LLM usage event with auto-computed cost from the PriceBook.

    Provenance (cost governance): `source` = the fine-grained logical reason for the
    call (interactive_chat / executive_synthesis / daily_executive_brief / … ), and
    `traffic_class` = the dev-vs-production axis (production / proactive / certification /
    background). Both are observability only — they never influence model reasoning.

    Best-effort: never raises. If PriceBook entry is missing, stores cost=0
    with metadata flag missing_pricebook=True. Records failures honestly (success=False,
    typically zero tokens) so retries/failures are represented, not hidden.
    """
    try:
        from django.db import transaction
        from apps.owner_finance.models import LLMPriceBook, LLMUsageEvent

        cost_usd = Decimal('0')
        cost_is_known = True
        meta = dict(metadata or {})
        today = date.today()
        if traffic_class is None:
            # NEVER default to production — an unclassified call is not evidence of a user.
            traffic_class = LLMUsageEvent.TRAFFIC_UNATTRIBUTED

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
            cost_is_known = False
            # WARNING, not debug: an unpriced model means real spend is invisible in every
            # cost surface. That is exactly how ~$4 of local development spend reported as
            # $0.00 and was first noticed on a credit-card recharge.
            logger.warning(
                "LLM COST UNKNOWN — no PriceBook entry for model=%s. Tokens are recorded "
                "but cost is NOT known; it is reported as unpriced, never as $0.00.",
                model_name,
            )

        # Use savepoint so a failed insert doesn't poison the outer
        # transaction (e.g. Django TestCase's wrapping atomic block).
        with transaction.atomic():
            LLMUsageEvent.objects.create(
                user=user,
                feature=feature,
                engine=engine or '',
                model_name=model_name,
                source=source or '',
                traffic_class=traffic_class,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_input_tokens=cached_input_tokens or 0,
                cost_usd=cost_usd,
                cost_is_known=cost_is_known,
                latency_ms=latency_ms or 0,
                success=success,
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
