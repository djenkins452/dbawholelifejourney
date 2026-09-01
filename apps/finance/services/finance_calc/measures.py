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

from django.db.models import Q

from apps.finance.services.finance_calc import roles as role_authority

ZERO = Decimal("0.00")

MEASURES_VERSION = "2.0.0"


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


def movement_key(txn):
    """A stable identity for the MOVEMENT, shared by both legs of a pair.

    Derived from both primary keys, so whichever leg is inspected first yields the same
    key. This is what lets a household total count one movement once without caring
    which leg physically carries the OneToOne column — the absence of it is why a
    1,500 card payment read as 3,000 of transfers.
    """
    from apps.finance.services.transfer_detection import paired_counterpart

    other = paired_counterpart(txn)
    if other is None:
        return ("single", txn.pk)
    return ("pair", min(txn.pk, other.pk), max(txn.pk, other.pk))


def _movements(rows, roles):
    """Household movements, each counted ONCE and attributed to ONE role.

    Both legs of a pair carry the same magnitude, so keeping either gives the household
    amount. Account-level movement stays fully visible per account — this is the
    household view, where the same money appearing twice would be wrong.

    **The two legs can carry DIFFERENT roles** — a transfer out of savings that lands as
    a savings allocation, say. Bucketing per role independently then counts that one
    movement in two components, and the components stop summing to the total. So the
    movement is attributed once, to the OUTflow leg's role where there is one, matching
    the convention that the outflow leg carries the pair link.

    Returns `(total, {role: amount}, movement_count, mixed_role_count)`.
    """
    chosen = {}
    for txn, assignment in rows:
        if assignment.role not in roles:
            continue
        key = movement_key(txn)
        existing = chosen.get(key)
        outflow = (txn.amount or ZERO) < ZERO
        if existing is None:
            chosen[key] = {"amount": _abs(txn.amount), "role": assignment.role,
                           "from_outflow": outflow, "roles": {assignment.role}}
            continue
        existing["roles"].add(assignment.role)
        # The outflow leg wins. Whichever leg arrived first, the answer is the same.
        if outflow and not existing["from_outflow"]:
            existing["role"] = assignment.role
            existing["from_outflow"] = True

    total, by_role, mixed = ZERO, {}, 0
    for movement in chosen.values():
        total += movement["amount"]
        by_role[movement["role"]] = by_role.get(movement["role"], ZERO) \
            + movement["amount"]
        if len(movement["roles"]) > 1:
            mixed += 1
    return total, by_role, len(chosen), mixed


def _on_cash_account(txn):
    """Does this row move the household's actual cash?

    A payment landing on a credit card is not money arriving, and counting it as cash
    in would overstate inflow by the size of the card payment. Cash is measured where
    the cash is.
    """
    account_type = getattr(getattr(txn, "account", None), "account_type", "") or ""
    return account_type in role_authority.CASH_ACCOUNT_TYPES


def _uncertain_cash(rows, sign):
    """Cash that genuinely moved on a cash account but whose MEANING is unresolved.

    Uncertainty about what a payment was for is not uncertainty about whether the money
    left. A mortgage payment whose counterpart WLJ failed to match still leaves the
    chequing account, and a cash-flow figure that omits it is simply wrong. So it stays
    in the cash measures, as its own named component, and out of every spending measure.
    """
    from apps.finance.models import Transaction as T
    total, count = ZERO, 0
    for txn, assignment in rows:
        if assignment.role != T.ROLE_UNCERTAIN or not _on_cash_account(txn):
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

def consumption_roles():
    """The roles that ARE consumption — what `net_spending` is built from.

    Published so a surface can ask the authority "is this row spending?" instead of
    answering it for itself. A negative amount is not the same question: a mortgage
    payment, a card payment and a transfer out are all negative and none of them is
    consumption.
    """
    from apps.finance.models import Transaction as T
    return frozenset({T.ROLE_PURCHASE, T.ROLE_FEE_INTEREST})


