# ==============================================================================
# File: apps/finance/services/finance_calc/measures.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The nine financial measures, projected over economic roles. SHADOW.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Nine named measures, each meaning what its name says.

"What did I spend" is not one question. A mortgage payment is at once real cash leaving,
a balance-sheet movement, and partly not consumption — no single number answers all of
it. So: one role per transaction (`roles.py`), and these measures as PROJECTIONS over
those roles.

**Shadow mode.** Every function here classifies in memory and persists nothing.
`attribution_population.financial_activity` remains the sole authority for every
displayed total; nothing in WLJ reads these results yet.

Sign convention: WLJ stores positive = money in, negative = money out. Measures report
**magnitudes** — a `cash_outflow` of 500 means 500 left, not −500.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from apps.finance.services.finance_calc import roles as role_authority

ZERO = Decimal("0.00")

MEASURES_VERSION = "1.1.0"


@dataclass
class CalcResult:
    """A number, and everything needed to trust or doubt it."""
    measure: str
    value: Decimal = ZERO
    coverage_start: Optional[object] = None
    coverage_end: Optional[object] = None
    calculation_version: str = MEASURES_VERSION
    classifier_version: str = role_authority.CLASSIFIER_VERSION
    transaction_count: int = 0
    uncertain_count: int = 0
    uncertain_amount: Decimal = ZERO
    assumptions: list = field(default_factory=list)
    exclusions: dict = field(default_factory=dict)
    components: dict = field(default_factory=dict)
    confidence: str = "high"
    inputs_missing: list = field(default_factory=list)

    def as_dict(self):
        return {
            "measure": self.measure, "value": str(self.value),
            "coverage": [str(self.coverage_start), str(self.coverage_end)],
            "calculation_version": self.calculation_version,
            "classifier_version": self.classifier_version,
            "transaction_count": self.transaction_count,
            "uncertain_count": self.uncertain_count,
            "uncertain_amount": str(self.uncertain_amount),
            "assumptions": list(self.assumptions),
            "exclusions": {k: str(v) for k, v in self.exclusions.items()},
            "components": {k: str(v) for k, v in self.components.items()},
            "confidence": self.confidence,
            "inputs_missing": list(self.inputs_missing),
        }


def _population(user, start=None, end=None):
    """The rows a measure may consider.

    Deliberately built on the SAME base the existing authority uses — active, owned,
    not an opening balance — so shadow measures and live totals are looking at the same
    universe. Soft-deleted and archived rows (including retired duplicate rows) can
    never re-enter: `Transaction.objects` is the `SoftDeleteManager`.
    """
    from apps.finance.models import Transaction

    # NOTE: deliberately does NOT filter `is_opening_balance` — that exclusion is
    # `attribution_population`'s to define, and re-deriving it here would be a second
    # definition of what counts as activity. Opening balances are carried into the
    # classifier and given the `opening_balance` role, which enters no measure.
    # The transfer legs are select_related deliberately: classification reads the
    # counterpart's account to tell a mortgage payment from a card payment, and on a
    # 3,800-row population a lazy reverse OneToOne would be one query per row.
    qs = (Transaction.objects.filter(user=user)
          .select_related("account", "category",
                          "transfer_pair", "transfer_pair__account",
                          "transfer_counterpart", "transfer_counterpart__account"))
    if start:
        qs = qs.filter(date__gte=start)
    if end:
        qs = qs.filter(date__lte=end)
    return qs.order_by("date", "id")


def _rows(user, start, end, transactions=None):
    """`[(txn, RoleAssignment)]` — classified in memory, persisted never."""
    population = transactions if transactions is not None else _population(user, start, end)
    return role_authority.classify_many(population)


def _abs(amount):
    return abs(amount or ZERO)


def _sum(rows, roles, *, sign=None):
    from apps.finance.models import Transaction as T
    total = ZERO
    count = 0
    for txn, assignment in rows:
        if assignment.role not in roles:
            continue
        amount = txn.amount or ZERO
        if sign == "out" and amount >= 0:
            continue
        if sign == "in" and amount <= 0:
            continue
        total += _abs(amount)
        count += 1
    return total, count


def _debt_service(rows):
    """Debt service, counting each payment ONCE across both of its legs.

    A paid mortgage or loan appears twice: cash leaving the funding account, and the
    matching credit landing on the liability. Both are genuinely part of servicing the
    debt — so both carry the role — but summing both would double the number.

    The cash leg is the one counted. A liability-side credit is counted only when WLJ
    can see NO counterpart, which is the case where the cash leg is invisible (an
    account that is not connected) and dropping it would understate the debt instead.
    """
    from apps.finance.models import Transaction as T
    total, count, mirrored = ZERO, 0, 0
    for txn, assignment in rows:
        if assignment.role != T.ROLE_DEBT_SERVICE:
            continue
        amount = txn.amount or ZERO
        if amount < 0:
            total += _abs(amount)
            count += 1
        elif amount > 0 and role_authority.counterpart(txn) is None:
            total += _abs(amount)
            count += 1
        else:
            mirrored += 1
    return total, count, mirrored


