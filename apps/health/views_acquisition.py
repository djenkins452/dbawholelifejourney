"""
Medication Acquisition UI (Sprint 3J) — Acquire → Review → Confirm.

Thin views over the acquisition service layer (`medication_acquisition` +
`medication_confidence`). No business logic here: views create drafts, render the
guided review (confidence bands, missing fields, duplicate candidates), and post
confirmations through the single canonical write path. No Timeline / Treatment /
Learning Plans UI — acquisition only.
"""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from apps.health.medication_acquisition import (
    confirm_draft,
    create_manual_draft,
    detect_duplicates,
)
from apps.health.medication_confidence import confidence_band, missing_fields
from apps.health.models import Intake, MedicationScanDraft

logger = logging.getLogger(__name__)

# The fields the manual-entry form / review screen present, in display order.
REVIEW_FIELDS = [
    ("name", "Name"),
    ("dose", "Dose"),
    ("frequency", "Frequency"),
    ("purpose", "Purpose"),
    ("sig", "Directions (SIG)"),
    ("provider", "Prescriber"),
    ("pharmacy", "Pharmacy"),
    ("quantity", "Quantity"),
    ("refills", "Refills"),
    ("expiration", "Expiration"),
]


class MedicationAcquireView(LoginRequiredMixin, View):
    """Manual entry — a first-class acquisition method (Sprint 3G).

    GET renders the entry form; POST creates a draft and routes to guided review
    (everything goes through the same review/confirm workflow, even manual entry).
    """

    template_name = "health/acquisition/acquire.html"

    def get(self, request):
        return render(request, self.template_name, {
            "fields": REVIEW_FIELDS,
            "intake_types": Intake.INTAKE_TYPE_CHOICES,
        })

    def post(self, request):
        values = {
            key: request.POST.get(key, "").strip()
            for key, _label in REVIEW_FIELDS
            if request.POST.get(key, "").strip()
        }
        if not values.get("name"):
            messages.error(request, "A medication or supplement name is required.")
            return redirect("health:medication_acquire")
        intake_type = request.POST.get("intake_type") or Intake.INTAKE_TYPE_MEDICATION
        draft = create_manual_draft(request.user, values, intake_type=intake_type)
        return redirect("health:medication_review", draft_id=draft.id)


class MedicationReviewView(LoginRequiredMixin, View):
    """Guided review (Sprint 3D) — "I believe I found…" with confidence bands,
    missing information, and duplicate candidates, all editable before confirm."""

    template_name = "health/acquisition/review.html"

    def get(self, request, draft_id):
        draft = get_object_or_404(
            MedicationScanDraft, id=draft_id, user=request.user
        )
        values = draft.extracted_values or {}
        confidences = draft.field_confidences or {}
        rows = []
        for key, label in REVIEW_FIELDS:
            val = values.get(key, "")
            conf = confidences.get(key)
            rows.append({
                "key": key,
                "label": label,
                "value": val,
                "confidence": conf,
                "band": confidence_band(conf) if val else "missing",
            })
        context = {
            "draft": draft,
            "rows": rows,
            "missing": missing_fields(values, intake_type=draft.intake_type),
            "duplicates": detect_duplicates(request.user, draft),
            "overall_confidence": draft.overall_confidence,
            "overall_band": confidence_band(draft.overall_confidence),
            "is_pending": draft.is_pending,
        }
        return render(request, self.template_name, context)


class MedicationConfirmView(LoginRequiredMixin, View):
    """Confirmation (Sprint 3F) — resolve the draft into canonical state through
    the single write path. POST only."""

    def post(self, request, draft_id):
        draft = get_object_or_404(
            MedicationScanDraft, id=draft_id, user=request.user
        )
        if not draft.is_pending:
            messages.info(request, "This acquisition has already been reviewed.")
            return redirect("health:intake_home")

        action = request.POST.get("action", MedicationScanDraft.ACTION_CREATE)
        # User edits during review (highest-confidence evidence).
        edits = {
            key: request.POST.get(key, "").strip()
            for key, _label in REVIEW_FIELDS
            if request.POST.get(key, "").strip()
        }
        target = None
        target_id = request.POST.get("target_intake_id")
        if target_id:
            target = Intake.objects.filter(
                user=request.user, id=target_id
            ).first()

        try:
            result = confirm_draft(
                draft, action, target_intake=target, edits=edits or None,
            )
        except Exception:
            logger.warning("Confirmation failed for draft %s", draft_id, exc_info=True)
            messages.error(request, "Something went wrong confirming that. Please try again.")
            return redirect("health:medication_review", draft_id=draft.id)

        if action == MedicationScanDraft.ACTION_IGNORE:
            messages.info(request, "Discarded — nothing was added.")
            return redirect("health:intake_home")

        name = (draft.extracted_values or {}).get("name", "the medication")
        messages.success(request, f"Confirmed {name}.")
        if result is not None:
            return redirect("health:intake_detail", pk=result.pk)
        return redirect("health:intake_home")
