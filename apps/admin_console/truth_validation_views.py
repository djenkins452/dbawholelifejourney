# ==============================================================================
# File: apps/admin_console/truth_validation_views.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Admin Console → AI Operations → Truth Validation Center. Operator surface
#   for continuously validating that the Chief of Staff faithfully represents WLJ truth.
#   Run by object / domain / whole Truth Layer; auto-graded deterministically; operator
#   reviews exceptions and overrides. Admin-only. Reuses AcceptanceRun/AcceptanceResult.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
import logging

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, View

from apps.admin_console.models import AcceptanceRun, AcceptanceResult
from apps.admin_console.views import AdminRequiredMixin

logger = logging.getLogger(__name__)

_OVERRIDE_STATUSES = {"present", "missing", "mismatch", "na"}


def _latest_result_per_object():
    """The most recent truth AcceptanceResult for each object_key (across all runs).
    One ordered query, first-seen-wins — avoids N queries for the 40-object grid."""
    latest = {}
    qs = (AcceptanceResult.objects
          .filter(run__validation_type="truth",
                  run__status__in=["completed", "cancelled"])
          .order_by("-run__created_at", "-id")
          .only("object_key", "passed", "is_na", "check_pass_count", "check_total",
                "run_id"))
    for r in qs:
        if r.object_key and r.object_key not in latest:
            latest[r.object_key] = r
    return latest


def _dashboard_metrics():
    """Executive truth-health metrics from the latest result per object + run history."""
    from apps.core.truth.discovery_suite import DISCOVERY_PROMPTS
    latest = _latest_result_per_object()
    objects_total = len(DISCOVERY_PROMPTS)
    validated = list(latest.values())
    scorable = [r for r in validated if not r.is_na]
    certified = sum(1 for r in scorable if r.passed)
    checks_passed = sum(r.check_pass_count for r in validated)
    checks_total = sum(r.check_total for r in validated)
    outstanding_bugs = sum(max(0, r.check_total - r.check_pass_count) for r in scorable)
    health = round(100 * checks_passed / checks_total) if checks_total else 0

    completed = list(AcceptanceRun.objects.filter(
        validation_type="truth", status="completed").order_by("-created_at")[:10])
    trend = [{"id": r.id, "score": r.score_percent,
              "at": r.created_at.strftime("%b %d")} for r in reversed(completed)]
    success_rate = round(sum(r.score_percent for r in completed) / len(completed)) \
        if completed else 0
    avg_ms = round(sum(r.duration_ms for r in completed) / len(completed)) \
        if completed else 0
    return {
        "objects_total": objects_total,
        "objects_validated": len(validated),
        "objects_certified": certified,
        "objects_remaining": objects_total - len(validated),
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "outstanding_bugs": outstanding_bugs,
        "truth_health": health,
        "trend": trend,
        "success_rate": success_rate,
        "avg_seconds": round(avg_ms / 1000) if avg_ms else 0,
    }


class TruthValidationCenterView(AdminRequiredMixin, TemplateView):
    """Landing page: executive dashboard + object grid (by domain) + run history."""
    template_name = "admin_console/truth_validation_center.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            from apps.ai.chatgpt_cos.acceptance_service import reap_stale_runs
            reap_stale_runs()
        except Exception:
            logger.warning("truth_validation: reap on center failed", exc_info=True)

        from apps.core.truth.discovery_suite import prompts_by_domain
        latest = _latest_result_per_object()
        by_domain = prompts_by_domain()
        domains = []
        for domain in sorted(by_domain):
            objs = []
            for p in by_domain[domain]:
                r = latest.get(p["id"])
                objs.append({
                    "id": p["id"], "object": p.get("object", p["id"]),
                    "prompt": p.get("prompt", ""),
                    "status": _object_status(r),
                    "detail_run": r.run_id if r else None,
                })
            passed = sum(1 for o in objs if o["status"] == "passed")
            domains.append({"domain": domain, "objects": objs,
                            "passed": passed, "total": len(objs)})
        ctx["domains"] = domains
        ctx["metrics"] = _dashboard_metrics()
        ctx["runs"] = list(AcceptanceRun.objects.filter(
            validation_type="truth")[:12])
        active = [r for r in AcceptanceRun.objects.filter(
            validation_type="truth", status__in=["running", "cancelling"])
            if not r.is_stale]
        ctx["active_runs"] = active
        return ctx