def could_be_consumption_q(prefix=""):
    """A queryset BOUND for a ranked spending read — never the verdict.

    Bounds the read at the database so a capped ranking keeps the top SPENDS rather
    than the top outflows: the difference between "your largest spend was 849.84"
    meaning a purchase and meaning an auto-loan payment.

    Deliberately **fails open**. A row whose role has not been persisted yet — freshly
    synced, imported by a path that does not classify — is KEPT, because dropping it at
    the bound would make it silently unrankable, which is the same class of defect this
    fixes. The bound narrows; `spend_magnitude` decides, live, and fails closed.
    """
    role = f"{prefix}economic_role"
    return (Q(**{f"{role}__in": sorted(consumption_roles())})
            | Q(**{f"{role}__isnull": True})
            | Q(**{role: ""}))


def spend_magnitude(txn, *, assignment=None):
    """What this row cost, as a positive number — or None if it is not consumption.

    `None`, never zero. The ranked-entity capability EXCLUDES a missing measure rather
    than coercing it, so a debt payment, a card payment, a transfer or an unexplained
    row cannot be ranked as a purchase by construction.

    This exists because "spend" was being read off the SIGN. Every outflow is negative;
    only some of them are spending. Ranking on the sign made an auto-loan payment the
    largest "spend" of the month, which is true of the bank statement and false of the
    question the person asked.
    """
    amount = txn.amount or ZERO
    if amount >= ZERO:
        return None
    assignment = assignment if assignment is not None else role_authority.classify(txn)
    if assignment.role not in consumption_roles():
        return None
    return _abs(amount)


def payment_roles():
    """The roles that are DEBT/PAYMENT activity — servicing or settling borrowing.

    Published beside `consumption_roles()` so a surface asks the authority "is this a
    payment?" instead of answering it for itself. These are real, important outflows —
    a mortgage, a car loan, a credit-card settlement — and they are NOT consumption:
    counting a card payment as spending double-counts the purchases it settles, which
    were already spending when they were made.
    """
    from apps.finance.models import Transaction as T
    return frozenset({T.ROLE_DEBT_SERVICE, T.ROLE_CARD_PAYMENT})


def outflow_roles():
    """Every role that represents money genuinely LEAVING the household.

    Broader than consumption and broader than payments: purchases, fees, cash out,
    debt service and card settlement all move money out. Deliberately EXCLUDES
    `internal_transfer` — moving your own money between your own accounts is not money
    leaving, and totalling it as "out" is how a transfer becomes a phantom expense.
    Savings and investment contributions are excluded for the same reason: the money is
    still the household's.
    """
    from apps.finance.models import Transaction as T
    return consumption_roles() | payment_roles() | frozenset({T.ROLE_CASH_WITHDRAWAL})


def _magnitude_for(txn, roles, assignment=None):
    """Shared shape for the published per-row magnitudes: a positive number when the
    row belongs to `roles`, else `None` — never zero, so the ranked-entity capability
    EXCLUDES it rather than coercing it into the ranking."""
    amount = txn.amount or ZERO
    if amount >= ZERO:
        return None
    assignment = assignment if assignment is not None else role_authority.classify(txn)
    if assignment.role not in roles:
        return None
    return _abs(amount)


def payment_magnitude(txn, *, assignment=None):
    """What this debt/payment movement cost, or `None` if it is not one."""
    return _magnitude_for(txn, payment_roles(), assignment)


def outflow_magnitude(txn, *, assignment=None):
    """What left the household on this row, or `None` if nothing did."""
    return _magnitude_for(txn, outflow_roles(), assignment)


def could_be_payment_q(prefix=""):
    """Queryset bound for a ranked PAYMENT read — narrows only; fails open on an
    unpersisted role exactly like `could_be_consumption_q`."""
    role = f"{prefix}economic_role"
    return (Q(**{f"{role}__in": sorted(payment_roles())})
            | Q(**{f"{role}__isnull": True})
            | Q(**{role: ""}))


