"""
Medication Acquisition UI (Sprint 3J) — Acquire → Review → Confirm.

Thin views over the acquisition service layer (`medication_acquisition` +
`medication_confidence`). No business logic here: views create drafts, render the
guided review (confidence bands, missing fields, duplicate candidates), and post
confirmations through the single canonical write path. No Timeline / Treatment /
Learning Plans UI — acquisition only.
"""

import json
import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_protect

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
        # Consent flags so the photo actions route to consent first when needed
        # (the scan/Vision pipeline requires AI + scan consent).
        from apps.scan.models import ScanConsent
        prefs = getattr(request.user, "preferences", None)
        has_ai_consent = bool(prefs and getattr(prefs, "ai_enabled", False)
                              and getattr(prefs, "ai_data_consent", False))
        has_scan_consent = ScanConsent.objects.filter(user=request.user).exists()
        return render(request, self.template_name, {
            "fields": REVIEW_FIELDS,
            "intake_types": Intake.INTAKE_TYPE_CHOICES,
            "photo_ready": has_ai_consent and has_scan_consent,
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


MAX_CAPTURE_IMAGES = 6


def _capture_consent_ok(user):
    """Photo acquisition needs AI + scan consent (same gate as Scan/Vision)."""
    from apps.scan.models import ScanConsent
    prefs = getattr(user, "preferences", None)
    ai_ok = bool(prefs and getattr(prefs, "ai_enabled", False)
                 and getattr(prefs, "ai_data_consent", False))
    return ai_ok and ScanConsent.objects.filter(user=user).exists()


def _capture_gate(request):
    """Consent + rate-limit gate for the capture POST endpoints. Returns a
    JsonResponse to short-circuit, or None when the request may proceed."""
    if not _capture_consent_ok(request.user):
        return JsonResponse(
            {"error": "consent_required", "url": reverse("scan:consent")}, status=403)
    try:
        from apps.scan.views import check_rate_limit, get_client_ip
        allowed, retry_after = check_rate_limit(request.user, get_client_ip(request))
        if not allowed:
            resp = JsonResponse({"error": "rate_limited"}, status=429)
            resp["Retry-After"] = str(retry_after)
            return resp
    except Exception:
        logger.debug("capture rate-limit check skipped", exc_info=True)
    return None


def _capture_payload(request):
    """Parse + bound the JSON capture payload → (images, intake_type) or error."""
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return None, JsonResponse({"error": "bad_request"}, status=400)
    images = (body.get("images") or [])[:MAX_CAPTURE_IMAGES]
    intake_type = body.get("intake_type") or "medication"
    if not images:
        return None, JsonResponse({"error": "no_images"}, status=400)
    return (images, intake_type), None


class CaptureSessionView(LoginRequiredMixin, View):
    """Guided Capture Session page — walk the user through profile-specific photos,
    accumulate them, and finalize into ONE draft (the existing pipeline). No
    canonical write happens here; review + confirm still follow."""

    template_name = "health/acquisition/capture.html"

    def get(self, request):
        from apps.health.capture_profiles import CAPTURE_PROFILES
        profile_key = request.GET.get("profile")
        return render(request, self.template_name, {
            "profiles": CAPTURE_PROFILES,
            "initial_profile": profile_key if profile_key in CAPTURE_PROFILES else "",
            "photo_ready": _capture_consent_ok(request.user),
        })


def _enqueue_capture(session):
    """Hand the session to the Celery worker (off the request path).

    NEVER live-computes Vision in the web process: `process_capture_session`
    calls the OpenAI Vision API (multi-second), so running it inline would pin a
    gunicorn worker. If the broker is unavailable, mark the session so the user
    can retry (CaptureRetryView) once background processing is healthy.
    safe_enqueue runs inline under EAGER (tests), async in prod."""
    from apps.core.celery_utils import safe_enqueue
    from apps.health.tasks import process_medication_capture
    if not safe_enqueue(process_medication_capture, session.id):
        logger.warning("capture %s: broker unavailable — marking for retry",
                       session.id)
        session.mark_failed("We couldn't start analysis right now. Please retry.")


def _session_review_url(session):
    if session.created_draft_id:
        return reverse("health:medication_review",
                       kwargs={"draft_id": session.created_draft_id})
    return None


@method_decorator(csrf_protect, name="dispatch")
class CaptureStartView(LoginRequiredMixin, View):
    """Create a capture session and return IMMEDIATELY — Vision runs in the
    background worker. The browser polls CaptureStatusView for progress. No Vision
    on the request path; nothing canonical until the user confirms in review."""

    def post(self, request):
        gated = _capture_gate(request)
        if gated is not None:
            return gated
        parsed, err = _capture_payload(request)
        if err is not None:
            return err
        images, intake_type = parsed
        try:
            body = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            body = {}
        profile = body.get("profile") or ""

        from apps.health.models import MedicationCaptureSession
        session = MedicationCaptureSession.objects.create(
            user=request.user, profile=profile, intake_type=intake_type,
            images=images, images_total=len(images),
            current_step="Uploading photos…",
        )
        _enqueue_capture(session)
        return JsonResponse({
            "session_id": session.id,
            "status_url": reverse("health:medication_capture_status",
                                  kwargs={"session_id": session.id}),
        }, status=202)


class CaptureStatusView(LoginRequiredMixin, View):
    """Poll target — current step, counts, confidence, and the review URL when
    ready. Read-only; never computes Vision (request-path-safe)."""

    def get(self, request, session_id):
        from apps.health.models import MedicationCaptureSession
        session = get_object_or_404(
            MedicationCaptureSession, id=session_id, user=request.user)
        return JsonResponse(session.progress_dict(
            review_url=_session_review_url(session)))


@method_decorator(csrf_protect, name="dispatch")
class CaptureRetryView(LoginRequiredMixin, View):
    """Re-run a failed session (images were kept). Optionally replace images first."""

    def post(self, request, session_id):
        from apps.health.models import MedicationCaptureSession
        session = get_object_or_404(
            MedicationCaptureSession, id=session_id, user=request.user)
        try:
            body = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            body = {}
        # Optional: replace the image set before retrying.
        new_images = body.get("images")
        if isinstance(new_images, list) and new_images:
            session.images = new_images[:MAX_CAPTURE_IMAGES]
            session.images_total = len(session.images)
        session.processing_status = MedicationCaptureSession.STATUS_CREATED
        session.retry_count = (session.retry_count or 0) + 1
        session.error_message = ""
        session.current_step = "Re-queued…"
        session.save(update_fields=["images", "images_total", "processing_status",
                                    "retry_count", "error_message",
                                    "current_step", "updated_at"])
        _enqueue_capture(session)
        return JsonResponse({
            "session_id": session.id,
            "status_url": reverse("health:medication_capture_status",
                                  kwargs={"session_id": session.id}),
        }, status=202)


@method_decorator(csrf_protect, name="dispatch")
class CaptureCancelView(LoginRequiredMixin, View):
    """Cancel a session — drops its images; nothing canonical was ever written."""

    def post(self, request, session_id):
        from apps.health.models import MedicationCaptureSession
        session = get_object_or_404(
            MedicationCaptureSession, id=session_id, user=request.user)
        session.processing_status = MedicationCaptureSession.STATUS_CANCELLED
        session.images = []
        session.current_step = "Cancelled."
        session.save(update_fields=["processing_status", "images", "current_step", "updated_at"])
        return JsonResponse({"cancelled": True})


class TreatmentDashboardView(LoginRequiredMixin, View):
    """Sprint 10F — read-only Treatment Intelligence dashboard. Shows active
    treatment plans, their linked medications/supplements, goals, tracked outcomes,
    recent changes, and "what we're watching" — composed deterministic state only.
    No recommendations, no predictions."""

    template_name = "health/intake/treatment_dashboard.html"

    def get(self, request):
        from apps.health.treatment_intelligence import build_treatment_state
        return render(request, self.template_name, {
            "treatment": build_treatment_state(request.user),
        })


class PhysicianModeView(LoginRequiredMixin, View):
    """Sprint 8 — Physician Mode. A clean, print-friendly, patient-owned summary
    assembled entirely from deterministic canonical layers. No diagnosis, no
    recommendations — it organizes what WLJ knows for a better physician visit."""

    template_name = "health/intake/physician_summary.html"

    def get(self, request):
        from apps.health.physician_summary import build_physician_summary
        from apps.health.observations.telemetry import record_physician_summary_generated

        record_physician_summary_generated()
        try:
            summary = build_physician_summary(request.user)
        except Exception:
            logger.warning("Physician summary failed for user %s",
                           request.user.id, exc_info=True)
            messages.error(
                request, "We couldn't build your summary right now. Please try again.")
            return redirect("health:intake_home")
        return render(request, self.template_name, {"summary": summary})


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
