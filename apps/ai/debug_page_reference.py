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

    # --- run_llm: execute the EXACT step the real chat path runs but the deterministic
    # diagnostic skips — answer_page_reference's LLM call — and report WHY it returns
    # None (no key / breaker open / OpenAI error). Opt-in so the default stays LLM-free.
    if data.get("run_llm"):
        from django.core.cache import cache
        from apps.ai.services import ai_service
        from apps.ai.chatgpt_cos.page_reference import answer_page_reference
        trace["llm_state"] = {
            "is_available": bool(getattr(ai_service, "is_available", False)),
            "breaker_open": bool(cache.get("openai_rate_limited")),
        }
        # 1) The raw call page_reference makes (same args, no bypass_breaker).
        try:
            raw = ai_service._call_api(
                "You are a Chief of Staff. Reply with the single word: ok.",
                message, max_tokens=8, endpoint="cos_page_reference", user=request.user,
            )
            trace["raw_call_api"] = {"returned": ("None" if raw is None else "text"),
                                     "value": (str(raw)[:60] if raw else None)}
        except Exception as e:
            trace["raw_call_api"] = {"exception": repr(e)}
        # 2) The full lane function (what route_message actually calls).
        try:
            res = answer_page_reference(request.user, message, None, pc)
            trace["answer_page_reference"] = (
                {"returned": "dict", "lane": res.get("lane"),
                 "answer_len": len(res.get("answer") or "")}
                if res else {"returned": "None -> route_message falls to general lane"})
        except Exception as e:
            trace["answer_page_reference"] = {"exception": repr(e)}
        # 3) WORKER-side probe — production streaming chat runs in the Celery worker, not
        # here (web). Dispatch a probe and return the PREVIOUS cached worker result, so a
        # second call shows whether the WORKER's LLM call works. This is the true
        # web-vs-worker comparison.
        trace["web_process_note"] = ("llm_state/raw_call_api/answer_page_reference above "
                                     "ran in the WEB process; production chat streams in "
                                     "the WORKER (below).")
        try:
            from apps.ai.chatgpt_cos.tasks import debug_probe_worker_llm
            debug_probe_worker_llm.delay(request.user.id, message)
            trace["worker_llm_state"] = (
                cache.get("wlj:debug:worker_llm_probe")
                or "dispatched — call this endpoint again in ~5s to read the worker result")
        except Exception as e:
            trace["worker_llm_state"] = {"dispatch_error": repr(e)}
    return JsonResponse(trace)
