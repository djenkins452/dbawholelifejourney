# ==============================================================================
# File: apps/finance/services/finance_calc/cos_evidence.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Governed, minimum-necessary Finance evidence for the Chief of Staff.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""What the Chief of Staff is allowed to know about the money, and how it is told.

Two rules shape every function here.

**WLJ computes; the model explains.** Nothing in this module asks the model to add,
subtract, amortise or rank. Every figure arrives already calculated by a named
deterministic service, with the version that produced it. A model doing arithmetic over
raw rows is a model that will eventually get it wrong in a way nobody catches, because
its answer looks exactly as confident either way.

**Minimum necessary.** These packets carry aggregates, named entities and calculation
metadata. They do NOT carry tokens, provider identifiers, full account numbers,
addresses, VINs, hull numbers, raw provider payloads, or transaction descriptions. The
model does not need a merchant string to explain a total, and the packet is the only
thing standing between a private ledger and a third-party service.

**Missing is answerable.** Every packet can say what it does not know and what the user
could supply. "I need the APR on the truck before I can compare that" is a good answer.
A confident payoff date derived from an assumed rate is not.
"""
from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

EVIDENCE_VERSION = "2.0.0"

ZERO = Decimal("0.00")

#: Fields that must never reach the model, whatever the caller passes. Enforced by a
#: test that walks every packet this module can produce.
FORBIDDEN_KEYS = frozenset({
    "access_token", "plaid_access_token", "plaid_item_id", "plaid_account_id",
    "plaid_transaction_id", "account_number", "routing_number", "iban",
    "street_address", "address", "vin", "hull_id", "title_number",
    "raw_payload", "provider_payload", "description", "merchant_name", "notes",
})


def _envelope(**extra):
    """The metadata every packet carries, so no figure travels without its provenance."""
    envelope = {
        "as_of": str(timezone.now().date()),
        "evidence_version": EVIDENCE_VERSION,
        "computed_by": "WLJ deterministic finance services",
        "arithmetic_note": (
            "Every figure here was calculated by WLJ. Do not recompute, re-add or "
            "re-rank them — explain them."),
    }
    envelope.update(extra)
    return envelope


# ---------------------------------------------------------------------------
# Measures
# ---------------------------------------------------------------------------

def measures_packet(user, start=None, end=None):
    """The nine measures with coverage, assumptions, exclusions and missing inputs."""
    from apps.finance.services.finance_calc import measures as M

    results = M.all_measures(user, start, end)
    reconciliation = M.reconcile(results)
    return {
        "packet": "financial_measures",
        "period": {"start": str(start) if start else None,
                   "end": str(end) if end else None},
        "measures": {name: result.as_dict() for name, result in results.items()},
        "reconciliation": reconciliation,
        "trustworthy": reconciliation["all_hold"],
        "envelope": _envelope(
            calculation_version=M.MEASURES_VERSION,
            classifier_version=results["net_spending"].classifier_version),
    }


def money_bridge_packet(user, start=None, end=None):
    """How spending, debt, transfers and cash relate. The anti-confusion packet.

    Given only the measures, a model asked "why is what I spent different from what
    left my account?" has to reason its way to an answer and may reason wrongly. This
    hands it the relationship as a fact.
    """
    from apps.finance.services.finance_calc import measures as M

    bridge = M.money_bridge(user, start=start, end=end)
    return {
        "packet": "money_bridge",
        "views": [{"key": v["key"], "label": v["label"],
                   "amount": str(v["amount"]), "means": v["means"]}
                  for v in bridge["views"]],
        "net_liquid_cash_change": str(bridge["net_liquid_cash_change"]),
        "liability_reduction": str(bridge["liability_reduction"]),
        "net_worth_effect_of_debt_payments": str(
            bridge["net_worth_effect_of_debt_payments"]),
        "explains_net_worth": bridge["explains_net_worth"],
        "explains_the_gap": bridge["explains_the_gap"],
        "envelope": _envelope(calculation_version=bridge["calculation_version"]),
    }


def coverage_packet(user):
    """How complete the underlying classification is. Freshness for the measures."""
    from apps.finance.models import Transaction

    rows = Transaction.objects.filter(user=user)
    total = rows.count()
    classified = rows.filter(economic_role__isnull=False).count()
    uncertain = rows.filter(economic_role=Transaction.ROLE_UNCERTAIN).count()
    return {
        "packet": "data_health",
        "transactions": total,
        "classified": classified,
        "unclassified": total - classified,
        "held_for_review": uncertain,
        "pct_classified": round(classified * 100.0 / total, 2) if total else 0.0,
        "envelope": _envelope(),
    }


# ---------------------------------------------------------------------------
# Debt
# ---------------------------------------------------------------------------

def debt_packet(user):
    """Every liability, what WLJ knows about it, and precisely what it does not."""
    from apps.finance.services.finance_calc import payoff as P

    debts = P.debts_for(user)
    return {
        "packet": "debt_facts",
        "debts": [{
            "name": d.name,
            "balance": str(d.balance),
            "apr": str(d.apr) if d.apr is not None else None,
            "minimum_payment": (str(d.minimum_payment)
                                if d.minimum_payment is not None else None),
            "missing_terms": list(d.missing),
        } for d in debts],
        "total_balance": str(sum((d.balance for d in debts), ZERO)),
        "debts_missing_terms": [
            {"name": d.name, "missing": list(d.missing)} for d in debts if d.missing],
        "envelope": _envelope(calculation_version=P.PAYOFF_VERSION),
    }


def payoff_packet(user, *, strategy="avalanche", extra_monthly=ZERO, lump_sum=ZERO,
                  custom_order=None):
    """One worked payoff scenario, with its limitations attached."""
    from apps.finance.services.finance_calc import payoff as P

    scenario = P.simulate(user, strategy, extra_monthly=extra_monthly,
                          lump_sum=lump_sum, custom_order=custom_order)
    return {
        "packet": "payoff_scenario",
        "scenario": scenario.as_dict(),
        "answerable": scenario.months is not None,
        "envelope": _envelope(calculation_version=P.PAYOFF_VERSION),
    }


def payoff_comparison_packet(user, *, extra_monthly=ZERO, lump_sum=ZERO):
    """Snowball against avalanche against minimums — a trade, never a verdict."""
    from apps.finance.services.finance_calc import payoff as P

    return {
        "packet": "payoff_comparison",
        **P.compare(user, extra_monthly=extra_monthly, lump_sum=lump_sum),
        "envelope": _envelope(calculation_version=P.PAYOFF_VERSION),
    }


def single_debt_priority_packet(user, name_fragment):
    """"Should I pay off X first?" — answered against the alternatives, or refused."""
    from apps.finance.services.finance_calc import payoff as P

    debts = P.debts_for(user)
    fragment = (name_fragment or "").strip().lower()
    matches = [d for d in debts if fragment and fragment in d.name.lower()]

    if not matches:
        return {
            "packet": "debt_priority",
            "answerable": False,
            "reason": "no_such_debt",
            "detail": (f"No liability matching '{name_fragment}' is recorded in WLJ. "
                       f"It can be added by hand — WLJ does not need the institution "
                       f"connected to plan around a debt."),
            "known_debts": [d.name for d in debts],
            "envelope": _envelope(),
        }

    target = matches[0]
    comparison = P.compare(user)
    avalanche = comparison["scenarios"]["avalanche"]

    if target.missing:
        return {
            "packet": "debt_priority",
            "answerable": False,
            "reason": "missing_terms",
            "debt": target.name,
            "missing": list(target.missing),
            "detail": (f"WLJ has {target.name} at {target.balance} but is missing "
                       f"{', '.join(target.missing)}. Ranking it against the other "
                       f"debts needs those; WLJ will not assume a rate."),
            "what_is_still_true": {
                "balance": str(target.balance),
                "other_debts": [d.name for d in debts if d.key != target.key],
            },
            "envelope": _envelope(calculation_version=P.PAYOFF_VERSION),
        }

    position = (avalanche["order"].index(target.name) + 1
                if target.name in avalanche["order"] else None)
    return {
        "packet": "debt_priority",
        "answerable": True,
        "debt": target.name,
        "avalanche_position": position,
        "avalanche_order": avalanche["order"],
        "snowball_order": comparison["scenarios"]["snowball"]["order"],
        "trade_off": comparison["trade_off"],
        "envelope": _envelope(calculation_version=P.PAYOFF_VERSION),
    }


# ---------------------------------------------------------------------------
# Spending, obligations and opportunities
# ---------------------------------------------------------------------------

def obligations_packet(user):
    """Confirmed commitments and expected income, with candidates counted separately."""
    from apps.finance.models import RecurringSeries as RS
    from apps.finance.services.finance_calc import recurring as REC

    total, unknown = REC.monthly_obligation_total(user)
    candidates = RS.objects.filter(user=user, status="active",
                                   review_state=RS.REVIEW_CANDIDATE).count()
    return {
        "packet": "recurring_obligations",
        "monthly_committed": str(total),
        "confirmed": [{
            "name": s.name, "kind": s.kind, "frequency": s.frequency,
            "monthly_equivalent": (
                str(s.monthly_equivalent(use='max' if s.is_variable else 'expected'))
                if s.monthly_equivalent(use='max' if s.is_variable else 'expected')
                else None),
            "variable": s.is_variable,
            "next_due": str(s.next_due_date) if s.next_due_date else None,
            "confidence": s.confidence,
        } for s in REC.confirmed_obligations(user)],
        "expected_income": [{
            "name": s.name, "frequency": s.frequency,
            "monthly_equivalent": (str(s.monthly_equivalent())
                                   if s.monthly_equivalent() else None),
        } for s in REC.confirmed_income(user)],
        "awaiting_review": candidates,
        "not_monthly_expressible": [s.name for s in unknown],
        "envelope": _envelope(detector_version=REC.DETECTOR_VERSION),
    }


def controllable_packet(user):
    """The ranked controllable costs, and what is stopping a better answer."""
    from apps.finance.services.finance_calc import opportunities as OPP

    return {
        "packet": "controllable_costs",
        **OPP.largest_controllable_cost(user),
        "envelope": _envelope(engine_version=OPP.ENGINE_VERSION),
    }


def find_amount_packet(user, target):
    """"Find me $X a month" — a specific plan, or a specific shortfall."""
    from apps.finance.services.finance_calc import opportunities as OPP

    return {
        "packet": "savings_plan",
        **OPP.find_amount(user, target),
        "envelope": _envelope(engine_version=OPP.ENGINE_VERSION),
    }


def opportunities_packet(user, limit=10):
    from apps.finance.services.finance_calc import opportunities as OPP

    return {
        "packet": "savings_opportunities",
        "opportunities": [{
            "title": o.title, "kind": o.kind,
            "projected_monthly": str(o.projected_monthly_savings),
            "realized_monthly": (str(o.realized_monthly_savings)
                                 if o.realized_monthly_savings is not None else None),
            "confidence": o.confidence, "effort": o.effort,
            "disruption": o.disruption, "decision": o.decision,
            "rationale": o.rationale,
            "reduces_household_spending": o.reduces_spending,
        } for o in OPP.ranked(user, limit=limit)],
        "envelope": _envelope(engine_version=OPP.ENGINE_VERSION),
    }


# ---------------------------------------------------------------------------
# Forecast, net worth, plans and health
# ---------------------------------------------------------------------------

def forecast_packet(user, horizon_days=30):
    """Free cash flow — the one figure that answers "can I afford this"."""
    from apps.finance.services.finance_calc import forecast as F

    result = F.build(user, horizon_days=horizon_days)
    return {
        "packet": "cash_flow_forecast",
        "horizon_days": result["horizon_days"],
        "projectable": result["projectable"],
        "starting_liquid": str(result["starting_liquid"]),
        "expected_inflow": str(result["expected_inflow"]),
        "committed_outflow": str(result["committed_outflow"]),
        "committed_breakdown": {k: str(v) for k, v
                                in result["committed_breakdown"].items()},
        "provisional_outflow": str(result["provisional_outflow"]),
        "provisional_count": result["provisional_count"],
        "provisional_note": result["provisional_note"],
        "reserve_floor": str(result["reserve_floor"]),
        "projected_ending_cash": str(result["projected_ending_cash"]),
        "free_cash_flow": str(result["free_cash_flow"]),
        "lowest_projected_balance": str(result["lowest_projected_balance"]),
        "lowest_balance_date": result["lowest_balance_date"],
        "debts_without_a_minimum": result["debts_without_a_minimum"],
        "confidence": result["confidence"],
        "inputs_missing": result["inputs_missing"],
        "assumptions": result["assumptions"],
        "setup": F.setup_state(user),
        "envelope": _envelope(calculation_version=F.FORECAST_VERSION),
    }


def affordability_packet(user, monthly_amount, horizon_days=90):
    """"Can I put an extra $X a month towards debt without breaking the floor?"

    Answered against the reserve the person actually set. With no floor set, WLJ says
    the question cannot be answered rather than inventing an emergency-fund target and
    ruling on it.
    """
    from decimal import Decimal as D

    from apps.finance.services.finance_calc import forecast as F

    amount = D(str(monthly_amount))
    result = F.build(user, horizon_days=horizon_days)
    months = D(horizon_days) / D("30.4375")
    extra = (amount * months).quantize(D("0.01"))

    if not result["projectable"]:
        return {
            "packet": "affordability",
            "answerable": False,
            "reason": "no_forecast",
            "detail": ("Nothing is confirmed yet, so WLJ has no committed cash to "
                       "subtract. It will not guess whether you can afford this."),
            "setup": F.setup_state(user),
            "envelope": _envelope(calculation_version=F.FORECAST_VERSION),
        }

    remaining = result["free_cash_flow"] - extra
    if result["reserve_floor"] == D("0.00"):
        return {
            "packet": "affordability",
            "answerable": False,
            "reason": "no_reserve_target",
            "detail": ("You have not set a reserve floor, so 'without dropping below "
                       "it' has nothing to test against. Set one and this becomes a "
                       "real answer."),
            "free_cash_flow": str(result["free_cash_flow"]),
            "extra_over_horizon": str(extra),
            "would_leave": str(remaining),
            "envelope": _envelope(calculation_version=F.FORECAST_VERSION),
        }

    return {
        "packet": "affordability",
        "answerable": True,
        "monthly_amount": str(amount),
        "horizon_days": horizon_days,
        "free_cash_flow": str(result["free_cash_flow"]),
        "extra_over_horizon": str(extra),
        "would_leave": str(remaining),
        "fits": remaining >= D("0.00"),
        "reserve_floor": str(result["reserve_floor"]),
        "confidence": result["confidence"],
        "inputs_missing": result["inputs_missing"],
        "envelope": _envelope(calculation_version=F.FORECAST_VERSION),
    }


def net_worth_packet(user):
    """Position, composition and every stated gap. No addresses, no VINs."""
    from apps.finance.services.finance_calc import net_worth as NW

    position = NW.compose(user)
    return {
        "packet": "net_worth",
        "as_of": position["as_of"],
        "cash_and_financial": str(position["cash_and_financial"]),
        "investments": str(position["investments"]),
        "tangible_assets": str(position["tangible_assets"]),
        "gross_assets": str(position["gross_assets"]),
        "liabilities": str(position["liabilities"]),
        "net_worth": str(position["net_worth"]),
        # Name, type, value, source, age, linked debt, equity, inclusion. Nothing that
        # identifies the thing itself — no address, VIN, hull number or title.
        "assets": [{
            "name": row["name"], "type": row["type"], "value": row["value"],
            "source": row["source"], "as_of": row["as_of"],
            "age_days": row["age_days"], "linked_debt": row["linked_debt"],
            "equity": row["equity"], "included": row["included"],
            "reason": row.get("reason"), "stale": row.get("stale", False),
        } for row in position["asset_rows"]],
        "unvalued_assets": position["unvalued_assets"],
        "stale_valuations": position["stale_valuations"],
        "confidence": position["confidence"],
        "assumptions": position["assumptions"],
        "inputs_missing": position["inputs_missing"],
        "envelope": _envelope(calculation_version=NW.NET_WORTH_VERSION),
    }


def net_worth_history_packet(user, days=365):
    from apps.finance.services.finance_calc import net_worth as NW

    return {
        "packet": "net_worth_history",
        **NW.history(user, days=days),
        "envelope": _envelope(calculation_version=NW.NET_WORTH_VERSION),
    }


def plan_results_packet(user):
    """Projected against realized. The two are never the same field."""
    from apps.finance.models import SavingsOpportunity as SO
    from apps.finance.services.finance_calc import outcomes as OUT

    tracked = [o for o in SO.objects.filter(user=user, status="active")
               .select_related("series") if o.is_being_tracked]
    return {
        "packet": "plan_results",
        "tracked": len(tracked),
        "underperforming": OUT.underperforming(user),
        "plans": [{
            "title": o.title, "decision": o.decision, "outcome": o.outcome,
            "projected_monthly": str(o.projected_monthly_savings),
            "realized_monthly": (str(o.realized_monthly_savings)
                                 if o.realized_monthly_savings is not None else None),
            "variance": str(o.variance) if o.variance is not None else None,
            "started_on": str(o.started_on) if o.started_on else None,
            "measurable": o.is_measurable,
            "note": (o.outcome_evidence or {}).get("note"),
        } for o in tracked],
        "note": ("'You could save' and 'you have saved' are different sentences. "
                 "Projected and realized are separate fields and are never merged."),
        "envelope": _envelope(calculation_version=OUT.OUTCOMES_VERSION),
    }


def data_health_packet(user):
    """What is stale, missing or unresolved — and where to fix each one."""
    from apps.finance.services.finance_calc import data_health as DH

    return {
        "packet": "data_health_detail",
        **DH.evaluate(user),
        "envelope": _envelope(calculation_version=DH.DATA_HEALTH_VERSION),
    }


# ---------------------------------------------------------------------------
# The whole picture
# ---------------------------------------------------------------------------

def snapshot_packet(user):
    """One reconciled financial position, for "how am I doing"."""
    from apps.finance.services.finance_calc import measures as M

    measures = measures_packet(user)
    debt = debt_packet(user)
    obligations = obligations_packet(user)
    coverage = coverage_packet(user)
    return {
        "packet": "financial_snapshot",
        "measures": measures["measures"],
        "reconciliation": measures["reconciliation"],
        "spending_bridge": {
            "difference_from_gross": str(
                M.spending_bridge(
                    M.all_measures(user)["net_spending"])["difference_from_gross"]),
            "explains": ("Net spending can exceed gross purchases: fees and interest "
                         "are a cost of consumption but are not purchases."),
        },
        "debt": debt,
        "money_bridge": money_bridge_packet(user),
        "obligations": obligations,
        "net_worth": net_worth_packet(user),
        "forecast": forecast_packet(user),
        "plans": plan_results_packet(user),
        "data_health": coverage,
        "trustworthy": measures["trustworthy"],
        "envelope": _envelope(calculation_version=M.MEASURES_VERSION),
    }
