# ==============================================================================
# TEMPORARY staff-only diagnostic (2026-07-06) — shows the EXACT system prompt that reached
# OpenAI (post token-governor) for the last cos_chat (tool-loop) and cos_page_reference
# (deixis) turns, so we can prove whether the focused object actually arrives at the LLM and
# whether the token governor trimmed the CURRENTLY VIEWING block. REMOVE once proven:
# delete this module + its URL line + the two _debug_capture_prompt calls + the helper in
# apps/ai/services.py; grep clean; verify startup. Never logs a secret.
# ==============================================================================
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def last_prompt_diag(request):
    if not (request.user.is_authenticated and getattr(request.user, "is_staff", False)):
        return JsonResponse({"error": "staff_only"}, status=403)
    uid = request.user.id
    out = {
        "user_id": uid,
        "cos_chat (tool-loop / non-deixis)": cache.get(f"wlj:debug:last_prompt:cos_chat:{uid}")
        or "no cos_chat turn captured yet — send a natural question e.g. 'Am I making progress?'",
        "cos_page_reference (deixis)": cache.get(f"wlj:debug:last_prompt:cos_page_reference:{uid}")
        or "no cos_page_reference turn captured yet — send 'Explain this.'",
    }
    return JsonResponse(out, json_dumps_params={"indent": 2})