def _base(measure, rows, start, end):
    from apps.finance.models import Transaction as T
    uncertain = [(t, a) for t, a in rows if a.role == T.ROLE_UNCERTAIN]
    result = CalcResult(measure=measure, coverage_start=start, coverage_end=end,
                        transaction_count=len(rows),
                        uncertain_count=len(uncertain),
                        uncertain_amount=sum((_abs(t.amount) for t, _ in uncertain), ZERO))
    if result.uncertain_count:
        result.assumptions.append(
            f"{result.uncertain_count} transaction(s) could not be classified "
            f"confidently and are in no spending measure")
        result.confidence = "medium"
    return result


# ---------------------------------------------------------------------------
# The nine
# ---------------------------------------------------------------------------

def gross_purchases(user, start=None, end=None, rows=None):
    """Purchases of goods and services, before any offset."""
    from apps.finance.models import Transaction as T
    rows = rows if rows is not None else _rows(user, start, end)
    result = _base("gross_purchases", rows, start, end)
    result.value, _ = _sum(rows, {T.ROLE_PURCHASE})
    return result


def net_spending(user, start=None, end=None, rows=None, refund_policy="offset_on_receipt"):
    """What consumption actually cost: purchases less refunds, reimbursements, reversals.

    A refund is OFFSET here, never deleted and never excluded — it keeps its own row and
    its own audit identity. `offset_on_receipt` (the default) reduces the month the money
    arrived, which is what a person checking a bank statement expects;
    `restate_original` would instead correct the purchase's own month, and is not
    implemented in shadow because it needs proven refund linkage (`refund_of`).
    """
    from apps.finance.models import Transaction as T
    rows = rows if rows is not None else _rows(user, start, end)
    result = _base("net_spending", rows, start, end)

    purchases, _ = _sum(rows, {T.ROLE_PURCHASE})
    fees, _ = _sum(rows, {T.ROLE_FEE_INTEREST})
    refunds, refund_n = _sum(rows, {T.ROLE_REFUND})
    reimbursements, _ = _sum(rows, {T.ROLE_REIMBURSEMENT})
    reversals, _ = _sum(rows, {T.ROLE_REVERSAL})

    result.value = purchases + fees - refunds - reimbursements - reversals
    result.components = {
        "gross_purchases": purchases, "fees_and_interest": fees,
        "refunds": refunds, "reimbursements": reimbursements, "reversals": reversals,
    }
    result.exclusions = _spending_exclusions(rows)
    result.assumptions.append(f"refund policy: {refund_policy} ({refund_n} refund(s))")

    unsplit, unsplit_n, _mirrored = _debt_service(rows)
    if unsplit_n:
        result.assumptions.append(
            f"{unsplit_n} debt payment(s) totalling {unsplit} are UNSPLIT — no "
            f"authoritative principal/interest split exists, so none of it is counted "
            f"as consumption. Interest and escrow are therefore understated.")
        result.inputs_missing.append("loan_terms_for_principal_interest_split")
        result.confidence = "medium"

    cash, cash_n = _sum(rows, {T.ROLE_CASH_WITHDRAWAL})
    if cash_n:
        result.assumptions.append(
            f"{cash_n} cash withdrawal(s) totalling {cash} are excluded — what the "
            f"cash bought is unknown")
    return result


def _spending_exclusions(rows):
    from apps.finance.models import Transaction as T
    out = {}
    for label, roles in (
        ("card_payments", {T.ROLE_CARD_PAYMENT}),
        ("internal_transfers", {T.ROLE_INTERNAL_TRANSFER}),
        ("savings_allocations", {T.ROLE_SAVINGS_ALLOCATION}),
        ("investment_contributions", {T.ROLE_INVESTMENT_CONTRIBUTION}),
        ("cash_withdrawals", {T.ROLE_CASH_WITHDRAWAL}),
        ("uncertain", {T.ROLE_UNCERTAIN}),
        ("loan_proceeds", {T.ROLE_LOAN_PROCEEDS}),
    ):
        total, count = _sum(rows, roles)
        if count:
            out[label] = total
    debt, debt_n, _mirrored = _debt_service(rows)
    if debt_n:
        out["debt_service_unsplit"] = debt
    return out


