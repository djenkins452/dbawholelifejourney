# ==============================================================================
# TEMPORARY staff-only worker-client diagnostic (2026-07-06). Proves the EXACT runtime
# reason ai_service.is_available is False in the Celery worker despite OPENAI_API_KEY being
# configured: captures the construction exception + traceback, key LENGTH (never the value),
# openai/httpx versions, construction-affecting env vars (presence only), and the live
# singleton state — in BOTH the web process and the worker. NO secret is ever logged.
# REMOVE once the runtime cause is known (delete this module + its URL line + the worker
# task + its import; grep clean; verify startup) — Temporary Infrastructure Lifecycle law.
# ==============================================================================
import os
import sys
import traceback

from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_GET

WORKER_CACHE_KEY = "wlj:debug:worker_client_probe"

# Env vars that influence OpenAI()/httpx client CONSTRUCTION. Presence only — never values.
_WATCH_ENV = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy",
    "NO_PROXY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "OPENAI_ORG_ID", "OPENAI_ORGANIZATION",
    "OPENAI_PROJECT", "OPENAI_PROXY", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
)


def probe():
    """Deep, process-agnostic probe of OpenAI client construction. Safe to run in web OR
    worker. Never returns or logs the API key — only its length/shape."""
    from django.conf import settings

    info = {
        "process": (os.path.basename(sys.argv[0]) if sys.argv else "?"),
        "argv": " ".join(sys.argv[:4]),
        "pid": os.getpid(),
        "git_sha": (os.environ.get("RAILWAY_GIT_COMMIT_SHA")
                    or os.environ.get("SOURCE_VERSION")
                    or os.environ.get("GIT_COMMIT") or "?")[:12],
    }

    # 1) Is the key actually present/non-empty at runtime IN THIS PROCESS?
    key = getattr(settings, "OPENAI_API_KEY", None)
    info["key_present"] = bool(key)
    info["key_len"] = (len(key) if isinstance(key, str) else None)
    info["key_type"] = type(key).__name__
    info["key_shape"] = ((key[:3] + "…len=" + str(len(key)))
                         if isinstance(key, str) and key else None)   # shape only, no secret

    # Construction-affecting env (presence only)
    info["env_present"] = {k: True for k in _WATCH_ENV if k in os.environ}

    # 2) Library versions (same image ships to both — a mismatch would be a surprise)
    try:
        import openai
        info["openai_version"] = getattr(openai, "__version__", "?")
    except Exception as e:  # noqa: BLE001
        info["openai_version"] = f"ERR {e!r}"
    try:
        import httpx
        info["httpx_version"] = getattr(httpx, "__version__", "?")
    except Exception as e:  # noqa: BLE001
        info["httpx_version"] = f"ERR {e!r}"

    # 3) FRESH construction — the EXACT call the factory makes — capture the real exception
    try:
        from openai import OpenAI

        from apps.ai.services import LLM_TIMEOUT_COS_CHAT
        c = OpenAI(api_key=key, timeout=LLM_TIMEOUT_COS_CHAT, max_retries=0)
        info["construct"] = "ok"
        info["construct_client_type"] = type(c).__name__
    except Exception as e:  # noqa: BLE001
        info["construct"] = "RAISED"
        info["construct_error"] = repr(e)
        info["construct_traceback"] = traceback.format_exc()[-2200:]

    # 4/5/6) LIVE singleton state — what production actually uses
    try:
        import apps.ai.services as svc
        info["ai_service_is_available"] = bool(svc.ai_service.is_available)
        info["ai_service_client_type"] = (type(svc.ai_service.client).__name__
                                          if svc.ai_service.client else None)
        info["ai_service_id"] = id(svc.ai_service)
        info["shared_singleton_set"] = svc._shared_openai_client is not None
        gc = svc.get_openai_client()          # does the REAL factory return a client here now?
        info["get_openai_client_returns"] = ("client" if gc is not None else "None")
    except Exception as e:  # noqa: BLE001
        info["singleton_error"] = repr(e)
        info["singleton_traceback"] = traceback.format_exc()[-2200:]
    return info


@require_GET
def worker_client_diag(request):
    if not (request.user.is_authenticated and getattr(request.user, "is_staff", False)):
        return JsonResponse({"error": "staff_only"}, status=403)
    result = {"web": probe()}
    try:
        from apps.ai.chatgpt_cos.tasks import debug_probe_worker_client
        debug_probe_worker_client.delay()
        result["worker"] = (cache.get(WORKER_CACHE_KEY)
                            or "dispatched — reload this URL in ~5s to read the worker probe")
    except Exception as e:  # noqa: BLE001
        result["worker"] = {"dispatch_error": repr(e)}
    return JsonResponse(result, json_dumps_params={"indent": 2})