def _object_status(result):
    if result is None:
        return "unvalidated"
    if result.is_na:
        return "na"
    return "passed" if result.passed else "failed"


class StartTruthValidationView(AdminRequiredMixin, View):
    """POST: create a Truth Validation run (scope = full | domain:<name> | object:<id>)
    and dispatch the async worker. Never runs inline (LLM + retrieval per object)."""

    def post(self, request, *args, **kwargs):
        from apps.ai.chatgpt_cos.acceptance_service import (
            environment_label, git_commit, reap_stale_runs,
        )
        from apps.ai.chatgpt_cos.truth_validation_service import (
            SUITE_VERSION, provider_version,
        )
        try:
            reap_stale_runs()
        except Exception:
            logger.warning("truth_validation: reap on start failed", exc_info=True)

        scope = (request.POST.get("scope") or "full").strip()
        scope_kind, scope_key = "full", ""
        if scope.startswith("domain:"):
            scope_kind, scope_key = "domain", scope.split(":", 1)[1]
        elif scope.startswith("object:"):
            scope_kind, scope_key = "object", scope.split(":", 1)[1]

        run = AcceptanceRun.objects.create(
            validation_type="truth", suite_name="truth", depth="truth",
            scope_kind=scope_kind, scope_key=scope_key,
            created_by=request.user, target_user=request.user,
            environment=environment_label(), git_commit=git_commit(),
            suite_version=SUITE_VERSION, provider_version=provider_version(),
            status="running")

        from apps.core.celery_utils import safe_enqueue
        from apps.ai.chatgpt_cos.tasks import run_truth_validation
        label = scope_key or "the whole Truth Layer"
        if safe_enqueue(run_truth_validation, run.id):
            messages.success(request, f"Started Truth Validation for {label} (run #{run.id}).")
        else:
            run.status = "failed"
            run.error_message = ("Could not dispatch the validation run (background "
                                 "workers unavailable). Retry when Celery is healthy.")
            run.save(update_fields=["status", "error_message"])
            messages.error(request, "Could not start validation — workers are unavailable.")
        return redirect(reverse("admin_console:truth_validation_run",
                                kwargs={"pk": run.id}))


class RerunObjectView(AdminRequiredMixin, View):
    """POST: re-validate a SINGLE object immediately (after a fix). Creates a fresh
    object-scoped run and dispatches it."""

    def post(self, request, *args, **kwargs):
        object_key = request.POST.get("object_key", "").strip()
        from apps.core.truth.discovery_suite import DISCOVERY_PROMPTS
        if object_key not in {p["id"] for p in DISCOVERY_PROMPTS}:
            messages.warning(request, "Unknown object.")
            return redirect(reverse("admin_console:truth_validation"))
        request.POST = request.POST.copy()
        request.POST["scope"] = f"object:{object_key}"
        return StartTruthValidationView.as_view()(request)


class TruthValidationRunDetailView(AdminRequiredMixin, TemplateView):
    """Run detail: per-object comparison, checks, operator decision, truth bugs."""
    template_name = "admin_console/truth_validation_run.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        run = get_object_or_404(AcceptanceRun, pk=kwargs["pk"])
        if run.status in ("running", "cancelling") and run.is_stale:
            try:
                from apps.ai.chatgpt_cos.acceptance_service import reap_stale_runs
                reap_stale_runs()
                run.refresh_from_db()
            except Exception:
                logger.warning("truth_validation: reap on detail failed", exc_info=True)
        results = list(run.results.order_by("sort_order"))
        ctx["run"] = run
        ctx["results"] = results
        ctx["is_running"] = run.is_active
        ctx["can_cancel"] = run.can_cancel
        ctx["failed_results"] = [r for r in results if not r.passed and not r.is_na]
        ctx["na_results"] = [r for r in results if r.is_na]
        ctx["bugs"] = (run.raw_report_json or {}).get("bugs", [])
        ctx["override_statuses"] = sorted(_OVERRIDE_STATUSES)
        return ctx