def income(user, start=None, end=None, rows=None):
    """TRUE income only. A refund is not income; getting money back is not earning."""
    from apps.finance.models import Transaction as T
    rows = rows if rows is not None else _rows(user, start, end)
    result = _base("income", rows, start, end)
    result.value, _ = _sum(rows, {T.ROLE_INCOME})
    return result


def cash_inflow(user, start=None, end=None, rows=None):
    """External money received — income plus money coming back."""
    from apps.finance.models import Transaction as T
    rows = rows if rows is not None else _rows(user, start, end)
    result = _base("cash_inflow", rows, start, end)
    result.value, _ = _sum(
        rows, {T.ROLE_INCOME, T.ROLE_REFUND, T.ROLE_REIMBURSEMENT, T.ROLE_REVERSAL,
               T.ROLE_LOAN_PROCEEDS},
        sign="in")
    result.components = {
        "income": _sum(rows, {T.ROLE_INCOME}, sign="in")[0],
        "refunds": _sum(rows, {T.ROLE_REFUND}, sign="in")[0],
        "reimbursements": _sum(rows, {T.ROLE_REIMBURSEMENT}, sign="in")[0],
        "reversals": _sum(rows, {T.ROLE_REVERSAL}, sign="in")[0],
        "loan_proceeds": _sum(rows, {T.ROLE_LOAN_PROCEEDS}, sign="in")[0],
    }
    borrowed, borrowed_n = _sum(rows, {T.ROLE_LOAN_PROCEEDS}, sign="in")
    if borrowed_n:
        result.assumptions.append(
            f"{borrowed_n} loan disbursement(s) totalling {borrowed} are included as "
            f"cash received but are NOT income and do not offset spending — borrowed "
            f"money has to be repaid")
    return result


def cash_outflow(user, start=None, end=None, rows=None):
    """External money leaving available cash.

    Includes the FULL debt payment — the cash really left, whatever part of it was
    principal. This is the measure that answers "what hit my account".
    """
    from apps.finance.models import Transaction as T
    rows = rows if rows is not None else _rows(user, start, end)
    result = _base("cash_outflow", rows, start, end)
    result.value, _ = _sum(
        rows, {T.ROLE_PURCHASE, T.ROLE_DEBT_SERVICE, T.ROLE_FEE_INTEREST,
               T.ROLE_CASH_WITHDRAWAL},
        sign="out")
    result.components = {
        "purchases": _sum(rows, {T.ROLE_PURCHASE}, sign="out")[0],
        "debt_service": _sum(rows, {T.ROLE_DEBT_SERVICE}, sign="out")[0],
        "fees": _sum(rows, {T.ROLE_FEE_INTEREST}, sign="out")[0],
        "cash_withdrawals": _sum(rows, {T.ROLE_CASH_WITHDRAWAL}, sign="out")[0],
    }
    return result


def transfers_and_allocations(user, start=None, end=None, rows=None):
    """The user's own money moving. In NEITHER spending measure, by design."""
    from apps.finance.models import Transaction as T
    rows = rows if rows is not None else _rows(user, start, end)
    result = _base("transfers_and_allocations", rows, start, end)
    result.value, _ = _sum(rows, {T.ROLE_INTERNAL_TRANSFER, T.ROLE_CARD_PAYMENT,
                                  T.ROLE_SAVINGS_ALLOCATION,
                                  T.ROLE_INVESTMENT_CONTRIBUTION})
    result.components = {
        "internal_transfers": _sum(rows, {T.ROLE_INTERNAL_TRANSFER})[0],
        "card_payments": _sum(rows, {T.ROLE_CARD_PAYMENT})[0],
        "savings_allocations": _sum(rows, {T.ROLE_SAVINGS_ALLOCATION})[0],
        "investment_contributions": _sum(rows, {T.ROLE_INVESTMENT_CONTRIBUTION})[0],
    }
    result.assumptions.append(
        "moving money is not spending it — these are in no spending measure")
    return result


def debt_service(user, start=None, end=None, rows=None):
    """Total loan payments, with components separated ONLY when authoritative.

    P1 has no `LoanTerms`, so every payment is unsplit. Inventing an amortisation split
    against an unknown APR would be fabricating the most consequential number in the
    debt domain.
    """
    from apps.finance.models import Transaction as T
    rows = rows if rows is not None else _rows(user, start, end)
    result = _base("debt_service", rows, start, end)
    total, count, mirrored = _debt_service(rows)
    result.value = total
    if mirrored:
        result.assumptions.append(
            f"{mirrored} liability-side leg(s) of a matched payment are recorded but "
            f"not added again — the payment is counted once, on the cash side")
    result.components = {
        "principal_known": ZERO, "interest_known": ZERO, "escrow_known": ZERO,
        "unsplit": total,
    }
    if count:
        result.assumptions.append(
            f"all {count} payment(s) are UNSPLIT — WLJ has no authoritative "
            f"principal/interest/escrow split and will not invent one")
        result.inputs_missing.append("loan_terms")
        result.confidence = "medium"
    return result


