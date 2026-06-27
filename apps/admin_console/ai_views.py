# ==============================================================================
# File: apps/admin_console/ai_views.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Admin Console → AI Operations → Beth Acceptance Center.
#   Run the live Beth acceptance suite from the browser, persist + view results,
#   and copy the generated ChatGPT-review / Claude-fix prompts. Admin-only.
# ==============================================================================
import logging

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import TemplateView, View

from apps.admin_console.models import AcceptanceRun
from apps.admin_console.views import AdminRequiredMixin
from apps.ai.chatgpt_cos.acceptance_rules import SUITES, DEPTHS

logger = logging.getLogger(__name__)


class BethAcceptanceCenterView(AdminRequiredMixin, TemplateView):
    """Landing page: run controls + latest run + run history."""
    template_name = "admin_console/beth_acceptance_center.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        runs = list(AcceptanceRun.objects.all()[:10])
        ctx["runs"] = runs
        ctx["latest"] = runs[0] if runs else None
        ctx["suites"] = [s for s in SUITES if s != "full"]
        ctx["depths"] = list(DEPTHS)
        return ctx


# button value -> (suite, depth)
_MODE_MAP = {
    "smoke": ("full", "smoke"), "full": ("full", "full"), "deep": ("full", "deep"),
    "goals": ("goals", "deep"), "health": ("health", "deep"),
    "checkin": ("checkin", "deep"), "general": ("general", "deep"),
    "rhythm": ("rhythm", "deep"), "boundary": ("boundary", "deep"),
}


class StartBethAcceptanceView(AdminRequiredMixin, View):
    """POST: create an AcceptanceRun and dispatch the async runner."""

    def post(self, request, *args, **kwargs):
        from apps.ai.chatgpt_cos.acceptance_service import (
            environment_label, git_commit,
        )
        mode = request.POST.get("mode", "full")
        suite, depth = _MODE_MAP.get(mode, ("full", "full"))
        if suite not in SUITES:
            suite = "full"
        if depth not in DEPTHS:
            depth = "full"
        evening = request.POST.get("evening", "1") != "0"

        run = AcceptanceRun.objects.create(
            suite_name=suite, depth=depth, created_by=request.user,
            target_user=request.user, environment=environment_label(),
            git_commit=git_commit(), status="running")
        try:
            from apps.ai.chatgpt_cos.tasks import run_beth_acceptance
            run_beth_acceptance.delay(run.id, evening)
            messages.success(request,
                             f"Started the {suite}/{depth} acceptance suite (run #{run.id}).")
        except Exception:
            logger.error("Failed to dispatch acceptance run", exc_info=True)
            # Fallback: run inline (small suites) so the user is never stuck.
            try:
                from apps.ai.chatgpt_cos.acceptance_service import execute_run
                execute_run(run, evening=evening)
            except Exception:
                run.status = "failed"
                run.error_message = "Could not dispatch or run the suite."
                run.save(update_fields=["status", "error_message"])
                messages.error(request, "Could not start the acceptance run.")
        return redirect(reverse("admin_console:beth_acceptance_run",
                                kwargs={"pk": run.id}))


class BethAcceptanceRunDetailView(AdminRequiredMixin, TemplateView):
    """Run detail: summary, results table/detail, and the two copy prompts."""
    template_name = "admin_console/beth_acceptance_run.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        run = get_object_or_404(AcceptanceRun, pk=kwargs["pk"])
        results = list(run.results.order_by("sort_order"))
        ctx["run"] = run
        ctx["results"] = results
        ctx["is_running"] = run.is_running
        ctx["failed_results"] = [r for r in results if not r.passed]
        # ordered category summary (skip zero counts)
        cats = run.category_summary or {}
        ctx["categories"] = [(k, v) for k, v in sorted(cats.items(), key=lambda x: -x[1]) if v]
        ctx["openai_fail"] = sum(1 for r in results
                                 if any("openai_failure" in f for f in (r.failed_rules or [])))
        ctx["wrong_domain"] = sum(1 for r in results
                                  if any("wrong_domain" in f for f in (r.failed_rules or [])))
        ctx["dupes"] = sum(1 for r in results
                           if any("duplicate_answer" in f for f in (r.failed_rules or [])))
        return ctx
