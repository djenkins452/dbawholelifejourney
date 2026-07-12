# ==============================================================================
# File: apps/health/views_body_intelligence.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Body Intelligence dashboard + Body Measurement Session (check-in) and
#              Body Progress Photo CRUD. Reads deterministic truth; never recomputes.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-12
# ==============================================================================
"""Body Intelligence — the flagship "what is happening to my body?" experience.

* ``BodyIntelligenceView`` — read-only dashboard composing existing deterministic truth
  (via ``services.body_intelligence.build_body_intelligence``). Declares its Current
  Context page summary (``summary:health.body_intelligence``).
* Session CRUD — event-driven check-ins (any cadence). Deleting a session never
  destroys measurements (SET_NULL on the measurement FKs).
* Progress photo upload/replace/soft-delete + side-by-side comparison.

Request-path-safe: pre-computed reads only. No heavy compute, no LLM.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from apps.core.current_context import PageSummaryMixin
from apps.core.views import UndoDeleteMixin
from apps.help.mixins import HelpContextMixin

from .forms import BodyMeasurementSessionForm, BodyProgressPhotoForm
from .models import (
    BodyMeasurementSession,
    BodyProgressPhoto,
    WeightEntry,
)
from .services.body_intelligence import build_body_intelligence


# ── Dashboard ──────────────────────────────────────────────────────────────


class BodyIntelligenceView(
    PageSummaryMixin, HelpContextMixin, LoginRequiredMixin, TemplateView
):
    """The Body Intelligence dashboard — the premium physical-progress experience."""

    template_name = "health/body_intelligence.html"
    help_context_id = "HEALTH_BODY_INTELLIGENCE"

    # Current Context — declares a deterministic PAGE SUMMARY (summary:health.body_intelligence)
    page_summary_key = "health.body_intelligence"
    page_summary_title = "Body Intelligence"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        bi = build_body_intelligence(self.request.user)
        ctx["bi"] = bi

        # Chart series (raw objects → json_script serializes them; parsed in a nonce'd
        # script, per WLJ convention).
        body_comp = bi.get("body_comp") or {}
        ctx["chart_weight"] = body_comp.get("weight_trend_56d") or []
        ctx["chart_fat"] = body_comp.get("fat_mass_trend_56d") or []
        ctx["chart_lean"] = body_comp.get("lean_mass_trend_56d") or []
        ctx["chart_measurements"] = bi.get("measurement_series") or {}
        return ctx


# ── Body Measurement Session (check-in) CRUD ────────────────────────────────


class BodyMeasurementSessionListView(HelpContextMixin, LoginRequiredMixin, ListView):
    """Event-driven timeline of body check-ins (any cadence — never monthly)."""

    model = BodyMeasurementSession
    template_name = "health/body_session_list.html"
    context_object_name = "sessions"
    paginate_by = 25
    help_context_id = "HEALTH_BODY_INTELLIGENCE"

    def get_queryset(self):
        return (
            BodyMeasurementSession.objects.filter(user=self.request.user)
            .order_by("-checked_in_at")
        )


class BodyMeasurementSessionDetailView(
    HelpContextMixin, LoginRequiredMixin, DetailView
):
    """A single check-in: its measurements, weigh-in, photos, notes, and comparison to
    the previous check-in."""

    model = BodyMeasurementSession
    template_name = "health/body_session_detail.html"
    context_object_name = "session"
    help_context_id = "HEALTH_BODY_INTELLIGENCE"

    def get_queryset(self):
        return BodyMeasurementSession.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        from .services.body_composition_snapshot import METRIC_LABELS

        ctx = super().get_context_data(**kwargs)
        session = self.object
        entries = list(session.entries(manager="objects").all())
        ctx["entries"] = entries
        photos = list(session.photos(manager="objects").all())
        ctx["photos"] = photos
        ctx["weigh_ins"] = list(session.weight_entries(manager="objects").all())
        ctx["metric_labels"] = METRIC_LABELS

        # Ordered pose slots for the grid (avoids variable dict-lookup in templates).
        pose_labels = dict(BodyProgressPhoto.POSE_CHOICES)
        photos_by_pose = {p.pose: p for p in photos}
        ctx["pose_slots"] = [
            {"pose": pose, "label": pose_labels.get(pose, pose), "photo": photos_by_pose.get(pose)}
            for pose in BodyProgressPhoto.POSE_ORDER
        ]
        return ctx


class BodyMeasurementSessionCreateView(HelpContextMixin, LoginRequiredMixin, CreateView):
    """Start a new check-in."""

    model = BodyMeasurementSession
    form_class = BodyMeasurementSessionForm
    template_name = "health/body_session_form.html"
    help_context_id = "HEALTH_BODY_INTELLIGENCE"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        from .services.body_intelligence import associate_ungrouped_for_session

        form.instance.user = self.request.user
        self.object = form.save()

        # Smooth workflow: pull in today's already-logged, still-ungrouped measurements
        # and weigh-in so the user doesn't have to re-enter or manually link them.
        m, w = associate_ungrouped_for_session(self.object)
        if m or w:
            bits = []
            if m:
                bits.append(f"{m} measurement{'s' if m != 1 else ''}")
            if w:
                bits.append(f"{w} weigh-in{'s' if w != 1 else ''}")
            messages.success(
                self.request,
                f"Check-in started — linked today's {' and '.join(bits)}. Add photos below.",
            )
        else:
            messages.success(
                self.request, "Check-in started. Add measurements and photos below."
            )
        return redirect("health:body_session_detail", pk=self.object.pk)


class BodyMeasurementSessionUpdateView(HelpContextMixin, LoginRequiredMixin, UpdateView):
    """Edit a check-in's details."""

    model = BodyMeasurementSession
    form_class = BodyMeasurementSessionForm
    template_name = "health/body_session_form.html"
    help_context_id = "HEALTH_BODY_INTELLIGENCE"

    def get_queryset(self):
        return BodyMeasurementSession.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_success_url(self):
        messages.success(self.request, "Check-in updated.")
        return reverse("health:body_session_detail", kwargs={"pk": self.object.pk})


