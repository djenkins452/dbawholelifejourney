"""TEMPORARY glass-box: trace a journal-document Structured Import on the ACTUAL prod runtime.

docs/WLJ_RUNTIME_TRACE_DEBUGGING.md — prove where readable document text becomes zero import
records, with REAL data (not unit tests). Authenticated via X-Claude-API-Key (operator channel).
REMOVE COMPLETELY after the trace (temporary infra lifecycle): this file + its URL, one commit.
"""
import json

from django.conf import settings
from django.http import JsonResponse
from django.views import View


def _auth_ok(request):
    from apps.core.rate_limiting import secure_compare_api_key
    if not settings.CLAUDE_API_KEY:
        return False
    return secure_compare_api_key(request.headers.get("X-Claude-API-Key", ""),
                                  settings.CLAUDE_API_KEY)


class ImportTraceView(View):
    """GET /admin-console/api/claude/import-trace/?email=<user>&artifact_id=<opt>

    Returns the full deterministic trace: the selected artifact, its perception state, the
    exact extracted_text WLJ has, and what the journal parser + Structured Import do with it.
    """

    def get(self, request):
        if not _auth_ok(request):
            return JsonResponse({"error": "Invalid or missing X-Claude-API-Key."}, status=401)

        from django.contrib.auth import get_user_model
        from apps.capture.models import MultimodalArtifact
        User = get_user_model()

        email = request.GET.get("email", "dannyjenkins71@gmail.com")
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            return JsonResponse({"error": f"no user {email}"}, status=404)

        art_id = request.GET.get("artifact_id")
        qs = MultimodalArtifact.objects.filter(user=user)
        if art_id:
            art = qs.filter(id=art_id).first()
        else:
            # Latest document artifact (the journal upload).
            art = qs.filter(kind="document").order_by("-id").first()
        if art is None:
            return JsonResponse({"error": "no matching artifact"}, status=404)

        text = art.extracted_text or ""
        out = {
            # Q1-Q6: the artifact + its readable field.
            "artifact_id": art.id,
            "kind": art.kind,
            "content_type": art.content_type,
            "original_filename": art.original_filename,
            "perception_status": art.perception_status,
            "storage_status": getattr(art, "storage_status", None),
            "has_perception": art.has_perception,
            "extracted_text_len": len(text),
            "extracted_text_first_500": text[:500],
            "extracted_text_last_500": text[-500:],
            "extracted_text_repr_first_300": repr(text[:300]),  # exposes \xa0, \r, \f, etc.
        }

        # Q7-Q8: source_text the engine would load, and whether it equals the readable text.
        try:
            from apps.ai.structured_import import _load_artifact_text
            source_text = _load_artifact_text(user, art.id)
        except Exception as e:  # pragma: no cover
            source_text = None
            out["source_text_error"] = repr(e)
        out["source_text_len"] = len(source_text or "")
        out["source_text_equals_extracted"] = (source_text or "") == text

        # Q9-Q12: the parser, its header candidates, and constructed records.
        try:
            from apps.ai.import_adapters.journal_import import (
                _HEADER_RE, _header_rest_is_clean, parse_journal_document,
            )
            raw_matches = list(_HEADER_RE.finditer(text))
            clean = [m for m in raw_matches if _header_rest_is_clean(m.group("rest"))]
            entries, had = parse_journal_document(text)
            out["parser"] = "journal_import.parse_journal_document"
            out["raw_header_candidates"] = len(raw_matches)
            out["clean_header_candidates"] = len(clean)
            out["records_constructed"] = len(entries)
            out["had_headers"] = had
            out["sample_records"] = [
                {"date": str(e["entry_date"]), "time": str(e["entry_time"]),
                 "skipped": e["skipped"], "body_preview": e["body"][:60]}
                for e in entries[:12]
            ]
            out["raw_match_lines"] = [text[m.start():m.start() + 60] for m in raw_matches[:12]]
        except Exception as e:  # pragma: no cover
            out["parser_error"] = repr(e)

        # Q13-Q14: the actual Structured Import outcome (dry — preview, confirmed=False).
        try:
            from apps.ai.import_adapters.journal_import import JournalImportAdapter
            from apps.ai.structured_import import run_structured_import
            outcome = run_structured_import(
                user, JournalImportAdapter(), [],
                source_artifact_id=art.id, source="journal document", confirmed=False)
            out["import_outcome_status"] = outcome.status
            out["import_outcome_error"] = outcome.error
            out["import_outcome_message"] = outcome.message
            cd = outcome.confirmation_detail or {}
            out["import_records"] = len(cd.get("records") or [])
            out["import_skipped"] = len(cd.get("skipped") or [])
        except Exception as e:  # pragma: no cover
            out["import_error"] = repr(e)

        return JsonResponse(out, json_dumps_params={"ensure_ascii": False})
