"""TEMPORARY glass-box: trace duplicate journal entries — which import made each + why dedup missed.

docs/WLJ_RUNTIME_TRACE_DEBUGGING.md. Authenticated via X-Claude-API-Key. REMOVE after the trace.
"""
from collections import defaultdict

from django.conf import settings
from django.http import JsonResponse
from django.views import View


def _auth_ok(request):
    from apps.core.rate_limiting import secure_compare_api_key
    if not settings.CLAUDE_API_KEY:
        return False
    return secure_compare_api_key(request.headers.get("X-Claude-API-Key", ""),
                                  settings.CLAUDE_API_KEY)


class DupeTraceView(View):
    """GET /admin-console/api/claude/dupe-trace/?email=<user>&year=2022

    Groups the user's journal entries by (entry_date) and reports every date with >1 entry —
    each entry's id, title, entry_time, created_via, created_at, body prefix + the
    StructuredImportRun / source artifact that produced it (via provenance)."""

    def get(self, request):
        if not _auth_ok(request):
            return JsonResponse({"error": "Invalid or missing X-Claude-API-Key."}, status=401)

        from django.contrib.auth import get_user_model
        from apps.journal.models import JournalEntry
        User = get_user_model()

        email = request.GET.get("email", "dannyjenkins71@gmail.com")
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            return JsonResponse({"error": f"no user {email}"}, status=404)

        qs = JournalEntry.objects.filter(user=user, status="active").order_by("entry_date", "id")
        year = request.GET.get("year")
        if year and year.isdigit():
            qs = qs.filter(entry_date__year=int(year))

        by_date = defaultdict(list)
        for e in qs:
            by_date[str(e.entry_date)].append(e)

        dupes = {}
        total_extra = 0
        for d, entries in by_date.items():
            if len(entries) < 2:
                continue
            total_extra += len(entries) - 1
            dupes[d] = [{
                "id": e.id,
                "title": e.title,
                "entry_time": str(e.entry_time),
                "created_via": e.created_via,
                "created_at": e.created_at.isoformat(),
                "word_count": e.word_count,
                "body_plain_prefix": (e.body_plain or "")[:70],
                "body_len": len(e.body_plain or ""),
            } for e in entries]

        # StructuredImportRuns for this user (which imports ran).
        runs = []
        try:
            from apps.ai.models import StructuredImportRun
            for r in StructuredImportRun.objects.filter(
                    user=user, target_domain="journal").order_by("-id")[:10]:
                runs.append({
                    "id": r.id, "created_at": r.created_at.isoformat(),
                    "source_artifact_id": r.source_artifact_id, "source": r.source,
                    "created": r.created_count, "skipped": r.skipped_count,
                    "duplicate": r.duplicate_count, "failed": r.failed_count,
                })
        except Exception as e:  # pragma: no cover
            runs = [{"error": repr(e)}]

        # created_via distribution across ALL the user's active journal entries.
        via = defaultdict(int)
        for e in JournalEntry.objects.filter(user=user, status="active"):
            via[e.created_via or "?"] += 1

        return JsonResponse({
            "duplicate_dates": len(dupes),
            "extra_records": total_extra,
            "created_via_distribution": dict(via),
            "structured_import_runs": runs,
            "duplicates": dupes,
        }, json_dumps_params={"ensure_ascii": False})
