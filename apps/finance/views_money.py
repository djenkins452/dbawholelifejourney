# ==============================================================================
# File: apps/finance/views_money.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Finance 2.0 workspaces — measures, obligations, control, payoff.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""The pages where the Finance 2.0 engines become something a person can use.

Every number rendered here comes from the same deterministic service the Chief of Staff
reads. That is the point: a page and an assistant that derive the same figure separately
will eventually disagree, and the user has no way to know which one to believe.

Request-path safe: each view reads pre-computed or bounded query results only. No
provider call, no classification sweep, no background work is triggered inline. Finance
stays externally read-only — these pages change WLJ's opinion about money, never money.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from apps.core.current_context import PageSummaryMixin
from apps.finance.access import FinanceEnabledRequiredMixin, finance_enabled_required
from apps.finance.models import (FinancialAccount, RecurringSeries, ReviewBatch,
                                 SavingsOpportunity, SpendingClassification,
                                 Transaction)

#: Presented in this order because it is the order a person asks the questions in:
#: what came in, what went out, what did it cost me, what am I committed to.
MEASURE_ORDER = (
    "cash_inflow", "cash_outflow", "income", "gross_purchases", "net_spending",
    "debt_service", "recurring_obligations", "controllable_spending",
    "transfers_and_allocations",
)

MEASURE_LABELS = {
    "cash_inflow": "Money in",
    "cash_outflow": "Money out",
    "income": "Income",
    "gross_purchases": "Purchases",
    "net_spending": "What it actually cost",
    "debt_service": "Debt service",
    "recurring_obligations": "Committed each month",
    "controllable_spending": "Spending you can change",
    "transfers_and_allocations": "Money you moved",
}

MEASURE_HELP = {
    "cash_inflow": "Everything that arrived, including money whose purpose is unresolved.",
    "cash_outflow": "Everything that left a cash account.",
    "income": "Earnings only. A refund is not income and borrowing is not income.",
    "gross_purchases": "Goods and services, before any refund is taken off.",
    "net_spending": "Purchases and fees, less refunds. Debt payments are not here.",
    "debt_service": "Loan and card payments, counted once across both legs.",
    "recurring_obligations": "Confirmed commitments only, as a monthly figure.",
    "controllable_spending": "Purchases you have marked as having a lever.",
    "transfers_and_allocations": "Your own money moving. In no spending measure.",
}


class _SignedInFinanceView(FinanceEnabledRequiredMixin, PageSummaryMixin,
                           TemplateView):
    """Shared guard: an anonymous request is redirected, never rendered.

    `get_context_data` on every page below filters by `request.user`, and an
    `AnonymousUser` reaching that raises deep in the ORM rather than sending someone
    to the login page. The check belongs before the body runs.
    """

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        return super().get(request, *args, **kwargs)


class MoneyOverviewView(_SignedInFinanceView):
    """The nine measures, each with its assumptions and its gaps."""

    template_name = "finance/money_overview.html"
    page_summary_key = "finance.money"
    page_summary_title = "Spending and Cash Flow"

    def get_context_data(self, **kwargs):
        from apps.finance.services.finance_calc import measures as M

        context = super().get_context_data(**kwargs)
        user = self.request.user

        results = M.all_measures(user)
        reconciliation = M.reconcile(results)

        context.update({
            # Published, not derivable: "why is net spending bigger than gross
            # purchases?" is the first question this page provokes, and a number a
            # person has to reverse-engineer to believe is one they will not believe.
            "bridge": M.spending_bridge(results["net_spending"]),
            "measures": [{
                "key": key,
                "label": MEASURE_LABELS[key],
                "help": MEASURE_HELP[key],
                "result": results[key],
            } for key in MEASURE_ORDER],
            "reconciliation": reconciliation,
            "review_counts": _review_counts(user),
            "coverage": _coverage(user),
        })
        return context


