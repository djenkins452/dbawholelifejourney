# ==============================================================================
# File: apps/finance/views_attribution.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: F2 — the attribution review workspace (read + confirm/correct).
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""The Finance attribution review workspace.

Request-path safe by construction: every read is a bounded, indexed query through
`attribution_review`; every write goes through the attribution services that own the
same-user and confirmation-precedence invariants. **No provider call, no heavy
intelligence, no background work is triggered inline** — F1's detector runs in the worker.

Finance stays externally read-only: this page changes WLJ's own classification of the
user's money. It cannot move any.
"""
from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from apps.core.current_context import PageSummaryMixin
from apps.finance.access import FinanceEnabledRequiredMixin, finance_enabled_required
from apps.finance.models import FinancialEntity, Transaction
from apps.finance.services import attribution_review as review
from apps.finance.services import attribution_population as population
from apps.finance.services.attribution import current_attribution
from apps.finance.services.finance_entities import ensure_default_entities


class AttributionReviewView(FinanceEnabledRequiredMixin, PageSummaryMixin,
                            TemplateView):
    """Who does this money belong to? — the review queue."""

    template_name = "finance/attribution_review.html"
    page_summary_key = "finance.attribution"
    page_summary_title = "Attribution Review"

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        ensure_default_entities(user)
        names = population.liability_account_names(user)

        inferred = list(review.inferred_attributions(user))
        context.update({
            "entities": FinancialEntity.objects.filter(user=user, is_active=True)
                                               .order_by("sort_order", "name"),
            "counts": review.review_counts(user),
            "unattributed": list(review.unattributed(user, liability_names=names)),
            "inferred": [
                {"attribution": row, "transaction": row.transaction,
                 "why": review.explain(row.transaction, row)}
                for row in inferred
            ],
            "uncertain": [
                {"transaction": txn, "reason": reason,
                 "reason_label": _REASON_LABELS.get(reason, reason)}
                for txn, reason in review.uncertain(user, liability_names=names)
            ],
        })

        # The review queue is where a person is already looking at each transaction, so
        # it is the natural place to fix the category too. ONE categories query covers
        # every row across all three sections.
        from apps.finance.services.category_assignment import attach_category_options
        attach_category_options(user, (
            list(context["unattributed"])
            + [row["transaction"] for row in context["inferred"]]
            + [row["transaction"] for row in context["uncertain"]]
        ))
        return context


_REASON_LABELS = {
    population.REVIEW_PENDING:
        "Still pending at the bank — the amount or date can change.",
    population.REVIEW_SUSPECTED_INTERNAL_TRANSFER:
        "Looks like a payment toward one of your own accounts, not a new expense.",
    population.REVIEW_AMBIGUOUS_TRANSFER:
        "Might be a transfer between your own accounts — held out of your totals until "
        "you say.",
    population.EXCLUDED_CONFIRMED_TRANSFER:
        "A transfer between your own accounts, so it is not spending.",
    population.EXCLUDED_CARD_PAYMENT:
        "A payment toward your own card, so it is not new spending.",
}


@login_required
@finance_enabled_required
@require_POST
def attribution_decide(request):
    """Confirm or correct who a transaction belongs to, at a bounded scope.

    Body: {"transaction_id": int, "entity_id": int, "scope": "transaction|payee|recurring"}
    """
    try:
        payload = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"success": False, "error": "Invalid request."}, status=400)

    scope = payload.get("scope") or "transaction"
    if scope not in ("transaction", "payee", "recurring"):
        return JsonResponse({"success": False, "error": "Unsupported scope."}, status=400)

    transaction = get_object_or_404(
        Transaction, pk=payload.get("transaction_id"), user=request.user,
    )
    entity = get_object_or_404(
        FinancialEntity, pk=payload.get("entity_id"), user=request.user, is_active=True,
    )

    try:
        result = review.apply_decision(request.user, transaction, entity, scope=scope)
    except ValidationError as exc:
        return JsonResponse({"success": False, "error": "; ".join(exc.messages)},
                            status=400)

    return JsonResponse({
        "success": True,
        "transaction_id": transaction.id,
        "entity": entity.name,
        "rule_created": result["rule"] is not None,
        "also_settled": result["also_settled"],
        "counts": review.review_counts(request.user),
    })


@login_required
@finance_enabled_required
def attribution_explain(request, pk):
    """Why WLJ proposed what it proposed — always available, never hidden."""
    transaction = get_object_or_404(Transaction, pk=pk, user=request.user)
    attribution = current_attribution(transaction)
    return JsonResponse({
        "transaction_id": transaction.id,
        "why": review.explain(transaction, attribution),
        "attributed_to": attribution.attributed_entity.name if attribution else None,
        "paid_by": attribution.paid_by_entity.name if attribution else None,
        "confirmed": bool(attribution and attribution.user_confirmed),
    })


@login_required
@finance_enabled_required
@require_POST
def opportunity_decide(request, pk):
    """Record what the user decided about a detected opportunity.

    WLJ changes NOTHING outside itself here — no payment method, no subscription, no
    external account. It records the decision and, on acceptance, starts watching ordinary
    transaction truth for evidence that the user made the change.
    """
    from apps.finance.models import FinanceOpportunity
    from apps.finance.services import opportunity_lifecycle as lifecycle

    opportunity = get_object_or_404(FinanceOpportunity, pk=pk, user=request.user)
    try:
        payload = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"success": False, "error": "Invalid request."}, status=400)

    decision = payload.get("decision")
    try:
        if decision == "accept":
            lifecycle.accept(request.user, opportunity)
        elif decision == "reject":
            lifecycle.reject(request.user, opportunity,
                             reason=str(payload.get("reason", ""))[:200])
        elif decision == "defer":
            from datetime import date as _date
            until = payload.get("until")
            lifecycle.defer(request.user, opportunity,
                            until=_date.fromisoformat(until) if until else None)
        elif decision == "in_progress":
            lifecycle.mark_in_progress(request.user, opportunity)
        elif decision == "done":
            lifecycle.verify_manually(request.user, opportunity,
                                      note=str(payload.get("note", ""))[:200])
        else:
            return JsonResponse({"success": False, "error": "Unknown decision."},
                                status=400)
    except (ValidationError, ValueError) as exc:
        message = "; ".join(getattr(exc, "messages", [str(exc)]))
        return JsonResponse({"success": False, "error": message}, status=400)

    opportunity.refresh_from_db()
    return JsonResponse({
        "success": True,
        "opportunity_id": opportunity.pk,
        "state": opportunity.state,
        "state_label": opportunity.get_state_display(),
        "follow_up_scheduled": opportunity.follow_up_id is not None,
    })


class EntityWorkspaceView(FinanceEnabledRequiredMixin, PageSummaryMixin,
                          TemplateView):
    """Set up who your money can belong to, and which entity owns each account.

    Without this, Finance intelligence cannot start: attribution needs a second entity to
    attribute *to*. The production audit found exactly this state — real history, Personal
    only, zero attribution.
    """

    template_name = "finance/entity_workspace.html"
    page_summary_key = "finance.entities"
    page_summary_title = "Financial Entities"

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        from apps.finance.models import AccountEntityAssignment, FinancialAccount
        from apps.finance.services.finance_entities import ensure_default_entities

        context = super().get_context_data(**kwargs)
        user = self.request.user
        ensure_default_entities(user)

        open_rows = {
            row.account_id: row for row in
            AccountEntityAssignment.objects.filter(user=user, effective_to__isnull=True)
            .select_related("entity")
        }
        accounts = list(FinancialAccount.objects.filter(user=user)
                        .order_by("sort_order", "name"))
        context.update({
            "entities": FinancialEntity.objects.filter(user=user, is_active=True)
                                               .order_by("sort_order", "name"),
            "entity_types": FinancialEntity.ENTITY_TYPE_CHOICES,
            "accounts": [
                {"account": account,
                 "assignment": open_rows.get(account.id),
                 "entity_id": open_rows[account.id].entity_id
                 if account.id in open_rows else None}
                for account in accounts
            ],
        })
        return context


@login_required
@finance_enabled_required
@require_POST
def entity_create(request):
    """Create a user-owned entity. The name is data; the type carries the meaning."""
    from apps.finance.services.finance_entities import create_entity

    try:
        payload = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"success": False, "error": "Invalid request."}, status=400)
    try:
        entity = create_entity(
            request.user,
            entity_type=str(payload.get("entity_type", "")).strip(),
            name=str(payload.get("name", ""))[:120],
        )
    except ValidationError as exc:
        return JsonResponse({"success": False, "error": "; ".join(exc.messages)},
                            status=400)
    return JsonResponse({"success": True, "id": entity.pk, "name": entity.name,
                         "entity_type": entity.get_entity_type_display()})


@login_required
@finance_enabled_required
@require_POST
def account_assign_entity(request, pk):
    """Set which entity economically owns an account.

    The first assignment reaches back over imported history; a later one is forward-dated.
    Neither rewrites an attribution that has already been made.
    """
    from apps.finance.models import FinancialAccount
    from apps.finance.services.finance_entities import assign_account_entity

    account = get_object_or_404(FinancialAccount, pk=pk, user=request.user)
    try:
        payload = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"success": False, "error": "Invalid request."}, status=400)
    entity = get_object_or_404(
        FinancialEntity, pk=payload.get("entity_id"), user=request.user, is_active=True)
    try:
        assignment = assign_account_entity(request.user, account, entity)
    except ValidationError as exc:
        return JsonResponse({"success": False, "error": "; ".join(exc.messages)},
                            status=400)
    return JsonResponse({
        "success": True, "account_id": account.pk, "entity": entity.name,
        "effective_from": assignment.effective_from.isoformat(),
    })