class CancelTruthValidationView(AdminRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        run = get_object_or_404(AcceptanceRun, pk=kwargs["pk"])
        from apps.ai.chatgpt_cos.acceptance_service import request_cancel
        new = request_cancel(run)
        if new == "cancelling":
            messages.info(request, "Cancelling — stops after the current object.")
        elif new == "cancelled":
            messages.success(request, "Run cancelled.")
        else:
            messages.warning(request, "That run is not running.")
        return redirect(reverse("admin_console:truth_validation_run", kwargs={"pk": run.pk}))


class DeleteTruthValidationView(AdminRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        run = get_object_or_404(AcceptanceRun, pk=kwargs["pk"])
        if not run.is_terminal:
            messages.warning(request, "Cancel the run before deleting it.")
            return redirect(reverse("admin_console:truth_validation_run", kwargs={"pk": run.pk}))
        run.delete()
        messages.success(request, f"Deleted validation run #{kwargs['pk']}.")
        return redirect(reverse("admin_console:truth_validation"))


class OverrideCheckView(AdminRequiredMixin, View):
    """POST: operator override of one check's status (final authority; recorded)."""

    def post(self, request, *args, **kwargs):
        result = get_object_or_404(AcceptanceResult, pk=kwargs["pk"])
        try:
            idx = int(request.POST.get("check_index"))
        except (TypeError, ValueError):
            messages.error(request, "Invalid check.")
            return self._back(result)
        new_status = (request.POST.get("status") or "").strip()
        reason = (request.POST.get("reason") or "").strip()
        if new_status not in _OVERRIDE_STATUSES:
            messages.error(request, "Invalid override status.")
            return self._back(result)
        if not reason:
            messages.error(request, "An override requires a reason.")
            return self._back(result)
        if result.apply_override(check_index=idx, new_status=new_status,
                                 reason=reason, by_user=request.user):
            _recompute_run_rollup(result.run)
            messages.success(request, "Override recorded.")
        else:
            messages.error(request, "Could not apply the override.")
        return self._back(result)

    def _back(self, result):
        return redirect(reverse("admin_console:truth_validation_run",
                                kwargs={"pk": result.run_id}))


class ApproveRunView(AdminRequiredMixin, View):
    """POST: operator sign-off — turn a run into a certification of record."""

    def post(self, request, *args, **kwargs):
        run = get_object_or_404(AcceptanceRun, pk=kwargs["pk"])
        if not run.is_terminal:
            messages.warning(request, "Only a finished run can be approved.")
        else:
            run.approved = True
            run.approved_by = request.user
            run.approved_at = timezone.now()
            run.save(update_fields=["approved", "approved_by", "approved_at"])
            messages.success(request, f"Run #{run.id} approved as a certification of record.")
        return redirect(reverse("admin_console:truth_validation_run", kwargs={"pk": run.pk}))


def _recompute_run_rollup(run):
    """Recompute run-level counts after an operator override changes an object's grade."""
    results = list(run.results.all())
    na = sum(1 for r in results if r.is_na)
    scorable = [r for r in results if not r.is_na]
    run.pass_count = sum(1 for r in scorable if r.passed)
    run.fail_count = len(scorable) - run.pass_count
    run.na_count = na
    run.checks_passed = sum(r.check_pass_count for r in results)
    run.checks_total = sum(r.check_total for r in results)
    run.score_percent = round(100 * run.checks_passed / run.checks_total) \
        if run.checks_total else 0
    # regenerate the truth-bug list from the (possibly overridden) results
    try:
        from apps.ai.chatgpt_cos.truth_validation_service import _truth_bugs
        rows = [{"object_key": r.object_key, "question": r.question_text,
                 "answer": r.response_text, "checks": r.checks, "is_na": r.is_na,
                 "passed": r.passed, "selector": (r.raw_result_json or {}).get("selector", ""),
                 "first_failing_layer": r.first_failing_layer} for r in results]
        rr = dict(run.raw_report_json or {})
        rr["bugs"] = _truth_bugs(run, rows)
        run.raw_report_json = rr
    except Exception:
        logger.warning("truth_validation: bug recompute failed run=%s", run.id, exc_info=True)
    run.save(update_fields=["pass_count", "fail_count", "na_count", "checks_passed",
                            "checks_total", "score_percent", "raw_report_json"])