class ReviewQueueView(_SignedInFinanceView):
    """Everything WLJ held back rather than guessed about — as decisions, not rows.

    A flat list asks the same question 155 times and gets abandoned around row nine.
    The rows cluster by WHY they were held and by WHO took the money, and one answer
    usually settles a whole cluster.
    """

    template_name = "finance/money_review.html"
    page_summary_key = "finance.money_review"
    page_summary_title = "Money Review Queue"

    def get_context_data(self, **kwargs):
        from apps.finance.services.finance_calc import review_queue as RQ

        context = super().get_context_data(**kwargs)
        user = self.request.user

        groups = RQ.build_groups(user)
        shortlist = RQ.highest_impact(user, limit=5)

        candidates = (RecurringSeries.objects.filter(
            user=user, status="active",
            review_state=RecurringSeries.REVIEW_CANDIDATE)
            .select_related("account", "declared_template")
            .order_by("-confidence", "name")[:100])

        context.update({
            "groups": groups,
            "shortlist": shortlist,
            "candidates": candidates,
            "review_counts": _review_counts(user),
            "role_choices": Transaction.ECONOMIC_ROLE_CHOICES,
            "leave_uncertain": RQ.DECISION_LEAVE,
            "recent_batches": ReviewBatch.objects.filter(
                user=user, status="active").order_by("-applied_at")[:5],
        })
        return context


class ControlView(_SignedInFinanceView):
    """What can this household actually change?"""

    template_name = "finance/money_control.html"
    page_summary_key = "finance.money_control"
    page_summary_title = "Controllable Spending"

    def get_context_data(self, **kwargs):
        from apps.finance.services.finance_calc import opportunities as OPP

        context = super().get_context_data(**kwargs)
        user = self.request.user

        context.update({
            "classifications": SpendingClassification.objects.filter(
                user=user, status="active").select_related("category")
                .order_by("scope", "payee")[:200],
            "opportunities": OPP.ranked(user, limit=25),
            "largest": OPP.largest_controllable_cost(user),
            "levers": SpendingClassification.LEVER_CHOICES,
            "necessities": SpendingClassification.NECESSITY_CHOICES,
            "variabilities": SpendingClassification.VARIABILITY_CHOICES,
            "confirmed_series": RecurringSeries.objects.filter(
                user=user, status="active",
                review_state=RecurringSeries.REVIEW_CONFIRMED).order_by("name"),
        })
        return context


class DebtView(_SignedInFinanceView):
    """Debts, their terms, what is missing, and the payoff comparison."""

    template_name = "finance/money_debt.html"
    page_summary_key = "finance.money_debt"
    page_summary_title = "Debts and Payoff"

    def get_context_data(self, **kwargs):
        from apps.finance.services.finance_calc import payoff as P

        context = super().get_context_data(**kwargs)
        user = self.request.user

        extra = _decimal(self.request.GET.get("extra"))
        debts = P.debts_for(user)
        comparison = P.compare(user, extra_monthly=extra, debts=debts)

        from apps.finance.models import LoanTerms, PayoffScenario
        from apps.finance.models_liability import SOURCE_CHOICES

        terms_by_account = {t.account_id: t for t in LoanTerms.objects.filter(
            user=user, status="active").select_related("account")}
        for debt in debts:
            debt.terms = terms_by_account.get(debt.account_id)

        context.update({
            "debts": debts,
            "extra": extra,
            "comparison": comparison,
            "scenarios": comparison["scenarios"],
            "needs_terms": [d for d in debts if d.missing],
            "saved_scenarios": PayoffScenario.objects.filter(
                user=user, status="active").order_by("-activated_on", "name"),
            "strategies": P.STRATEGIES,
            "term_sources": SOURCE_CHOICES,
            "has_any_liability": bool(debts),
        })
        return context


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

@require_POST
@finance_enabled_required
def run_detection(request):
    """Ask the worker to look for recurring patterns. Never runs inline.

    Detection classifies the whole population and then walks it looking for schedules.
    Doing that on the request path would tie up a Gunicorn worker that should be
    serving pages, so it is enqueued fire-and-forget and the page says so.
    """
    from apps.core.celery_utils import safe_enqueue
    from apps.finance.tasks import detect_recurring_and_opportunities

    enqueued = safe_enqueue(detect_recurring_and_opportunities, request.user.pk)
    if enqueued:
        messages.success(
            request, "Looking for recurring patterns. Refresh in a moment — anything "
                     "found will appear here as a candidate for you to confirm.")
    else:
        messages.warning(
            request, "WLJ could not start the search just now. Nothing has changed; "
                     "try again shortly.")
    return redirect(reverse("finance:money_review"))