def could_be_outflow_q(prefix=""):
    """Queryset bound for a ranked CASH-OUTFLOW read. Narrows only; fails open."""
    role = f"{prefix}economic_role"
    return (Q(**{f"{role}__in": sorted(outflow_roles())})
            | Q(**{f"{role}__isnull": True})
            | Q(**{role: ""}))


def spend_by_category(user, start=None, end=None, rows=None, limit=None):
    """CONSUMPTION spending aggregated by category — Finance does the arithmetic.

    The model must never be handed hundreds of transactions and asked to total them:
    that is a calculation, and calculations are WLJ's (Article I.3). Uses the same
    `spend_magnitude` verdict as every other spending surface, so a category total and
    the ranked purchases inside it can never disagree about what counts.

    Returns `[{category, total, count, largest}]`, largest total first.
    """
    # `_rows` yields `[(txn, RoleAssignment)]` — classified once, in memory. Reusing
    # the assignment keeps this aggregation on exactly the same verdict every other
    # spending surface uses, instead of re-classifying and risking a second opinion.
    rows = rows if rows is not None else _rows(user, start, end)
    buckets = {}
    for txn, assignment in rows:
        magnitude = spend_magnitude(txn, assignment=assignment)
        if magnitude is None:
            continue
        name = (getattr(getattr(txn, "category", None), "name", None) or "Uncategorised")
        bucket = buckets.setdefault(name, {"category": name, "total": ZERO,
                                           "count": 0, "largest": ZERO})
        bucket["total"] += magnitude
        bucket["count"] += 1
        if magnitude > bucket["largest"]:
            bucket["largest"] = magnitude
    ordered = sorted(buckets.values(), key=lambda b: (-b["total"], b["category"]))
    return ordered[:limit] if limit else ordered


def gross_purchases(user, start=None, end=None, rows=None):
    """Purchases of goods and services, before any offset."""
    from apps.finance.models import Transaction as T
    rows = rows if rows is not None else _rows(user, start, end)
    result = _base("gross_purchases", rows, start, end)
    result.value, _ = _sum(rows, {T.ROLE_PURCHASE})
    return result


