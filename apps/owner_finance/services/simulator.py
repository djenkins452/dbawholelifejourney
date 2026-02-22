"""Scenario simulator for projecting costs, revenue, and margin."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict

from apps.owner_finance.models import LLMPriceBook, VendorBillingRecord


@dataclass
class SimulationResult:
    monthly_llm_cost: Decimal = Decimal('0')
    monthly_non_llm_cost: Decimal = Decimal('0')
    monthly_total_cost: Decimal = Decimal('0')
    monthly_revenue: Decimal = Decimal('0')
    gross_margin: Decimal = Decimal('0')
    margin_pct: Decimal = Decimal('0')
    per_user_cost: Decimal = Decimal('0')
    per_user_revenue: Decimal = Decimal('0')
    break_even_users: int = 0


# Observed average tokens per call by model (from real usage patterns)
DEFAULT_AVG_TOKENS = {
    'gpt-4o': (800, 300),
    'gpt-4o-mini': (500, 200),
}


def simulate_scenario(
    user_count: int,
    avg_interactions_per_day: float,
    escalation_rate: float,
    model_mix: Dict[str, float],
    tier_mix: Dict[str, float],
    tier_prices: Dict[str, Decimal],
    avg_tokens_per_call: Dict[str, tuple] = None,
) -> SimulationResult:
    """
    Project monthly costs, revenue, and margin for a given scenario.

    Args:
        user_count: Total users
        avg_interactions_per_day: Average LLM calls per user per day
        escalation_rate: 0.0–1.0 fraction of calls that escalate
        model_mix: {"gpt-4o": 0.1, "gpt-4o-mini": 0.9}
        tier_mix: {"FREE": 0.6, "STUDENT": 0.2, "ADULT": 0.2}
        tier_prices: {"FREE": Decimal("0"), "STUDENT": Decimal("3.99"), ...}
        avg_tokens_per_call: Override {model: (input_tokens, output_tokens)}
    """
    if avg_tokens_per_call is None:
        avg_tokens_per_call = DEFAULT_AVG_TOKENS

    days_per_month = 30
    total_calls_per_month = int(user_count * avg_interactions_per_day * days_per_month)

    # Compute LLM cost
    monthly_llm_cost = Decimal('0')
    for model_name, mix_pct in model_mix.items():
        calls_for_model = int(total_calls_per_month * mix_pct)
        input_tok, output_tok = avg_tokens_per_call.get(model_name, (500, 200))

        # Look up pricing
        price = (
            LLMPriceBook.objects
            .filter(model_name=model_name, is_active=True)
            .order_by('-effective_start')
            .first()
        )
        if price:
            cost_per_call = (
                Decimal(str(input_tok)) * price.input_cost_per_1m_tokens_usd / Decimal('1000000')
                + Decimal(str(output_tok)) * price.output_cost_per_1m_tokens_usd / Decimal('1000000')
            )
        else:
            cost_per_call = Decimal('0')

        monthly_llm_cost += cost_per_call * calls_for_model

    # Escalation adds ~2x cost for escalated calls
    escalation_extra = monthly_llm_cost * Decimal(str(escalation_rate))
    monthly_llm_cost += escalation_extra

    # Non-LLM cost: average from recent vendor billing records
    recent_non_llm = (
        VendorBillingRecord.objects
        .exclude(vendor__category='LLM')
        .order_by('-period_start')[:3]
    )
    if recent_non_llm:
        monthly_non_llm_cost = sum(r.cost_usd for r in recent_non_llm) / len(recent_non_llm)
    else:
        monthly_non_llm_cost = Decimal('0')

    monthly_total_cost = monthly_llm_cost + monthly_non_llm_cost

    # Revenue
    monthly_revenue = Decimal('0')
    for tier, mix_pct in tier_mix.items():
        tier_users = int(user_count * mix_pct)
        price = tier_prices.get(tier, Decimal('0'))
        monthly_revenue += price * tier_users

    gross_margin = monthly_revenue - monthly_total_cost
    margin_pct = (gross_margin / monthly_revenue * 100) if monthly_revenue else Decimal('0')

    per_user_cost = monthly_total_cost / user_count if user_count else Decimal('0')
    per_user_revenue = monthly_revenue / user_count if user_count else Decimal('0')

    # Break-even: how many users at this per-user revenue to cover total cost
    break_even_users = 0
    if per_user_revenue > 0:
        break_even_users = int(monthly_total_cost / per_user_revenue) + 1

    return SimulationResult(
        monthly_llm_cost=monthly_llm_cost.quantize(Decimal('0.01')),
        monthly_non_llm_cost=monthly_non_llm_cost.quantize(Decimal('0.01')),
        monthly_total_cost=monthly_total_cost.quantize(Decimal('0.01')),
        monthly_revenue=monthly_revenue.quantize(Decimal('0.01')),
        gross_margin=gross_margin.quantize(Decimal('0.01')),
        margin_pct=margin_pct.quantize(Decimal('0.1')),
        per_user_cost=per_user_cost.quantize(Decimal('0.0001')),
        per_user_revenue=per_user_revenue.quantize(Decimal('0.01')),
        break_even_users=break_even_users,
    )
