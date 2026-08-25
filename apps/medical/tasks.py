"""
Celery tasks for the Medication Reference truth domain (M1).

REQUEST-PATH SAFETY IS THE POINT OF THIS MODULE. Resolving a medication to its
authoritative label requires outbound HTTP to NLM/FDA, which may never happen on an
interactive Chief-of-Staff request (`docs/WLJ_REQUEST_PATH_SAFETY.md`). All of it
happens here, in the background; the truth surface only ever reads the database.

Scope: only medications users ACTUALLY TAKE are resolved — never a whole catalog.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)

# Re-resolve a label at most this often. Labels change, but slowly; this bounds
# outbound traffic while keeping `retrieved_at` meaningful.
REFRESH_AFTER_DAYS = 30

# A hard ceiling per run, so one pass can never become an unbounded crawl.
MAX_PER_RUN = 50


@shared_task(name="medical.refresh_medication_reference_labels")
def refresh_medication_reference_labels(limit=MAX_PER_RUN):
    """Resolve/refresh authoritative labels for active medications users take.

    Idempotent and fail-safe: one medication's failure never aborts the pass, and a
    refusal (ambiguous / unsupported / no_label) is RECORDED on the Intake rather than
    retried forever — a generic that cannot be resolved in M1 is a settled state, not
    an error.
    """
    from datetime import timedelta

    from django.db.models import Q
    from django.utils import timezone

    from apps.health.models import Intake
    from apps.medical.services import medication_reference as ref

    cutoff = timezone.now() - timedelta(days=REFRESH_AFTER_DAYS)
    due = (Intake.objects
           .filter(intake_status="active", intake_type="medication")
           .filter(Q(reference_resolved_at__isnull=True)
                   | Q(reference_resolved_at__lt=cutoff))
           .order_by("reference_resolved_at", "id")[:max(1, int(limit or MAX_PER_RUN))])

    counts = {"resolved": 0, "ambiguous": 0, "unsupported": 0, "no_label": 0,
              "errors": 0}
    for intake in due:
        try:
            outcome = ref.resolve_and_link_intake(intake)
            counts[outcome.state] = counts.get(outcome.state, 0) + 1
        except Exception:
            counts["errors"] += 1
            logger.error("medication_reference: resolve failed for intake %s",
                         getattr(intake, "id", "?"), exc_info=True)
    logger.info("medication_reference refresh: %s", counts)
    return counts