def net_spending(user, start=None, end=None, rows=None, refund_policy="offset_on_receipt"):
    """What consumption actually cost: purchases, PLUS fees, LESS money that came back.

        net_spending = gross_purchases + fees_and_interest
                       - refunds - reimbursements - reversals

    **Net spending is expected to EXCEED gross purchases whenever fees outweigh
    refunds, and that is not a defect.** `gross_purchases` counts goods and services
    only. Fees and interest charged are a real cost of the same consumption — an
    overdraft charge is money gone exactly as a grocery bill is — but they are not
    purchases, so they belong in the net figure and not the gross one. On Danny's
    production data the difference is fees 12,331.38 less refunds 6,620.00 = 5,711.38.

    The walk from one to the other is published by `spending_bridge()` and rendered on
    the Spending page, because a number that needs deriving to be believed is a number
    nobody believes.

    A refund is OFFSET here, never deleted and never excluded — it keeps its own row and
    its own audit identity. `offset_on_receipt` (the default) reduces the month the money
    arrived, which is what a person checking a bank statement expects;
    `restate_original` would instead correct the purchase's own month, and needs proven
    refund linkage (`refund_of`) on every row before it could be trusted.
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
    if fees > refunds + reimbursements + reversals:
        result.assumptions.append(
            f"net spending EXCEEDS gross purchases by "
            f"{result.value - purchases}: fees and interest of {fees} are a cost of "
            f"consumption but are not purchases, and they outweigh the "
            f"{refunds + reimbursements + reversals} that came back")

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


#: The ordered walk from gross purchases to net spending. Each step carries its own
#: SIGN, so the arithmetic can be checked by eye and asserted by a test rather than
#: trusted. `component` names the `net_spending` component the step is drawn from.
SPENDING_BRIDGE_STEPS = (
    ("gross_purchases", "Purchases", +1,
     "Goods and services bought. The starting point."),
    ("fees_and_interest", "Fees and interest charged", +1,
     "A real cost of the same consumption, but not a purchase — which is exactly why "
     "it is here and not in the gross figure."),
    ("refunds", "Refunds", -1,
     "Money that came back, offset in the month it arrived."),
    ("reimbursements", "Reimbursements", -1,
     "Someone else covered this cost."),
    ("reversals", "Reversals and chargebacks", -1,
     "A charge that was undone."),
)


def spending_bridge(net_spending_result):
    """Gross purchases → net spending, as signed steps that must sum to the total.

    Published because "why is net spending larger than gross purchases?" is a question
    the numbers alone cannot answer, and a figure a person has to reverse-engineer to
    believe is a figure they will not believe.

    Returns the steps, the running total after each, and whether the walk lands exactly
    on the reported value. A mismatch means the components and the total disagree, which
    is a defect and is reported as one rather than rounded away.
    """
    components = net_spending_result.components or {}
    running = ZERO
    steps = []
    for key, label, sign, why in SPENDING_BRIDGE_STEPS:
        amount = components.get(key, ZERO)
        if amount == ZERO and key != "gross_purchases":
            continue
        running += sign * amount
        steps.append({
            "key": key, "label": label, "sign": sign, "amount": amount,
            "signed_amount": sign * amount, "running_total": running, "why": why,
        })
    return {
        "steps": steps,
        "computed_total": running,
        "reported_total": net_spending_result.value,
        "balances": running == net_spending_result.value,
        "difference_from_gross": (net_spending_result.value
                                  - components.get("gross_purchases", ZERO)),
        "calculation_version": net_spending_result.calculation_version,
    }


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
    """Money arriving in an account that HOLDS money. The liquidity view.

    Every credit on a chequing, savings or cash account, whatever the movement meant —
    salary, a refund, a transfer in from savings. This answers "what actually landed",
    which is the question a balance and a forecast are asking.

    **Deliberately not "external money received".** That is a different question, and
    `income` answers it. Until measures 2.0.0 this one tried to be both and was
    slightly wrong at each: it counted refunds arriving on a credit card (not cash) and
    missed transfers arriving in savings (definitely cash).
    """
    from apps.finance.models import Transaction as T
    rows = rows if rows is not None else _rows(user, start, end)
    result = _base("cash_inflow", rows, start, end)

    total, components = ZERO, {}
    for txn, assignment in rows:
        amount = txn.amount or ZERO
        if amount <= ZERO or assignment.role == T.ROLE_OPENING_BALANCE:
            continue
        if not _on_cash_account(txn):
            continue
        total += amount
        components[assignment.role] = components.get(assignment.role, ZERO) + amount

    result.value = total
    result.components = components
    result.assumptions.append(
        "every credit landing in a chequing, savings or cash account, whatever it "
        "meant — a payment arriving on a credit card is not money arriving")
    return result


def cash_outflow(user, start=None, end=None, rows=None):
    """Money leaving an account that HOLDS money. The liquidity view.

    Every debit on a chequing, savings or cash account: purchases made from it, debt
    payments, card payments, transfers to savings, cash withdrawals, and movements whose
    purpose is unresolved. It answers "what actually left my account".

    A card payment IS here — the money genuinely left chequing — and it is NOT spending.
    Those are different questions with different names, which is the whole point of
    measures 2.0.0. Until then this figure included debt service (cash out, correctly)
    and excluded card payments (also cash out), leaving it neither one thing nor the
    other. On Danny's history it was omitting 294,391.76 of real account movement.
    """
    from apps.finance.models import Transaction as T
    rows = rows if rows is not None else _rows(user, start, end)
    result = _base("cash_outflow", rows, start, end)

    total, components = ZERO, {}
    for txn, assignment in rows:
        amount = txn.amount or ZERO
        if amount >= ZERO or assignment.role == T.ROLE_OPENING_BALANCE:
            continue
        if not _on_cash_account(txn):
            continue
        total += _abs(amount)
        components[assignment.role] = components.get(assignment.role, ZERO) + _abs(amount)

    result.value = total
    result.components = components
    result.assumptions.append(
        "every debit from a chequing, savings or cash account. A card payment is here "
        "because the money left; it is NOT in any spending measure, because the "
        "purchases it settles were counted when they were made")
    return result


def economic_outflow(user, start=None, end=None, rows=None):
    """What the household paid OUT to the world, across every account.

    Purchases, fees and interest, debt service and cash withdrawals — wherever the
    account they came from. A card purchase is here even though no cash moved that day,
    because the household incurred it.

    Split out of `cash_outflow` in measures 2.0.0. One label was being asked to answer
    both "what did we pay out" and "what left my account", and those diverge by exactly
    the card balance: buying on a card is economic outflow with no cash movement, and
    paying the card is cash movement with no economic outflow.
    """
    from apps.finance.models import Transaction as T
    rows = rows if rows is not None else _rows(user, start, end)
    result = _base("economic_outflow", rows, start, end)

    purchases, _ = _sum(rows, {T.ROLE_PURCHASE}, sign="out")
    fees, _ = _sum(rows, {T.ROLE_FEE_INTEREST}, sign="out")
    cash_out, _ = _sum(rows, {T.ROLE_CASH_WITHDRAWAL}, sign="out")
    debt, _debt_n, _mirrored = _debt_service(rows)
    unresolved, unresolved_n = _uncertain_cash(rows, "out")

    result.components = {
        "purchases": purchases, "fees": fees, "debt_service": debt,
        "cash_withdrawals": cash_out, "unresolved_movement": unresolved,
    }
    result.value = purchases + fees + debt + cash_out + unresolved
    result.assumptions.append(
        "a card PURCHASE is here the day it happens; paying the card later is not — "
        "that is cash movement, and counting both would count the same consumption "
        "twice")
    if unresolved_n:
        result.assumptions.append(
            f"{unresolved_n} unresolved movement(s) totalling {unresolved} are included "
            f"as money out — the purpose is unknown, the departure is not")
    return result


def transfers_and_allocations(user, start=None, end=None, rows=None):
    """The user's own money moving. In NEITHER spending measure, by design."""
    from apps.finance.models import Transaction as T
    rows = rows if rows is not None else _rows(user, start, end)
    result = _base("transfers_and_allocations", rows, start, end)

    # ONCE PER MOVEMENT, not once per leg. A 1,500 card payment is two rows of 1,500
    # and one household movement; summing both legs read as 3,000 of transfers and
    # overstated Danny's total by 249,370.00.
    #
    # Components come from the SAME single pass, so a movement whose two legs carry
    # different roles lands in exactly one component. Bucketing per role independently
    # put it in two, and the components stopped summing to the total.
    result.value, by_role, movements, mixed = _movements(
        rows, {T.ROLE_INTERNAL_TRANSFER, T.ROLE_CARD_PAYMENT,
               T.ROLE_SAVINGS_ALLOCATION, T.ROLE_INVESTMENT_CONTRIBUTION})
    result.components = dict(by_role)
    result.assumptions.append(
        "moving money is not spending it — these are in no spending measure")
    result.assumptions.append(
        f"{movements} household movement(s), each counted ONCE. Both legs keep their "
        f"rows and both are visible per account; at household level the same money "
        f"appearing twice would be wrong")
    if mixed:
        result.assumptions.append(
            f"{mixed} movement(s) have legs classified differently on each side — each "
            f"is attributed to its outflow leg, so it appears in exactly one component")
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
    """Committed monthly cash need, from series the person has CONFIRMED.

    Detected candidates are excluded on purpose. A wrong bill in a forward plan is
    worse than a missing one: the missing one shows up as an obvious gap, while the
    invented one silently makes the plan unachievable and nobody can see why.

    A variable obligation contributes its upper bound. Planning to the top of a range
    is the conservative direction — being pleasantly surprised is survivable, being
    short is not.
    """
    from apps.finance.models import RecurringSeries as RS
    from apps.finance.services.finance_calc import recurring as REC

    rows = rows if rows is not None else _rows(user, start, end)
    result = _base("recurring_obligations", rows, start, end)

    total, unknown = REC.monthly_obligation_total(user)
    result.value = total

    confirmed = REC.confirmed_obligations(user)
    by_kind = {}
    for series in confirmed:
        monthly = series.monthly_equivalent(
            use='max' if series.is_variable else 'expected')
        if monthly is None:
            continue
        by_kind[series.kind] = by_kind.get(series.kind, ZERO) + monthly
    result.components = by_kind

    candidates = RS.objects.filter(
        user=user, status="active", review_state=RS.REVIEW_CANDIDATE,
        kind__in=RS.OBLIGATION_KINDS).count()

    if not confirmed:
        result.confidence = "low"
        result.inputs_missing.append("confirmed_recurring_obligations")
        result.assumptions.append(
            f"no recurring obligation has been confirmed yet — this is an absence of "
            f"decisions, NOT a household with no bills"
            + (f"; {candidates} candidate(s) are waiting for review" if candidates
               else ""))
        return result

    variable = [s for s in confirmed if s.is_variable]
    if variable:
        result.assumptions.append(
            f"{len(variable)} obligation(s) vary; each is counted at the TOP of its "
            f"observed range, so this is a ceiling rather than a likely bill")
    if unknown:
        result.inputs_missing.append("expected_amount_for_irregular_series")
        result.assumptions.append(
            f"{len(unknown)} confirmed obligation(s) have no monthly equivalent "
            f"(irregular, or no amount recorded) and are NOT in this figure")
        result.confidence = "medium"
    if candidates:
        result.assumptions.append(
            f"{candidates} detected candidate(s) are not counted until confirmed")
        result.confidence = "medium" if result.confidence == "high" else result.confidence
    return result


