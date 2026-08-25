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
from apps.finance.models import FinancialEntity, Transaction
from apps.finance.services import attribution_review as review
from apps.finance.services import attribution_population as population
from apps.finance.services.attribution import current_attribution
from apps.finance.services.finance_entities import ensure_default_entities


class AttributionReviewView(PageSummaryMixin, TemplateView):
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
        return context


_REASON_LABELS = {
    population.REVIEW_PENDING:
        "Still pending at the bank — the amount or date can change.",
    population.REVIEW_SUSPECTED_INTERNAL_TRANSFER:
        "Looks like a payment toward one of your own accounts, not a new expense.",
}


@login_required
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