class BodyMeasurementSessionDeleteView(LoginRequiredMixin, UndoDeleteMixin, View):
    """Soft-delete a check-in. The grouped measurements/weigh-ins are NOT destroyed —
    their session FK is SET_NULL and they remain as ungrouped canonical truth. Photos
    (which belong to the check-in) are soft-deleted with it."""

    model = BodyMeasurementSession
    item_type = "health.bodymeasurementsession"
    item_name = "check-in"
    success_url = "health:body_session_list"

    def get_object(self):
        return get_object_or_404(
            BodyMeasurementSession.objects.filter(user=self.request.user),
            pk=self.kwargs["pk"],
        )

    def post(self, request, *args, **kwargs):
        from .models import BodyCompositionEntry, WeightEntry

        obj = self.get_object()
        # Preserve the canonical truth: unlink measurements/weigh-ins so they become
        # ungrouped rows immediately (they are NEVER destroyed). SET_NULL only fires on
        # a hard delete, so we null the grouping explicitly here for the soft delete.
        BodyCompositionEntry.objects.filter(user=request.user, session=obj).update(session=None)
        WeightEntry.objects.filter(user=request.user, session=obj).update(session=None)
        # Photos belong to the check-in — soft-delete them with it.
        for photo in obj.photos(manager="objects").all():
            photo.soft_delete()
        return super().post(request, *args, **kwargs)


# ── Progress photos ─────────────────────────────────────────────────────────


class BodyProgressPhotoCreateView(HelpContextMixin, LoginRequiredMixin, CreateView):
    """Upload a progress photo into a check-in. Replaces an existing photo for the same
    pose in that check-in (upload = replace) so a pose holds one current image."""

    model = BodyProgressPhoto
    form_class = BodyProgressPhotoForm
    template_name = "health/body_photo_form.html"
    help_context_id = "HEALTH_BODY_INTELLIGENCE"

    def _session(self):
        return get_object_or_404(
            BodyMeasurementSession.objects.filter(user=self.request.user),
            pk=self.kwargs["session_pk"],
        )

    def get_initial(self):
        initial = super().get_initial()
        pose = self.request.GET.get("pose")
        if pose:
            initial["pose"] = pose
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["session"] = self._session()
        return ctx

    def form_valid(self, form):
        session = self._session()
        form.instance.user = self.request.user
        form.instance.session = session
        # Upload = replace: soft-delete any existing active photo for this pose.
        existing = BodyProgressPhoto.objects.filter(
            user=self.request.user, session=session, pose=form.instance.pose
        )
        for old in existing:
            old.soft_delete()
        self.object = form.save()
        messages.success(self.request, "Photo uploaded.")
        return redirect("health:body_session_detail", pk=session.pk)


class BodyProgressPhotoDeleteView(LoginRequiredMixin, UndoDeleteMixin, View):
    """Soft-delete a single progress photo (with undo)."""

    model = BodyProgressPhoto
    item_type = "health.bodyprogressphoto"
    item_name = "progress photo"

    def get_object(self):
        return get_object_or_404(
            BodyProgressPhoto.objects.filter(user=self.request.user),
            pk=self.kwargs["pk"],
        )

    def get_success_url(self):
        obj = self.get_object()
        return reverse("health:body_session_detail", kwargs={"pk": obj.session_id})


class BodyProgressComparisonView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """Side-by-side progress-photo comparison between two check-ins (defaults to the two
    most recent check-ins that have photos)."""

    template_name = "health/body_photo_compare.html"
    help_context_id = "HEALTH_BODY_INTELLIGENCE"

    def _resolve_session(self, param, sessions_with_photos, default_index):
        raw = self.request.GET.get(param)
        if raw:
            match = next((s for s in sessions_with_photos if str(s.pk) == raw), None)
            if match:
                return match
        if len(sessions_with_photos) > default_index:
            return sessions_with_photos[default_index]
        return None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        sessions_with_photos = [
            s for s in BodyMeasurementSession.objects.filter(user=user)
            .order_by("-checked_in_at")
            if s.photos(manager="objects").exists()
        ]
        ctx["available_sessions"] = sessions_with_photos

        # Default: newest as "after", next-newest as "before".
        after = self._resolve_session("after", sessions_with_photos, 0)
        before = self._resolve_session("before", sessions_with_photos, 1)

        def _photos_by_pose(session):
            if not session:
                return {}
            return {p.pose: p for p in session.photos(manager="objects").all()}

        ctx["before_session"] = before
        ctx["after_session"] = after

        before_photos = _photos_by_pose(before)
        after_photos = _photos_by_pose(after)
        pose_labels = dict(BodyProgressPhoto.POSE_CHOICES)
        ctx["pose_rows"] = [
            {
                "pose": pose,
                "label": pose_labels.get(pose, pose),
                "before": before_photos.get(pose),
                "after": after_photos.get(pose),
            }
            for pose in BodyProgressPhoto.POSE_ORDER
        ]
        return ctx