@require_POST
@finance_enabled_required
def confirm_series(request, pk):
    """Confirm, ignore, or reopen a detected recurring series."""
    series = get_object_or_404(RecurringSeries, pk=pk, user=request.user,
                               status="active")
    decision = (request.POST.get("decision") or "").strip()
    if decision not in dict(RecurringSeries.REVIEW_CHOICES):
        messages.error(request, "That is not a decision WLJ recognises.")
        return redirect(reverse("finance:money_review"))

    series.review_state = decision
    if decision == RecurringSeries.REVIEW_CONFIRMED:
        kind = (request.POST.get("kind") or "").strip()
        if kind in dict(RecurringSeries.KIND_CHOICES):
            series.kind = kind
        series.source = RecurringSeries.SOURCE_USER
    series.save(update_fields=["review_state", "kind", "source", "updated_at"])
    messages.success(request, f"{series.name} marked {series.get_review_state_display().lower()}.")
    return redirect(reverse("finance:money_review"))


@require_POST
@finance_enabled_required
def preview_bulk(request):
    """What would this decision do? Returns a token that binds the answer to the set."""
    from apps.finance.services.finance_calc import review_queue as RQ

    ids = _int_list(request.POST.getlist("ids"))
    decision = (request.POST.get("decision") or "").strip()
    if not ids:
        return JsonResponse({"error": "select at least one transaction"}, status=400)

    result = RQ.preview(request.user, ids, decision)
    return JsonResponse({
        "eligible_count": result["eligible_count"],
        "refused_count": result["refused_count"],
        "refused_reason": result["refused_reason"],
        "total_amount": str(result["total_amount"]),
        "inflow": str(result["inflow"]),
        "outflow": str(result["outflow"]),
        "affects": result["affects"],
        "token": result["token"],
    })


@require_POST
@finance_enabled_required
def apply_bulk(request):
    """Apply a previewed decision. Refuses any set the preview did not cover."""
    from apps.finance.services.finance_calc import review_queue as RQ

    ids = _int_list(request.POST.getlist("ids"))
    decision = (request.POST.get("decision") or "").strip()
    token = (request.POST.get("token") or "").strip()
    create_rule = request.POST.get("create_rule") == "on"

    try:
        result = RQ.apply_bulk(request.user, ids, decision, token=token,
                               create_rule=create_rule,
                               group_label=(request.POST.get("group_label") or "")[:200])
    except ValueError:
        messages.error(request, "That is not a decision WLJ recognises.")
        return redirect(reverse("finance:money_review"))

    from apps.finance.security import get_audit_logger
    get_audit_logger(request).log(
        action="update", entity_type="transaction",
        details={"bulk_decision": decision, "rows": result.get("applied", 0),
                 "refused": result.get("refused", False)})

    if result.get("refused"):
        messages.warning(request, f"Nothing was changed: {result['reason']}.")
    else:
        messages.success(
            request,
            f"{result['applied']} transaction(s) set to {decision.replace('_', ' ')}. "
            f"You can undo this.")
    return redirect(reverse("finance:money_review"))


@require_POST
@finance_enabled_required
def undo_bulk(request, pk):
    from apps.finance.services.finance_calc import review_queue as RQ

    result = RQ.undo(request.user, pk)
    if result.get("refused"):
        messages.warning(request, f"Nothing was undone: {result['reason']}.")
    else:
        skipped = result.get("skipped_edited_since", 0)
        tail = (f" {skipped} row(s) you edited afterwards were left as you set them."
                if skipped else "")
        messages.success(request,
                         f"Restored {result['restored']} transaction(s).{tail}")
    return redirect(reverse("finance:money_review"))


