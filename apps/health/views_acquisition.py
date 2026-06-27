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

# Review fields, grouped for a clean, scannable review screen (Sprint 3.6E).
FIELD_GROUPS = [
    ("Medication identity", [
        ("name", "Name"), ("strength", "Strength"), ("dose", "Dose"),
        ("dosage_form", "Form"), ("route", "Route"), ("ndc", "NDC"),
    ]),
    ("Directions & schedule", [
        ("frequency", "Frequency"), ("sig", "Directions (SIG)"),
        ("purpose", "Purpose"),
    ]),
    ("Pharmacy & prescription", [
        ("provider", "Prescriber"), ("pharmacy", "Pharmacy"),
        ("pharmacy_phone", "Pharmacy phone"), ("rx_number", "Rx number"),
    ]),
    ("Refill & inventory", [
        ("quantity", "Quantity"), ("refills", "Refills"),
        ("expiration", "Expiration"),
    ]),
]

# Flat list of (key, label) across all groups — for the manual form + POST parsing.
REVIEW_FIELDS = [field for _title, fields in FIELD_GROUPS for field in fields]


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

        def _row(key, label):
            val = values.get(key, "")
            conf = confidences.get(key)
            return {
                "key": key, "label": label, "value": val, "confidence": conf,
                "band": confidence_band(conf) if val else "missing",
            }

        # Grouped rows (Sprint 3.6E). A group is hidden if it has no acquired
        # values AND it isn't the always-shown identity group — keeps it simple.
        groups = []
        for title, fields in FIELD_GROUPS:
            rows = [_row(k, l) for k, l in fields]
            has_value = any(r["value"] for r in rows)
            if title == "Medication identity" or has_value:
                groups.append({"title": title, "rows": rows})

        context = {
            "draft": draft,
            "groups": groups,
            "missing": missing_fields(values, intake_type=draft.intake_type),
            "duplicates": detect_duplicates(request.user, draft),
            "overall_confidence": draft.overall_confidence,
            "overall_band": confidence_band(draft.overall_confidence),
            "evidence_summary": ", ".join(
                e.get("summary", "") for e in (draft.evidence or []) if e.get("summary")
            ),
            "is_pending": draft.is_pending,
        }
        return render(request, self.template_name, context)


class MedicationTimelineView(LoginRequiredMixin, View):
    """Sprint 4D — chronological treatment history. Not analytics, not a dashboard:
    the deterministic, evidence-first story of how treatment changed over time.
    Reads the canonical timeline service only (no inference, no correlation)."""

    template_name = "health/intake/timeline.html"

    def get(self, request):
        from apps.health.treatment_timeline import build_full_timeline
        from apps.health.models import Intake

        # Optional filters: ?intake=<id> (one medication), ?scope=medication (hide
        # cross-domain markers).
        intake = None
        intake_id = request.GET.get("intake")
        if intake_id:
            intake = Intake.objects.filter(user=request.user, id=intake_id).first()
        include_cross = request.GET.get("scope") != "medication"

        entries = build_full_timeline(
            request.user, intake=intake,
            include_cross_domain=include_cross, newest_first=True,
        )
        # Group by date for a clean chronological read.
        groups = []
        current = None
        for e in entries:
            if current is None or current["date"] != e["date"]:
                current = {"date": e["date"], "entries": []}
                groups.append(current)
            current["entries"].append(e)

        return render(request, self.template_name, {
            "groups": groups,
            "entry_count": len(entries),
            "intake": intake,
            "include_cross": include_cross,
        })


class MedicationNoticedView(LoginRequiredMixin, View):
    """Sprint 7G — "What We've Noticed". The visual equivalent of Beth's
    understanding: the SAME deterministic narration objects she consumes, grouped,
    each with a "why am I seeing this?" evidence trail. No duplicate logic — it
    reads the narration boundary directly."""

    template_name = "health/intake/noticed.html"

    def get(self, request):
        from apps.health.observations.narration import build_narration_view
        view = build_narration_view(request.user)
        return render(request, self.template_name, {
            "groups": view["groups"],
            "count": len(view["narrations"]),
        })


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
