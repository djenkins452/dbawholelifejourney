# ==============================================================================
# TEMPORARY staff-only runtime diagnostic (2026-07-06) — proves the exact runtime route
# for a page-reference message ("Explain this" on a Goal page). Deterministic facts only;
# makes NO LLM call. REMOVE after the focused-object issue is diagnosed, per the
# Temporary Infrastructure Lifecycle law (delete this module + its URL line, grep clean,
# verify startup). Do not build on top of this.
# ==============================================================================
import json
import os
import re

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


def _sha():
    for k in ("RAILWAY_GIT_COMMIT_SHA", "SOURCE_VERSION", "GIT_COMMIT"):
        v = os.environ.get(k)
        if v:
            return v[:8]
    return "?"


@csrf_exempt
@require_POST
def page_reference_diag(request):
    if not (request.user.is_authenticated and getattr(request.user, "is_staff", False)):
        return JsonResponse({"error": "staff_only"}, status=403)
    try:
        data = json.loads(request.body or b"{}")
    except Exception:
        data = {}

    message = data.get("message") or "Explain this."
    pc = data.get("page_context")
    reconstructed = not isinstance(pc, dict)
    if reconstructed:
        pc = {"url": data.get("url", ""), "module": data.get("module", ""),
              "page_title": data.get("page_title", ""), "page_content": {}}

    from apps.ai.chatgpt_cos.page_reference import (
        is_page_reference, resolve_focused_object, resolve_page_focus,
    )

    url = pc.get("url") or ""
    module = pc.get("module") or ""
    content = pc.get("page_content") if isinstance(pc.get("page_content"), dict) else {}
    m = re.search(r"/(\d+)(?:/|$)", url.lower())
    pk = int(m.group(1)) if m else None

    trace = {
        "git_sha": _sha(),
        "user_id": request.user.id,
        "message": message,
        "page_context_received": {
            "was_full_page_context": not reconstructed,
            "module": module,
            "page_title": pc.get("page_title"),
            "url": url,
            "page_content_keys": sorted(content.keys()),
            "url_pk_extracted": pk,
        },
        "is_page_reference": is_page_reference(message),
    }

    obj = None
    try:
        obj = resolve_focused_object(request.user, url, module)
    except Exception as e:
        trace["resolve_focused_object_error"] = repr(e)
    trace["resolve_focused_object"] = (
        {"found": True, "kind": obj.get("kind"), "title": obj.get("title"),
         "content_len": len(obj.get("content") or "")}
        if obj else {"found": False})

    focus = None
    try:
        focus = resolve_page_focus(pc, user=request.user)
    except Exception as e:
        trace["resolve_page_focus_error"] = repr(e)
    trace["resolve_page_focus"] = (
        {"resolved": True, "kind": focus.get("kind"), "title": focus.get("title"),
         "content_len": len(focus.get("content") or "")}
        if focus else {"resolved": False})

    if trace["is_page_reference"] and focus and (focus.get("content") or "").strip():
        trace["would_answer"] = "page_reference GROUNDED — answers from the object content"
    elif trace["is_page_reference"] and focus:
        trace["would_answer"] = "page_reference CONTENT-MISSING — 'I can see you're on X, paste it'"
    else:
        trace["would_answer"] = ("page_reference DECLINES -> normal routing (general lane -> "
                                 "the 'external knowledge service unavailable' fallback)")
    return JsonResponse(trace)