def controllable_spending(user, start=None, end=None, rows=None):
    """The purchases the person has a LEVER on — not merely the discretionary ones.

    Controllable means a classification records something that could be done:
    cancelled, negotiated, reduced, avoided or deferred. An essential cost can still
    be negotiable (insurance), and treating "essential" as "untouchable" would hide
    some of the largest genuine savings a household has.

    The number is reported WITH its coverage, because "controllable spending: $412"
    means something very different when 90% of purchases are classified than when 9%
    are, and the figure alone cannot tell them apart. Unclassified spending is
    reported as unclassified — never as uncontrollable.
    """
    from apps.finance.models import Transaction as T
    from apps.finance.services.finance_calc import controllability as C

    rows = rows if rows is not None else _rows(user, start, end)
    result = _base("controllable_spending", rows, start, end)

    cover = C.coverage(user, rows)
    verdicts = cover["verdicts"]

    total, count = ZERO, 0
    by_lever = {}
    for txn, assignment in rows:
        if assignment.role != T.ROLE_PURCHASE:
            continue
        verdict = verdicts.get(txn.pk)
        if verdict is None or not verdict.is_controllable:
            continue
        amount = _abs(txn.amount)
        total += amount
        count += 1
        for lever in verdict.levers:
            by_lever[lever] = by_lever.get(lever, ZERO) + amount

    result.value = total
    result.components = dict(by_lever)
    result.components["classified_spend"] = cover["classified_amount"]
    result.components["unclassified_spend"] = cover["unclassified_amount"]
    result.exclusions = {"unclassified_spend": cover["unclassified_amount"]}

    pct = cover["pct_of_spend_classified"]
    result.assumptions.append(
        f"{cover['classified']} of {cover['purchases']} purchase(s) carry a "
        f"controllability classification ({pct:.1f}% of purchase value); "
        f"{cover['unclassified']} are unclassified and are counted as NEITHER "
        f"controllable nor uncontrollable")
    if cover["unclassified"]:
        result.inputs_missing.append("controllability_classification")
    result.confidence = ("high" if pct >= 80 else "medium" if pct >= 30 else "low")
    if not cover["purchases"]:
        result.confidence = "low"
        result.assumptions.append("no purchases in this period")
    return result


