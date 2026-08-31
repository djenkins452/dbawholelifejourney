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
from apps.finance.models import (RecurringSeries, SavingsOpportunity,
                                 SpendingClassification, Transaction)

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
    """Everything WLJ has held back rather than guessed about."""

    template_name = "finance/money_review.html"
    page_summary_key = "finance.money_review"
    page_summary_title = "Money Review Queue"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        labels = _held_reason_labels()
        held = list(Transaction.objects.filter(
            user=user, economic_role=Transaction.ROLE_UNCERTAIN)
            .select_related("account")
            .order_by("-date")[:100])
        # Resolved here rather than in the template: a dictionary lookup by key is not
        # something Django templates do, and adding a filter for it would be a new
        # piece of platform surface for one page.
        for txn in held:
            txn.reason_label = labels.get(txn.role_reason, txn.role_reason)

        candidates = (RecurringSeries.objects.filter(
            user=user, status="active",
            review_state=RecurringSeries.REVIEW_CANDIDATE)
            .select_related("account", "declared_template")
            .order_by("-confidence", "name")[:100])

        context.update({
            "held": held,
            "candidates": candidates,
            "review_counts": _review_counts(user),
            "role_choices": Transaction.ECONOMIC_ROLE_CHOICES,
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

        context.update({
            "debts": debts,
            "extra": extra,
            "comparison": comparison,
            "scenarios": comparison["scenarios"],
            "needs_terms": [d for d in debts if d.missing],
        })
        return context


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

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
