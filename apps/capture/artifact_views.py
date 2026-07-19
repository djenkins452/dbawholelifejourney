"""
Artifact Library — the user-facing view of everything they've uploaded.

A lightweight, Chief-of-Staff-native experience (NOT a file manager): a simple
gallery of uploads with search + filter, and a detail view showing the file, what
WLJ read from it, its provenance, and links back to the conversation and any
associated domain records. Both pages declare Current Context via the page-summary
mechanism so the CoS answers "what am I looking at?" from the same deterministic
truth the page shows.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, Http404
from django.views import View
from django.views.generic import DetailView, TemplateView

from apps.capture.models import MultimodalArtifact
from apps.capture.services.artifact_queries import ArtifactQueries
from apps.core.current_context import PageSummaryMixin

_KINDS = ("image", "document", "audio", "video")


class ArtifactLibraryView(LoginRequiredMixin, PageSummaryMixin, TemplateView):
    template_name = "capture/artifact_library.html"
    page_summary_key = "artifacts.library"
    page_summary_title = "Your uploads"

    def get_page_summary_params(self):
        p = {}
        if self.request.GET.get("q", "").strip():
            p["q"] = self.request.GET.get("q").strip()[:60]
        if self.request.GET.get("kind", "").strip().lower() in _KINDS:
            p["kind"] = self.request.GET.get("kind").strip().lower()
        return p

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        q = self.request.GET.get("q", "").strip()
        kind = self.request.GET.get("kind", "").strip().lower()
        kind = kind if kind in _KINDS else None
        if q:
            artifacts = ArtifactQueries.search(user, q, kind=kind, limit=120)
        else:
            artifacts = ArtifactQueries.recent(user, kind=kind, limit=120)
        ctx.update({
            "artifacts": artifacts,
            "q": q,
            "active_kind": kind or "",
            "kinds": _KINDS,
            "counts": ArtifactQueries.counts_by_kind(user),
        })
        return ctx


class ArtifactDetailView(LoginRequiredMixin, PageSummaryMixin, DetailView):
    model = MultimodalArtifact
    template_name = "capture/artifact_detail.html"
    context_object_name = "artifact"
    page_summary_key = "artifacts.detail"
    page_summary_title = "Uploaded file"

    def get_queryset(self):
        # Ownership boundary — a user only ever sees their own artifacts.
        return MultimodalArtifact.objects.filter(user=self.request.user)

    def get_page_summary_params(self):
        return {"id": self.kwargs.get("pk")}


class ArtifactDownloadView(LoginRequiredMixin, View):
    """Serve an artifact's original bytes (owner-scoped, authenticated) — used for
    the image preview and the download link."""

    def get(self, request, pk):
        from django.core.files.storage import default_storage
        artifact = (MultimodalArtifact.objects
                    .filter(user=request.user, id=pk).first())
        if artifact is None or not artifact.storage_ref:
            raise Http404("File not available")
        try:
            fh = default_storage.open(artifact.storage_ref, "rb")
        except Exception:
            raise Http404("File not available")
        resp = FileResponse(fh, content_type=artifact.content_type or "application/octet-stream")
        disposition = "inline" if request.GET.get("inline") else "attachment"
        name = artifact.original_filename or f"artifact-{artifact.id}"
        resp["Content-Disposition"] = f'{disposition}; filename="{name}"'
        return resp
