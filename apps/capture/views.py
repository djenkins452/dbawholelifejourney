"""Capture views - Handle audio capture and transcription requests."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, TemplateView

from .models import CaptureEntry


class CaptureRecordView(LoginRequiredMixin, TemplateView):
    """
    Browser-based audio recording interface.

    Provides a mobile-first UI for recording audio directly in the browser
    using the MediaRecorder API. Records in webm format for best compatibility.
    """

    template_name = "capture/capture_record.html"


class CaptureListView(LoginRequiredMixin, ListView):
    """
    List all capture entries for the current user.

    Shows recordings, transcripts, and summaries ordered by most recent first.
    """

    model = CaptureEntry
    template_name = "capture/capture_list.html"
    context_object_name = "entries"
    paginate_by = 20

    def get_queryset(self):
        """Filter entries to current user, ordered by creation date."""
        return CaptureEntry.objects.filter(
            user=self.request.user
        ).order_by('-created_at')

    def get_context_data(self, **kwargs):
        """Add additional context for the template."""
        context = super().get_context_data(**kwargs)
        user_entries = CaptureEntry.objects.filter(user=self.request.user)
        context['total_count'] = user_entries.count()
        context['ready_count'] = user_entries.filter(
            status=CaptureEntry.STATUS_READY
        ).count()
        return context