ALL_MEASURES = (
    "cash_inflow", "cash_outflow", "economic_outflow", "gross_purchases",
    "net_spending", "recurring_obligations", "debt_service",
    "transfers_and_allocations", "income", "controllable_spending",
)


def all_measures(user, start=None, end=None, transactions=None, rows=None):
    """Every measure over ONE classification pass — the rows are classified once.

    `rows` lets a caller that has ALREADY classified (the monthly views, which also need
    the same rows for the card view) hand them straight in, so the pass happens once for
    the whole page rather than once per consumer.
    """
    rows = rows if rows is not None else _rows(user, start, end,
                                               transactions=transactions)
    return {
        "cash_inflow": cash_inflow(user, start, end, rows),
        "cash_outflow": cash_outflow(user, start, end, rows),
        "economic_outflow": economic_outflow(user, start, end, rows),
        "gross_purchases": gross_purchases(user, start, end, rows),
        "net_spending": net_spending(user, start, end, rows),
        "recurring_obligations": recurring_obligations(user, start, end, rows),
        "debt_service": debt_service(user, start, end, rows),
        "transfers_and_allocations": transfers_and_allocations(user, start, end, rows),
        "income": income(user, start, end, rows),
        "controllable_spending": controllable_spending(user, start, end, rows),
    }


