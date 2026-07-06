# ==============================================================================
# TEMPORARY staff-only diagnostic (2026-07-06) — proves the WHOLE Current-Context chain for
# the user's last turn: (1) what page_context arrived (focus_ref?), (2) whether the object
# resolved, (3) whether the CURRENT CONTEXT preamble actually reached the cos_chat prompt the
# reasoning lane sent. REMOVE once proven: delete this module + URL line + the two
# `wlj:dbg:cc:` capture blocks in service.py and services.py; grep clean; verify startup.
# ==============================================================================
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def cc_chain_diag(request):
    if not (request.user.is_authenticated and getattr(request.user, "is_staff", False)):
        return JsonResponse({"error": "staff_only"}, status=403)
    uid = request.user.id
    return JsonResponse({
        "user_id": uid,
        "1_generate (page_context + resolved focus)":
            cache.get(f"wlj:dbg:cc:generate:{uid}")
            or "no turn captured — ask a question on the Goal page first",
        "2_cos_chat_prompt (was the object in the prompt the lane sent?)":
            cache.get(f"wlj:dbg:cc:prompt:{uid}")
            or "no cos_chat call captured yet",
    }, json_dumps_params={"indent": 2})
