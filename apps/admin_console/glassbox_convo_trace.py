"""TEMPORARY glass-box: trace the ACTUAL conversation turn — did the attachment reach the server?

docs/WLJ_RUNTIME_TRACE_DEBUGGING.md. The persisted user-message `attachment_receipts` is derived
SERVER-SIDE from the resolved `attachments` (runtime/task), so it proves whether the server had
the attachment for a turn — vs a cosmetic client-only receipt. Also dumps `_attach_debug`
(received attachment_ids + resolved attachments) that the instrumented request path records.
Authenticated via X-Claude-API-Key. REMOVE after the trace (one commit: this file + its URL).
"""
from django.conf import settings
from django.http import JsonResponse
from django.views import View


def _auth_ok(request):
    from apps.core.rate_limiting import secure_compare_api_key
    if not settings.CLAUDE_API_KEY:
        return False
    return secure_compare_api_key(request.headers.get("X-Claude-API-Key", ""),
                                  settings.CLAUDE_API_KEY)


class ConvoTraceView(View):
    """GET /admin-console/api/claude/convo-trace/?email=<user>&limit=<n>

    Dumps the user's most-recent conversation's recent messages with the SERVER-SIDE attachment
    evidence for each turn (receipts + the request-path debug trace).
    """

    def get(self, request):
        if not _auth_ok(request):
            return JsonResponse({"error": "Invalid or missing X-Claude-API-Key."}, status=401)

        from django.contrib.auth import get_user_model
        from apps.ai.models import AssistantConversation, AssistantMessage
        from apps.capture.models import MultimodalArtifact
        User = get_user_model()

        email = request.GET.get("email", "dannyjenkins71@gmail.com")
        try:
            limit = min(int(request.GET.get("limit", 12)), 40)
        except (ValueError, TypeError):
            limit = 12
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            return JsonResponse({"error": f"no user {email}"}, status=404)

        conv = (AssistantConversation.objects.filter(user=user)
                .order_by("-updated_at", "-id").first())
        if conv is None:
            return JsonResponse({"error": "no conversation"}, status=404)

        msgs = list(AssistantMessage.objects.filter(conversation=conv)
                    .order_by("-id")[:limit])
        msgs.reverse()
        out_msgs = []
        for m in msgs:
            md = m.metadata or {}
            out_msgs.append({
                "id": m.id, "role": m.role,
                "content": (m.content or "")[:120],
                "attachment_receipts": getattr(m, "attachment_receipts", None),
                "attach_debug": md.get("_attach_debug"),  # request-path instrumentation
                "cos_path": md.get("cos_path"),
                "status": md.get("status"),
                "created_at": m.created_at.isoformat(),
            })

        # The user's document artifacts (what COULD have been attached).
        docs = list(MultimodalArtifact.objects.filter(user=user, kind="document")
                    .order_by("-id")[:5]
                    .values("id", "original_filename", "perception_status",
                            "source_conversation_id"))

        return JsonResponse({
            "conversation_id": conv.id,
            "conversation_updated_at": conv.updated_at.isoformat(),
            "messages": out_msgs,
            "recent_document_artifacts": docs,
        }, json_dumps_params={"ensure_ascii": False})
