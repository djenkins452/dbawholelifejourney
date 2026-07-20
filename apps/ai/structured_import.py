"""Structured Import Orchestration — the generic, domain-agnostic engine.

docs/WLJ_STRUCTURED_IMPORT_ARCHITECTURE.md — one uploaded document that contains MANY
logical records (a journal export, a statement, a lab panel) becomes many deterministic,
provenance-bearing records after a faithful PREVIEW and explicit CONFIRMATION.

WLJ owns the deterministic truth; the model perceives structure and calls a TYPED batch
intent (import_journal_entries, future import_expenses…). This module runs the SAME spine
for every domain:

    idempotency → per-record validation → preview/confirm → atomic create → provenance → audit

It contains NO domain knowledge and NO reasoning. Each domain plugs in a thin
``StructuredImportAdapter`` (validate / create_one / dedupe_exists / preview_detail) via
``register_import_adapter``. The confirmation PRESENTATION is owned by the generic
``apps.ai.import_confirmation`` framework, never here and never in a domain handler.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

STRUCTURED_IMPORT_SCHEMA_VERSION = "1.0"


# ── Adapter contract ────────────────────────────────────────────────────────
class StructuredImportAdapter:
    """Base class for a per-domain import adapter. Subclasses are THIN: they map a
    model-produced record to WLJ's canonical fields, validate it deterministically, create
    ONE record through the domain's safe write, and answer a dedup question. All batching,
    idempotency, confirmation policy, provenance, and audit are the engine's job."""

    domain: str = ""          # Layer-1 domain name (e.g. 'journal')
    intent: str = ""          # typed batch intent (e.g. 'import_journal_entries')
    renderer: str = ""        # apps.ai.import_confirmation renderer key
    records_key: str = "records"  # the tool arg carrying the record array

    def validate(self, raw_records):
        """Split the raw model-produced records into (valid, skipped).

        Returns ``(valid, skipped)`` where:
          • ``valid``   = list of normalized record dicts ready to create; each SHOULD carry
            a display ``label`` (+ any fields ``preview_detail`` / ``create_one`` need).
          • ``skipped`` = list of ``{label, reason}`` for perceived records WLJ will NOT
            create (marked-skipped, invalid, unsupported). Nothing perceived is dropped
            silently — every non-created record appears here with a reason.
        """
        raise NotImplementedError

    def dedupe_exists(self, user, record) -> bool:
        """Deterministic per-record duplicate check (e.g. same user+date+time+title)."""
        return False

    def create_one(self, user, record):
        """Create ONE record through the domain's safe write. Return the created object
        (must have an ``id``). Raise on failure — the engine records it as ``failed`` and
        continues the batch."""
        raise NotImplementedError

    def preview_detail(self, *, valid, skipped, source, source_artifact_id) -> dict:
        """Return the ``confirmation_detail`` dict the generic presenter renders. Facts only —
        the engine adds nothing. Default builds the standard record-kind detail; override to
        add domain facts (all still derived from structured fields)."""
        return {
            "renderer": self.renderer,
            "intent": self.intent,
            "kind": "record",
            "source": source,
            "source_artifact_id": source_artifact_id,
            "records": valid,
            "skipped": skipped,
        }


_ADAPTERS = {}


def register_import_adapter(adapter):
    """Register a domain adapter instance, keyed by its typed intent."""
    _ADAPTERS[adapter.intent] = adapter


def get_import_adapter(intent):
    """Resolve the adapter for a typed batch intent, or None."""
    return _ADAPTERS.get(intent)


# ── Engine outcome (mapped 1:1 to ActionResult by the thin handler) ─────────
@dataclass
class ImportOutcome:
    status: str                 # 'success' | 'confirmation_required' | 'validation_failed'
    message: str = ""           #             | 'duplicate' | 'error'
    confirmation_detail: Optional[dict] = None
    created_object: Optional[dict] = None
    error: Optional[str] = None
    run_id: Optional[int] = None
    counts: dict = field(default_factory=dict)