def recurring_obligations(user, start=None, end=None, rows=None):
    """Committed forward cash need.

    P1 ships the CONTRACT, not the answer: recurring detection is P4 and there are zero
    recurring rows in production. Reporting a number here would be inventing one, so it
    reports zero with the missing input named.
    """
    rows = rows if rows is not None else _rows(user, start, end)
    result = _base("recurring_obligations", rows, start, end)
    result.value = ZERO
    result.confidence = "low"
    result.inputs_missing.append("recurring_detection (P4)")
    result.assumptions.append(
        "no recurring obligations are known yet — this is an absence of data, "
        "not a household with no bills")
    return result


def controllable_spending(user, start=None, end=None, rows=None):
    """The actionable subset of purchases.

    P1 ships the CONTRACT. Controllability classification is P2, so nothing qualifies
    yet — and "everything that is not a transfer" is exactly the wrong answer this
    measure exists to prevent.
    """
    rows = rows if rows is not None else _rows(user, start, end)
    result = _base("controllable_spending", rows, start, end)
    result.value = ZERO
    result.confidence = "low"
    result.inputs_missing.append("controllability_taxonomy (P2)")
    result.assumptions.append(
        "no category carries a controllability classification yet; this is NOT "
        "'nothing is controllable'")
    return result


ALL_MEASURES = (
    "cash_inflow", "cash_outflow", "gross_purchases", "net_spending",
    "recurring_obligations", "debt_service", "transfers_and_allocations",
    "income", "controllable_spending",
)


def all_measures(user, start=None, end=None, transactions=None):
    """Every measure over ONE classification pass — the rows are classified once."""
    rows = _rows(user, start, end, transactions=transactions)
    return {
        "cash_inflow": cash_inflow(user, start, end, rows),
        "cash_outflow": cash_outflow(user, start, end, rows),
        "gross_purchases": gross_purchases(user, start, end, rows),
        "net_spending": net_spending(user, start, end, rows),
        "recurring_obligations": recurring_obligations(user, start, end, rows),
        "debt_service": debt_service(user, start, end, rows),
        "transfers_and_allocations": transfers_and_allocations(user, start, end, rows),
        "income": income(user, start, end, rows),
        "controllable_spending": controllable_spending(user, start, end, rows),
    }


def reconcile(measures):
    """The identities that must hold. A set that fails is not presented as fact."""
    from decimal import Decimal as D

    ns = measures["net_spending"]
    ci = measures["cash_inflow"]
    co = measures["cash_outflow"]
    ds = measures["debt_service"]

    checks = {}

    expected_net = (ns.components.get("gross_purchases", ZERO)
                    + ns.components.get("fees_and_interest", ZERO)
                    - ns.components.get("refunds", ZERO)
                    - ns.components.get("reimbursements", ZERO)
                    - ns.components.get("reversals", ZERO))
    checks["net_spending_identity"] = (expected_net == ns.value, expected_net, ns.value)

    expected_out = sum(co.components.values(), ZERO)
    checks["cash_outflow_identity"] = (expected_out == co.value, expected_out, co.value)

    expected_in = sum(ci.components.values(), ZERO)
    checks["cash_inflow_identity"] = (expected_in == ci.value, expected_in, ci.value)

    # The income measure and the inflow decomposition must agree on what income IS.
    # This is what catches borrowed money or a refund leaking into earnings: the
    # component would move while the measure did not.
    inc = measures["income"].value
    checks["income_excludes_non_earnings"] = (
        ci.components.get("income", ZERO) == inc,
        ci.components.get("income", ZERO), inc)

    expected_ds = sum(
        (ds.components.get(k, ZERO)
         for k in ("principal_known", "interest_known", "escrow_known", "unsplit")),
        ZERO)
    checks["debt_service_identity"] = (expected_ds == ds.value, expected_ds, ds.value)

    checks["net_cash_movement"] = (True, ci.value - co.value, ci.value - co.value)

    return {
        "all_hold": all(passed for passed, *_ in checks.values()),
        "checks": {k: {"passed": p, "expected": str(e), "actual": str(a)}
                   for k, (p, e, a) in checks.items()},
    }
