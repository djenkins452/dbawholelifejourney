# ==============================================================================
# TEMPORARY — Multi-Domain Evidence Representation A/B experiment (operator-only).
# Investigation for docs/WLJ_COS_MULTIDOMAIN_EVIDENCE.md. REMOVE after the run.
# Isolates ONE variable: the get_analysis('overall') tool-RESULT representation.
# Same model, same system prompt (CONSTITUTION), same question, same tool-call
# count and domains — only the result payload differs:
#   A = current production envelopes (verbatim get_domain_analysis output)
#   B = same deterministic FACTS, evidence-oriented (report scaffolding removed:
#       scope prose, per-call metadata, note, concepts/subjects duplication,
#       verbose change internals). No facts removed, no conclusions added.
# ==============================================================================
import json
import logging

from celery import shared_task
from django.core.cache import cache

logger = logging.getLogger(__name__)

MATERIAL_DOMAINS = ("health", "nutrition", "finance", "relationships", "goals")


def _clean_domain(env):
    """B: same facts as the envelope, report scaffolding removed. Never adds a verdict."""
    facts = []
    for grp in (env.get("concepts") or {}).values():
        if not isinstance(grp, dict):
            continue
        for m in (grp.get("members") or {}).values():
            if isinstance(m, dict) and m.get("value") is not None:
                s = f"{m.get('label')}: {m.get('value')}{(' ' + m['unit']) if m.get('unit') else ''}"
                if m.get("change") not in (None, ""):
                    s += f" (Δ {m['change']})"
                facts.append(s)
    st = env.get("state")
    if isinstance(st, dict):
        for k, v in st.items():
            if isinstance(v, (int, float, str)) and k not in ("enabled",) and not str(k).endswith("basis"):
                facts.append(f"{k}: {v}")
    subs = env.get("subjects")
    if isinstance(subs, dict):
        for name, s in subs.items():
            if not isinstance(s, dict) or not s.get("present"):
                continue
            ch = s.get("change") or {}
            if ch:
                facts.append(f"{name}: {ch.get('first')}→{ch.get('last')} "
                             f"(Δ {ch.get('delta')}, {ch.get('direction')}) over {s.get('count')} pts")
            elif s.get("average") is not None:
                facts.append(f"{name}: avg {s.get('average')} {s.get('unit', '')}")
    win = (env.get("window") or {}).get("label")
    return {"domain": env.get("domain"), "window": win,
            "holds_data": env.get("holds_data"), "facts": facts}


def _synthesize(question, payload_by_domain):
    """Run ONE real model continuation: system=CONSTITUTION, the question, a synthetic
    assistant get_analysis fan, and the tool results (A or B). Mirrors production shape."""
    from apps.ai.services import ai_service
    from apps.ai.model_interface.constitution import CONSTITUTION
    domains = list(payload_by_domain.keys())
    tool_calls = [{
        "id": f"call_{i}", "type": "function",
        "function": {"name": "get_analysis",
                     "arguments": json.dumps({"domain": d, "subject": "overall"})},
    } for i, d in enumerate(domains)]
    msgs = [
        {"role": "system", "content": CONSTITUTION},
        {"role": "user", "content": question},
        {"role": "assistant", "content": None, "tool_calls": tool_calls},
    ] + [
        {"role": "tool", "tool_call_id": f"call_{i}",
         "content": json.dumps(payload_by_domain[d], default=str)}
        for i, d in enumerate(domains)
    ]
    resp = ai_service.client.chat.completions.create(
        model=ai_service.model, messages=msgs, temperature=0.4)
    answer = resp.choices[0].message.content or ""
    usage = getattr(resp, "usage", None)
    return {
        "answer": answer,
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "evidence_chars": sum(len(json.dumps(payload_by_domain[d], default=str)) for d in domains),
    }


@shared_task(name="admin_console.run_analysis_ab", ignore_result=True)
def run_analysis_ab(email, question, rk):
    from django.contrib.auth import get_user_model
    from apps.ai.cos_services.domain_analysis import get_domain_analysis
    try:
        user = get_user_model().objects.get(email__iexact=email)
        A = {}
        for dom in MATERIAL_DOMAINS:
            try:
                env = get_domain_analysis(user, dom, "overall", period="this_month")
                if isinstance(env, dict) and env.get("holds_data"):
                    A[dom] = env
            except Exception:
                logger.warning("ab: get_domain_analysis failed dom=%s", dom, exc_info=True)
        B = {dom: _clean_domain(env) for dom, env in A.items()}
        # C: the SAME cleaned facts, POOLED into ONE cross-domain evidence block delivered as a
        # SINGLE tool result (not N domain-partitioned results). Tests whether the domain
        # PARTITIONING (N results) — not the per-result content — is what drives sectioning.
        pooled = {"window": next(iter(B.values()), {}).get("window") if B else None,
                  "facts": [f"[{dom}] {f}" for dom, cb in B.items() for f in cb["facts"]]}
        C = {"life_evidence": pooled}
        out = {
            "status": "ready", "question": question, "domains": list(A.keys()),
            "A": _synthesize(question, A),
            "B": _synthesize(question, B),
            "C": _synthesize(question, C),
        }
        cache.set(rk, out, 1800)
    except Exception as exc:
        cache.set(rk, {"status": "error", "error": repr(exc)}, 1800)


# --- TEMPORARY operator endpoint -------------------------------------------------
from django.http import JsonResponse  # noqa: E402
from django.views import View  # noqa: E402


class AnalysisABView(View):
    """GET ?email=&question=  -> {run_id};  GET ?run_id=  -> poll. API-key guarded."""

    def get(self, request):
        import uuid
        from django.conf import settings
        from apps.core.rate_limiting import secure_compare_api_key
        if not settings.CLAUDE_API_KEY or not secure_compare_api_key(
                request.headers.get("X-Claude-API-Key", ""), settings.CLAUDE_API_KEY):
            return JsonResponse({"error": "bad api key"}, status=401)
        run_id = request.GET.get("run_id")
        if run_id:
            return JsonResponse(cache.get(run_id) or {"status": "pending"},
                                json_dumps_params={"default": str})
        email = (request.GET.get("email") or "").strip()
        question = (request.GET.get("question")
                    or "How am I doing overall in my life right now?").strip()
        rk = "wlj:abx:" + uuid.uuid4().hex
        try:
            from apps.core.celery_utils import safe_enqueue
            safe_enqueue(run_analysis_ab, email, question, rk)
        except Exception as exc:
            return JsonResponse({"error": f"enqueue failed: {exc!r}"}, status=500)
        return JsonResponse({"run_id": rk, "poll": f"?run_id={rk}"})
