# ==============================================================================
# File: apps/ai/chatgpt_cos/cos_acceptance_service.py
# Description: Runner for the CHIEF-OF-STAFF Acceptance Suite. Gated: refuses to run
#   unless the latest Deep (Truth Certification) run graded GREEN — Beth must prove
#   her facts before her judgment is evaluated. Persists results as an AcceptanceRun
#   (suite_name="chief_of_staff"), reusing the existing run model + history + UI.
#   The deterministic scoring lives in cos_acceptance.py (pure); this layer adds the
#   Deep dependency, the live Beth calls, and persistence.
# ==============================================================================
import logging

from apps.ai.chatgpt_cos import cos_acceptance as cos

logger = logging.getLogger(__name__)

COS_SUITE_NAME = "chief_of_staff"


class CoSDeepNotGreen(Exception):
    """Raised when the Chief-of-Staff suite is invoked while Deep is not GREEN."""


def latest_deep_grade():
    """Grade of the most recent COMPLETED Deep (Truth Certification) run, or None.
    Deep = a run whose depth covers the factual-trust categories (depth='deep')."""
    from apps.admin_console.models import AcceptanceRun
    run = (AcceptanceRun.objects
           .filter(depth="deep", status="completed")
           .exclude(suite_name=COS_SUITE_NAME)
           .order_by("-completed_at", "-created_at")
           .first())
    return (run.grade or None) if run else None


def cos_status():
    """UI helper: (enabled, deep_grade, reason). Enabled only when Deep is GREEN."""
    grade = latest_deep_grade()
    enabled = cos.cos_enabled(grade)
    return {"enabled": enabled, "deep_grade": grade,
            "reason": "" if enabled else cos.disabled_reason(grade)}


def _default_ask(user, question):
    """Ask Beth the question through the REAL chat path and return her answer text."""
    from apps.ai.chatgpt_cos.service import ChatGPTCoSService
    try:
        res = ChatGPTCoSService(user).generate(object(), question) or {}
        return (res.get("answer") or "").strip()
    except Exception as exc:
        logger.warning("cos_acceptance ask failed: %s", exc, exc_info=True)
        return f"<EXCEPTION: {type(exc).__name__}: {exc}>"


def create_and_execute_cos(target_user, created_by=None, ask_fn=None):
    """Run the Chief-of-Staff suite against `target_user`. Gated on Deep GREEN.

    `ask_fn(user, question) -> answer_text` is injectable (defaults to live Beth) so
    the gate + scoring + persistence are unit-testable without OpenAI. Returns the
    persisted AcceptanceRun. Raises CoSDeepNotGreen if Deep is not GREEN.
    """
    from django.utils import timezone
    from apps.admin_console.models import AcceptanceRun
    from apps.ai.chatgpt_cos.acceptance_service import environment_label, git_commit

    deep_grade = latest_deep_grade()
    if not cos.cos_enabled(deep_grade):
        raise CoSDeepNotGreen(cos.disabled_reason(deep_grade))

    ask = ask_fn or _default_ask
    run = AcceptanceRun.objects.create(
        suite_name=COS_SUITE_NAME, depth="deep", target_user=target_user,
        created_by=created_by, environment=environment_label(), git_commit=git_commit(),
        status="running", started_at=timezone.now())

    pairs = []
    try:
        for scn in cos.scenarios():
            answer = ask(target_user, scn["question"])
            pairs.append((scn, answer))
        report = cos.build_report(pairs)

        run.total_count = report["count"]
        run.pass_count = len(report["first_class"])
        run.fail_count = len(report["behaved_like_chatbot"])
        run.score_percent = round(report["avg_weighted"] * 100)
        run.grade = report["grade"]
        run.critical_count = report["hard_fails"]
        run.category_summary = report["priority_by_capability"]
        run.analysis = report
        run.trustworthy = report["grade"] != "RED"
        run.status = "completed"
        run.completed_at = timezone.now()
        run.save()
    except CoSDeepNotGreen:
        raise
    except Exception as exc:
        run.status = "failed"
        run.error_message = f"{type(exc).__name__}: {exc}"
        run.completed_at = timezone.now()
        run.save()
        logger.error("cos_acceptance run %s failed", run.pk, exc_info=True)
    return run
