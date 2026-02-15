"""
E3 — Views.

Provides the explain detail page showing evidence and explanations.
URL: /intelligence/explain/<source_engine>/<object_type>/<object_id>/
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.views.generic import DetailView

from apps.core.ai_explain.explain_engine import ensure_explain_record
from apps.core.ai_explain.models import ExplainRecord


class ExplainDetailView(LoginRequiredMixin, DetailView):
    """
    Display the evidence and explanation for an intelligence output.

    URL pattern: /intelligence/explain/<engine>/<type>/<id>/
    If no ExplainRecord exists yet, creates one on-demand.
    """

    template_name = "ai_explain/detail.html"
    context_object_name = "record"

    def get_object(self, queryset=None):
        """Look up or create explain record on demand."""
        engine = self.kwargs["source_engine"].upper()
        obj_type = self.kwargs["object_type"]
        obj_id = int(self.kwargs["object_id"])
        user = self.request.user

        # Try to find existing record
        record = ExplainRecord.objects.filter(
            user=user,
            source_object_type=obj_type,
            source_object_id=obj_id,
        ).first()

        if record:
            return record

        # No record yet — try to create one on-demand
        source_obj = self._load_source_object(user, engine, obj_type, obj_id)
        if not source_obj:
            raise Http404("Intelligence output not found.")

        record = ensure_explain_record(user, engine, source_obj)
        if not record:
            raise Http404("Unable to generate explanation.")

        return record

    def _load_source_object(self, user, engine, obj_type, obj_id):
        """Load the original source object for on-demand explain record creation."""
        try:
            if obj_type == "GuidanceItem":
                from apps.core.ai_guidance.models import GuidanceItem
                return GuidanceItem.objects.filter(user=user, pk=obj_id).first()

            elif obj_type == "DailyBriefing":
                from apps.core.ai_briefing.models import DailyBriefing
                return DailyBriefing.objects.filter(user=user, pk=obj_id).first()

            elif obj_type == "WeeklyIntelligenceReport":
                from apps.core.ai_weekly_report.models import WeeklyIntelligenceReport
                return WeeklyIntelligenceReport.objects.filter(user=user, pk=obj_id).first()

        except Exception:
            return None

        return None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["app_name"] = "intelligence"
        context["help_context_id"] = "EXPLAIN_DETAIL"
        return context