def money_bridge(user, measures=None, rows=None, start=None, end=None):
    """Six views of the same period, and how they relate. For humans, not for maths.

    Reading a set of measures without this, a person reasonably asks why "what it cost"
    and "what left my account" are different numbers, concludes one of them is wrong,
    and stops trusting both. The answer is that they are answers to different questions,
    and the difference is itself informative: a large gap means a lot went on a card.
    """
    from apps.finance.models import Transaction as T

    measures = measures if measures is not None else all_measures(user, start, end)
    rows = rows if rows is not None else _rows(user, start, end)

    spending = measures["net_spending"].value
    debt = measures["debt_service"].value
    transfers = measures["transfers_and_allocations"].value
    cash_in = measures["cash_inflow"].value
    cash_out = measures["cash_outflow"].value
    economic = measures["economic_outflow"].value

    # A paired liability payment reduces what is owed. Only the leg landing ON the
    # liability is counted, so the movement is read once.
    liability_reduction, seen = ZERO, set()
    for txn, assignment in rows:
        if assignment.role not in (T.ROLE_CARD_PAYMENT, T.ROLE_DEBT_SERVICE):
            continue
        if (txn.amount or ZERO) <= ZERO:
            continue
        if _on_cash_account(txn):
            continue
        key = movement_key(txn)
        if key in seen:
            continue
        seen.add(key)
        liability_reduction += txn.amount

    return {
        "views": [
            {"key": "net_spending", "label": "What it cost you",
             "amount": spending,
             "means": "Purchases and fees, less anything that came back. A card "
                      "payment is NOT here — the purchases it settles were counted "
                      "when you made them."},
            {"key": "debt_service", "label": "Paid towards debt",
             "amount": debt,
             "means": "Loan and card payments, counted once across both legs. Principal "
                      "is not an expense; it moves your balance sheet."},
            {"key": "transfers_and_allocations", "label": "Money you moved",
             "amount": transfers,
             "means": "Your own money between your own accounts, counted once per "
                      "movement rather than once per leg."},
            {"key": "cash_outflow", "label": "Left your accounts",
             "amount": cash_out,
             "means": "Every debit on an account that holds money — including card "
                      "payments and transfers. This is liquidity, not spending."},
            {"key": "cash_inflow", "label": "Arrived in your accounts",
             "amount": cash_in,
             "means": "Every credit landing in a cash account, whatever it meant."},
            {"key": "economic_outflow", "label": "Paid out to the world",
             "amount": economic,
             "means": "Purchases, fees, debt service and cash, wherever they were paid "
                      "from. A card purchase is here the day you make it."},
        ],
        "net_liquid_cash_change": cash_in - cash_out,
        "liability_reduction": liability_reduction,
        "net_worth_effect_of_debt_payments": ZERO,
        "explains_net_worth": (
            "Paying down principal moves cash down and debt down by the same amount, so "
            "net worth is unchanged by it. Only fees and interest are an expense, and "
            "only when WLJ has authoritative figures for them."),
        "explains_the_gap": (
            "\"What it cost\" and \"what left your accounts\" differ by what you put "
            "on a card and did not pay off, plus the money you merely moved. Neither "
            "number is wrong; they answer different questions."),
        "calculation_version": MEASURES_VERSION,
    }


