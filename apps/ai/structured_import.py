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

    def validate(self, raw_records, source_text=None):
        """Split records into (valid, skipped). ``source_text`` is the extracted text of the
        source document when one was uploaded — the adapter uses it to GROUND records against
        the real source (deterministic truth), never trusting an unverifiable model value.

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

    # RESOLVE the source artifact robustly. The model frequently passes the human FILENAME
    # ("Danny's Journal.docx") instead of the numeric artifact id — WLJ must not depend on the
    # model getting an exact id right. Resolve by id OR filename and NORMALIZE to the numeric id
    # so every downstream step (text load, perception state, idempotency, provenance) is exact.
    if source_artifact_id:
        _art = _resolve_artifact(user, source_artifact_id)
        if _art is not None:
            source_artifact_id = _art.id

    # Load the source document's own text up front. When a document was uploaded, IT is the
    # authority — WLJ parses records/dates from it and does NOT need (or trust) the model's
    # transcription. So a document import may proceed even with an empty model `raw_records`.
    source_text = _load_artifact_text(user, source_artifact_id)
    has_source_doc = bool(source_text and source_text.strip())
    raw_records = raw_records if isinstance(raw_records, list) else []

    # A document import NEVER uses model-transcribed dates. If the uploaded document is not yet
    # readable (perception still running, or it failed), report that honestly instead of
    # silently falling back to the model's records — which is exactly how a fabricated date
    # could slip in during the async window right after upload.
    if source_artifact_id and not has_source_doc:
        state = _artifact_perception_state(user, source_artifact_id)
        if state == "pending":
            return ImportOutcome(
                status="processing", error="perception_pending",
                message=("I'm still reading that document — give me a few seconds, then ask me "
                         "to add them again."))
        if state in ("failed", "unreadable"):
            return ImportOutcome(
                status="validation_failed", error="unreadable_document",
                message=("I wasn't able to read that document. Could you re-upload it, or paste "
                         "the entries directly, and I'll add them?"))
        # state in ('image', 'missing') → there is NO deterministic document text to ground
        # against (an image journal is read BY THE MODEL; a missing/foreign id has no doc), so
        # the model-provided records ARE the source here — fall through to the normal path.

    if not raw_records and not has_source_doc:
        return ImportOutcome(status="validation_failed", error="no_records",
                             message="I couldn't find any records to import.")

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
    #    The artifact's extracted text (when the source was a document) is handed to the
    #    adapter so it can GROUND records against the real source — never trusting a
    #    model-proposed value it cannot verify (e.g. a fabricated date). Deterministic truth
    #    cannot be inferred: the source document is the authority, not the model.
    try:
        valid, skipped = adapter.validate(raw_records, source_text=source_text)
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
def _resolve_artifact(user, ref):
    """Resolve the source artifact from whatever the model passed — a numeric id, OR the human
    FILENAME (the model often passes 'Danny's Journal.docx' instead of the id). Owner-scoped;
    returns the MultimodalArtifact or None. WLJ never depends on the model echoing an exact id."""
    if not ref:
        return None
    try:
        from apps.capture.models import MultimodalArtifact
        qs = MultimodalArtifact.objects.filter(user=user)
        # 1) exact numeric id.
        try:
            a = qs.filter(id=int(ref)).first()
            if a is not None:
                return a
        except (ValueError, TypeError):
            pass
        # 2) by filename (exact, then case-insensitive) — most recent match wins.
        s = str(ref).strip()
        return (qs.filter(original_filename=s).order_by("-id").first()
                or qs.filter(original_filename__iexact=s).order_by("-id").first())
    except Exception:  # pragma: no cover - defensive
        return None


def _load_artifact_text(user, source_artifact_id):
    """The extracted text of the source artifact (owner-scoped), or None. This is the
    deterministic ground truth a document adapter parses — WLJ reads the source, it does not
    take the model's word for what the document said."""
    a = _resolve_artifact(user, source_artifact_id)
    return (a.extracted_text or "") if a is not None else None


def _artifact_perception_state(user, source_artifact_id):
    """'done' | 'pending' | 'failed' | 'unreadable' | 'image' | 'missing'. Distinguishes a TEXT
    document (which must be deterministically parsed — never model dates) from an IMAGE journal
    (no document text; the MODEL read the image, so its records are the legitimate source)."""
    if not source_artifact_id:
        return "missing"
    try:
        from apps.capture.models import MultimodalArtifact  # noqa: F401 (kind constants)
        a = _resolve_artifact(user, source_artifact_id)
        if a is None:
            return "missing"
        if a.has_perception:
            return "done"
        # An image is not text-perceived — the model reads it directly; no doc text to ground.
        if (a.kind == "image") or (a.content_type or "").startswith("image/"):
            return "image"
        if a.perception_pending:
            return "pending"
        if a.perception_status == MultimodalArtifact.PERCEPTION_UNSUPPORTED:
            return "unreadable"
        return "failed"
    except Exception:  # pragma: no cover - defensive
        return "missing"


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