@require_POST
@finance_enabled_required
def set_transaction_role(request, pk):
    """Resolve a held transaction. The user's decision becomes the authority."""
    txn = get_object_or_404(Transaction, pk=pk, user=request.user)
    role = (request.POST.get("economic_role") or "").strip()
    if role not in dict(Transaction.ECONOMIC_ROLE_CHOICES):
        return JsonResponse({"error": "unknown role"}, status=400)

    txn.economic_role = role
    txn.role_source = Transaction.ROLE_SOURCE_USER
    txn.role_confidence = Transaction.ROLE_CONFIDENCE_HIGH
    txn.role_reason = "user_confirmed_role"
    txn.save(update_fields=["economic_role", "role_source", "role_confidence",
                            "role_reason", "updated_at"])

    # `get_audit_logger` redacts its own details and swallows its own failures, so a
    # broken audit sink can never cost the user the decision they just made.
    from apps.finance.security import get_audit_logger
    get_audit_logger(request).log(
        action="update", entity_type="transaction", entity_id=txn.pk,
        details={"economic_role": role, "role_source": "user"})
    return JsonResponse({"ok": True, "role": role,
                         "label": dict(Transaction.ECONOMIC_ROLE_CHOICES)[role]})


@require_POST
@finance_enabled_required
def set_controllability(request):
    """Create or update one controllability decision for a payee."""
    payee = (request.POST.get("payee") or "").strip()
    if not payee:
        messages.error(request, "A payee is needed to record that.")
        return redirect(reverse("finance:money_control"))

    levers = [lv for lv in request.POST.getlist("levers")
              if lv in SpendingClassification.ALL_LEVERS]
    classification, _ = SpendingClassification.objects.update_or_create(
        user=request.user, payee=payee.lower(), status="active",
        defaults={
            "scope": SpendingClassification.SCOPE_PAYEE,
            "necessity": request.POST.get("necessity")
                         or SpendingClassification.NECESSITY_UNKNOWN,
            "variability": request.POST.get("variability")
                           or SpendingClassification.VARIABILITY_UNKNOWN,
            "levers": levers,
            "source": SpendingClassification.SOURCE_USER,
            "note": (request.POST.get("note") or "")[:500],
        })
    messages.success(request, f"Recorded what you can change about {payee}.")
    return redirect(reverse("finance:money_control"))


@require_POST
@finance_enabled_required
def archive_controllability(request, pk):
    classification = get_object_or_404(SpendingClassification, pk=pk,
                                       user=request.user)
    classification.status = "archived"
    classification.save(update_fields=["status", "updated_at"])
    messages.success(request, "Classification archived. It stops applying immediately.")
    return redirect(reverse("finance:money_control"))