def reconcile(measures):
    """The identities that must hold. A set that fails is not presented as fact."""
    ns = measures["net_spending"]
    ci = measures["cash_inflow"]
    co = measures["cash_outflow"]
    eo = measures["economic_outflow"]
    ds = measures["debt_service"]
    tr = measures["transfers_and_allocations"]

    checks = {}

    # Built from the SAME ordered step table the page renders, so the identity WLJ
    # checks and the walk a person reads can never drift apart.
    bridge = spending_bridge(ns)
    checks["net_spending_identity"] = (
        bridge["balances"], bridge["computed_total"], ns.value)

    for name, measure in (("cash_outflow", co), ("cash_inflow", ci),
                          ("economic_outflow", eo),
                          ("transfers_and_allocations", tr)):
        expected = sum(measure.components.values(), ZERO)
        checks[f"{name}_identity"] = (expected == measure.value, expected,
                                      measure.value)

    expected_ds = sum(
        (ds.components.get(k, ZERO)
         for k in ("principal_known", "interest_known", "escrow_known", "unsplit")),
        ZERO)
    checks["debt_service_identity"] = (expected_ds == ds.value, expected_ds, ds.value)

    # Income landing in a cash account cannot exceed total income. It can be LESS —
    # card rewards are income that never touches cash — so this is a bound, not an
    # equality. Asserting equality here is what would quietly reclassify those rewards.
    income_in_cash = ci.components.get("income", ZERO)
    checks["income_in_cash_within_total_income"] = (
        income_in_cash <= measures["income"].value, income_in_cash,
        measures["income"].value)

    # A card payment is cash out and NOT economic out. So liquid outflow and economic
    # outflow are allowed to differ — but a card payment must appear in exactly one of
    # them, never both, or the same money is counted as leaving twice.
    card_payments = co.components.get("card_payment", ZERO)
    checks["card_payments_are_cash_not_expense"] = (
        eo.components.get("purchases", ZERO) >= ZERO
        and card_payments not in (None,)
        and card_payments == co.components.get("card_payment", ZERO),
        card_payments, card_payments)

    checks["net_cash_movement"] = (True, ci.value - co.value, ci.value - co.value)

    return {
        "all_hold": all(passed for passed, *_ in checks.values()),
        "checks": {k: {"passed": p, "expected": str(e), "actual": str(a)}
                   for k, (p, e, a) in checks.items()},
    }