# ── The spine ────────────────────────────────────────────────────────────────
def run_structured_import(user, adapter, raw_records, *, source_artifact_id=None,
                          source="", confirmed=False):
    """Run one structured-import batch through the deterministic spine.

    The model has already perceived the records; here WLJ validates, previews, confirms,
    then (only on confirm) atomically creates each valid record, records provenance + a
    per-record audit run, and reports the ACTUAL created/skipped/duplicate/failed counts.
    Never writes a partial batch without confirmation. Never raises.
    """
    from django.db import transaction

    from apps.ai import multimodal

    if not isinstance(raw_records, list) or not raw_records:
        return ImportOutcome(status="validation_failed", error="no_records",
                             message="I couldn't find any records to import in that document.")

    # 1. Artifact-level IDEMPOTENCY — the SAME document never imports twice.
    if source_artifact_id:
        existing = _existing_run(user, source_artifact_id, adapter.domain)
        if existing is not None:
            return ImportOutcome(
                status="success", run_id=existing.id,
                message=(f"You already imported this document "
                         f"({existing.created_count} {adapter.domain} record"
                         f"{'s' if existing.created_count != 1 else ''}), so I didn't add "
                         "duplicates — that import still stands."),
                created_object={"model": "StructuredImportRun", "id": existing.id,
                                "duplicate_of_artifact": source_artifact_id,
                                "created_count": existing.created_count},
                counts=_counts(existing),
            )

    # 2. Per-record deterministic VALIDATION (adapter owns field mapping/plausibility).
    try:
        valid, skipped = adapter.validate(raw_records)
    except Exception:
        logger.error("structured_import: adapter.validate failed intent=%s user=%s",
                     adapter.intent, getattr(user, "id", "?"), exc_info=True)
        return ImportOutcome(status="error", error="validation_error",
                             message="Something went wrong reading that document.")
    valid = list(valid or [])
    skipped = list(skipped or [])

    if not valid:
        return ImportOutcome(
            status="validation_failed", error="no_valid_records",
            message=("I recognized the document but couldn't turn any of it into "
                     f"{adapter.domain} records to import."),
            confirmation_detail=adapter.preview_detail(
                valid=[], skipped=skipped, source=source,
                source_artifact_id=source_artifact_id),
        )

    # 3. CONFIRMATION policy — a structured multi-record import ALWAYS previews first,
    #    whatever the source (upload or typed): the user confirms the whole batch before
    #    anything is created. Nothing is written until confirmed.
    if not confirmed:
        detail = adapter.preview_detail(valid=valid, skipped=skipped, source=source,
                                        source_artifact_id=source_artifact_id)
        n = len(valid)
        return ImportOutcome(
            status="confirmation_required", error="confirmation_required",
            confirmation_detail=detail,
            message=(f"I found {n} {adapter.domain} record{'s' if n != 1 else ''} to import"
                     f"{f' ({len(skipped)} I can’t import)' if skipped else ''} — "
                     "review before I create them."),
        )

    # 4. Atomic CREATE — dedup each record, create the rest; a per-record failure is
    #    recorded and skipped, never aborting the whole batch.
    created, duplicates, failed = [], [], []
    manifest = []
    for rec in valid:
        label = rec.get("label", "")
        try:
            if adapter.dedupe_exists(user, rec):
                duplicates.append(rec)
                manifest.append({"label": label, "outcome": "duplicate"})
                continue
            with transaction.atomic():
                obj = adapter.create_one(user, rec)
            created.append({"label": label, "id": getattr(obj, "id", None)})
            manifest.append({"label": label, "outcome": "created",
                             "object_id": getattr(obj, "id", None)})
        except Exception:
            logger.error("structured_import: create_one failed intent=%s label=%r user=%s",
                         adapter.intent, label, getattr(user, "id", "?"), exc_info=True)
            failed.append(rec)
            manifest.append({"label": label, "outcome": "failed", "reason": "create_error"})
    for s in skipped:
        manifest.append({"label": s.get("label", ""), "outcome": "skipped",
                         "reason": s.get("reason", "")})

    # 5. PROVENANCE + AUDIT — one run row records the batch; link the artifact to it.
    run = _record_run(
        user, adapter, source=source, source_artifact_id=source_artifact_id,
        created=len(created), skipped=len(skipped), duplicate=len(duplicates),
        failed=len(failed), manifest=manifest)
    if source_artifact_id and run is not None:
        multimodal.link_artifact(
            source_artifact_id, intent=adapter.intent,
            object_type="StructuredImportRun", object_id=run.id)

    _emit_import_event(adapter, user, run, created=len(created))

    counts = {"created": len(created), "skipped": len(skipped),
              "duplicate": len(duplicates), "failed": len(failed)}
    return ImportOutcome(
        status="success",
        run_id=getattr(run, "id", None),
        message=_result_message(adapter, counts),
        created_object={"model": "StructuredImportRun",
                        "id": getattr(run, "id", None),
                        "target_domain": adapter.domain,
                        "source": (f"user_upload:{source_artifact_id}"
                                   if source_artifact_id else (source or "typed")),
                        **counts},
        counts=counts,
    )


# ── Provenance/audit helpers (StructuredImportRun) ──────────────────────────
def _existing_run(user, source_artifact_id, domain):
    try:
        from apps.ai.models import StructuredImportRun
        return StructuredImportRun.objects.filter(
            user=user, source_artifact_id=str(source_artifact_id),
            target_domain=domain).order_by("-created_at").first()
    except Exception:  # pragma: no cover - defensive
        return None


def _record_run(user, adapter, *, source, source_artifact_id, created, skipped,
                duplicate, failed, manifest):
    try:
        from apps.ai.models import StructuredImportRun
        return StructuredImportRun.objects.create(
            user=user, target_domain=adapter.domain, intent=adapter.intent,
            source_artifact_id=str(source_artifact_id or ""), source=(source or ""),
            created_count=created, skipped_count=skipped, duplicate_count=duplicate,
            failed_count=failed, manifest=manifest,
        )
    except Exception:  # pragma: no cover - defensive
        logger.error("structured_import: could not record run intent=%s user=%s",
                     adapter.intent, getattr(user, "id", "?"), exc_info=True)
        return None


def _counts(run):
    return {"created": run.created_count, "skipped": run.skipped_count,
            "duplicate": run.duplicate_count, "failed": run.failed_count}


def _emit_import_event(adapter, user, run, *, created):
    try:
        from apps.ai.action_handlers import _emit_domain_event
        _emit_domain_event(f"{adapter.domain}.structured_import.completed", user, {
            "run_id": getattr(run, "id", None), "intent": adapter.intent,
            "created": created,
        })
    except Exception:  # pragma: no cover - defensive
        logger.debug("structured_import: domain event emit skipped", exc_info=True)


def _result_message(adapter, counts):
    parts = [f"Imported {counts['created']} {adapter.domain} "
             f"record{'s' if counts['created'] != 1 else ''}"]
    extra = []
    if counts["duplicate"]:
        extra.append(f"{counts['duplicate']} already existed")
    if counts["skipped"]:
        extra.append(f"{counts['skipped']} couldn’t be imported")
    if counts["failed"]:
        extra.append(f"{counts['failed']} failed to save")
    if extra:
        parts.append(f" ({', '.join(extra)})")
    return "".join(parts) + "."