@require_POST
@finance_enabled_required
def decide_opportunity(request, pk):
    opportunity = get_object_or_404(SavingsOpportunity, pk=pk, user=request.user,
                                    status="active")
    decision = (request.POST.get("decision") or "").strip()
    if decision not in dict(SavingsOpportunity.DECISION_CHOICES):
        messages.error(request, "That is not a decision WLJ recognises.")
        return redirect(reverse("finance:money_control"))

    snooze = request.POST.get("snooze_until") or None
    opportunity.decide(decision, reason=(request.POST.get("reason") or "")[:300],
                       snooze_until=snooze or None).save()
    messages.success(request, f"{opportunity.title}: {opportunity.get_decision_display().lower()}.")
    return redirect(reverse("finance:money_control"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _int_list(raw_values):
    """Only well-formed ids. A malformed one is dropped, never guessed at."""
    out = []
    for raw in raw_values:
        for part in str(raw).split(","):
            part = part.strip()
            if part.isdigit():
                out.append(int(part))
    return out


def _decimal(raw, default="0"):
    try:
        return Decimal(str(raw or default))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


def _review_counts(user):
    return {
        "held_transactions": Transaction.objects.filter(
            user=user, economic_role=Transaction.ROLE_UNCERTAIN).count(),
        "recurring_candidates": RecurringSeries.objects.filter(
            user=user, status="active",
            review_state=RecurringSeries.REVIEW_CANDIDATE).count(),
        "unclassified": Transaction.objects.filter(
            user=user, economic_role__isnull=True).count(),
    }


def _coverage(user):
    rows = Transaction.objects.filter(user=user)
    total = rows.count()
    classified = rows.filter(economic_role__isnull=False).count()
    return {
        "total": total, "classified": classified,
        "pct": round(classified * 100.0 / total, 1) if total else 0.0,
    }


def _held_reason_labels():
    return {
        "ambiguous_credit": "Money arrived and WLJ cannot say why",
        "unmatched_liability_credit": "A credit on a card — a payment, or borrowing?",
        "unmatched_transfer_candidate": "Looks like a transfer, but the other side is not visible",
        "zero_amount": "No amount to classify",
    }


class BudgetReserveView(_SignedInFinanceView):
    """Budgets, reserves, sinking funds — and what they leave free."""

    template_name = "finance/money_budget.html"
    page_summary_key = "finance.money_budget"
    page_summary_title = "Budgets and Reserves"

    def get_context_data(self, **kwargs):
        from apps.finance.models import Budget, CashReserve, FinancialGoal
        from apps.finance.services.finance_calc import forecast as F

        context = super().get_context_data(**kwargs)
        user = self.request.user
        horizon = _int(self.request.GET.get("horizon"), 30)

        reserves = list(CashReserve.objects.filter(user=user, status="active")
                        .select_related("goal", "account"))

        context.update({
            "forecast": F.build(user, horizon_days=horizon),
            "horizons": F.HORIZONS,
            "horizon": horizon,
            "setup": F.setup_state(user),
            "reserves": [r for r in reserves if r.kind == CashReserve.KIND_RESERVE],
            "sinking_funds": [r for r in reserves
                              if r.kind == CashReserve.KIND_SINKING],
            "kinds": CashReserve.KIND_CHOICES,
            "budgets": Budget.objects.filter(user=user, status="active")
                       .select_related("category").order_by("-month")[:24],
            # Offered so a reserve can LINK an existing goal rather than restating it.
            "goals": FinancialGoal.objects.filter(user=user, status="active")
                     .order_by("name"),
            "accounts": FinancialAccount.objects.filter(
                user=user, status="active",
                account_type__in=["checking", "savings", "cash"]).order_by("name"),
        })
        return context


class NetWorthView(_SignedInFinanceView):
    """What you are worth, what is unknown, and how it has moved."""

    template_name = "finance/money_networth.html"
    page_summary_key = "finance.money_networth"
    page_summary_title = "Assets and Net Worth"

    def get_context_data(self, **kwargs):
        from apps.finance.services.finance_calc import net_worth as NW

        context = super().get_context_data(**kwargs)
        user = self.request.user
        context.update({
            "position": NW.compose(user),
            "history": NW.history(user),
        })
        return context


class DataHealthView(_SignedInFinanceView):
    """What is stale, missing or unresolved — and where to fix it."""

    template_name = "finance/money_health.html"
    page_summary_key = "finance.money_health"
    page_summary_title = "Finance Data Health"

    def get_context_data(self, **kwargs):
        from apps.finance.services.finance_calc import data_health as DH

        context = super().get_context_data(**kwargs)
        report = DH.evaluate(self.request.user)
        # Route names are resolved here: a template cannot reverse a name held in data,
        # and a bespoke template filter for one page is more surface than it is worth.
        for issue in report["issues"]:
            issue["url"] = _safe_reverse(issue.get("route"))
        context["report"] = report
        return context


@require_POST
@finance_enabled_required
def save_reserve(request):
    """Create or update a reserve or sinking fund."""
    from apps.finance.models import CashReserve, FinancialAccount, FinancialGoal

    name = (request.POST.get("name") or "").strip()
    if not name:
        messages.error(request, "Give it a name so you can recognise it later.")
        return redirect(reverse("finance:money_budget"))

    kind = request.POST.get("kind")
    if kind not in dict(CashReserve.KIND_CHOICES):
        kind = CashReserve.KIND_SINKING

    goal = _owned(FinancialGoal, request.user, request.POST.get("goal"))
    account = _owned(FinancialAccount, request.user, request.POST.get("account"))

    CashReserve.objects.update_or_create(
        user=request.user, name=name, status="active",
        defaults={
            "kind": kind,
            "target_amount": _optional_decimal(request.POST.get("target_amount")),
            "monthly_contribution": _optional_decimal(
                request.POST.get("monthly_contribution")),
            "due_date": (request.POST.get("due_date") or None) or None,
            "goal": goal, "account": account,
            "note": (request.POST.get("note") or "")[:500],
        })
    messages.success(request, f"Saved {name}.")
    return redirect(reverse("finance:money_budget"))


@require_POST
@finance_enabled_required
def archive_reserve(request, pk):
    from apps.finance.models import CashReserve

    reserve = get_object_or_404(CashReserve, pk=pk, user=request.user)
    reserve.status = "archived"
    reserve.save(update_fields=["status", "updated_at"])
    messages.success(request, f"{reserve.name} archived. It no longer affects your "
                              f"free cash figure.")
    return redirect(reverse("finance:money_budget"))


@require_POST
@finance_enabled_required
def take_snapshot(request):
    """Record today's net worth. Idempotent — one per day, updated in place."""
    from apps.finance.services.finance_calc import net_worth as NW

    result = NW.take_snapshot(request.user, commit=True)
    messages.success(
        request,
        f"Net worth recorded for {result['as_of']}: {result['net_worth']}."
        if result.get("created") else
        f"Today's snapshot updated: {result['net_worth']}.")
    return redirect(reverse("finance:money_networth"))


def _int(raw, default):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value in (30, 60, 90) else default


def _optional_decimal(raw):
    """A blank field means "not decided", which is NOT zero."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def _owned(model, user, pk):
    if not pk:
        return None
    return model.objects.filter(pk=pk, user=user, status="active").first()


def _safe_reverse(route):
    from django.urls import NoReverseMatch, reverse as django_reverse

    if not route:
        return None
    try:
        return django_reverse(route)
    except NoReverseMatch:
        return None


@require_POST
@finance_enabled_required
def save_loan_terms(request, pk):
    """Record loan terms with the provenance of each field.

    A term without provenance is how a payoff projection built on a six-month-old rate
    gets presented as though the bank confirmed it this morning. Every field the user
    fills in is stamped with WHERE it came from and WHEN it was true.
    """
    from apps.finance.models import FinancialAccount, LoanTerms, LoanTermsChange
    from apps.finance.models_liability import TRACKED_TERMS

    account = get_object_or_404(FinancialAccount, pk=pk, user=request.user,
                                status="active")
    terms, _ = LoanTerms.objects.get_or_create(user=request.user, account=account)

    source = request.POST.get("source") or "user"
    as_of = request.POST.get("as_of") or None
    changed = []

    for field in TRACKED_TERMS:
        if field == "current_balance":
            continue                        # the account owns the balance, not this form
        if field not in request.POST:
            continue
        raw = (request.POST.get(field) or "").strip()
        value = _term_value(field, raw)
        if value is None and raw == "":
            continue                        # left blank means "still unknown"
        previous = terms.value_of(field)
        if _same_term(previous, value):
            continue
        terms.record(field, value, source=source, as_of=as_of)
        changed.append((field, previous, value))

    if not changed:
        messages.info(request, "Nothing changed.")
        return redirect(reverse("finance:money_debt"))

    terms.save()
    for field, previous, value in changed:
        LoanTermsChange.objects.create(
            user=request.user, terms=terms, field=field,
            old_value=str(previous or "")[:120], new_value=str(value or "")[:120],
            source=source, as_of=as_of or None)

    messages.success(
        request,
        f"Recorded {len(changed)} term(s) for {account.name}. "
        f"Payoff planning can use them now.")
    return redirect(reverse("finance:money_debt"))


@require_POST
@finance_enabled_required
def save_scenario(request):
    """Save a payoff scenario as a draft, with what the engine said at the time."""
    from apps.finance.models import PayoffScenario
    from apps.finance.services.finance_calc import payoff as P

    name = (request.POST.get("name") or "").strip()
    if not name:
        messages.error(request, "Give the scenario a name so you can compare it later.")
        return redirect(reverse("finance:money_debt"))

    strategy = request.POST.get("strategy") or P.STRATEGY_AVALANCHE
    if strategy not in P.STRATEGIES:
        strategy = P.STRATEGY_AVALANCHE
    extra = _decimal(request.POST.get("extra_monthly"))
    lump = _decimal(request.POST.get("lump_sum"))

    scenario = P.simulate(request.user, strategy, extra_monthly=extra, lump_sum=lump)
    PayoffScenario.objects.update_or_create(
        user=request.user, name=name, status="active",
        defaults={
            "strategy": strategy, "extra_monthly": extra, "lump_sum": lump,
            # Snapshotted deliberately: re-deriving against today's balances would make
            # every saved plan look permanently on track.
            "projected": scenario.as_dict(),
            "calculation_version": P.PAYOFF_VERSION,
            "note": (request.POST.get("note") or "")[:500],
        })
    messages.success(request, f"Saved “{name}”. It is a draft until you activate it.")
    return redirect(reverse("finance:money_debt"))


@require_POST
@finance_enabled_required
def scenario_state(request, pk):
    """Activate, pause, archive or restore a scenario. Never moves money."""
    from django.db import transaction as db_transaction

    from apps.finance.models import PayoffScenario

    scenario = get_object_or_404(PayoffScenario, pk=pk, user=request.user)
    action = (request.POST.get("action") or "").strip()

    if action == "delete":
        scenario.status = "archived"
        scenario.save(update_fields=["status", "updated_at"])
        messages.success(request, f"“{scenario.name}” archived.")
        return redirect(reverse("finance:money_debt"))

    if action not in dict(PayoffScenario.STATE_CHOICES):
        messages.error(request, "That is not a state WLJ recognises.")
        return redirect(reverse("finance:money_debt"))

    with db_transaction.atomic():
        if action == PayoffScenario.STATE_ACTIVE:
            # "The plan I am following" is singular — a household with three active
            # plans has none. The database enforces it too; this makes the swap
            # deliberate rather than an error the user has to decode.
            PayoffScenario.objects.filter(
                user=request.user, status="active",
                plan_state=PayoffScenario.STATE_ACTIVE).exclude(
                pk=scenario.pk).update(plan_state=PayoffScenario.STATE_PAUSED)
            from apps.core.utils import get_user_today
            scenario.activated_on = get_user_today(request.user)
        scenario.plan_state = action
        scenario.save(update_fields=["plan_state", "activated_on", "updated_at"])

    messages.success(request,
                     f"“{scenario.name}” is now {scenario.get_plan_state_display().lower()}.")
    return redirect(reverse("finance:money_debt"))


def _same_term(previous, value):
    """Is this actually a change?

    Compared as VALUES, not as strings. An APR stored as 7.250 and re-entered as 7.25
    is the same rate, and treating it as an edit writes a history entry recording that
    nothing happened.
    """
    if previous is None or value is None:
        return previous is None and value is None
    if isinstance(previous, Decimal) and isinstance(value, Decimal):
        return previous == value
    return str(previous) == str(value)


def _term_value(field, raw):
    """Parse one term, keeping "blank means unknown" distinct from "zero"."""
    from datetime import date as _date

    if raw == "":
        return None
    date_fields = {"origination_date", "maturity_date", "payoff_quote_expires",
                   "promotional_apr_ends"}
    int_fields = {"due_day", "remaining_term_months"}
    text_fields = {"interest_method", "prepayment_penalty"}

    if field in date_fields:
        try:
            return _date.fromisoformat(raw[:10])
        except ValueError:
            return None
    if field in int_fields:
        return int(raw) if raw.isdigit() else None
    if field in text_fields:
        return raw[:200]
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
